SELECT 
    a.codemp,          -- Código de empresa
    a.codalm,          -- Código de almacén
    a.nomalm AS nombre_almacen, -- Nombre del almacén
    COALESCE(
        (SELECT TOP 1 t.establ
         FROM tiposecuencias t
         WHERE t.codemp = a.codemp AND t.codalm = a.codalm AND t.establ IS NOT NULL AND t.establ <> ''
         GROUP BY t.establ
         ORDER BY COUNT(*) DESC, t.establ ASC),
        (SELECT TOP 1 k.establ
         FROM kardex k
         WHERE k.codemp = a.codemp AND k.codalm = a.codalm AND k.establ IS NOT NULL AND k.establ <> ''
         GROUP BY k.establ
         ORDER BY COUNT(*) DESC, k.establ ASC),
        RIGHT('000' + a.codalm, 3)
    ) AS establ           -- Establecimiento inferido. El tie-break determinista (…, establ ASC) evita
                          -- resultados no reproducibles ante empates. Ver auditoría §A4.
FROM
    almacenes a
WHERE
    a.codemp = '{CODEMP}';
