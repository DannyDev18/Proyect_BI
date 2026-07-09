-- Agregado de referencia contra SAP (SOLO SELECT) para reconciliar fact_movimientos_inventario.
-- Mismo recorte que kardex_extractor.sql. cantot es SIEMPRE positivo (regla de negocio §3/§4,
-- docs/auditoria/02_reglas_negocio_validadas.md): no se reinterpreta el signo aquí.
SELECT
    COUNT(*)                    AS filas,
    SUM(cantot)                  AS total_cantidad,
    SUM(costot)                  AS total_costo,
    MIN(fecdoc)                  AS fecha_min,
    MAX(fecdoc)                  AS fecha_max
FROM kardex
WHERE
    codemp = '{CODEMP}'
    AND fecdoc >= '{FECHA_DESDE}'
