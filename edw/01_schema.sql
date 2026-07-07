-- ============================================================
-- ARQUITECTURA DATA WAREHOUSE — MODELO MULTIESTRELLA
-- Motor: PostgreSQL 16 | Schema: edw
-- ============================================================

CREATE SCHEMA IF NOT EXISTS edw;
COMMENT ON SCHEMA edw IS
    'Enterprise Data Warehouse — Modelo Multiestrella (Constelación de Hechos)
     Fuente: SAP SQL Anywhere → ETL Python → PostgreSQL';

-- Usuario de solo lectura para el backend
DO
$do$
BEGIN
   IF NOT EXISTS (
      SELECT FROM pg_catalog.pg_roles WHERE rolname = 'bi_readonly'
   ) THEN
      CREATE ROLE bi_readonly LOGIN PASSWORD 'CHANGE_ME_READONLY';
   END IF;
END
$do$;

GRANT CONNECT ON DATABASE edw TO bi_readonly;
GRANT USAGE ON SCHEMA edw TO bi_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA edw
    GRANT SELECT ON TABLES TO bi_readonly;
