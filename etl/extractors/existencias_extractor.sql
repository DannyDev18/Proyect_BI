-- Snapshot de existencias / stock por bodega (Hechos: Fact_Inventario_Snapshot)
-- Fuente validada contra Producción: vista `vi_mv_existencias` (stock por almacén).
-- El costo NO está en la vista, se toma de `articulos.ultcos` (último costo).
-- Ver docs/auditoria/02_reglas_negocio_validadas.md §7.
-- Nota: es un snapshot con fecha = CURRENT DATE; el orquestador reemplaza sólo la foto de hoy.
SELECT
    e.codemp,
    e.codart,
    e.codalm,
    CURRENT DATE AS fecha,                        -- fecha del snapshot (resolver reconoce 'fecha')
    e.existe AS stock_actual,                     -- existencia por bodega
    COALESCE(a.ultcos, 0.0) AS costo_promedio,    -- último costo (nombre de columna del DW conservado)
    (e.existe * COALESCE(a.ultcos, 0.0)) AS valor_inventario,
    0.0 AS stock_minimo,                          -- [PENDIENTE] no hay maestro de mínimos en el origen
    0.0 AS stock_maximo,                          -- [PENDIENTE] no hay maestro de máximos en el origen
    0.0 AS punto_reorden                          -- [PENDIENTE] a definir por reglas de reposición
FROM
    vi_mv_existencias e
LEFT JOIN articulos a ON e.codemp = a.codemp AND e.codart = a.codart
WHERE
    e.codemp = '{CODEMP}';
