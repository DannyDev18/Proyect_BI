-- ============================================================
-- EXTRACCIÓN DE CUENTAS POR PAGAR (VERSIÓN SIMPLIFICADA)
-- ============================================================
-- Campos mínimos necesarios para el EDW
-- ============================================================

SELECT 
    codemp,
    numcpp AS num_transaccion,
    tipdoc AS tipo_documento,      -- RT, FC, AB
    codpro,
    fecemi AS fecha_emision,
    fecven AS fecha_vencimiento,
    fectra AS fecha_transaccion,
    valcob AS valor_documento,      -- Siempre negativo
    totnet AS total_neto,
    totiva AS total_iva,
    cerrado AS documento_cerrado,   -- 'S' = Cerrado
    estadoconta AS estado_contable, -- 'P' = Contabilizado
    numdoc AS documento_origen,     -- Factura de compra
    codusu AS usuario,
    establ,                         -- Auditoría 10: faltaba para resolver sucursal_sk (caía a -1).
    'C' AS codforpag                -- Fijo: Crédito
FROM
    cuentasporpagar
WHERE
    codemp = '{CODEMP}' AND fecemi >= '{FECHA_DESDE}';
