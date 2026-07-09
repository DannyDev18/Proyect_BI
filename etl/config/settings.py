# config/settings.py
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class ETLConfig:
    # ── SAP SQL Anywhere (Origen) ───────────────────────────────────────────
    DB_DRIVER:       str = os.getenv("DB_DRIVER",       "SQL Anywhere 12")
    DB_SERVER:       str = os.getenv("DB_SERVER",       "")
    DB_DATABASE:     str = os.getenv("DB_DATABASE",     "")
    # Sin default: "dba" es la cuenta privilegiada por convención en SQL Anywhere. Si falta en
    # .env, el pipeline debe fallar rápido al conectar en vez de intentarlo silenciosamente
    # como esa cuenta (mismo criterio que DB_PASSWORD/DB_SERVER).
    DB_USER:         str = os.getenv("DB_USER",         "")
    DB_PASSWORD:     str = os.getenv("DB_PASSWORD",     "")
    DB_HOST:         str = os.getenv("DB_HOST",         "")
    DB_PORT:         str = os.getenv("DB_PORT",         "")

    # ── PostgreSQL EDW ──────────────────────────────────────────────────────
    PG_HOST:         str = os.getenv("PG_HOST",     "localhost")
    PG_PORT:         int = int(os.getenv("PG_PORT", "5432"))
    PG_DB:           str = os.getenv("PG_DB",       "edw")
    PG_USER:         str = os.getenv("PG_USER",     "etl_user")
    PG_PASSWORD:     str = os.getenv("PG_PASSWORD", "")
    PG_SCHEMA:       str = "edw"

    # ── Control del pipeline ────────────────────────────────────────────────
    BATCH_SIZE:      int  = int(os.getenv("BATCH_SIZE", "10000"))
    # Timeout (segundos) por lote de fetch contra SAP. El driver FreeTDS/ODBC puede quedar
    # colgado en un recv() bloqueante a mitad de un cursor server-side sin devolver error
    # (observado en fact_ventas_detalle: la conexión queda ESTABLISHED pero sin datos en
    # ambas colas TCP, indefinidamente). pyodbc no expone un timeout de fetch fiable para
    # este driver, así que se aplica con signal.alarm() alrededor de cada lote.
    SAP_FETCH_TIMEOUT_SECONDS: int = int(os.getenv("SAP_FETCH_TIMEOUT_SECONDS", "120"))
    FECHA_DESDE:     str  = os.getenv("FECHA_DESDE",    "2020-01-01")
    MODO_INCREMENTAL:bool = os.getenv("MODO_INCREMENTAL","true").lower()=="true"
    CODEMP:          str  = os.getenv("CODEMP",         "01")
    # Estado de documento válido en el ERP (P=Procesada). Validado contra Producción
    # (docs/auditoria/02_reglas_negocio_validadas.md §1). Parametrizable por si cambia.
    ESTADO_VALIDO:   str  = os.getenv("ESTADO_VALIDO",  "P")
    # Piso de fecha para la carga inicial / full (no incremental). Preserva el histórico.
    FECHA_HISTORICA: str  = os.getenv("FECHA_HISTORICA","1900-01-01")
    # Rango de Dim_Tiempo (generada algorítmicamente, no viene del ERP). Cualquier fecha fuera
    # de este rango no resuelve fecha_sk en resolver_llaves_hecho(). Parametrizable en vez de
    # quedar hardcodeado en transformers/dim_tiempo.py.
    DIM_TIEMPO_DESDE: str  = os.getenv("DIM_TIEMPO_DESDE", "2010-01-01")
    DIM_TIEMPO_HASTA: str  = os.getenv("DIM_TIEMPO_HASTA", "2030-12-31")
    # Salt para el hashing PII de clientes. NO debe usar el valor por defecto en producción:
    # run_etl() aborta si detecta el salt inseguro (ver orchestrator.validar_configuracion).
    PII_SALT:        str  = os.getenv("PII_SALT",       "")

    # Marcador del salt inseguro heredado (para detección y bloqueo).
    _PII_SALT_INSEGURO: str = "s3cr3t_s4lt_v3ry_s3cur3"