-- Extracción de la tabla articulos (Dimensión Producto/Artículo)
-- Auditoría 34 (H-14): 'subcodcla' existe en SAP y está 100% poblado (50 valores
-- distintos, codemp='01') -- se traía como NULL sin motivo, bloqueando la resolución
-- por (clase, subclase) que ya soporta commission_engine._resolver_regla.
SELECT
    codemp,
    codart,
    nomart AS nombre_articulo,
    codcla AS clase,
    NULL AS nombre_clase,
    subcodcla AS subclase,
    NULL AS nombre_subclase,
    coduni AS unidad,
    NULL AS nombre_unidad,
    prec01 AS precio_oficial,
    ultcos AS ultimo_costo,
    estado,
    fecult
FROM
    articulos
WHERE
    codemp = '{CODEMP}';
