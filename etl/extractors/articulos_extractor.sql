-- Extracción de la tabla articulos (Dimensión Producto/Artículo)
SELECT 
    codemp,
    codart,
    nomart AS nombre_articulo,
    codcla AS clase,
    NULL AS nombre_clase,
    NULL AS subclase,
    NULL AS nombre_subclase,
    coduni AS unidad,
    NULL AS nombre_unidad,
    prec01 AS precio_oficial,
    ultcos AS costo_promedio,   -- OJO: 'ultcos' es el ÚLTIMO costo, no un promedio. El nombre de
                                -- la columna del DW (dim_producto.costo_promedio) se conserva para no
                                -- alterar el esquema. Ver docs/auditoria/02_reglas_negocio_validadas.md §9.
    estado,
    fecult
FROM
    articulos
WHERE
    codemp = '{CODEMP}';
