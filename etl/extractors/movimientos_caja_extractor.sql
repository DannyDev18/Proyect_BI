-- Extracción de movimientos_caja (Hechos: Movimientos de Caja)
SELECT 
    codemp,
    codcaja AS num_caja,
    codusu,
    fectra AS fecape, -- Usar fecha de transacción como apertura/corte
    0.0 AS monto_apertura,
    valor AS monto_ingreso,
    0.0 AS monto_egreso,
    valor AS monto_cierre,
    descuadre,
    codforpag
FROM 
    movimientos_caja
WHERE 
    codemp = '01';
