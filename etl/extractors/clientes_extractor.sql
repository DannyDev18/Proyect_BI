-- Extracción de la tabla clientes (Dimensión Cliente)
SELECT 
    codemp,
    codcli,
    nomcli AS nombre_cliente,
    rucced AS ruc_cedula,
    '05' AS tipo_id,
    codcla AS clase_cliente,
    NULL AS nombre_clase,
    codzona AS zona,
    NULL AS nombre_zona,
    ciucli AS ciudad,
    cupo AS limite_credito,
    30 AS dias_credito,
    estado,
    'U' AS sexo,
    fecult
FROM 
    clientes
WHERE 
    codemp = '{CODEMP}';
