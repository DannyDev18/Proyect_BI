-- Agregado equivalente contra el EDW para reconciliar fact_movimientos_inventario.
SELECT
    COUNT(*)                     AS filas,
    SUM(f.cantidad_movimiento)    AS total_cantidad,
    SUM(f.costo_total)            AS total_costo,
    MIN(d.fecha_completa)         AS fecha_min,
    MAX(d.fecha_completa)         AS fecha_max
FROM edw.fact_movimientos_inventario f
JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
WHERE d.fecha_completa >= '{FECHA_DESDE}'
