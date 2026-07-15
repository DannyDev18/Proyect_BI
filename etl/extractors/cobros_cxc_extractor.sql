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
    codforpag,       -- Forma de pago asociada
    tiporg AS tipo_doc,
    establ           -- Auditoría 31 (H2): faltaba para resolver sucursal_sk (caía a -1 en el 100% de las filas)
FROM
    cuentasporcobrar
WHERE 
    codemp = '{CODEMP}' AND fecemi >= '{FECHA_DESDE}';
