-- Extracción de la tabla encabezadofacturas (Hechos: Facturación Cabecera)
SELECT 
    codemp,          -- Código de empresa
    numfac,          -- Número de factura
    codcli,          -- Código de cliente
    codven,          -- Código de vendedor
    codalm,          -- Código de almacén (bodega)
    fecfac,          -- Fecha de la factura
    totnet,          -- Total neto
    totdes,          -- Total descuento
    totiva,          -- Total IVA
    totfac,          -- Total factura
    estado,          -- Estado de la factura
    conpag,          -- Condición de pago
    establ           -- Código de establecimiento
FROM 
    encabezadofacturas
WHERE 
    codemp = '01' AND estado = 'P'

UNION ALL

SELECT 
    codemp,
    numfac,
    codcli,
    codven,
    codalm,
    fecfac,
    (totnet * -1) AS totnet,
    (totdes * -1) AS totdes,
    (totiva * -1) AS totiva,
    (totfac * -1) AS totfac,
    estado,
    conpag,
    establ
FROM 
    encabezadodevoluciones
WHERE 
    codemp = '01' AND estado = 'P';
