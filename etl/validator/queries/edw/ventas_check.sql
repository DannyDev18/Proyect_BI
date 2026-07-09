-- Agregado equivalente contra el EDW para reconciliar fact_ventas_detalle.
-- Se filtra por dim_fecha.fecha_completa (no por fecha_sk) para usar el mismo criterio de
-- rango que la consulta de Producción.
SELECT
    COUNT(*)                     AS filas,
    SUM(f.cantidad)               AS total_cantidad,
    SUM(f.total_linea)            AS total_valor,
    MIN(d.fecha_completa)         AS fecha_min,
    MAX(d.fecha_completa)         AS fecha_max
FROM edw.fact_ventas_detalle f
JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
WHERE d.fecha_completa >= '{FECHA_DESDE}'
