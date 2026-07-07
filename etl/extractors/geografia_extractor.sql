-- Extracción agrupada de Geografía (Dimensión Geografía)
SELECT 
    'Ecuador' AS pais,
    p.nomprovin AS provincia,
    c.nomciu AS canton,          
    NULL AS parroquia
FROM 
    ciudad c
LEFT JOIN provincia p ON c.codprovin = p.codprovin
-- LEFT JOIN zona z ON c.codciu = z.codciu
WHERE 
    c.codemp = '01';
