-- Extracción de metas (Hechos: Metas Comerciales)
SELECT 
    codemp,
    codven,
    coditem AS codart,
    fchcrea AS fecmes,
    cantid * 10.0 AS monto_meta,
    cantid AS unidades_meta
FROM 
    vendedorespres
WHERE 
    codemp = '01';
