-- == Tabla de control ETL ========================================
CREATE TABLE IF NOT EXISTS edw.etl_control (
    id              SERIAL PRIMARY KEY,
    tabla_destino   VARCHAR(60) NOT NULL,
    ultimo_etl_ok   TIMESTAMP,
    registros_carg  BIGINT DEFAULT 0,
    estado          VARCHAR(15),
    duracion_seg    INTEGER,
    mensaje_error   TEXT,
    fecha_ejecucion TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE edw.etl_control IS 'Tabla de auditoría y control del pipeline ETL para idempotencia.';
