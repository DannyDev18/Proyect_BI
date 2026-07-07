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
    DB_USER:         str = os.getenv("DB_USER",         "dba")
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
    FECHA_DESDE:     str  = os.getenv("FECHA_DESDE",    "2020-01-01")
    MODO_INCREMENTAL:bool = os.getenv("MODO_INCREMENTAL","true").lower()=="true"
    CODEMP:          str  = os.getenv("CODEMP",         "01")
    PII_SALT:        str  = os.getenv("PII_SALT",       "s3cr3t_s4lt_v3ry_s3cur3")