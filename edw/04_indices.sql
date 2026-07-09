-- ============================================================
-- ARQUITECTURA DATA WAREHOUSE — INDICES DE DESEMPEÑO
-- ============================================================

-- == 1. Índices Fact_Ventas_Detalle ==
CREATE INDEX idx_fvd_fecha      ON edw.Fact_Ventas_Detalle (fecha_sk);
CREATE INDEX idx_fvd_prod       ON edw.Fact_Ventas_Detalle (producto_sk);
CREATE INDEX idx_fvd_cli        ON edw.Fact_Ventas_Detalle (cliente_sk);
CREATE INDEX idx_fvd_suc        ON edw.Fact_Ventas_Detalle (sucursal_sk);
CREATE INDEX idx_fvd_ven        ON edw.Fact_Ventas_Detalle (vendedor_sk);
CREATE INDEX idx_fvd_multikey   ON edw.Fact_Ventas_Detalle (fecha_sk, sucursal_sk, producto_sk);
CREATE INDEX idx_fvd_estado_doc ON edw.Fact_Ventas_Detalle (estado_documento_sk);

-- == 2. Índices Fact_Inventario_Snapshot ==
CREATE INDEX idx_fis_composite  ON edw.Fact_Inventario_Snapshot (fecha_sk, sucursal_sk, almacen_sk);
CREATE INDEX idx_fis_prod       ON edw.Fact_Inventario_Snapshot (producto_sk);

-- == 3. Índices Fact_Movimientos_Inventario ==
CREATE INDEX idx_fmi_composite  ON edw.Fact_Movimientos_Inventario (fecha_sk, sucursal_sk, almacen_sk);
CREATE INDEX idx_fmi_prod       ON edw.Fact_Movimientos_Inventario (producto_sk);

-- == 4. Índices Fact_Compras ==
CREATE INDEX idx_fc_compr       ON edw.Fact_Compras (fecha_sk, proveedor_sk);
CREATE INDEX idx_fc_prod        ON edw.Fact_Compras (producto_sk);

-- == 5. Índices Fact_Cobros_CXC ==
CREATE INDEX idx_fcc_composite  ON edw.Fact_Cobros_CXC (fecha_sk, cliente_sk);
CREATE INDEX idx_fcc_ven        ON edw.Fact_Cobros_CXC (vendedor_sk);

-- == 6. Índices Fact_Pagos_CXP ==
CREATE INDEX idx_fpc_composite  ON edw.Fact_Pagos_CXP (fecha_sk, proveedor_sk);

-- == 7. Índices Fact_Nomina ==
CREATE INDEX idx_fn_emp         ON edw.Fact_Nomina (fecha_sk, empleado_sk);

-- == 8. Índices Fact_Movimientos_Caja ==
CREATE INDEX idx_fmc_composite  ON edw.Fact_Movimientos_Caja (fecha_sk, sucursal_sk);

-- == 9. Índices Fact_Metas_Comerciales ==
CREATE INDEX idx_fmc_metas      ON edw.Fact_Metas_Comerciales (fecha_sk, vendedor_sk);

-- == 10. Índices Fact_Logs_Auditoria ==
CREATE INDEX idx_fla_userlog    ON edw.Fact_Logs_Auditoria (fecha_sk, usuario_sk);

-- == 11. Índices Fact_Devoluciones ==
CREATE INDEX idx_fd_devol       ON edw.Fact_Devoluciones (fecha_sk, cliente_sk, producto_sk);

-- == 12. Índices Fact_Transferencias ==
CREATE INDEX idx_ft_composite   ON edw.Fact_Transferencias (fecha_sk, almacen_origen_sk, almacen_destino_sk);
CREATE INDEX idx_ft_prod        ON edw.Fact_Transferencias (producto_sk);

-- == 12. Índices de SCD Tipo 2 ==
-- Únicos parciales: garantizan que exista como máximo UNA fila vigente por llave de negocio.
-- Ver docs/auditoria/07_revision_diseno_edw.md (H1). Sin esto, un loader que reintente una
-- carga fallida podía duplicar la versión vigente sin que la base lo impidiera.
CREATE UNIQUE INDEX idx_dp_vigente ON edw.Dim_Producto (codemp, codart) WHERE es_vigente = TRUE;
CREATE UNIQUE INDEX idx_dc_vigente ON edw.Dim_Cliente (hash_anonimo) WHERE es_vigente = TRUE;
