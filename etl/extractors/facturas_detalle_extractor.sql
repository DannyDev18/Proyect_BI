-- Extracción de facturas (datos crudos)
-- Auditoría 34 (H-13/H-15): 'bienser' y 'desinv' existen en renglonesfacturas y estaban
-- descartados (NULL AS desinv, bienser ni siquiera se seleccionaba). Confirmado contra
-- Producción (solo SELECT): bienser='S' en 58.407 líneas reales (~$204 mil), desinv='N'
-- en 904 líneas -- ambos con volumen real que el ETL ignoraba.
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
    r.bienser,  -- 'S' = línea de servicio, 'B' = línea de bien (RN-CM1, grano línea)
    r.desinv    -- 'S' = descarga inventario (aplica costo), 'N' = no inventariable (regla de negocio #5)
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

