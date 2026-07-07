SELECT 
    d.codemp,
    d.numfac AS num_nota_credito,
    d.codart,
    d.codcli,
    d.codalm,
    d.establ,
    e.codven,
    d.cantid AS cantidad_devuelta,
    d.totren AS total_linea_devolucion,
    (d.cantid * d.valuni) AS costo_total_devolucion,
    e.fecfac
FROM 
    renglonesdevoluciones d
JOIN encabezadodevoluciones e ON d.codemp = e.codemp AND d.numfac = e.numfac
WHERE 
    d.codemp = '01' AND e.estado = 'P';
