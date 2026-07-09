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

