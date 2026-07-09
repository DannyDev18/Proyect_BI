-- Extracción de la tabla kardex (Hechos: Inventario / Movimientos)
-- Reglas de negocio validadas en docs/auditoria/02_reglas_negocio_validadas.md:
--   §3 tiporg: FAC=venta, TRA=transferencia, CPA=compra, DEV=devolución, ING/EGR/BOD/DEC.
--   §4 tipdoc: EN=entrada, SA=salida, AC/AD=ajuste. cantot SIEMPRE es positivo (magnitud);
--      la dirección la determina tipdoc (no el signo).
SELECT
    codemp,          -- Código de empresa
    numdoc AS num_documento, -- Número de documento referencial
    tiporg AS tipo_movimiento, -- Tipo de movimiento (ver §3)
    tipdoc,          -- Dirección del movimiento (EN/SA/AC/AD) -> define es_entrada/es_salida
    codart,          -- Código del artículo
    codalm,          -- Almacén/Bodega
    establ,          -- Establecimiento (permite resolver la sucursal en el DW)
    fecdoc,          -- Fecha del documento (movimiento)
    cantot AS cantidad_movimiento, -- Cantidad del movimiento (siempre positiva)
    cosuni AS costo_unitario,      -- Costo unitario
    costot AS costo_total,         -- Costo total
    totven AS valor_venta,         -- Total venta asociada
    codcli,          -- Cliente asociado (si aplica)
    codven           -- Vendedor asociado (si aplica)
FROM
    kardex
WHERE
    codemp = '{CODEMP}' AND fecdoc >= '{FECHA_DESDE}';
