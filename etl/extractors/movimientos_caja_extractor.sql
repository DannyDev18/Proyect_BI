-- Extracción de movimientos_caja (Hechos: Movimientos de Caja)
SELECT 
    codemp,
    codcaja AS num_caja,
    codusu,
    tiporg AS tipo_movimiento,  -- Auditoría 10: la columna real es 'tiporg', no 'tipoorg'
                                -- (Error -143 de SQL Anywhere: "Column 'tipoorg' not found").
    establ,                     -- Necesaria para resolver sucursal_sk (antes caía al centinela -1).
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
    codemp = '{CODEMP}' AND fectra >= '{FECHA_DESDE}';
