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
    num_factura         VARCHAR(10) NOT NULL,
    tipo_documento      VARCHAR(5),
    cantidad            NUMERIC(15,4) NOT NULL,
    precio_unitario     NUMERIC(15,4) NOT NULL,
    costo_unitario      NUMERIC(15,4) NOT NULL,
    subtotal_bruto      NUMERIC(15,4) NOT NULL,
    valor_descuento     NUMERIC(15,4) NOT NULL,
    subtotal_neto       NUMERIC(15,4) NOT NULL,
    valor_iva           NUMERIC(15,4) NOT NULL,
    total_linea         NUMERIC(15,4) NOT NULL,
    costo_total         NUMERIC(15,4) NOT NULL,
    margen_bruto        NUMERIC(15,4) NOT NULL,
    pct_margen          NUMERIC(8,4) NOT NULL,
    es_devolucion       BOOLEAN DEFAULT FALSE,
    estado_factura      VARCHAR(1) DEFAULT 'A',
    fecha_carga         TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE edw.Fact_Ventas_Detalle IS 'Hechos detallados de transacciones de venta.';

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
    tipo_movimiento     VARCHAR(3) NOT NULL,
    num_documento       VARCHAR(10) NOT NULL,
    cantidad_movimiento NUMERIC(15,4) NOT NULL,
    costo_unitario      NUMERIC(15,4),
    costo_total         NUMERIC(15,4),
    valor_venta         NUMERIC(15,4),
    es_entrada          BOOLEAN NOT NULL,
    es_salida           BOOLEAN NOT NULL
);
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
    saldo_documento     NUMERIC(15,4) NOT NULL,
    dias_vencimiento    INTEGER NOT NULL,
    esta_vencido        BOOLEAN DEFAULT FALSE,
    fecha_carga         TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE edw.Fact_Cobros_CXC IS 'Seguimiento de cobros y cuentas por cobrar de la cartera.';

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
