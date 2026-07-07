# DISEÑO DE ARQUITECTURA DE DATA WAREHOUSE COMPLETO: MODELO MULTIESTRELLA

> **Proyecto de Tesis:** Plataforma Inteligente de Analítica Empresarial y Predicción de Ventas para Empresas Multisucursal
> **Autor:** Danny Dev — Ingeniería de Sistemas
> **Motor de Base de Datos Destino:** PostgreSQL 16
> **Fuente Transaccional:** SAP SQL Anywhere 17
> **Versión del Documento:** 2.0 (Completo) — Fecha: 2026-07-03

---

## 1. Análisis Comparativo: BD Transaccional (OLTP) vs. Data Warehouse (OLAP)

### 1.1 Tabla Comparativa Detallada

| Criterio                   | BD Transaccional (OLTP — SAP SQL Anywhere)                                                                                                    | Data Warehouse (OLAP — PostgreSQL EDW)                                                                                    |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **Propósito principal**    | Registro y gestión de operaciones diarias (ventas, compras, inventario). Orientado a la captura de transacciones individuales en tiempo real. | Consolidación histórica de múltiples fuentes para análisis, reportería de gestión y entrenamiento de Machine Learning.    |
| **Diseño del Esquema**     | Altamente normalizado (3FN/BCNF) para evitar redundancias y garantizar la consistencia relacional. 500+ tablas.                               | Desnormalizado (Modelo Dimensional — Constelación de Hechos). Minimiza cruzamientos (`JOINs`) para agilizar agrupaciones. |
| **Actualización de Datos** | Transaccional continua (OLTP). Alta frecuencia de escrituras unitarias e individuales.                                                        | Por lotes (ETL programado diario o incremental continuo) con control histórico e idempotencia.                            |
| **Pérdida de Historial**   | Sobrescritura de datos maestros (e.g. cambios en la dirección o límite de crédito de un cliente borran el valor previo).                      | Preservación del histórico utilizando Slowly Changing Dimensions (SCD Tipo 2) con marcas de vigencia temporal.            |
| **Índices y Estructura**   | Optimizado con índices transaccionales B-Tree simples sobre llaves naturales de negocio.                                                      | Índices compuestos, parciales de vigencia rápida (`es_vigente = TRUE`) e indexación sobre surrogate keys enteras.         |

### 1.2 Justificación Académica: Desacoplamiento Analítico

La ejecución de consultas analíticas directas sobre la base de datos de producción (OLTP) de SAP interrumpe la carga de trabajo transaccional. Las agregaciones espaciadas en el tiempo (como el cálculo anual de tendencias de stock o utilidades brutas) generan bloqueos que detienen las terminales de los puntos de venta. El desacoplamiento analítico mediante un Enterprise Data Warehouse (EDW) aislado garantiza:

1. **Rendimiento Operativo:** Cero competencia por recursos (I/O, CPU y bloqueo de registros) entre cajeros y analistas.
2. **Homogeneización Semántica:** Las dimensiones conformadas transforman la nomenclatura críptica de SAP (e.g. `codart`, `cospro`, `lispre`) en términos unificados amigables para el usuario de negocio.
3. **Consistencia Temporoeconómica:** El DW calcula y congela las métricas financieras (margen, IVA, subtotal neto, ICE) y de stock en la fecha exacta de su ocurrencia, aislando los resultados de posteriores modificaciones operativas.

---

## 2. Arquitectura de Constelación de Hechos (Multiestrella)

El diseño propuesto consolida la operación de la empresa multisucursal mediante **11 dimensiones** y **11 tablas de hechos** interconectadas. Este esquema permite el control integral de la empresa distribuido en 4 roles organizacionales:

- **Administrator:** Gestión de seguridad, control de accesos e integridad del flujo de carga (`Fact_Logs_Auditoria`, `Dim_Usuario`).
- **Gerencia:** Control financiero consolidado de tesorería, cuentas por cobrar, cuentas por pagar y rentabilidad integrada (`Fact_Cobros_CXC`, `Fact_Pagos_CXP`, `Fact_Movimientos_Caja`, `Fact_Nomina`, `Dim_FormaPago`).
- **Ventas:** Rendimiento comercial de sucursales, cumplimiento de presupuestos, efectividad de la fuerza de ventas e integraciones predictivas de ingresos (`Fact_Ventas_Detalle`, `Fact_Metas_Comerciales`, `Dim_Vendedor`, `Dim_Cliente`).
- **Bodega:** Trazabilidad física del inventario, flujos de entrada/salida (Kardex), valorización en tiempo real y optimización de cadena de suministro (`Fact_Movimientos_Inventario`, `Fact_Inventario_Snapshot`, `Fact_Compras`, `Fact_Devoluciones`, `Dim_Proveedor`, `Dim_Almacen`).

### 2.1 Mapa de la Constelación de Hechos

```
                Dim_Fecha (Compartida - Conformed Dimension)
                      ▲                       ▲
                      │                       │
         ┌────────────┴──────────┐ ┌──────────┴────────────┐
         │  Fact_Ventas_Detalle  │ │Fact_Mov_Inventario    │
         │───────────────────────│ │───────────────────────│
         │ - venta_sk       (PK) │ │ - movimiento_sk  (PK) │
         │ - producto_sk    (FK)─┼─┼─► producto_sk    (FK) │
         │ - sucursal_sk    (FK)─┼─┼─► sucursal_sk    (FK) │
         │ - cliente_sk     (FK) │ │ - almacen_sk     (FK) │
         │ - vendedor_sk    (FK) │ │                       │
         └───────────────────────┘ └───────────────────────┘
                      ▲                       ▲
                      │                       │
                Dim_Producto  (Compartida)    Dim_Sucursal (Compartida)
```

---

## 3. Catálogo de Dimensiones (Dimensions)

### 3.1 Dim_Fecha

- **Propósito:** Dimensión conformada temporal para agregaciones analíticas cronológicas rápidas.
- **Atributos:** `fecha_sk` (PK), `fecha_completa` (Date, Unique), `anio` (Smallint), `trimestre` (Smallint), `mes` (Smallint), `nombre_mes` (Varchar), `semana_anio` (Smallint), `dia_mes` (Smallint), `dia_semana` (Smallint), `nombre_dia` (Varchar), `es_fin_semana` (Boolean), `es_feriado` (Boolean), `semestre` (Smallint), `periodo_fiscal` (Varchar).

### 3.2 Dim_Producto (SCD Tipo 2)

- **Propósito:** Almacena la jerarquía y estado de los artículos.
- **Atributos:** `producto_sk` (PK), `codemp` (Varchar), `codart` (Varchar), `nombre_articulo` (Varchar), `clase` (Varchar), `nombre_clase` (Varchar), `subclase` (Varchar), `nombre_subclase` (Varchar), `unidad` (Varchar), `nombre_unidad` (Varchar), `precio_oficial` (Numeric), `costo_promedio` (Numeric), `estado` (Varchar), `es_servicio` (Boolean), `fecha_inicio_vigencia` (Date), `fecha_fin_vigencia` (Date), `es_vigente` (Boolean).

### 3.3 Dim_Sucursal

- **Propósito:** Modelar los establecimientos de venta físicos/digitales.
- **Atributos:** `sucursal_sk` (PK), `codemp` (Varchar), `establ` (Varchar), `codigo_sucursal` (Varchar, Unique), `nombre_sucursal` (Varchar), `direccion` (Varchar), `telefono` (Varchar), `activa` (Boolean).

### 3.4 Dim_Cliente (SCD Tipo 2)

- **Propósito:** Datos demográficos e históricos de los clientes.
- **Atributos:** `cliente_sk` (PK), `codcli` (Varchar), `codemp` (Varchar), `nombre_cliente` (Varchar), `ruc_cedula` (Varchar), `tipo_id` (Varchar), `clase_cliente` (Varchar), `nombre_clase` (Varchar), `zona` (Varchar), `nombre_zona` (Varchar), `ciudad` (Varchar), `limite_credito` (Numeric), `dias_credito` (Integer), `estado` (Varchar), `sexo` (Char), `fecha_inicio_vigencia` (Date), `fecha_fin_vigencia` (Date), `es_vigente` (Boolean).

### 3.5 Dim_Proveedor

- **Propósito:** Identidad de los proveedores para abastecimiento.
- **Atributos:** `proveedor_sk` (PK), `codpro` (Varchar), `codemp` (Varchar), `nombre_proveedor` (Varchar), `ruc` (Varchar), `ciudad` (Varchar), `dias_credito` (Integer), `estado` (Varchar).

### 3.6 Dim_Vendedor

- **Propósito:** Fuerza de venta encargada de facturación.
- **Atributos:** `vendedor_sk` (PK), `codven` (Varchar), `codemp` (Varchar), `nombre_vendedor` (Varchar), `comision` (Numeric), `activo` (Boolean).

### 3.7 Dim_Empleado

- **Propósito:** Nómina y personal de operaciones.
- **Atributos:** `empleado_sk` (PK), `codemp` (Varchar), `codemple` (Varchar), `nombre_empleado` (Varchar), `cedula` (Varchar), `cargo` (Varchar), `departamento` (Varchar), `sueldo_base` (Numeric), `fecha_ingreso` (Date), `activo` (Boolean).

### 3.8 Dim_Usuario

- **Propósito:** Control e identidad en los logs de auditoría.
- **Atributos:** `usuario_sk` (PK), `codusu` (Varchar), `codemp` (Varchar), `nombre_usuario` (Varchar), `rol` (Varchar), `estado` (Varchar).

### 3.9 Dim_FormaPago

- **Propósito:** Medios de cobro y pago de transacciones.
- **Atributos:** `formapago_sk` (PK), `codforpag` (Varchar), `codemp` (Varchar), `nombre_forma_pago` (Varchar), `dias_plazo` (Integer).

### 3.10 Dim_Geografia

- **Propósito:** Desnormalización espacial para mapas de ventas y despacho.
- **Atributos:** `geografia_sk` (PK), `pais` (Varchar), `provincia` (Varchar), `canton` (Varchar), `parroquia` (Varchar).

### 3.11 Dim_Almacen

- **Propósito:** Bodegas físicas mapeadas dentro de cada sucursal.
- **Atributos:** `almacen_sk` (PK), `codalm` (Varchar), `codemp` (Varchar), `nombre_almacen` (Varchar), `establ` (Varchar).

---

## 4. Catálogo de Tablas de Hechos (Facts)

### 4.1 Fact_Ventas_Detalle

- **Granularidad:** Detalle por renglón/línea de cada factura.
- **Vinculación:** `fecha_sk`, `producto_sk`, `cliente_sk`, `sucursal_sk`, `vendedor_sk`, `formapago_sk`.
- **Métricas:** `cantidad` (Aditiva), `precio_unitario` (No aditiva), `costo_unitario` (No aditiva), `subtotal_bruto` (Aditiva), `valor_descuento` (Aditiva), `subtotal_neto` (Aditiva), `valor_iva` (Aditiva), `total_linea` (Aditiva), `costo_total` (Aditiva), `margen_bruto` (Aditiva), `pct_margen` (No aditiva).

### 4.2 Fact_Inventario_Snapshot

- **Granularidad:** Balance de stock al final del día por artículo/establecimiento/almacén.
- **Vinculación:** `fecha_sk`, `producto_sk`, `sucursal_sk`, `almacen_sk`.
- **Métricas:** `stock_actual` (Semi-aditiva), `costo_promedio` (No aditiva), `valor_inventario` (Semi-aditiva), `stock_minimo` (No aditiva), `stock_maximo` (No aditiva), `punto_reorden` (No aditiva), `alerta_desabastecimiento` (Boolean), `alerta_sobrestock` (Boolean).

### 4.3 Fact_Movimientos_Inventario

- **Granularidad:** Entrada/salida unitaria del Kardex físico.
- **Vinculación:** `fecha_sk`, `producto_sk`, `sucursal_sk`, `almacen_sk`.
- **Métricas:** `cantidad_movimiento` (Aditiva), `costo_unitario` (No aditiva), `costo_total` (Aditiva), `valor_venta` (Aditiva).

### 4.4 Fact_Compras

- **Granularidad:** Detalle por renglón de facturas de compra a proveedores.
- **Vinculación:** `fecha_sk`, `producto_sk`, `proveedor_sk`, `sucursal_sk`, `almacen_sk`.
- **Métricas:** `cantidad` (Aditiva), `costo_unitario` (No aditiva), `costo_linea` (Aditiva), `descuento_valor` (Aditiva), `total_factura` (Aditiva).

### 4.5 Fact_Cobros_CXC

- **Granularidad:** Cuotas o cobros individuales aplicados sobre cartera de clientes.
- **Vinculación:** `fecha_sk`, `cliente_sk`, `vendedor_sk`, `sucursal_sk`, `formapago_sk`.
- **Métricas:** `valor_cobrado` (Aditiva), `saldo_documento` (Semi-aditiva), `dias_vencimiento` (No aditiva), `esta_vencido` (Boolean).

### 4.6 Fact_Pagos_CXP

- **Granularidad:** Control de egresos y facturas pendientes de pago a proveedores.
- **Vinculación:** `fecha_sk`, `proveedor_sk`, `sucursal_sk`, `formapago_sk`.
- **Métricas:** `valor_pagado` (Aditiva), `saldo_pendiente` (Semi-aditiva), `dias_vencimiento` (No aditiva).

### 4.7 Fact_Nomina

- **Granularidad:** Pagos mensuales/quincenales detallando rubros por empleado.
- **Vinculación:** `fecha_sk`, `empleado_sk`, `sucursal_sk`.
- **Métricas:** `ingreso_sueldo` (Aditiva), `horas_extras_valor` (Aditiva), `comisiones_valor` (Aditiva), `descuento_seguro` (Aditiva), `liquido_a_recibir` (Aditiva).

### 4.8 Fact_Movimientos_Caja

- **Granularidad:** Movimientos de flujo en efectivo o equivalentes por caja de sucursal.
- **Vinculación:** `fecha_sk`, `usuario_sk`, `sucursal_sk`, `formapago_sk`.
- **Métricas:** `monto_apertura` (Semi-aditiva), `monto_ingreso` (Aditiva), `monto_egreso` (Aditiva), `monto_cierre` (Semi-aditiva), `diferencia_arqueo` (Aditiva).

### 4.9 Fact_Metas_Comerciales

- **Granularidad:** Presupuesto de ventas asignado a una dimensión de tiempo y espacio.
- **Vinculación:** `fecha_sk`, `vendedor_sk`, `sucursal_sk`, `producto_sk`.
- **Métricas:** `monto_meta` (Aditiva), `unidades_meta` (Aditiva).

### 4.10 Fact_Logs_Auditoria

- **Granularidad:** Log consolidado de modificaciones críticas relativas a transacciones.
- **Vinculación:** `fecha_sk`, `usuario_sk`, `sucursal_sk`.
- **Métricas:** `cantidad_alterada` (Aditiva), `valor_anterior` (No aditiva), `valor_nuevo` (No aditiva).

### 4.11 Fact_Devoluciones

- **Granularidad:** Devoluciones de mercadería aplicadas por clientes e ingresadas al stock.
- **Vinculación:** `fecha_sk`, `producto_sk`, `cliente_sk`, `sucursal_sk`, `almacen_sk`.
- **Métricas:** `cantidad_devuelta` (Aditiva), `total_linea_devolucion` (Aditiva), `costo_total_devolucion` (Aditiva).

---

## 5. Scripts DDL en SQL (PostgreSQL 16)

A continuación se presenta el DDL unificado y completo para desplegar la Constelación de Hechos en PostgreSQL dentro del esquema `edw`.

### 5.1 Definición de Esquema y Rol Base

```sql
CREATE SCHEMA IF NOT EXISTS edw;

-- Asegurar rol de visualización analítica
DO $$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'bi_readonly') THEN
      CREATE ROLE bi_readonly LOGIN PASSWORD 'CHANGE_ME_READONLY';
   END IF;
END $$;

GRANT CONNECT ON DATABASE edw TO bi_readonly;
GRANT USAGE ON SCHEMA edw TO bi_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA edw GRANT SELECT ON TABLES TO bi_readonly;
```

### 5.2 Estructura de Dimensiones

```sql
-- ── 1. DIM_FECHA ──
CREATE TABLE edw.Dim_Fecha (
    fecha_sk        SERIAL PRIMARY KEY,
    fecha_completa  DATE NOT NULL UNIQUE,
    anio            SMALLINT NOT NULL,
    trimestre       SMALLINT NOT NULL CHECK (trimestre BETWEEN 1 AND 4),
    mes             SMALLINT NOT NULL CHECK (mes BETWEEN 1 AND 12),
    nombre_mes      VARCHAR(15) NOT NULL,
    semana_anio     SMALLINT NOT NULL,
    dia_mes         SMALLINT NOT NULL,
    dia_semana      SMALLINT NOT NULL CHECK (dia_semana BETWEEN 1 AND 7),
    nombre_dia      VARCHAR(15) NOT NULL,
    es_fin_semana   BOOLEAN NOT NULL DEFAULT FALSE,
    es_feriado      BOOLEAN NOT NULL DEFAULT FALSE,
    semestre        SMALLINT NOT NULL CHECK (semestre BETWEEN 1 AND 2),
    periodo_fiscal  VARCHAR(10)
);

-- ── 2. DIM_SUCURSAL ──
CREATE TABLE edw.Dim_Sucursal (
    sucursal_sk     SERIAL PRIMARY KEY,
    codemp          VARCHAR(2) NOT NULL,
    establ          VARCHAR(3) NOT NULL,
    codigo_sucursal VARCHAR(5) NOT NULL UNIQUE,
    nombre_sucursal VARCHAR(100),
    direccion       VARCHAR(200),
    telefono        VARCHAR(14),
    activa          BOOLEAN DEFAULT TRUE,
    fecha_carga     TIMESTAMP DEFAULT NOW()
);

-- ── 3. DIM_ALMACEN ──
CREATE TABLE edw.Dim_Almacen (
    almacen_sk      SERIAL PRIMARY KEY,
    codemp          VARCHAR(2) NOT NULL,
    codalm          VARCHAR(10) NOT NULL,
    nombre_almacen  VARCHAR(100),
    establ          VARCHAR(3) NOT NULL,
    UNIQUE (codemp, codalm)
);

-- ── 4. DIM_PRODUCTO ──
CREATE TABLE edw.Dim_Producto (
    producto_sk     SERIAL PRIMARY KEY,
    codemp          VARCHAR(2) NOT NULL,
    codart          VARCHAR(20) NOT NULL,
    nombre_articulo VARCHAR(300),
    clase           VARCHAR(5),
    nombre_clase    VARCHAR(100),
    subclase        VARCHAR(5),
    nombre_subclase VARCHAR(100),
    unidad          VARCHAR(3),
    nombre_unidad   VARCHAR(60),
    precio_oficial  NUMERIC(15,4),
    costo_promedio  NUMERIC(15,4),
    estado          VARCHAR(1),
    es_servicio     BOOLEAN DEFAULT FALSE,
    fecha_inicio_vigencia DATE NOT NULL DEFAULT CURRENT_DATE,
    fecha_fin_vigencia    DATE,
    es_vigente      BOOLEAN DEFAULT TRUE,
    fecha_carga     TIMESTAMP DEFAULT NOW()
);

-- ── 5. DIM_CLIENTE ──
CREATE TABLE edw.Dim_Cliente (
    cliente_sk      SERIAL PRIMARY KEY,
    codcli          VARCHAR(20) NOT NULL,
    codemp          VARCHAR(2) NOT NULL,
    nombre_cliente  VARCHAR(200),
    ruc_cedula      VARCHAR(13),
    tipo_id         VARCHAR(2),
    clase_cliente   VARCHAR(5),
    nombre_clase    VARCHAR(100),
    zona            VARCHAR(8),
    nombre_zona     VARCHAR(60),
    ciudad          VARCHAR(30),
    limite_credito  NUMERIC(15,4),
    dias_credito    INTEGER,
    estado          VARCHAR(1),
    sexo            CHAR(1),
    fecha_inicio_vigencia DATE NOT NULL DEFAULT CURRENT_DATE,
    fecha_fin_vigencia    DATE,
    es_vigente      BOOLEAN DEFAULT TRUE,
    fecha_carga     TIMESTAMP DEFAULT NOW()
);

-- ── 6. DIM_PROVEEDOR ──
CREATE TABLE edw.Dim_Proveedor (
    proveedor_sk    SERIAL PRIMARY KEY,
    codemp          VARCHAR(2) NOT NULL,
    codpro          VARCHAR(20) NOT NULL,
    nombre_proveedor VARCHAR(200),
    ruc             VARCHAR(13),
    ciudad          VARCHAR(30),
    dias_credito    INTEGER,
    estado          VARCHAR(1),
    fecha_carga     TIMESTAMP DEFAULT NOW(),
    UNIQUE (codemp, codpro)
);

-- ── 7. DIM_VENDEDOR ──
CREATE TABLE edw.Dim_Vendedor (
    vendedor_sk     SERIAL PRIMARY KEY,
    codemp          VARCHAR(2) NOT NULL,
    codven          VARCHAR(10) NOT NULL,
    nombre_vendedor VARCHAR(120),
    comision        NUMERIC(5,2),
    activo          BOOLEAN DEFAULT TRUE,
    UNIQUE (codemp, codven)
);

-- ── 8. DIM_EMPLEADO ──
CREATE TABLE edw.Dim_Empleado (
    empleado_sk     SERIAL PRIMARY KEY,
    codemp          VARCHAR(2) NOT NULL,
    codemple        VARCHAR(15) NOT NULL,
    nombre_empleado VARCHAR(250),
    cedula          VARCHAR(10) UNIQUE,
    cargo           VARCHAR(80),
    departamento    VARCHAR(80),
    sueldo_base     NUMERIC(15,4),
    fecha_ingreso   DATE,
    activo          BOOLEAN DEFAULT TRUE,
    UNIQUE (codemp, codemple)
);

-- ── 9. DIM_USUARIO ──
CREATE TABLE edw.Dim_Usuario (
    usuario_sk      SERIAL PRIMARY KEY,
    codemp          VARCHAR(2) NOT NULL,
    codusu          VARCHAR(15) NOT NULL,
    nombre_usuario  VARCHAR(150),
    rol             VARCHAR(50),
    estado          VARCHAR(1) DEFAULT 'A',
    UNIQUE (codemp, codusu)
);

-- ── 10. DIM_FORMAPAGO ──
CREATE TABLE edw.Dim_FormaPago (
    formapago_sk     SERIAL PRIMARY KEY,
    codemp           VARCHAR(2) NOT NULL,
    codforpag        VARCHAR(10) NOT NULL,
    nombre_forma_pago VARCHAR(100),
    dias_plazo       INTEGER DEFAULT 0,
    UNIQUE (codemp, codforpag)
);

-- ── 11. DIM_GEOGRAFIA ──
CREATE TABLE edw.Dim_Geografia (
    geografia_sk    SERIAL PRIMARY KEY,
    pais            VARCHAR(60) NOT NULL,
    provincia       VARCHAR(60),
    canton          VARCHAR(60),
    parroquia       VARCHAR(60)
);
```

### 5.3 Estructura de Hechos

```sql
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

-- ── 11. FACT_DEVOLUCIONES ──
CREATE TABLE edw.Fact_Devoluciones (
    devolucion_sk       BIGSERIAL PRIMARY KEY,
    fecha_sk            INT NOT NULL REFERENCES edw.Dim_Fecha(fecha_sk),
    producto_sk         INT NOT NULL REFERENCES edw.Dim_Producto(producto_sk),
    cliente_sk          INT NOT NULL REFERENCES edw.Dim_Cliente(cliente_sk),
    sucursal_sk         INT NOT NULL REFERENCES edw.Dim_Sucursal(sucursal_sk),
    almacen_sk          INT NOT NULL REFERENCES edw.Dim_Almacen(almacen_sk),
    num_nota_credito    VARCHAR(50) NOT NULL,
    cantidad_devuelta   NUMERIC(15,4) NOT NULL,
    total_linea_devolucion NUMERIC(15,4) NOT NULL,
    costo_total_devolucion NUMERIC(15,4) NOT NULL,
    fecha_carga         TIMESTAMP DEFAULT NOW()
);
```

### 5.4 Estructuras de Indexación

```sql
-- Índices para Optimización de Cruzamiento de Dimensiones de Hechos (Fact_Ventas_Detalle)
CREATE INDEX idx_fvd_fecha      ON edw.Fact_Ventas_Detalle (fecha_sk);
CREATE INDEX idx_fvd_prod       ON edw.Fact_Ventas_Detalle (producto_sk);
CREATE INDEX idx_fvd_cli        ON edw.Fact_Ventas_Detalle (cliente_sk);
CREATE INDEX idx_fvd_suc        ON edw.Fact_Ventas_Detalle (sucursal_sk);
CREATE INDEX idx_fvd_ven        ON edw.Fact_Ventas_Detalle (vendedor_sk);
CREATE INDEX idx_fvd_multikey   ON edw.Fact_Ventas_Detalle (fecha_sk, sucursal_sk, producto_sk);

-- Índices sobre snapshots y movimientos financieros
CREATE INDEX idx_fis_composite  ON edw.Fact_Inventario_Snapshot (fecha_sk, sucursal_sk, almacen_sk);
CREATE INDEX idx_fmi_composite  ON edw.Fact_Movimientos_Inventario (fecha_sk, sucursal_sk, almacen_sk);
CREATE INDEX idx_fla_userlog    ON edw.Fact_Logs_Auditoria (fecha_sk, usuario_sk);

-- Índices de SCD Tipo 2
CREATE INDEX idx_dp_vigente     ON edw.Dim_Producto (codart) WHERE es_vigente = TRUE;
CREATE INDEX idx_dc_vigente     ON edw.Dim_Cliente (codcli) WHERE es_vigente = TRUE;
```

---

## 6. Soporte Analítico y Modelado Predictivo (ML & MLOps)

La arquitectura de la base de datos se integra de forma directa con los pipelines de ciencia de datos mediante las siguientes características estructurales:

### 6.1 Predicción del Margen y Ventas por Renglón (XGBoost y Feature Engineering)

- **Atributo `pct_margen` precalculado:** Al almacenar de forma aditiva el costo y la utilidad por línea en `Fact_Ventas_Detalle`, los algoritmos de regresión evitan fases redundantes de agregación en memoria (Pandas).
- **Indexación Compuesta Clave:** El índice `idx_fvd_multikey` permite escaneos por rangos de tiempo acelerados para extraer matrices temporales para series de tiempo.

### 6.2 Detección de Anomalías Operativas (Clustering K-Means / Auditoría)

- **Consolidación `Fact_Logs_Auditoria`:** Mapea directamente el comportamiento de los operadores con las diferencias reportadas en `Fact_Movimientos_Caja`, permitiendo modelos de clasificación de desviaciones o riesgos en tiempo de ejecución.

### 6.3 Reposición Inteligente de Abastecimiento (Algoritmos de Clasificación)

- **Alertas booleanas binarias:** Las banderas `alerta_desabastecimiento` y `alerta_sobrestock` en `Fact_Inventario_Snapshot` actúan como etiquetas inmediatas (_labels_) para entrenar clasificadores encargados de predecir puntos de reorden óptimos.
