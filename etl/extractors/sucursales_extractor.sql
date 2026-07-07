-- Extracción de la tabla establecimientos (Dimensión Sucursal)
SELECT 
    codemp,          -- Código de empresa
    establ,          -- Código del establecimiento (sucursal)
    establ AS codigo_sucursal, -- PK de sucursal
    nomest AS nombre_sucursal, -- Nombre de la sucursal
    direc  AS direccion, -- Dirección
    NULL AS telefono -- Teléfono
FROM 
    establecimientos
WHERE 
    codemp = '01';
