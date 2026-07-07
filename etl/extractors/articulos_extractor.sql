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
    precio AS precio_oficial,
    ultcos AS costo_promedio,
    estado,
    fecult
FROM 
    articulos
WHERE 
    codemp = '01';
