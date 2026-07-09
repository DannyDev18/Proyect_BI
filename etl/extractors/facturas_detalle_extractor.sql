-- Extracción de facturas (datos crudos)
SELECT 
    r.codemp,
    r.numfac,
    'F' AS tipo_documento,
    r.codart,
    e.codcli,
    e.codven,
    e.conpag,
    r.codalm,
    r.cantid,
    r.preuni,
    r.desren,
    r.totren,
    a.ultcos,
    r.porceiva,       -- Tasa de IVA ya resuelta por línea (fracción decimal, ej. 0.15).
                       -- NO usar e.poriva: es el código de tarifa (FK a iva.codiva), no la
                       -- tasa (auditoría 10, docs/auditoria/10_auditoria_ventas_detalle_calculo.md).
    e.estado,
    e.fecfac,
    NULL AS desinv  -- Para unificar con devoluciones
FROM 
    renglonesfacturas r
JOIN encabezadofacturas e 
    ON r.codemp = e.codemp AND r.numfac = e.numfac
LEFT JOIN articulos a 
    ON r.codemp = a.codemp AND r.codart = a.codart
WHERE 
    r.codemp = '{CODEMP}' 
    AND e.estado = '{ESTADO}' 
    AND e.fecfac >= '{FECHA_DESDE}'

