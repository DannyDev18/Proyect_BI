-- Duplicados exactos en fact_movimientos_inventario: mismo documento+artículo+tipo+cantidad+fecha
-- repetido más de una vez indica reproceso de carga (la idempotencia del ETL borra por rango
-- de fecha antes de recargar, así que un duplicado real aquí es un hallazgo, no ruido esperado).
SELECT COUNT(*) AS grupos_duplicados
FROM (
    SELECT num_documento, producto_sk, tipo_movimiento, cantidad_movimiento, fecha_sk
    FROM edw.fact_movimientos_inventario f
    JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
    WHERE d.fecha_completa >= '{FECHA_DESDE}'
    GROUP BY num_documento, producto_sk, tipo_movimiento, cantidad_movimiento, fecha_sk
    HAVING COUNT(*) > 1
) dup
