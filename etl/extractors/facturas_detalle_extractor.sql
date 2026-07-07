-- Extracción de la tabla renglonesfacturas (Hechos: Detalle de Facturas)
SELECT 
    r.codemp,
    r.numfac AS num_factura,
    'F' AS tipo_documento,
    r.codart,
    e.codcli,
    e.codven,
    e.conpag AS codforpag,
    r.codalm,
    r.cantid AS cantidad,
    r.preuni AS precio_unitario,
    a.ultcos AS costo_unitario,
    (r.cantid * r.preuni) AS subtotal_bruto,
    r.desren AS valor_descuento,
    r.totren AS subtotal_neto,
    (r.totren * e.poriva / 100.0) AS valor_iva,
    (r.totren + (r.totren * e.poriva / 100.0)) AS total_linea,
    (r.cantid * a.ultcos) AS costo_total,
    (r.totren - (r.cantid * a.ultcos)) AS margen_bruto,
    e.estado AS estado_factura,
    e.fecfac
FROM 
    renglonesfacturas r
JOIN encabezadofacturas e ON r.codemp = e.codemp AND r.numfac = e.numfac
JOIN articulos a ON r.codemp = a.codemp AND r.codart = a.codart
WHERE 
    r.codemp = '01' AND e.estado = 'P'

UNION ALL

SELECT 
    d.codemp,
    d.numfac AS num_factura,
    'NC' AS tipo_documento,
    d.codart,
    e.codcli,
    e.codven,
    e.conpag AS codforpag,
    d.codalm,
    (d.cantid * -1) AS cantidad,
    d.valuni AS precio_unitario,
    a.ultcos AS costo_unitario,
    ((d.cantid * d.valuni) * -1) AS subtotal_bruto,
    0 AS valor_descuento,
    (d.totren * -1) AS subtotal_neto,
    ((d.totren * e.poriva / 100.0) * -1) AS valor_iva,
    ((d.totren + (d.totren * e.poriva / 100.0)) * -1) AS total_linea,
    ((d.cantid * a.ultcos) * -1) AS costo_total,
    ((d.totren - (d.cantid * a.ultcos)) * -1) AS margen_bruto,
    e.estado AS estado_factura,
    e.fecfac
FROM 
    renglonesdevoluciones d
JOIN encabezadodevoluciones e ON d.codemp = e.codemp AND d.numfac = e.numfac
JOIN articulos a ON d.codemp = a.codemp AND d.codart = a.codart
WHERE 
    d.codemp = '01' AND e.estado = 'P';
