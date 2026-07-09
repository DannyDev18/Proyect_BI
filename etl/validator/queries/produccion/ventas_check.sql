-- Agregado de referencia contra SAP (SOLO SELECT) para reconciliar fact_ventas_detalle.
-- Mismo recorte que facturas_detalle_extractor.sql: codemp, estado de documento válido y
-- piso de fecha, para comparar exactamente el mismo universo de filas que cargó el ETL.
SELECT
    COUNT(*)                    AS filas,
    SUM(r.cantid)                AS total_cantidad,
    SUM(r.totren)                AS total_valor,
    MIN(e.fecfac)                AS fecha_min,
    MAX(e.fecfac)                AS fecha_max
FROM renglonesfacturas r
JOIN encabezadofacturas e
    ON r.codemp = e.codemp AND r.numfac = e.numfac
WHERE
    r.codemp = '{CODEMP}'
    AND e.estado = '{ESTADO}'
    AND e.fecfac >= '{FECHA_DESDE}'
