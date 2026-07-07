-- Extracción de cuentasporpagar (Hechos: Pagos CXP)
SELECT 
    codemp,          -- Código de empresa
    numcpp AS num_transaccion, -- Número de CPP
    codpro,          -- Código proveedor
    fecemi,          -- Fecha emisión
    fecven,          -- Fecha de vencimiento
    valcob AS valor_pagado, -- Valor del documento
    CASE WHEN cerrado = 'S' THEN 0.0 ELSE valcob END AS saldo_pendiente, -- Saldo a pagar
    dias AS dias_vencimiento, -- Días plazo
    'C' AS codforpag -- Forma de pago (siempre crédito por ser CXP)
FROM 
    cuentasporpagar
WHERE 
    codemp = '01';
