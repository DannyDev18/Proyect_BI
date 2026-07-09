# connectors/sqlany_connector.py
import pyodbc
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
import pandas as pd
import logging
import multiprocessing
import os
import tempfile
from contextlib import contextmanager
from config.settings import ETLConfig

logger = logging.getLogger(__name__)


class SAPFetchTimeoutError(TimeoutError):
    """El subproceso de fetch contra SAP no terminó dentro del timeout configurado y fue
    forzado a terminar (SIGKILL). Observado en producción: el driver FreeTDS/ODBC puede quedar
    bloqueado en un recv() a mitad de un cursor server-side sin devolver error ni cerrar el
    socket (queda ESTABLISHED, sin bytes en cola en ningún sentido, indefinidamente). Un
    timeout de aplicación (p.ej. signal.alarm) NO sirve aquí: mientras el driver retiene el
    GIL liberado dentro de la llamada C bloqueante, Python nunca vuelve a ejecutar bytecode
    para procesar la señal, así que el handler nunca se dispara. Solo una terminación a nivel
    de proceso del SO garantiza cortar el bloqueo, de ahí que el fetch corra en un subproceso.
    Esta excepción hace que el aislamiento de errores por tabla de orchestrator.py la capture,
    marque FAIL en edw.etl_control y continúe con la siguiente tabla."""
    pass


def _fetch_worker(conn_str: str, sql: str, result_path: str, error_path: str) -> None:
    """Ejecuta la extracción completa en un proceso aparte, con su propia conexión ODBC
    fresca (nunca se comparte una conexión pyodbc entre procesos). El resultado se escribe a
    disco (pickle) en vez de pasarlo por una Queue de multiprocessing, para no tener límites
    de tamaño de mensaje con DataFrames grandes (hasta ~950k filas en este proyecto)."""
    try:
        conn = pyodbc.connect(conn_str, autocommit=True, timeout=60)
        try:
            df = pd.read_sql(sql, conn)
        finally:
            conn.close()
        df.to_pickle(result_path)
    except Exception as e:
        with open(error_path, "w", encoding="utf-8") as f:
            f.write(str(e))


class SQLAnywhereConnector:
    """Maneja la conexión ODBC a SAP SQL Anywhere adaptado a SQLAlchemy."""

    def __init__(self, config: ETLConfig):
        self.config = config
        self._conn = None
        self._engine = None
        self._conn_str = self._build_connection_string()

    def _build_connection_string(self) -> str:
        c = self.config
        # Dos rutas de conexión según el driver configurado en DB_DRIVER:
        #   - FreeTDS (contenedor Linux): SQL Anywhere acepta el protocolo TDS en su
        #     listener tcpip, así el driver es apt-instalable y la imagen no depende
        #     del cliente propietario de SAP instalado en el host. TDS_Version=5.0 es
        #     el dialecto Sybase que entiende SQL Anywhere.
        #   - Driver nativo "SQL Anywhere NN" (host Windows): cadena ENG/DBN/Links
        #     original. Se conserva para desarrollo local fuera de Docker.
        # Ver docs/auditoria/06_auditoria_driver_sap_docker.md.
        if "freetds" in c.DB_DRIVER.lower():
            return (
                f"Driver={{{c.DB_DRIVER}}};"
                f"Server={c.DB_HOST};"
                f"Port={c.DB_PORT};"
                f"Database={c.DB_DATABASE};"
                f"UID={c.DB_USER};"
                f"PWD={c.DB_PASSWORD};"
                f"TDS_Version=5.0;"
            )

        conn_str = (
            f"Driver={{{c.DB_DRIVER}}};"
            f"ENG={c.DB_SERVER};"
            f"DBN={c.DB_DATABASE};"
            f"UID={c.DB_USER};"
            f"PWD={c.DB_PASSWORD};"
        )
        if c.DB_HOST and c.DB_PORT:
            conn_str += f"Links=tcpip(Host={c.DB_HOST};Port={c.DB_PORT});"

        return conn_str

    def connect(self) -> Engine:
        """
        Retorna un engine de SQLAlchemy que funciona con SQL Anywhere.
        Crea el engine a partir de una conexión pyodbc real para evitar diagnósticos.
        """
        if not self._engine:
            logger.info("Estableciendo conexión ODBC directa a SAP SQL Anywhere...")
            try:
                self._conn = pyodbc.connect(self._conn_str, autocommit=True, timeout=60)
                
                # Creamos el engine usando la conexión existente como 'creator'
                # Esto evita que SQLAlchemy ejecute consultas de diagnóstico incompatibles
                self._engine = create_engine(
                    "mssql+pyodbc://", 
                    creator=lambda: self._conn
                )
                logger.info("Conectado exitosamente a SAP SQL Anywhere mediante SQLAlchemy + PyODBC.")
            except Exception as e:
                logger.error(f"[Error] al crear engine SQLAlchemy a SQL Anywhere: {e}")
                raise
        return self._engine

    def disconnect(self) -> None:
        if self._engine:
            self._engine.dispose()
            self._engine = None
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
        logger.info("Conexión a SAP SQL Anywhere cerrada.")

    @contextmanager
    def connection(self):
        engine = self.connect()
        try:
            yield engine
        finally:
            self.disconnect()

    def _fetch_all_con_timeout(self, sql: str) -> pd.DataFrame:
        """Ejecuta la extracción completa en un subproceso con una conexión ODBC propia, con
        timeout duro (config.SAP_FETCH_TIMEOUT_SECONDS). Si el subproceso no termina a tiempo
        se le manda SIGKILL — la única forma confiable de cortar un driver ODBC bloqueado en
        una llamada C (ver SAPFetchTimeoutError). Params no se soportan aquí: los extractores
        de este proyecto no usan bind params (los tokens {CODEMP}/{ESTADO}/{FECHA_DESDE} se
        renderizan como texto antes de llegar aquí — ver orchestrator.render_sql)."""
        timeout_s = self.config.SAP_FETCH_TIMEOUT_SECONDS
        ctx = multiprocessing.get_context("fork")
        with tempfile.TemporaryDirectory() as tmpdir:
            result_path = os.path.join(tmpdir, "result.pkl")
            error_path = os.path.join(tmpdir, "error.txt")
            proc = ctx.Process(
                target=_fetch_worker,
                args=(self._conn_str, sql, result_path, error_path),
            )
            proc.start()
            proc.join(timeout_s)

            if proc.is_alive():
                logger.error(
                    f"Sin respuesta de SAP por más de {timeout_s}s — el driver ODBC/FreeTDS "
                    f"quedó bloqueado. Terminando el subproceso de fetch (SIGKILL)."
                )
                proc.kill()
                proc.join()
                raise SAPFetchTimeoutError(
                    f"Fetch de SAP excedió {timeout_s}s sin responder. SQL: {sql[:200]}"
                )

            if os.path.exists(error_path):
                with open(error_path, "r", encoding="utf-8") as f:
                    error_msg = f.read()
                raise RuntimeError(f"Error en subproceso de fetch SAP: {error_msg}")

            if not os.path.exists(result_path):
                raise RuntimeError(
                    f"El subproceso de fetch SAP terminó (exitcode={proc.exitcode}) sin "
                    f"generar resultado ni error — posible crash silencioso."
                )

            return pd.read_pickle(result_path)

    def query_to_dataframe(self, sql: str,
                           params: tuple = (),
                           chunksize: int | None = None) -> pd.DataFrame:
        """Ejecuta una consulta SQL nativa contra SAP y devuelve un DataFrame de pandas.
        `chunksize` se ignora deliberadamente: el fetch siempre trae el resultado completo
        (ver _fetch_all_con_timeout) — dividir en lotes ya no ocurre contra SAP, solo al cargar
        al EDW (BATCH_SIZE en postgres_connector)."""
        try:
            return self._fetch_all_con_timeout(sql)
        except Exception as e:
            logger.error(f"Error ejecutando query nativa: {e}\nSQL: {sql[:300]}")
            raise

    def yield_query_chunks(self, sql: str,
                           params: tuple = (),
                           chunksize: int = 5000):
        """Generador que entrega el resultado en fragmentos de `chunksize` filas.

        La extracción contra SAP ya no se hace con un cursor server-side re-fetcheado en
        lotes (`pd.read_sql(..., chunksize=N)`): eso fue la causa raíz de un cuelgue
        reproducible en producción (fact_ventas_detalle quedó bloqueado esperando el segundo
        lote, con la conexión TCP hacia SAP en ESTADO ESTABLISHED pero sin datos en ninguna
        cola, indefinidamente — ver docs/auditoria). En su lugar, se trae la tabla completa en
        una sola llamada (misma estrategia que un `tsql` directo, que sí funcionó: 520,753
        filas en 12.6s) dentro de un subproceso con timeout duro, y el fraccionamiento en
        `chunksize` ocurre en memoria, en Python, sin más round-trips a SAP."""
        df_completo = self._fetch_all_con_timeout(sql)
        total = len(df_completo)
        if total == 0:
            return
        for inicio in range(0, total, chunksize):
            yield df_completo.iloc[inicio:inicio + chunksize].reset_index(drop=True)