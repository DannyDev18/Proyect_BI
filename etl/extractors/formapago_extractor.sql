-- Extracción estática de Formas de Pago ya que tipo_formapago_cxc está vacía en este origen
SELECT '01' AS codemp, 'E' AS codforpag, 'EFECTIVO' AS nombre_forma_pago, 0 AS dias_plazo FROM dummy
UNION ALL
SELECT '01' AS codemp, 'C' AS codforpag, 'CREDITO' AS nombre_forma_pago, 30 AS dias_plazo FROM dummy
UNION ALL
SELECT '01' AS codemp, '0' AS codforpag, 'OTRO/VARIOS' AS nombre_forma_pago, 0 AS dias_plazo FROM dummy;
