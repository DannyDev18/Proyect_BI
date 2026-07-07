# connectors/sqlany_connector.py
import pyodbc
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
import pandas as pd
import logging
from contextlib import contextmanager
from config.settings import ETLConfig

logger = logging.getLogger(__name__)

class SQLAnywhereConnector:
    """Maneja la conexión ODBC a SAP SQL Anywhere adaptado a SQLAlchemy."""

    def __init__(self, config: ETLConfig):
        self.config = config
        self._conn = None
        self._engine = None
        self._conn_str = self._build_connection_string()

    def _build_connection_string(self) -> str:
        c = self.config
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

    def query_to_dataframe(self, sql: str,
                           params: tuple = (),
                           chunksize: int | None = None) -> pd.DataFrame:
        """Ejecuta una consulta SQL nativa usando pyodbc puro y devuelve un DataFrame de pandas."""
        # Pandas read_sql puede fallar con el engine falso, caemos directo a pyodbc para lectura cruda si es necesario
        # o intentamos pd.read_sql
        if not self._conn:
            self.connect()

        try:
            # Para SQL Anywhere suele ser mucho más estable usar la conexión pyodbc raw con pandas
            if chunksize:
                frames = []
                for chunk in pd.read_sql(sql, self._conn, params=params, chunksize=chunksize):
                    frames.append(chunk)
                return pd.concat(frames, ignore_index=True)
            return pd.read_sql(sql, self._conn, params=params)
        except Exception as e:
            logger.error(f"Error ejecutando query nativa: {e}\nSQL: {sql[:300]}")
            raise

    def yield_query_chunks(self, sql: str,
                           params: tuple = (),
                           chunksize: int = 5000):
        """Generador que obtiene resultados en fragmentos para evitar sobrecarga de memoria."""
        if not self._conn:
            self.connect()
        try:
            for chunk in pd.read_sql(sql, self._conn, params=params, chunksize=chunksize):
                yield chunk
        except Exception as e:
            logger.error(f"Error en yield_query_chunks: {e}\nSQL: {sql[:300]}")
            raise