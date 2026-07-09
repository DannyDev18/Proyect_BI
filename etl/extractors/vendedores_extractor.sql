-- Extracción de la tabla vendedorescob (Dimensión Vendedores)
SELECT 
    codemp,          -- Código de empresa
    codven,          -- Código del vendedor / cobrador
    nomven AS nombre_vendedor, -- Nombre del vendedor
    fecult,          -- Fecha de última actualización
    estado           -- Estado del vendedor
FROM 
    vendedorescob
WHERE 
    codemp = '{CODEMP}';
