-- Extracción de encabezadodevoluciones (Hechos: Devoluciones Cabecera)
SELECT 
    codemp,          -- Código de empresa
    numfac AS num_nota_credito, -- Nota de crédito
    codcli,          -- Cliente
    codalm,          -- Almacén al que devuelve
    fecfac AS fecha_devolucion, -- Fecha devolucion
    totfac AS costo_total_devolucion -- Total devolución
FROM 
    encabezadodevoluciones
WHERE 
    codemp = '01' AND estado = 'P';
