-- Llaves huérfanas (resueltas al centinela -1, regla de negocio §12) en fact_ventas_detalle.
SELECT
    COUNT(*) AS filas_total,
    SUM(CASE WHEN producto_sk = -1 THEN 1 ELSE 0 END)  AS producto_huerfano,
    SUM(CASE WHEN cliente_sk = -1 THEN 1 ELSE 0 END)   AS cliente_huerfano,
    SUM(CASE WHEN vendedor_sk = -1 THEN 1 ELSE 0 END)  AS vendedor_huerfano,
    SUM(CASE WHEN sucursal_sk = -1 THEN 1 ELSE 0 END)  AS sucursal_huerfana,
    SUM(CASE WHEN formapago_sk = -1 THEN 1 ELSE 0 END) AS formapago_huerfana
FROM edw.fact_ventas_detalle f
JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
WHERE d.fecha_completa >= '{FECHA_DESDE}'
