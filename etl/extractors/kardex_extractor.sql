-- Extracción de la tabla kardex (Hechos: Inventario / Movimientos)
SELECT 
    codemp,          -- Código de empresa
    numdoc AS num_documento, -- Número de documento referencial
    tipdoc AS tipo_movimiento, -- Tipo de documento
    codart,          -- Código del artículo
    codalm,          -- Almacén/Bodega
    fecdoc,          -- Fecha del documento (movimiento)
    cantot AS cantidad_movimiento, -- Cantidad del movimiento
    cosuni AS costo_unitario,      -- Costo unitario
    costot AS costo_total,         -- Costo total
    totven AS valor_venta,         -- Total venta asociada
    codcli,          -- Cliente asociado (si aplica)
    codven           -- Vendedor asociado (si aplica)
FROM 
    kardex
WHERE 
    codemp = '01';
