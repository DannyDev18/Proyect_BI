-- Extracción de cuentasporcobrar (Hechos: Cobros CXC)
SELECT 
    codemp,          -- Código de empresa
    numcpc AS num_transaccion, -- Número de transacción CDC
    codcli,          -- Código cliente
    codven,          -- Código vendedor asociado
    fecemi,          -- Fecha de emisión
    fecven,          -- Fecha vencimiento
    valcob AS valor_cobrado, -- Valor del documento
    saldodoc AS saldo_documento, -- Saldo pendiente
    diasvence AS dias_vencimiento, -- Días de vencimiento
    codforpag        -- Forma de pago asociada
FROM 
    cuentasporcobrar
WHERE 
    codemp = '01';
