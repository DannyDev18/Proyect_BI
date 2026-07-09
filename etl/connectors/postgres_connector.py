# connectors/postgres_connector.py
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
import pandas as pd
import logging
from config.settings import ETLConfig

logger = logging.getLogger(__name__)

class PostgresConnector:
    """Administra la conexión y carga hacia el EDW en PostgreSQL."""

    def __init__(self, config: ETLConfig):
        self.config = config
        self._engine: Engine | None = None

    def _build_url(self) -> str:
        c = self.config
        return (f"postgresql+psycopg2://{c.PG_USER}:{c.PG_PASSWORD}"
                f"@{c.PG_HOST}:{c.PG_PORT}/{c.PG_DB}")

    def connect(self) -> Engine:
        if not self._engine:
            self._engine = create_engine(
                self._build_url(),
                pool_size=5, max_overflow=10,
                pool_pre_ping=True,
                connect_args={"options": f"-csearch_path={self.config.PG_SCHEMA}"}
            )
            logger.info("Conexión a PostgreSQL establecida.")
        return self._engine

    def disconnect(self) -> None:
        if self._engine:
            self._engine.dispose()
            self._engine = None
            logger.info("Conexión a PostgreSQL cerrada.")

    def load_dataframe(self, df: pd.DataFrame, tabla: str, modo: str = 'append',
                       claves_negocio: list = None, conn=None) -> int:
        """Carga un DataFrame de pandas a PostgreSQL utilizando el modo especificado.

        Auditoría 09 (H4): acepta una conexión/transacción externa ya abierta (`conn`) para
        que el llamador pueda envolver varias cargas (p.ej. un DELETE de idempotencia + N
        chunks) en una única transacción atómica. Si no se pasa, se comporta como antes
        (abre y comitea su propia transacción).
        """
        if df.empty:
            logger.warning(f"DataFrame vacío para tabla {tabla}. Se omite la carga.")
            return 0

        engine = self.connect()
        schema = self.config.PG_SCHEMA

        # Filtrar columnas para que coincidan exactamente con la tabla destino
        from sqlalchemy import inspect
        try:
            inspector = inspect(engine)
            db_cols = [col['name'] for col in inspector.get_columns(tabla, schema=schema)]
            if db_cols:
                valid_cols = [c for c in df.columns if c in db_cols]
                columnas_descartadas = [c for c in df.columns if c not in db_cols]
                if columnas_descartadas:
                    # Un drift de esquema real (columna nueva en el origen que no llegó a la
                    # tabla destino) perdería datos en silencio si no se reporta.
                    logger.warning(
                        f"{tabla}: {len(columnas_descartadas)} columna(s) del DataFrame no "
                        f"existen en la tabla destino y se descartan: {columnas_descartadas}"
                    )
                df = df[valid_cols].copy()
                if claves_negocio:
                    claves_negocio = [c for c in claves_negocio if c in db_cols]
        except Exception as ex_col:
            logger.warning(f"No se pudieron verificar las columnas en la DB para {tabla}: {ex_col}")

        if conn is not None:
            return self._ejecutar_carga(conn, df, tabla, modo, claves_negocio, schema)

        with engine.begin() as conn_propia:
            return self._ejecutar_carga(conn_propia, df, tabla, modo, claves_negocio, schema)

    def _ejecutar_carga(self, conn, df: pd.DataFrame, tabla: str, modo: str,
                        claves_negocio: list, schema: str) -> int:
        registros = 0
        batch_size = self.config.BATCH_SIZE

        if modo == 'truncate':
            conn.execute(text(f"TRUNCATE TABLE {schema}.{tabla} RESTART IDENTITY CASCADE"))
            df.to_sql(tabla, conn, schema=schema, if_exists='append',
                      index=False, method='multi', chunksize=batch_size)
            registros = len(df)
            logger.info(f"TRUNCATE+RELOAD {tabla}: {registros} filas.")
        elif modo == 'append':
            df.to_sql(tabla, conn, schema=schema, if_exists='append',
                      index=False, method='multi', chunksize=batch_size)
            registros = len(df)
            logger.info(f"APPEND {tabla}: {registros} filas nuevas.")
        elif modo == 'upsert':
            if not claves_negocio:
                raise ValueError("Se requieren llaves de negocio para modo 'upsert'.")
            df = df.drop_duplicates(subset=claves_negocio, keep='last')
            staging = f"_stg_{tabla}"
            # Escribir dataframe a tabla de staging temporal
            df.to_sql(staging, conn, schema=schema, if_exists='replace',
                      index=False, method='multi', chunksize=batch_size)

            # Construir INSERT ON CONFLICT DO UPDATE
            cols = [c for c in df.columns if c not in claves_negocio]
            set_expr = ", ".join([f"{c}=EXCLUDED.{c}" for c in cols])
            conflict = ", ".join(claves_negocio)

            sql_ups = text(f"""
                INSERT INTO {schema}.{tabla} ({','.join(df.columns)})
                SELECT {','.join(df.columns)} FROM {schema}.{staging}
                ON CONFLICT ({conflict}) DO UPDATE SET {set_expr}
            """)

            result = conn.execute(sql_ups)
            registros = result.rowcount
            conn.execute(text(f"DROP TABLE IF EXISTS {schema}.{staging}"))
            logger.info(f"UPSERT {tabla}: {registros} filas procesadas.")

        return registros