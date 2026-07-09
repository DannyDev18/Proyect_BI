-- Duplicados exactos en fact_ventas_detalle: misma factura+artículo+cantidad+total repetidos
-- indica reproceso/duplicación de carga, no una línea de negocio legítima repetida.
SELECT COUNT(*) AS grupos_duplicados
FROM (
    SELECT num_factura, producto_sk, cantidad, total_linea
    FROM edw.fact_ventas_detalle f
    JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
    WHERE d.fecha_completa >= '{FECHA_DESDE}'
    GROUP BY num_factura, producto_sk, cantidad, total_linea
    HAVING COUNT(*) > 1
) dup
