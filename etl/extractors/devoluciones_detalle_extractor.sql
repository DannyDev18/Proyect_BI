SELECT 
    d.codemp,
    d.numfac AS num_nota_credito,
    d.codart,
    d.codalm,
    d.establ,
    e.codcli,
    e.codven,
    d.cantid AS cantidad_devuelta,
    d.totren AS total_linea_devolucion,
    (CASE WHEN d.desinv = 'S' THEN (d.cantid * COALESCE(a.ultcos, 0.0)) ELSE 0.0 END) AS costo_total_devolucion,
    e.fecfac
FROM 
    renglonesdevoluciones d
JOIN encabezadodevoluciones e ON d.codemp = e.codemp AND d.numfac = e.numfac
LEFT JOIN articulos a ON d.codemp = a.codemp AND d.codart = a.codart
WHERE 
    d.codemp = '{CODEMP}' AND e.estado = '{ESTADO}' AND e.fecfac >= '{FECHA_DESDE}';
