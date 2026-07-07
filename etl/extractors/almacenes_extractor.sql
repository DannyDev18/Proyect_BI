-- Extracción de la tabla almacenes (Dimensión Almacén/Bodega)
SELECT 
    codemp,          -- Código de empresa
    codalm,          -- Código de almacén
    nomalm AS nombre_almacen, -- Nombre del almacén
    '001' AS establ           -- Código del establecimiento al que pertenece
FROM 
    almacenes
WHERE 
    codemp = '01';
