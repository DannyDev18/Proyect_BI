-- Extracción de fp_cxc_cuotas (Hechos: Cobros por cuota / formas de pago de cobranza).
--
-- Fuente de verdad de la COMISIÓN SOBRE COBROS (docs/auditoria/44_comisiones_sobre_cobros.md,
-- docs/features/plan_comisiones_sobre_cobros.md). Es la misma tabla sobre la que el ERP
-- construye su reporte "Consultas e Informes Nº 10, A.- Comisión sobre cobros".
--
-- Por qué esta tabla y no 'cuentasporcobrar' ni 'movimientos_caja' (auditoría 44):
--   - 'cuentasporcobrar' es un libro mayor mixto: 70.928 filas de FAC/FC son FACTURAS
--     EMITIDAS, no cobros (H-4). No distingue el instrumento de pago.
--   - 'movimientos_caja' es un canal PARCIAL: los depósitos/transferencias (DP), el
--     instrumento de mayor monto del mes, no pasan por caja en absoluto (H-10).
--   - 'fp_cxc_cuotas' tiene el grano exacto (un cobro, de una cuota, con un instrumento)
--     y las dos fechas que la regla de negocio necesita.
--
-- banfec vs fectra (H-3, el hallazgo central): 'banfec' es la fecha en que el dinero se
-- hace EFECTIVO y es la que devenga la comisión; 'fectra' es la fecha en que se registró
-- el cobro. Para cheques postfechados (tiptra='CP') difieren: el 47,4% de los CP cruzan de
-- mes entre ambas fechas ($366.688 de $839.412 en ene-2025..jul-2026, desfase promedio de
-- 35,5 días). Usar 'fectra' asignaría casi la mitad de ese dinero al mes equivocado.
-- NOTA: 'banfec' puede estar en el FUTURO respecto de la corrida (un cheque postfechado se
-- registra hoy y se cobra en octubre) -- el cierre de un período debe filtrar por rango
-- cerrado, nunca por '>= inicio'.
--
-- fecemi es la fecha de la factura origen: verificado contra
-- cuentasporcobrar (tiporg='FAC', tipdoc='FC') -- coincide exactamente, por lo que NO hace
-- falta replicar las 4 subconsultas correlacionadas del reporte PowerBuilder original.
--
-- La exclusión de notas de débito (substring(numcco,1,2)='ND') que aplica el reporte del ERP
-- NO se hace aquí a propósito: el EDW guarda el hecho completo y la regla se decide en la
-- capa de negocio (columna derivada es_nota_debito), para que siga siendo configurable.
SELECT
    codemp,
    numcco,          -- Comprobante de cobro (recibo de caja 'RC' / nota de débito 'ND')
    numren,          -- Renglón dentro del comprobante
    codcli,
    codven,          -- Vendedor acreditado (98,5% coincide con el codven de la factura origen)
    tiptra,          -- Instrumento: EF/CP/DP/CH/TA/ND/NC (dimensión degenerada, ver DDL)
    numtra,          -- Factura origen
    ncuota,          -- Número de cuota de esa factura
    banfec,          -- FECHA DE EFECTIVIZACIÓN -> devengo de la comisión
    fectra,          -- Fecha de registro del cobro
    fecemi,          -- Fecha de emisión de la factura origen
    fecven,          -- Fecha de vencimiento de la cuota
    valfor AS valor_cobrado,
    numche,          -- Número de cheque
    bannum,          -- Número de banco/cheque alterno
    codban,
    depositado
FROM
    fp_cxc_cuotas
WHERE
    codemp = '{CODEMP}' AND banfec >= '{FECHA_DESDE}';
