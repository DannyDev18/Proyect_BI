-- Extracción de encabezadocompras (Hechos: Compras Cabecera)
SELECT 
    codemp,          -- Código de empresa
    numfac,          -- Número de factura compra
    codalm,          -- Almacén destino
    codpro,          -- Código proveedor
    fecfac,          -- Fecha factura
    totnet,          -- Total neto
    totdes,          -- Total descuento
    totiva,          -- Total IVA
    totfac           -- Total factura
FROM 
    encabezadocompras
WHERE 
    codemp = '01';
