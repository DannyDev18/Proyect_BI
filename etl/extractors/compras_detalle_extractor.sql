-- Extracción de renglonescompras (Hechos: Compras Detalle)
SELECT 
    c.codemp,
    c.numfac AS num_factura,
    c.codart,
    c.cantid AS cantidad,
    c.preuni AS costo_unitario,
    c.totren AS costo_linea,
    c.desren AS descuento_valor,
    e.totfac AS total_factura,
    c.codpro,
    c.codalm,
    c.fecfac
FROM 
    renglonescompras c
JOIN encabezadocompras e ON c.codemp = e.codemp AND c.numfac = e.numfac
WHERE 
    c.codemp = '{CODEMP}' AND c.fecfac >= '{FECHA_DESDE}';
