-- Extracción de nom_nomina (Hechos: Nómina)
SELECT 
    codemp,
    codnom AS codemple,
    fecnom AS fecdoc,
    sueldo AS ingreso_sueldo,
    hextra AS horas_extras_valor,
    comisi AS comisiones_valor,
    totegr AS descuento_seguro,
    liquid AS liquido_a_recibir
FROM 
    nom_nomina
WHERE 
    codemp = '01';
