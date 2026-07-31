-- ============================================================
-- ARQUITECTURA DATA WAREHOUSE — HECHOS (PostgreSQL 16)
-- ============================================================

-- ── 1. FACT_VENTAS_DETALLE ──
CREATE TABLE edw.Fact_Ventas_Detalle (
    venta_sk            BIGSERIAL PRIMARY KEY,
    fecha_sk            INT NOT NULL REFERENCES edw.Dim_Fecha(fecha_sk),
    producto_sk         INT NOT NULL REFERENCES edw.Dim_Producto(producto_sk),
    cliente_sk          INT NOT NULL REFERENCES edw.Dim_Cliente(cliente_sk),
    sucursal_sk         INT NOT NULL REFERENCES edw.Dim_Sucursal(sucursal_sk),
    vendedor_sk         INT NOT NULL REFERENCES edw.Dim_Vendedor(vendedor_sk),
    formapago_sk        INT NOT NULL REFERENCES edw.Dim_FormaPago(formapago_sk),
    estado_documento_sk INT NOT NULL REFERENCES edw.Dim_Estado_Documento(estado_documento_sk),
    almacen_sk          INT NOT NULL REFERENCES edw.Dim_Almacen(almacen_sk),
    num_factura         VARCHAR(20) NOT NULL,
    cantidad            NUMERIC(15,4) NOT NULL,
    precio_unitario     NUMERIC(15,4) NOT NULL,
    costo_unitario      NUMERIC(15,4),
    subtotal_bruto      NUMERIC(15,4) NOT NULL,
    valor_descuento     NUMERIC(15,4) NOT NULL,
    subtotal_neto       NUMERIC(15,4) NOT NULL,
    valor_iva           NUMERIC(15,4) NOT NULL,
    total_linea         NUMERIC(15,4) NOT NULL,
    costo_total         NUMERIC(15,4),
    margen_bruto        NUMERIC(15,4),
    pct_margen          NUMERIC(8,4) NOT NULL,
    es_linea_servicio   BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_carga         TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE edw.Fact_Ventas_Detalle IS 'Hechos detallados de transacciones de venta.';
COMMENT ON COLUMN edw.Fact_Ventas_Detalle.es_linea_servicio IS
    'Auditoría 34 (H-13): derivado de renglonesfacturas.bienser (línea de transacción), NO
     de dim_producto.es_servicio (articulos.bienser casi no se usa en Producción: 1 fila en
     ''S'' de 8.152 artículos, contra 58.407 líneas reales en ''S''). Fuente real para el
     grupo S (servicios) del motor de Comisiones Variables (commission_engine.py).';
COMMENT ON COLUMN edw.Fact_Ventas_Detalle.pct_margen IS
    'margen_bruto / subtotal_neto. Convención (auditoría 07 H8): si subtotal_neto = 0
     (promociones/cortesías con precio 0), pct_margen = 0, no NULL ni error de carga.';
COMMENT ON COLUMN edw.Fact_Ventas_Detalle.costo_unitario IS
    'NULL cuando el artículo no tiene costo definido en articulos.ultcos (auditoría 08 F2:
     no se fuerza a 0.0, o el margen se infla artificialmente al 100%). Auditoría 10
     (docs/auditoria/10_auditoria_ventas_detalle_calculo.md) relajó el NOT NULL original
     tras confirmar filas reales de Producción con este caso.';
COMMENT ON COLUMN edw.Fact_Ventas_Detalle.margen_bruto IS
    'NULL cuando costo_total es NULL (ver costo_unitario) — no se puede calcular margen sin costo.';

-- ── 2. FACT_INVENTARIO_SNAPSHOT ──
CREATE TABLE edw.Fact_Inventario_Snapshot (
    snapshot_sk         BIGSERIAL PRIMARY KEY,
    fecha_sk            INT NOT NULL REFERENCES edw.Dim_Fecha(fecha_sk),
    producto_sk         INT NOT NULL REFERENCES edw.Dim_Producto(producto_sk),
    sucursal_sk         INT NOT NULL REFERENCES edw.Dim_Sucursal(sucursal_sk),
    almacen_sk          INT NOT NULL REFERENCES edw.Dim_Almacen(almacen_sk),
    stock_actual        NUMERIC(15,4) NOT NULL,
    costo_promedio      NUMERIC(15,4) NOT NULL,
    valor_inventario    NUMERIC(15,4) NOT NULL,
    stock_minimo        NUMERIC(15,4) DEFAULT 0,
    stock_maximo        NUMERIC(15,4) DEFAULT 0,
    punto_reorden       NUMERIC(15,4) DEFAULT 0,
    alerta_desabastecimiento BOOLEAN DEFAULT FALSE,
    alerta_sobrestock        BOOLEAN DEFAULT FALSE,
    fecha_carga         TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE edw.Fact_Inventario_Snapshot IS 'Fotografía diaria del inventario por bodega y sucursal.';

-- ── 3. FACT_MOVIMIENTOS_INVENTARIO ──
CREATE TABLE edw.Fact_Movimientos_Inventario (
    movimiento_sk       BIGSERIAL PRIMARY KEY,
    fecha_sk            INT NOT NULL REFERENCES edw.Dim_Fecha(fecha_sk),
    producto_sk         INT NOT NULL REFERENCES edw.Dim_Producto(producto_sk),
    sucursal_sk         INT NOT NULL REFERENCES edw.Dim_Sucursal(sucursal_sk),
    almacen_sk          INT NOT NULL REFERENCES edw.Dim_Almacen(almacen_sk),
    cliente_sk          INT REFERENCES edw.Dim_Cliente(cliente_sk),
    vendedor_sk         INT REFERENCES edw.Dim_Vendedor(vendedor_sk),
    tipo_movimiento     VARCHAR(3) NOT NULL,
    num_documento       VARCHAR(10) NOT NULL,
    cantidad_movimiento NUMERIC(15,4) NOT NULL,
    costo_unitario      NUMERIC(15,4),
    costo_total         NUMERIC(15,4),
    valor_venta         NUMERIC(15,4),
    es_entrada          BOOLEAN NOT NULL,
    es_salida           BOOLEAN NOT NULL
);
COMMENT ON COLUMN edw.Fact_Movimientos_Inventario.cliente_sk IS
    'Cliente asociado al movimiento (kardex.codcli). NULL salvo tipo_movimiento=''FAC''. Ver auditoría 07 H5.';
COMMENT ON COLUMN edw.Fact_Movimientos_Inventario.vendedor_sk IS
    'Vendedor asociado al movimiento (kardex.codven). NULL salvo tipo_movimiento=''FAC''. Ver auditoría 07 H5.';
COMMENT ON TABLE edw.Fact_Movimientos_Inventario IS 'Historial analítico de movimientos físicos de stock (Kardex).';

-- ── 4. FACT_COMPRAS ──
CREATE TABLE edw.Fact_Compras (
    compra_sk           BIGSERIAL PRIMARY KEY,
    fecha_sk            INT NOT NULL REFERENCES edw.Dim_Fecha(fecha_sk),
    producto_sk         INT NOT NULL REFERENCES edw.Dim_Producto(producto_sk),
    proveedor_sk        INT NOT NULL REFERENCES edw.Dim_Proveedor(proveedor_sk),
    sucursal_sk         INT NOT NULL REFERENCES edw.Dim_Sucursal(sucursal_sk),
    almacen_sk          INT NOT NULL REFERENCES edw.Dim_Almacen(almacen_sk),
    num_factura         VARCHAR(20) NOT NULL,
    cantidad            NUMERIC(15,4) NOT NULL,
    costo_unitario      NUMERIC(15,4) NOT NULL,
    costo_linea         NUMERIC(15,4) NOT NULL,
    descuento_valor     NUMERIC(15,4) DEFAULT 0,
    total_factura       NUMERIC(15,4) NOT NULL,
    fecha_carga         TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE edw.Fact_Compras IS 'Línea de facturas de abastecimiento de mercaderías.';

-- ── 5. FACT_COBROS_CXC ──
CREATE TABLE edw.Fact_Cobros_CXC (
    cobro_sk            BIGSERIAL PRIMARY KEY,
    fecha_sk            INT NOT NULL REFERENCES edw.Dim_Fecha(fecha_sk),
    cliente_sk          INT NOT NULL REFERENCES edw.Dim_Cliente(cliente_sk),
    vendedor_sk         INT NOT NULL REFERENCES edw.Dim_Vendedor(vendedor_sk),
    sucursal_sk         INT NOT NULL REFERENCES edw.Dim_Sucursal(sucursal_sk),
    formapago_sk        INT NOT NULL REFERENCES edw.Dim_FormaPago(formapago_sk),
    num_transaccion     VARCHAR(20) NOT NULL,
    valor_cobrado       NUMERIC(15,4) NOT NULL,
    -- Auditoría 41 (H3): NULL real en SAP (cuentasporcobrar.saldodoc, 55.5% de los documentos)
    -- significa "saldo desconocido", no "documento pagado" -- antes se coaccionaba a 0.0 con
    -- fillna(0), indistinguible de un cierre real. Nullable a propósito.
    saldo_documento     NUMERIC(15,4),
    dias_vencimiento    INTEGER NOT NULL,
    esta_vencido        BOOLEAN DEFAULT FALSE,
    fecha_carga         TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE edw.Fact_Cobros_CXC IS 'Seguimiento de cobros y cuentas por cobrar de la cartera.';

-- ── 5b. FACT_COBROS_CUOTAS ──
-- Cobranza al grano real de negocio: un cobro, de una cuota de una factura, con un
-- instrumento de pago. Fuente de la COMISIÓN SOBRE COBROS
-- (docs/auditoria/44_comisiones_sobre_cobros.md, docs/features/plan_comisiones_sobre_cobros.md).
--
-- Convive con Fact_Cobros_CXC sin reemplazarla: aquélla la consumen analytics/Cartera 360 y
-- su semántica mixta (mezcla facturas emitidas con cobros, H-4) queda documentada pero NO
-- corregida aquí -- cambiarla rompería consumidores actuales.
CREATE TABLE edw.Fact_Cobros_Cuotas (
    cobro_cuota_sk      BIGSERIAL PRIMARY KEY,
    -- fecha_sk = banfec (EFECTIVIZACIÓN). Es la fecha que devenga la comisión: para cheques
    -- postfechados el dinero entra semanas después de recibirse el cheque y el 47,4% de esos
    -- cobros cruzan de mes (auditoría 44, H-3).
    fecha_sk            INT NOT NULL REFERENCES edw.Dim_Fecha(fecha_sk),
    fecha_registro_sk   INT REFERENCES edw.Dim_Fecha(fecha_sk),   -- fectra
    fecha_emision_sk    INT REFERENCES edw.Dim_Fecha(fecha_sk),   -- fecemi (factura origen)
    cliente_sk          INT NOT NULL REFERENCES edw.Dim_Cliente(cliente_sk),
    vendedor_sk         INT NOT NULL REFERENCES edw.Dim_Vendedor(vendedor_sk),
    -- Instrumento de pago como DIMENSIÓN DEGENERADA (varchar en el hecho), no FK a
    -- Dim_FormaPago. Decisión deliberada con evidencia (auditoría 44, H-2): Dim_FormaPago
    -- proviene de un extractor estático de 3 filas (E/C/0) y hoy deja el 100% de las 214.108
    -- filas de Fact_Cobros_CXC en el centinela -1. El vocabulario real es cerrado y de 7
    -- valores (EF/CP/DP/CH/TA/ND/NC); una FK repetiría exactamente el defecto que esta tabla
    -- corrige.
    tipo_instrumento    VARCHAR(2) NOT NULL,
    es_postfechado      BOOLEAN NOT NULL DEFAULT FALSE,           -- tiptra = 'CP'
    -- dias_cobro = banfec - fecemi, con piso en 0. Se materializa en el ETL (no se calcula
    -- por consulta) porque es el discriminante del tramo de comisión: así el tramo es
    -- auditable sobre el dato cargado. Piso 0 por 12 filas históricas con banfec anterior a
    -- fecemi (mínimo -25 días, auditoría 44 H-9).
    dias_cobro          INTEGER NOT NULL,
    valor_cobrado       NUMERIC(15,4) NOT NULL,
    num_comprobante     VARCHAR(20) NOT NULL,                     -- numcco ('RC…'/'ND…')
    num_transaccion     VARCHAR(20),                              -- numtra (factura origen)
    num_cuota           INTEGER,
    num_cheque          VARCHAR(20),
    -- Las notas de débito se excluyen de la base comisionable (el reporte del ERP filtra
    -- substring(numcco,1,2) <> 'ND'). Se marca en vez de descartarse en el ETL para que la
    -- regla siga siendo configurable en la capa de negocio.
    es_nota_debito      BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_carga         TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE edw.Fact_Cobros_Cuotas IS 'Cobranza al grano (cobro, cuota, instrumento). Base de la comisión sobre cobros; devengo por fecha de efectivización.';

-- ── 6. FACT_PAGOS_CXP ──
CREATE TABLE edw.Fact_Pagos_CXP (
    pago_sk             BIGSERIAL PRIMARY KEY,
    fecha_sk            INT NOT NULL REFERENCES edw.Dim_Fecha(fecha_sk),
    proveedor_sk        INT NOT NULL REFERENCES edw.Dim_Proveedor(proveedor_sk),
    sucursal_sk         INT NOT NULL REFERENCES edw.Dim_Sucursal(sucursal_sk),
    formapago_sk        INT NOT NULL REFERENCES edw.Dim_FormaPago(formapago_sk),
    num_transaccion     VARCHAR(20) NOT NULL,
    valor_pagado        NUMERIC(15,4) NOT NULL,
    saldo_pendiente     NUMERIC(15,4) NOT NULL,
    dias_vencimiento    INTEGER NOT NULL,
    fecha_carga         TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE edw.Fact_Pagos_CXP IS 'Pagos efectuados y cuentas pendientes de proveedores.';

-- ── 7. FACT_NOMINA ──
CREATE TABLE edw.Fact_Nomina (
    nomina_sk           BIGSERIAL PRIMARY KEY,
    fecha_sk            INT NOT NULL REFERENCES edw.Dim_Fecha(fecha_sk),
    empleado_sk         INT NOT NULL REFERENCES edw.Dim_Empleado(empleado_sk),
    sucursal_sk         INT NOT NULL REFERENCES edw.Dim_Sucursal(sucursal_sk),
    ingreso_sueldo      NUMERIC(15,4) NOT NULL,
    horas_extras_valor  NUMERIC(15,4) DEFAULT 0,
    comisiones_valor    NUMERIC(15,4) DEFAULT 0,
    descuento_seguro    NUMERIC(15,4) DEFAULT 0,
    liquido_a_recibir   NUMERIC(15,4) NOT NULL,
    fecha_carga         TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE edw.Fact_Nomina IS 'Consolidado histórico de rubros de salarios de empleados.';

-- ── 8. FACT_MOVIMIENTOS_CAJA ──
CREATE TABLE edw.Fact_Movimientos_Caja (
    caja_mov_sk         BIGSERIAL PRIMARY KEY,
    fecha_sk            INT NOT NULL REFERENCES edw.Dim_Fecha(fecha_sk),
    usuario_sk          INT NOT NULL REFERENCES edw.Dim_Usuario(usuario_sk),
    sucursal_sk         INT NOT NULL REFERENCES edw.Dim_Sucursal(sucursal_sk),
    formapago_sk        INT NOT NULL REFERENCES edw.Dim_FormaPago(formapago_sk),
    num_caja            VARCHAR(10) NOT NULL,
    monto_apertura      NUMERIC(15,4) NOT NULL,
    monto_ingreso       NUMERIC(15,4) DEFAULT 0,
    monto_egreso        NUMERIC(15,4) DEFAULT 0,
    monto_cierre        NUMERIC(15,4) NOT NULL,
    diferencia_arqueo   NUMERIC(15,4) DEFAULT 0,
    fecha_carga         TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE edw.Fact_Movimientos_Caja IS 'Movimientos y arqueos de cajas de las sucursales.';

-- ── 9. FACT_METAS_COMERCIALES ──
CREATE TABLE edw.Fact_Metas_Comerciales (
    meta_sk             BIGSERIAL PRIMARY KEY,
    fecha_sk            INT NOT NULL REFERENCES edw.Dim_Fecha(fecha_sk),
    vendedor_sk         INT NOT NULL REFERENCES edw.Dim_Vendedor(vendedor_sk),
    sucursal_sk         INT NOT NULL REFERENCES edw.Dim_Sucursal(sucursal_sk),
    producto_sk         INT NOT NULL REFERENCES edw.Dim_Producto(producto_sk),
    monto_meta          NUMERIC(15,4) NOT NULL,
    unidades_meta       NUMERIC(15,4) NOT NULL,
    fecha_carga         TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE edw.Fact_Metas_Comerciales IS 'Presupuestos de desempeño de metas comerciales.';

-- ── 10. FACT_LOGS_AUDITORIA ──
CREATE TABLE edw.Fact_Logs_Auditoria (
    log_sk              BIGSERIAL PRIMARY KEY,
    fecha_sk            INT NOT NULL REFERENCES edw.Dim_Fecha(fecha_sk),
    usuario_sk          INT NOT NULL REFERENCES edw.Dim_Usuario(usuario_sk),
    sucursal_sk         INT NOT NULL REFERENCES edw.Dim_Sucursal(sucursal_sk),
    tabla_afectada      VARCHAR(80) NOT NULL,
    tipo_operacion      VARCHAR(10) NOT NULL,
    cantidad_alterada   NUMERIC(15,4),
    valor_anterior      NUMERIC(15,4),
    valor_nuevo         NUMERIC(15,4),
    modulo              VARCHAR(20),
    fecha_carga         TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE edw.Fact_Logs_Auditoria IS 'Log histórico consolidado para control administrativo.';

-- ── 11. FACT_DEVOLUCIONES ──
CREATE TABLE edw.Fact_Devoluciones (
    devolucion_sk       BIGSERIAL PRIMARY KEY,
    fecha_sk            INT NOT NULL REFERENCES edw.Dim_Fecha(fecha_sk),
    producto_sk         INT NOT NULL REFERENCES edw.Dim_Producto(producto_sk),
    cliente_sk          INT NOT NULL REFERENCES edw.Dim_Cliente(cliente_sk),
    sucursal_sk         INT NOT NULL REFERENCES edw.Dim_Sucursal(sucursal_sk),
    vendedor_sk         INT NOT NULL REFERENCES edw.Dim_Vendedor(vendedor_sk),
    almacen_sk          INT NOT NULL REFERENCES edw.Dim_Almacen(almacen_sk),
    num_nota_credito    VARCHAR(50) NOT NULL,
    cantidad_devuelta   NUMERIC(15,4) NOT NULL,
    total_linea_devolucion NUMERIC(15,4) NOT NULL,
    costo_total_devolucion NUMERIC(15,4) NOT NULL,
    fecha_carga         TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE edw.Fact_Devoluciones IS 'Devoluciones de stock hechas por clientes.';

-- ── 12. FACT_TRANSFERENCIAS ──
-- Grain: transferencia por línea, pareada por (num_documento, num_renglon, codart) según
-- transferencias_extractor.sql (regla de negocio §5 de docs/auditoria/02_reglas_negocio_validadas.md:
-- cada ítem transferido genera 2 filas de kardex, SA=origen/EN=destino, ya reconstruidas por
-- el extractor en una sola fila origen→destino). Ver auditoría 07 H10.
CREATE TABLE edw.Fact_Transferencias (
    transferencia_sk    BIGSERIAL PRIMARY KEY,
    fecha_sk            INT NOT NULL REFERENCES edw.Dim_Fecha(fecha_sk),
    producto_sk         INT NOT NULL REFERENCES edw.Dim_Producto(producto_sk),
    sucursal_sk         INT NOT NULL REFERENCES edw.Dim_Sucursal(sucursal_sk),
    almacen_origen_sk   INT NOT NULL REFERENCES edw.Dim_Almacen(almacen_sk),
    almacen_destino_sk  INT NOT NULL REFERENCES edw.Dim_Almacen(almacen_sk),
    num_documento       VARCHAR(20) NOT NULL,
    num_renglon         VARCHAR(20) NOT NULL,
    cantidad_enviada    NUMERIC(15,4) NOT NULL,
    costo_unitario      NUMERIC(15,4),
    costo_total         NUMERIC(15,4),
    fecha_carga         TIMESTAMP DEFAULT NOW(),
    UNIQUE (num_documento, num_renglon, producto_sk)
);
COMMENT ON TABLE edw.Fact_Transferencias IS 'Transferencias de mercadería entre bodegas, reconstruidas origen→destino.';
