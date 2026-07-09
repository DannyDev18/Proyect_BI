-- Llaves huérfanas (resueltas al centinela -1, regla de negocio §12) en fact_movimientos_inventario.
SELECT
    COUNT(*) AS filas_total,
    SUM(CASE WHEN producto_sk = -1 THEN 1 ELSE 0 END) AS producto_huerfano,
    SUM(CASE WHEN almacen_sk = -1 THEN 1 ELSE 0 END)  AS almacen_huerfano,
    SUM(CASE WHEN sucursal_sk = -1 THEN 1 ELSE 0 END) AS sucursal_huerfana
FROM edw.fact_movimientos_inventario f
JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
WHERE d.fecha_completa >= '{FECHA_DESDE}'
