-- Extracción de la tabla proveedores (Dimensión Proveedor)
SELECT 
    codemp,          -- Código de empresa
    codpro,          -- Código del proveedor
    nompro AS nombre_proveedor, -- Nombre del proveedor
    rucced AS ruc,   -- RUC del proveedor
    codciu AS ciudad,-- Código/nombre de ciudad
    30     AS dias_credito, -- Valor por defecto ya que no existe columna dias
    estatus AS estado -- Estado
FROM 
    proveedores
WHERE 
    codemp = '01';
