-- Transferencias entre bodegas (derivadas del Kardex, tiporg='TRA')
-- Regla validada contra Producción (docs/auditoria/02_reglas_negocio_validadas.md §5):
--   cada ítem transferido genera 2 filas con igual cantot; tipdoc='SA' es el origen y
--   tipdoc='EN' el destino. Se reconstruye la transferencia pareando por (numdoc, numren, codart).
-- [PENDIENTE ERP] El origen NO expone 'cantidad solicitada' ni 'estado' de la transferencia.
-- [PENDIENTE DDL] Aún no existe Fact_Transferencias en el DW. Este extractor queda validado y
--   listo para conectarse a PIPELINE_CONFIG cuando se cree dicha tabla (fuera del alcance sin-DDL).
SELECT
    s.codemp,
    s.numdoc  AS num_documento,
    s.numren  AS num_renglon,
    s.codart,
    s.codalm  AS codalm_origen,     -- fila tipdoc='SA' -> bodega origen
    d.codalm  AS codalm_destino,    -- fila tipdoc='EN' -> bodega destino
    s.fecdoc  AS fecha,
    s.cantot  AS cantidad_enviada,  -- cantidad efectivamente movida
    s.cosuni  AS costo_unitario,
    s.establ
FROM
    kardex s
JOIN kardex d
    ON  d.codemp = s.codemp
    AND d.numdoc = s.numdoc
    AND d.numren = s.numren
    AND d.codart = s.codart
    AND d.tiporg = 'TRA'
    AND d.tipdoc = 'EN'
WHERE
    s.codemp = '{CODEMP}'
    AND s.tiporg = 'TRA'
    AND s.tipdoc = 'SA'
    AND s.fecdoc >= '{FECHA_DESDE}';
