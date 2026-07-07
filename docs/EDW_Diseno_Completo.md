# Plataforma Inteligente de Analítica Empresarial y Predicción de Ventas

## Diseño Completo del Enterprise Data Warehouse (EDW)

### Arquitectura: Constelación de Hechos — SAP SQL Anywhere → PostgreSQL

---

# 1. DISEÑO DE LA CONSTELACIÓN DE HECHOS (MAPEO COMPLETO)

## 1.1 Visión General de la Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                  CONSTELACIÓN DE HECHOS                      │
│                                                             │
│  Fact_Ventas_Detalle ──────────────────────────────────────┐│
│  Fact_Devoluciones ──────────────┐                         ││
│  Fact_Compras ───────────────────┤                         ││
│  Fact_Movimientos_Inventario ────┤    Dim_Tiempo           ││
│  Fact_Inventario_Snapshot ───────┤    Dim_Producto         ││
│  Fact_Cobros_CXC ────────────────┤    Dim_Cliente          ││
│  Fact_Pagos_CXP ─────────────────┤    Dim_Vendedor         ││
│  Fact_Metas_Comerciales ─────────┤    Dim_Sucursal         ││
│  Fact_Movimientos_Caja ──────────┤    Dim_Proveedor        ││
│  Fact_Logs_Auditoria ────────────┘    Dim_Categoria        ││
│  Fact_Nomina                          Dim_Almacen          ││
│                                       Dim_Empleado         ││
│                                       Dim_FormaPago        ││
│                                       Dim_Geografia        ││
│                                       Dim_Usuario          ││
└─────────────────────────────────────────────────────────────┘
```

---

## 1.2 DIMENSIONES

### DIM_TIEMPO

**Propósito:** Eje temporal para todos los hechos. Generada algorítmicamente.

```sql
CREATE TABLE edw.Dim_Tiempo (
    tiempo_sk       SERIAL PRIMARY KEY,               -- SK surrogate
    fecha_completa  DATE NOT NULL UNIQUE,
    anio            SMALLINT NOT NULL,
    trimestre       SMALLINT NOT NULL,                -- 1-4
    mes             SMALLINT NOT NULL,                -- 1-12
    nombre_mes      VARCHAR(15) NOT NULL,
    semana_anio     SMALLINT NOT NULL,
    dia_mes         SMALLINT NOT NULL,
    dia_semana      SMALLINT NOT NULL,                -- 1=Lun..7=Dom
    nombre_dia      VARCHAR(15) NOT NULL,
    es_fin_semana   BOOLEAN NOT NULL DEFAULT FALSE,
    es_feriado      BOOLEAN NOT NULL DEFAULT FALSE,
    semestre        SMALLINT NOT NULL,                -- 1-2
    periodo_fiscal  VARCHAR(10)                       -- Ej: '2024-Q1'
);
```

**Tablas Origen:** Ninguna (generación algorítmica Python).

---

### DIM_SUCURSAL

**Propósito:** Cada establecimiento/punto de venta de la empresa.

```sql
CREATE TABLE edw.Dim_Sucursal (
    sucursal_sk     SERIAL PRIMARY KEY,
    codemp          VARCHAR(2) NOT NULL,
    establ          VARCHAR(3) NOT NULL,
    codigo_sucursal VARCHAR(5) NOT NULL UNIQUE,       -- codemp+establ
    nombre_sucursal VARCHAR(100),
    direccion       VARCHAR(200),
    telefono        VARCHAR(14),
    eslogan         VARCHAR(200),
    activa          BOOLEAN DEFAULT TRUE,
    fecha_carga     TIMESTAMP DEFAULT NOW()
);
```

**Tablas Origen:** `establecimientos` (establ, nomest, direc, telf, eslogan), `empresa` (codemp, nomemp).

---

### DIM_CLIENTE

**Propósito:** Todos los clientes del sistema con atributos de segmentación.

```sql
CREATE TABLE edw.Dim_Cliente (
    cliente_sk      SERIAL PRIMARY KEY,
    codcli          VARCHAR(20) NOT NULL,
    codemp          VARCHAR(2) NOT NULL,
    nombre_cliente  VARCHAR(200),
    ruc_cedula      VARCHAR(13),
    tipo_id         VARCHAR(2),                       -- RUC, CI, PASAP
    clase_cliente   VARCHAR(5),
    nombre_clase    VARCHAR(100),
    zona            VARCHAR(8),
    nombre_zona     VARCHAR(60),
    ciudad          VARCHAR(30),
    direccion       VARCHAR(200),
    telefono        VARCHAR(20),
    email           VARCHAR(200),
    limite_credito  NUMERIC(15,4),
    dias_credito    INTEGER,
    lista_precio    VARCHAR(2),
    vendedor_asig   VARCHAR(5),
    cobrador_asig   VARCHAR(5),
    estado          VARCHAR(1),                       -- A=Activo, I=Inactivo
    sexo            CHAR(1),
    fecha_nacimiento DATE,
    parte_relacionada CHAR(2),
    fecha_registro  DATE,
    -- SCD Tipo 2
    fecha_inicio_vigencia DATE NOT NULL DEFAULT CURRENT_DATE,
    fecha_fin_vigencia    DATE,
    es_vigente      BOOLEAN DEFAULT TRUE,
    fecha_carga     TIMESTAMP DEFAULT NOW()
);
```

**Tablas Origen:** `clientes` (codcli, nomcli, rucced, tiprucced, codcla, codzona, ciucli, dircli, telcli, mail, limcre, dias, lispre, codven, codcob, estado, sexo, fecnac, parterel), `clasesclientes` (nomcla), `zona` (nomzon).

---

### DIM_PRODUCTO

**Propósito:** Catálogo completo de artículos con jerarquía de categorías.

```sql
CREATE TABLE edw.Dim_Producto (
    producto_sk     SERIAL PRIMARY KEY,
    codemp          VARCHAR(2) NOT NULL,
    codart          VARCHAR(20) NOT NULL,
    nombre_articulo VARCHAR(300),
    codigo_alterno  VARCHAR(20),
    codigo_barra    VARCHAR(50),
    clase           VARCHAR(5),
    nombre_clase    VARCHAR(100),
    subclase        VARCHAR(5),
    nombre_subclase VARCHAR(100),
    unidad          VARCHAR(3),
    nombre_unidad   VARCHAR(60),
    aplica_iva      VARCHAR(1),
    porcentaje_iva  NUMERIC(5,2),
    precio_oficial  NUMERIC(15,4),
    precio_1        NUMERIC(18,6),
    precio_2        NUMERIC(18,6),
    precio_3        NUMERIC(18,6),
    precio_4        NUMERIC(18,6),
    costo_promedio  NUMERIC(15,4),
    peso            NUMERIC(12,4),
    es_servicio     BOOLEAN DEFAULT FALSE,
    es_produccion   BOOLEAN DEFAULT FALSE,
    aplica_ice      BOOLEAN DEFAULT FALSE,
    estado          VARCHAR(1),
    proveedor_habitual VARCHAR(30),
    -- SCD Tipo 2
    fecha_inicio_vigencia DATE NOT NULL DEFAULT CURRENT_DATE,
    fecha_fin_vigencia    DATE,
    es_vigente      BOOLEAN DEFAULT TRUE,
    fecha_carga     TIMESTAMP DEFAULT NOW()
);
```

**Tablas Origen:** `articulos` (codart, nomart, codalt, codcla, subcodcla, coduni, codiva, prec01..04, cospro, ultcos, peso, estado, produ, codice), `clasesarticulos` (nomcla), `subclasesarticulos` (nomsubcla), `unidades` (nomuni), `iva` (poriva).

---

### DIM_CATEGORIA (Jerarquía de Productos)

```sql
CREATE TABLE edw.Dim_Categoria (
    categoria_sk    SERIAL PRIMARY KEY,
    codemp          VARCHAR(2),
    codcla          VARCHAR(5) NOT NULL,
    nombre_clase    VARCHAR(100),
    subcodcla       VARCHAR(5),
    nombre_subclase VARCHAR(100),
    cuenta_contable VARCHAR(20),
    utilidad_esperada NUMERIC(15,4),
    fecha_carga     TIMESTAMP DEFAULT NOW()
);
```

**Tablas Origen:** `clasesarticulos`, `subclasesarticulos`.

---

### DIM_VENDEDOR

**Propósito:** Vendedores y cobradores para análisis de desempeño comercial.

```sql
CREATE TABLE edw.Dim_Vendedor (
    vendedor_sk     SERIAL PRIMARY KEY,
    codemp          VARCHAR(2),
    codven          VARCHAR(5) NOT NULL UNIQUE,
    nombre_vendedor VARCHAR(200),
    tipo            VARCHAR(1),                       -- V=Vendedor, C=Cobrador
    zona_asignada   VARCHAR(8),
    sucursal_asig   VARCHAR(3),
    comision_pct    NUMERIC(5,2),
    activo          BOOLEAN DEFAULT TRUE,
    fecha_carga     TIMESTAMP DEFAULT NOW()
);
```

**Tablas Origen:** `vendedorescob` (codven, nomven, codzon, establ, comision, activo).

---

### DIM_PROVEEDOR

```sql
CREATE TABLE edw.Dim_Proveedor (
    proveedor_sk    SERIAL PRIMARY KEY,
    codemp          VARCHAR(2),
    codpro          VARCHAR(8) NOT NULL,
    nombre_proveedor VARCHAR(200),
    ruc             VARCHAR(15),
    tipo_id         VARCHAR(2),
    clase           VARCHAR(5),
    nombre_clase    VARCHAR(100),
    ciudad          VARCHAR(60),
    pais            VARCHAR(5),
    direccion       VARCHAR(200),
    telefono        VARCHAR(20),
    email           VARCHAR(100),
    activo          BOOLEAN DEFAULT TRUE,
    fecha_carga     TIMESTAMP DEFAULT NOW()
);
```

**Tablas Origen:** `proveedores` (codpro, nompro, rucced, tiprucced, codcla, ciudad, dircli, telcli, mail), `clasesproveedores` (nomcla).

---

### DIM_ALMACEN

```sql
CREATE TABLE edw.Dim_Almacen (
    almacen_sk      SERIAL PRIMARY KEY,
    codemp          VARCHAR(2),
    codalm          VARCHAR(2) NOT NULL,
    nombre_almacen  VARCHAR(100),
    codigo_sucursal VARCHAR(3),
    inventariable   BOOLEAN DEFAULT TRUE,
    cuenta_contable VARCHAR(20),
    fecha_carga     TIMESTAMP DEFAULT NOW()
);
```

**Tablas Origen:** `almacenes` (codalm, nomalm, inv, codcta, establ).

---

### DIM_EMPLEADO (Nómina / Recursos Humanos)

```sql
CREATE TABLE edw.Dim_Empleado (
    empleado_sk     SERIAL PRIMARY KEY,
    codemp          VARCHAR(2),
    codemp_nom      VARCHAR(10) NOT NULL,
    cedula          VARCHAR(13),
    nombre_empleado VARCHAR(200),
    cargo           VARCHAR(5),
    nombre_cargo    VARCHAR(100),
    departamento    VARCHAR(5),
    nombre_depto    VARCHAR(100),
    fecha_ingreso   DATE,
    fecha_salida    DATE,
    sueldo_base     NUMERIC(15,4),
    activo          BOOLEAN DEFAULT TRUE,
    fecha_carga     TIMESTAMP DEFAULT NOW()
);
```

**Tablas Origen:** `nom_empleados` (cedula, nombre, codcargo, coddept, fecing, fecsali, sueldo), `nom_cargos` (nomcargo), `nom_departamentos` (nomdept).

---

### DIM_FORMA_PAGO

```sql
CREATE TABLE edw.Dim_FormaPago (
    formapago_sk    SERIAL PRIMARY KEY,
    codforpag       VARCHAR(2) NOT NULL,
    descripcion     VARCHAR(60),
    tipo            VARCHAR(20),                      -- Efectivo, Cheque, Tarjeta, Crédito
    fecha_carga     TIMESTAMP DEFAULT NOW()
);
```

**Tablas Origen:** `tipo_formapago_cxc`, catálogos internos deducidos de `encabezadofacturas`.

---

### DIM_GEOGRAFIA

```sql
CREATE TABLE edw.Dim_Geografia (
    geografia_sk    SERIAL PRIMARY KEY,
    codprovincia    VARCHAR(5),
    nombre_provincia VARCHAR(60),
    codciudad       VARCHAR(5),
    nombre_ciudad   VARCHAR(60),
    codemp          VARCHAR(2),
    fecha_carga     TIMESTAMP DEFAULT NOW()
);
```

**Tablas Origen:** `provincia`, `ciudad` (codciu, nomciu, codprovin).

---

### DIM_USUARIO (Control de Acceso — Administrador)

```sql
CREATE TABLE edw.Dim_Usuario (
    usuario_sk      SERIAL PRIMARY KEY,
    codusu          VARCHAR(10) NOT NULL UNIQUE,
    nombre_usuario  VARCHAR(100),
    tipo_usuario    VARCHAR(1),
    rol             VARCHAR(50),
    modulos_acceso  TEXT,
    activo          BOOLEAN DEFAULT TRUE,
    fecha_carga     TIMESTAMP DEFAULT NOW()
);
```

**Tablas Origen:** `usuarios` (codusu, nomusu, tipusu), `roles`, `usuarios_roles`, `accesosmodulos`.

---

## 1.3 TABLAS DE HECHOS

### FACT_VENTAS_DETALLE

**Propósito:** Granularidad por línea de factura. Motor central del análisis de ventas, rentabilidad y ML.

```sql
CREATE TABLE edw.Fact_Ventas_Detalle (
    venta_sk            BIGSERIAL PRIMARY KEY,
    -- FKs Dimensiones
    tiempo_sk           INT NOT NULL REFERENCES edw.Dim_Tiempo(tiempo_sk),
    producto_sk         INT NOT NULL REFERENCES edw.Dim_Producto(producto_sk),
    cliente_sk          INT NOT NULL REFERENCES edw.Dim_Cliente(cliente_sk),
    vendedor_sk         INT NOT NULL REFERENCES edw.Dim_Vendedor(vendedor_sk),
    sucursal_sk         INT NOT NULL REFERENCES edw.Dim_Sucursal(sucursal_sk),
    almacen_sk          INT NOT NULL REFERENCES edw.Dim_Almacen(almacen_sk),
    formapago_sk        INT REFERENCES edw.Dim_FormaPago(formapago_sk),
    -- Claves de negocio (para trazabilidad)
    num_factura         VARCHAR(10) NOT NULL,
    num_renglon         NUMERIC(20,0),
    tipo_documento      VARCHAR(5),                   -- FAC, NV, PRO
    -- Métricas aditivas
    cantidad            NUMERIC(15,4),
    precio_unitario     NUMERIC(18,6),
    costo_unitario      NUMERIC(15,4),
    descuento_pct       NUMERIC(5,2),
    valor_descuento     NUMERIC(15,4),
    subtotal_neto       NUMERIC(15,4),
    base_iva            NUMERIC(15,4),
    valor_iva           NUMERIC(15,4),
    valor_ice           NUMERIC(15,4),
    total_linea         NUMERIC(15,4),
    costo_total         NUMERIC(15,4),
    margen_bruto        NUMERIC(15,4),
    -- Métricas calculadas/enriquecidas
    pct_margen          NUMERIC(8,4),
    es_devolucion       BOOLEAN DEFAULT FALSE,
    estado_factura      VARCHAR(1),
    fecha_carga         TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_fvd_tiempo    ON edw.Fact_Ventas_Detalle(tiempo_sk);
CREATE INDEX idx_fvd_producto  ON edw.Fact_Ventas_Detalle(producto_sk);
CREATE INDEX idx_fvd_cliente   ON edw.Fact_Ventas_Detalle(cliente_sk);
CREATE INDEX idx_fvd_vendedor  ON edw.Fact_Ventas_Detalle(vendedor_sk);
CREATE INDEX idx_fvd_sucursal  ON edw.Fact_Ventas_Detalle(sucursal_sk);
```

**Tablas Origen (SAP):**

- `encabezadofacturas`: numfac, codven, codalm, codcli, fecfac, lispre, totnet, totiva, totfac, estado, establ, formapago, codcajero
- `renglonesfacturas`: numfac, codart, cantid, preuni, descue, subcos, totali, cosuni

---

### FACT_DEVOLUCIONES

```sql
CREATE TABLE edw.Fact_Devoluciones (
    devolucion_sk       BIGSERIAL PRIMARY KEY,
    tiempo_sk           INT NOT NULL REFERENCES edw.Dim_Tiempo(tiempo_sk),
    producto_sk         INT NOT NULL REFERENCES edw.Dim_Producto(producto_sk),
    cliente_sk          INT NOT NULL REFERENCES edw.Dim_Cliente(cliente_sk),
    vendedor_sk         INT REFERENCES edw.Dim_Vendedor(vendedor_sk),
    sucursal_sk         INT NOT NULL REFERENCES edw.Dim_Sucursal(sucursal_sk),
    almacen_sk          INT REFERENCES edw.Dim_Almacen(almacen_sk),
    num_devolucion      VARCHAR(10),
    factura_origen      VARCHAR(10),
    cantidad_devuelta   NUMERIC(15,4),
    valor_devolucion    NUMERIC(15,4),
    costo_devolucion    NUMERIC(15,4),
    motivo              VARCHAR(300),
    estado              VARCHAR(1),
    fecha_carga         TIMESTAMP DEFAULT NOW()
);
```

**Tablas Origen:** `encabezadodevoluciones`, `renglonesdevoluciones`.

---

### FACT_COMPRAS

```sql
CREATE TABLE edw.Fact_Compras (
    compra_sk           BIGSERIAL PRIMARY KEY,
    tiempo_sk           INT NOT NULL REFERENCES edw.Dim_Tiempo(tiempo_sk),
    producto_sk         INT NOT NULL REFERENCES edw.Dim_Producto(producto_sk),
    proveedor_sk        INT NOT NULL REFERENCES edw.Dim_Proveedor(proveedor_sk),
    sucursal_sk         INT NOT NULL REFERENCES edw.Dim_Sucursal(sucursal_sk),
    almacen_sk          INT REFERENCES edw.Dim_Almacen(almacen_sk),
    num_compra          VARCHAR(10),
    cantidad            NUMERIC(15,4),
    costo_unitario      NUMERIC(15,4),
    costo_total         NUMERIC(15,4),
    descuento           NUMERIC(15,4),
    total_iva           NUMERIC(15,4),
    total_compra        NUMERIC(15,4),
    total_retencion     NUMERIC(15,4),
    forma_pago          VARCHAR(2),
    es_devolucion       BOOLEAN DEFAULT FALSE,
    estado              VARCHAR(1),
    fecha_carga         TIMESTAMP DEFAULT NOW()
);
```

**Tablas Origen:** `encabezadocompras`, `renglonescompras`.

---

### FACT_MOVIMIENTOS_INVENTARIO

```sql
CREATE TABLE edw.Fact_Movimientos_Inventario (
    movimiento_sk       BIGSERIAL PRIMARY KEY,
    tiempo_sk           INT NOT NULL REFERENCES edw.Dim_Tiempo(tiempo_sk),
    producto_sk         INT NOT NULL REFERENCES edw.Dim_Producto(producto_sk),
    almacen_sk          INT NOT NULL REFERENCES edw.Dim_Almacen(almacen_sk),
    sucursal_sk         INT REFERENCES edw.Dim_Sucursal(sucursal_sk),
    -- Claves de negocio
    tipo_org            VARCHAR(3),                   -- FAC, CPA, TRA, ING, etc.
    num_documento       VARCHAR(10),
    tipo_documento      VARCHAR(2),
    num_renglon         NUMERIC(20,0),
    -- Métricas
    cantidad_movimiento NUMERIC(15,4),               -- Positivo=entrada, Negativo=salida
    costo_unitario      NUMERIC(15,4),
    costo_total         NUMERIC(15,4),
    valor_venta         NUMERIC(15,4),
    -- Flags
    es_entrada          BOOLEAN,
    es_salida           BOOLEAN,
    fecha_carga         TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_fmi_producto ON edw.Fact_Movimientos_Inventario(producto_sk);
CREATE INDEX idx_fmi_almacen  ON edw.Fact_Movimientos_Inventario(almacen_sk);
CREATE INDEX idx_fmi_tiempo   ON edw.Fact_Movimientos_Inventario(tiempo_sk);
```

**Tablas Origen:** `kardex` (tiporg, numdoc, codart, tipdoc, codalm, fecdoc, cantot, cosuni, costot, totven), `kardex_cerrado`.

---

### FACT_INVENTARIO_SNAPSHOT (Snapshot mensual)

```sql
CREATE TABLE edw.Fact_Inventario_Snapshot (
    snapshot_sk         BIGSERIAL PRIMARY KEY,
    tiempo_sk           INT NOT NULL REFERENCES edw.Dim_Tiempo(tiempo_sk),
    producto_sk         INT NOT NULL REFERENCES edw.Dim_Producto(producto_sk),
    almacen_sk          INT NOT NULL REFERENCES edw.Dim_Almacen(almacen_sk),
    sucursal_sk         INT REFERENCES edw.Dim_Sucursal(sucursal_sk),
    -- Métricas del snapshot
    stock_actual        NUMERIC(15,4),
    costo_promedio      NUMERIC(15,4),
    valor_inventario    NUMERIC(15,4),
    stock_minimo        NUMERIC(15,4),
    stock_maximo        NUMERIC(15,4),
    punto_reorden       NUMERIC(15,4),
    dias_sin_movimiento INTEGER,
    -- Indicadores derivados
    alerta_desabastecimiento BOOLEAN DEFAULT FALSE,
    alerta_sobrestock   BOOLEAN DEFAULT FALSE,
    rotacion_30dias     NUMERIC(15,4),
    fecha_carga         TIMESTAMP DEFAULT NOW()
);
```

**Tablas Origen:** `articulos` (exiact, cospro, eximin, eximax, punreo), `kardex` agregado por almacén.

---

### FACT_COBROS_CXC

```sql
CREATE TABLE edw.Fact_Cobros_CXC (
    cobro_sk            BIGSERIAL PRIMARY KEY,
    tiempo_sk           INT NOT NULL REFERENCES edw.Dim_Tiempo(tiempo_sk),
    cliente_sk          INT NOT NULL REFERENCES edw.Dim_Cliente(cliente_sk),
    vendedor_sk         INT REFERENCES edw.Dim_Vendedor(vendedor_sk),
    sucursal_sk         INT REFERENCES edw.Dim_Sucursal(sucursal_sk),
    formapago_sk        INT REFERENCES edw.Dim_FormaPago(formapago_sk),
    num_cobro           VARCHAR(10),
    factura_origen      VARCHAR(10),
    tipo_documento      VARCHAR(2),
    valor_cobrado       NUMERIC(15,2),
    valor_capital       NUMERIC(15,4),
    valor_iva           NUMERIC(15,4),
    dias_plazo          INTEGER,
    num_cuota           INTEGER,
    total_cuotas        INTEGER,
    saldo_documento     NUMERIC(15,4),
    valor_interes       NUMERIC(15,4),
    dias_vencimiento    INTEGER,
    esta_vencido        BOOLEAN DEFAULT FALSE,
    fue_cancelado       BOOLEAN DEFAULT FALSE,
    fecha_carga         TIMESTAMP DEFAULT NOW()
);
```

**Tablas Origen:** `cuentasporcobrar` (numcco, tipdoc, codcli, codven, fecemi, fecven, valcob, totnet, totiva, ncuota, ncuota1, dias, saldodoc, diasvence, cerrado, establ).

---

### FACT_PAGOS_CXP

```sql
CREATE TABLE edw.Fact_Pagos_CXP (
    pago_sk             BIGSERIAL PRIMARY KEY,
    tiempo_sk           INT NOT NULL REFERENCES edw.Dim_Tiempo(tiempo_sk),
    proveedor_sk        INT NOT NULL REFERENCES edw.Dim_Proveedor(proveedor_sk),
    sucursal_sk         INT REFERENCES edw.Dim_Sucursal(sucursal_sk),
    formapago_sk        INT REFERENCES edw.Dim_FormaPago(formapago_sk),
    num_pago            VARCHAR(10),
    compra_origen       VARCHAR(10),
    tipo_documento      VARCHAR(2),
    valor_pagado        NUMERIC(15,4),
    valor_capital       NUMERIC(15,4),
    valor_iva           NUMERIC(15,4),
    total_retencion     NUMERIC(15,4),
    dias_plazo          INTEGER,
    num_cuota           INTEGER,
    esta_vencido        BOOLEAN DEFAULT FALSE,
    fue_cancelado       BOOLEAN DEFAULT FALSE,
    fecha_carga         TIMESTAMP DEFAULT NOW()
);
```

**Tablas Origen:** `cuentasporpagar` (numcpp, tipdoc, codpro, fecemi, fecven, valcob, totnet, totiva, cerrado, establ).

---

### FACT_MOVIMIENTOS_CAJA

```sql
CREATE TABLE edw.Fact_Movimientos_Caja (
    movcaja_sk          BIGSERIAL PRIMARY KEY,
    tiempo_sk           INT NOT NULL REFERENCES edw.Dim_Tiempo(tiempo_sk),
    sucursal_sk         INT NOT NULL REFERENCES edw.Dim_Sucursal(sucursal_sk),
    formapago_sk        INT REFERENCES edw.Dim_FormaPago(formapago_sk),
    usuario_sk          INT REFERENCES edw.Dim_Usuario(usuario_sk),
    num_documento       VARCHAR(10),
    tipo_org            VARCHAR(3),
    tipo_documento      VARCHAR(2),
    valor               NUMERIC(15,4),
    codigo_caja         VARCHAR(5),
    es_ingreso          BOOLEAN,
    es_egreso           BOOLEAN,
    num_cierre          VARCHAR(10),
    fecha_carga         TIMESTAMP DEFAULT NOW()
);
```

**Tablas Origen:** `movimientos_caja` (fectra, numfac, tiporg, valor, formapag, codven, codcaja, establ, tipdoc, numcierre).

---

### FACT_METAS_COMERCIALES

```sql
CREATE TABLE edw.Fact_Metas_Comerciales (
    meta_sk             BIGSERIAL PRIMARY KEY,
    tiempo_sk           INT NOT NULL REFERENCES edw.Dim_Tiempo(tiempo_sk),
    vendedor_sk         INT NOT NULL REFERENCES edw.Dim_Vendedor(vendedor_sk),
    sucursal_sk         INT REFERENCES edw.Dim_Sucursal(sucursal_sk),
    categoria_sk        INT REFERENCES edw.Dim_Categoria(categoria_sk),
    meta_ventas_monto   NUMERIC(15,4),
    meta_ventas_unid    NUMERIC(15,4),
    real_ventas_monto   NUMERIC(15,4),
    real_ventas_unid    NUMERIC(15,4),
    pct_cumplimiento    NUMERIC(8,4),
    brecha              NUMERIC(15,4),
    fecha_carga         TIMESTAMP DEFAULT NOW()
);
```

**Tablas Origen:** `presupuesto`/`vendedorespres` (codven, anio, mes, meta por categoría).

---

### FACT_LOGS_AUDITORIA

```sql
CREATE TABLE edw.Fact_Logs_Auditoria (
    auditoria_sk        BIGSERIAL PRIMARY KEY,
    tiempo_sk           INT NOT NULL REFERENCES edw.Dim_Tiempo(tiempo_sk),
    usuario_sk          INT REFERENCES edw.Dim_Usuario(usuario_sk),
    sucursal_sk         INT REFERENCES edw.Dim_Sucursal(sucursal_sk),
    tabla_afectada      VARCHAR(50),
    tipo_operacion      VARCHAR(10),                  -- INSERT, UPDATE, DELETE
    num_documento       VARCHAR(20),
    tipo_documento      VARCHAR(10),
    valor_anterior      NUMERIC(15,4),
    valor_nuevo         NUMERIC(15,4),
    ip_origen           VARCHAR(50),
    modulo              VARCHAR(20),
    descripcion         VARCHAR(500),
    fecha_carga         TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_fla_tiempo  ON edw.Fact_Logs_Auditoria(tiempo_sk);
CREATE INDEX idx_fla_usuario ON edw.Fact_Logs_Auditoria(usuario_sk);
```

**Tablas Origen:** `mxauduser`, `mxaucxp`, `mxaukardex`, `mxauencabezadotrans`, `mxaurenglonestrans` (todas las tablas de auditoría `mxau*`).

---

### FACT_NOMINA

```sql
CREATE TABLE edw.Fact_Nomina (
    nomina_sk           BIGSERIAL PRIMARY KEY,
    tiempo_sk           INT NOT NULL REFERENCES edw.Dim_Tiempo(tiempo_sk),
    empleado_sk         INT NOT NULL REFERENCES edw.Dim_Empleado(empleado_sk),
    sucursal_sk         INT REFERENCES edw.Dim_Sucursal(sucursal_sk),
    periodo             VARCHAR(10),
    sueldo_base         NUMERIC(15,4),
    horas_extras        NUMERIC(10,4),
    valor_horas_extras  NUMERIC(15,4),
    total_ingresos      NUMERIC(15,4),
    total_descuentos    NUMERIC(15,4),
    neto_pagar          NUMERIC(15,4),
    aporte_iess         NUMERIC(15,4),
    fecha_carga         TIMESTAMP DEFAULT NOW()
);
```

**Tablas Origen:** `nom_nomina` (sueldo, htotal, dtotal, liquido), `nom_componentes`, `nom_empleados`.

---

# 2. CONSULTAS DE EXTRACCIÓN (EXTRACT — SAP SQL Anywhere)

> Todos los scripts se ejecutan en el motor **SAP SQL Anywhere** (sintaxis compatible con SQL estándar ISO + extensiones Sybase). Usar el driver ODBC/JDBC apropiado desde Python.

---

## 2.1 Extracción — Dim_Cliente

```sql
-- SAP SQL Anywhere
SELECT
    c.codemp,
    c.codcli,
    c.nomcli,
    c.rucced,
    c.tiprucced,
    c.codcla,
    cc.nomcla                       AS nombre_clase,
    c.codzona,
    z.nomzon                        AS nombre_zona,
    c.ciucli,
    c.dircli,
    c.telcli,
    c.mail,
    c.limcre,
    c.dias,
    c.lispre,
    c.codven,
    c.codcob,
    c.estado,
    c.sexo,
    CAST(c.fecnac AS DATE)          AS fecha_nacimiento,
    c.parterel,
    c.fecult                        AS fecha_ultima_modificacion
FROM clientes c
LEFT JOIN clasesclientes cc ON cc.codemp = c.codemp AND cc.codcla = c.codcla
LEFT JOIN zona z             ON z.codemp  = c.codemp AND z.codzona = c.codzona
WHERE c.estado IN ('A','I','S')
ORDER BY c.codemp, c.codcli;
```

---

## 2.2 Extracción — Dim_Producto

```sql
SELECT
    a.codemp,
    a.codart,
    a.nomart,
    a.codalt,
    a.codbar,
    a.codcla,
    ca.nomcla                       AS nombre_clase,
    a.subcodcla,
    sc.nomsubcla                    AS nombre_subclase,
    a.coduni,
    u.nomuni                        AS nombre_unidad,
    a.codiva,
    iv.poriva                       AS pct_iva,
    a.prec01,
    a.prec02,
    a.prec03,
    a.prec04,
    a.precio                        AS precio_oficial,
    a.cospro                        AS costo_promedio,
    a.ultcos                        AS ultimo_costo,
    a.exiact                        AS existencia_actual,
    a.eximin                        AS stock_minimo,
    a.eximax                        AS stock_maximo,
    a.punreo                        AS punto_reorden,
    a.peso,
    a.estado,
    a.produ                         AS es_produccion,
    a.bienser,
    a.activado,
    a.ice,
    a.codice,
    a.fecult
FROM articulos a
LEFT JOIN clasesarticulos  ca ON ca.codemp = a.codemp AND ca.codcla     = a.codcla
LEFT JOIN subclasesarticulos sc ON sc.codemp = a.codemp AND sc.subcodcla = a.subcodcla
LEFT JOIN unidades          u  ON u.codemp  = a.codemp AND u.coduni     = a.coduni
LEFT JOIN iva               iv ON iv.codemp = a.codemp AND iv.codiva    = a.codiva
WHERE a.estado <> 'E'
ORDER BY a.codemp, a.codart;
```

---

## 2.3 Extracción — Dim_Vendedor

```sql
SELECT
    v.codemp,
    v.codven,
    v.nomven,
    v.tipven,
    v.codzon,
    v.establ,
    v.comision,
    v.activo,
    v.fecult
FROM vendedorescob v
ORDER BY v.codemp, v.codven;
```

---

## 2.4 Extracción — Dim_Sucursal

```sql
SELECT
    e.codemp,
    e.establ,
    e.codemp || e.establ            AS codigo_sucursal,
    e.nomest,
    e.direc,
    e.telf,
    e.eslogan,
    em.nomemp
FROM establecimientos e
JOIN empresa em ON em.codemp = e.codemp
ORDER BY e.codemp, e.establ;
```

---

## 2.5 Extracción — Fact_Ventas_Detalle

```sql
-- QUERY PRINCIPAL: Desnormaliza cabecera + renglones en una sola pasada
-- Incluye cálculo de margen bruto a nivel de línea
SELECT
    ef.codemp,
    ef.numfac,
    rf.numren,
    ef.establ,
    ef.codalm,
    ef.codcli,
    ef.codven,
    CAST(ef.fecfac AS DATE)         AS fecha_factura,
    ef.hora                         AS hora_factura,
    ef.lispre,
    ef.estado,
    ef.estadow,
    ef.codcajero,
    ef.codforpag,
    -- Renglón
    rf.codart,
    rf.cantid                       AS cantidad,
    rf.preuni                       AS precio_unitario,
    rf.cosuni                       AS costo_unitario,
    rf.descue                       AS pct_descuento,
    rf.cantid * rf.preuni           AS subtotal_bruto,
    rf.cantid * rf.preuni * (rf.descue / 100.0) AS valor_descuento,
    rf.cantid * rf.preuni * (1 - rf.descue / 100.0) AS subtotal_neto,
    -- IVA por renglón
    CASE a.codiva
        WHEN '1' THEN rf.cantid * rf.preuni * (1 - rf.descue/100.0) * (iv.poriva/100.0)
        ELSE 0
    END                             AS valor_iva,
    -- ICE
    COALESCE(a.ice, 0) * rf.cantid AS valor_ice,
    -- Total línea
    rf.cantid * rf.preuni * (1 - rf.descue/100.0)
        + CASE a.codiva WHEN '1' THEN rf.cantid * rf.preuni * (1-rf.descue/100.0)*(iv.poriva/100.0) ELSE 0 END
                                    AS total_linea,
    -- Costo y margen
    rf.cantid * COALESCE(rf.cosuni, a.cospro, a.ultcos, 0) AS costo_total,
    (rf.cantid * rf.preuni * (1 - rf.descue/100.0))
        - (rf.cantid * COALESCE(rf.cosuni, a.cospro, a.ultcos, 0)) AS margen_bruto
FROM encabezadofacturas ef
JOIN renglonesfacturas rf
    ON rf.codemp = ef.codemp AND rf.numfac = ef.numfac
JOIN articulos a
    ON a.codemp = ef.codemp AND a.codart = rf.codart
LEFT JOIN iva iv
    ON iv.codemp = ef.codemp AND iv.codiva = a.codiva
WHERE ef.estadow = 'A'                          -- Solo facturas activas
  AND ef.fecfac >= '2020-01-01'                 -- Ajustar ventana temporal
ORDER BY ef.codemp, ef.numfac, rf.numren;
```

---

## 2.6 Extracción — Fact_Movimientos_Inventario (Kardex)

```sql
-- UNIÓN de kardex abierto + kardex cerrado para historial completo
SELECT
    k.codemp,
    k.tiporg,
    k.numdoc,
    k.numren,
    k.codart,
    k.tipdoc,
    k.codalm,
    k.coduni,
    CAST(k.fecdoc AS DATE)          AS fecha_movimiento,
    k.hora,
    k.establ,
    k.cantot                        AS cantidad_movimiento,
    k.cosuni                        AS costo_unitario,
    k.costot                        AS costo_total,
    k.totven                        AS valor_venta,
    k.codcli,
    k.codven,
    ktd.sigdoc                      AS signo_movimiento  -- '+' entrada, '-' salida
FROM kardex k
LEFT JOIN kardex_tipo_doc ktd ON ktd.tipdoc = k.tipdoc

UNION ALL

SELECT
    kc.codemp,
    kc.tiporg,
    kc.numdoc,
    kc.numren,
    kc.codart,
    kc.tipdoc,
    kc.codalm,
    kc.coduni,
    CAST(kc.fecdoc AS DATE),
    kc.hora,
    kc.establ,
    kc.cantot,
    kc.cosuni,
    kc.costot,
    kc.totven,
    kc.codcli,
    kc.codven,
    ktd.sigdoc
FROM kardex_cerrado kc
LEFT JOIN kardex_tipo_doc ktd ON ktd.tipdoc = kc.tipdoc

ORDER BY codemp, codart, fecdoc, numren;
```

---

## 2.7 Extracción — Fact_Compras

```sql
SELECT
    ec.codemp,
    ec.numfac,
    rc.numren,
    ec.establ,
    ec.codalm,
    ec.codpro,
    CAST(ec.fecfac AS DATE)         AS fecha_compra,
    ec.hora,
    ec.estado,
    ec.estadow,
    rc.codart,
    rc.cantid,
    rc.cosuni,
    rc.cantid * rc.cosuni           AS costo_linea,
    rc.descue,
    rc.totali,
    ec.totnet,
    ec.totiva,
    ec.totfac,
    ec.totret,
    ec.porcentajeiva
FROM encabezadocompras ec
JOIN renglonescompras rc
    ON rc.codemp = ec.codemp AND rc.numfac = ec.numfac
WHERE ec.estadow = 'A'
ORDER BY ec.codemp, ec.numfac, rc.numren;
```

---

## 2.8 Extracción — Fact_Cobros_CXC

```sql
SELECT
    cxc.codemp,
    cxc.numcco,
    cxc.tipdoc,
    cxc.numtra                      AS factura_origen,
    cxc.codcli,
    cxc.codven,
    cxc.establ,
    CAST(cxc.fecemi AS DATE)        AS fecha_emision,
    CAST(cxc.fecven AS DATE)        AS fecha_vencimiento,
    CAST(cxc.fectra AS DATE)        AS fecha_transaccion,
    cxc.valcob                      AS valor_cobrado,
    cxc.totnet,
    cxc.totiva,
    cxc.ncuota,
    cxc.ncuota1                     AS total_cuotas,
    cxc.dias,
    cxc.saldodoc,
    cxc.diasvence,
    cxc.cerrado,
    cxc.porinter,
    cxc.valinter,
    cxc.codforpag,
    CASE WHEN cxc.cerrado = 'S' THEN TRUE ELSE FALSE END AS fue_cancelado,
    CASE WHEN cxc.diasvence < 0 THEN TRUE ELSE FALSE END AS esta_vencido
FROM cuentasporcobrar cxc
WHERE cxc.estadow = 'A'
ORDER BY cxc.codemp, cxc.fecemi;
```

---

## 2.9 Extracción — Fact_Logs_Auditoria

```sql
-- Consolida todas las tablas de auditoría mxau*
SELECT
    'mxauduser'                     AS tabla_fuente,
    u.codemp,
    u.codusu,
    CAST(u.fecult AS DATE)          AS fecha_evento,
    u.fecult                        AS timestamp_evento,
    'USUARIOS'                      AS tabla_afectada,
    u.tipope                        AS tipo_operacion,
    u.numfac                        AS num_documento,
    u.tipdoc                        AS tipo_documento,
    NULL::DECIMAL                   AS valor_anterior,
    NULL::DECIMAL                   AS valor_nuevo,
    u.establ,
    u.modulo
FROM mxauduser u

UNION ALL

SELECT
    'mxaukardex',
    mk.codemp,
    mk.codusu,
    CAST(mk.fecult AS DATE),
    mk.fecult,
    'KARDEX',
    mk.tipope,
    mk.numdoc,
    mk.tipdoc,
    mk.cantot_ant,
    mk.cantot_nue,
    mk.establ,
    'INV'
FROM mxaukardex mk

UNION ALL

SELECT
    'mxauencabezadotrans',
    mt.codemp,
    mt.codusu,
    CAST(mt.fecult AS DATE),
    mt.fecult,
    mt.tabla,
    mt.tipope,
    mt.numdoc,
    mt.tipdoc,
    mt.valant,
    mt.valnue,
    mt.establ,
    mt.modulo
FROM mxauencabezadotrans mt

ORDER BY codemp, timestamp_evento;
```

---

## 2.10 Extracción — Fact_Inventario_Snapshot (Snapshot de Stock Actual)

```sql
-- Saldo de existencias por artículo y almacén al momento de la extracción
SELECT
    a.codemp,
    a.codart,
    alm.codalm,
    alm.establ,
    a.exiact                                      AS stock_actual,
    a.cospro                                      AS costo_promedio,
    a.exiact * a.cospro                           AS valor_inventario,
    a.eximin                                      AS stock_minimo,
    a.eximax                                      AS stock_maximo,
    a.punreo                                      AS punto_reorden,
    CASE WHEN a.exiact <= a.eximin THEN 1 ELSE 0 END AS alerta_desabastecimiento,
    CASE WHEN a.exiact >= a.eximax THEN 1 ELSE 0 END AS alerta_sobrestock,
    CAST(CURRENT_DATE AS DATE)                    AS fecha_snapshot
FROM articulos a
CROSS JOIN almacenes alm
WHERE a.codemp = alm.codemp
  AND a.estado = 'A'
  AND alm.inv  = 'S'
ORDER BY a.codemp, a.codart, alm.codalm;
```

---

# 3. LÓGICA DE TRANSFORMACIÓN (TRANSFORM — Python/Pandas)

## 3.1 Reglas Generales de Limpieza

### 3.1.1 Tratamiento de Tipos de Datos

```python
import pandas as pd
import numpy as np
from datetime import datetime

# ── Fechas ─────────────────────────────────────────────────────────────────
def normalizar_fechas(df: pd.DataFrame, columnas_fecha: list) -> pd.DataFrame:
    """Convierte columnas al tipo datetime64 de forma segura."""
    for col in columnas_fecha:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
            # Fechas fuera de rango (SAP guarda timestamps '1900-01-01') → NaT
            df.loc[df[col] < pd.Timestamp('2000-01-01'), col] = pd.NaT
    return df

# ── Numéricos ──────────────────────────────────────────────────────────────
def normalizar_numericos(df: pd.DataFrame, columnas_num: list) -> pd.DataFrame:
    """Reemplaza nulos y valores negativos inválidos en campos monetarios."""
    for col in columnas_num:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
            df[col] = df[col].round(4)
    return df

# ── Strings ────────────────────────────────────────────────────────────────
def normalizar_strings(df: pd.DataFrame, columnas_str: list) -> pd.DataFrame:
    for col in columnas_str:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.upper()
            df[col] = df[col].replace({'NAN': None, 'NONE': None, '': None})
    return df
```

---

### 3.1.2 Resolución de Inconsistencias en Catálogos

```python
# ── Normalización de flags de estado ───────────────────────────────────────
ESTADO_MAP = {'A': 'ACTIVO', 'I': 'INACTIVO', 'S': 'SUSPENDIDO',
              'E': 'ELIMINADO', '1': 'ACTIVO', '0': 'INACTIVO'}

def normalizar_estado(df: pd.DataFrame, col: str) -> pd.DataFrame:
    df[col] = df[col].str.strip().str.upper().map(ESTADO_MAP).fillna('DESCONOCIDO')
    return df

# ── Normalización de tipo de ID ─────────────────────────────────────────────
TIPO_ID_MAP = {'04': 'RUC', '05': 'CEDULA', '06': 'PASAPORTE',
               '07': 'CONSUMIDOR_FINAL', '08': 'ID_EXTERIOR'}

def normalizar_tipo_id(df: pd.DataFrame, col: str) -> pd.DataFrame:
    df[col] = df[col].str.strip().map(TIPO_ID_MAP).fillna('OTRO')
    return df

# ── Eliminar duplicados de claves de negocio ────────────────────────────────
def deduplicar(df: pd.DataFrame, clave_natural: list) -> pd.DataFrame:
    """Conserva el registro con fecult (fecha de modificación) más reciente."""
    if 'fecult' in df.columns:
        df = df.sort_values('fecult', ascending=False)
    df = df.drop_duplicates(subset=clave_natural, keep='first')
    return df
```

---

### 3.1.3 Generación Algorítmica de Dim_Tiempo

```python
def generar_dim_tiempo(fecha_inicio: str = '2010-01-01',
                       fecha_fin:    str = '2030-12-31') -> pd.DataFrame:
    """Genera la tabla Dim_Tiempo completa de forma algorítmica."""
    MESES_ES = {1:'Enero',2:'Febrero',3:'Marzo',4:'Abril',5:'Mayo',
                6:'Junio',7:'Julio',8:'Agosto',9:'Septiembre',
                10:'Octubre',11:'Noviembre',12:'Diciembre'}
    DIAS_ES  = {0:'Lunes',1:'Martes',2:'Miércoles',3:'Jueves',
                4:'Viernes',5:'Sábado',6:'Domingo'}

    fechas = pd.date_range(start=fecha_inicio, end=fecha_fin, freq='D')
    df = pd.DataFrame({'fecha_completa': fechas})

    df['anio']         = df.fecha_completa.dt.year
    df['trimestre']    = df.fecha_completa.dt.quarter
    df['mes']          = df.fecha_completa.dt.month
    df['nombre_mes']   = df.mes.map(MESES_ES)
    df['semana_anio']  = df.fecha_completa.dt.isocalendar().week.astype(int)
    df['dia_mes']      = df.fecha_completa.dt.day
    df['dia_semana']   = df.fecha_completa.dt.dayofweek + 1    # 1=Lun..7=Dom
    df['nombre_dia']   = (df.fecha_completa.dt.dayofweek).map(DIAS_ES)
    df['es_fin_semana']= df.fecha_completa.dt.dayofweek >= 5
    df['semestre']     = np.where(df.mes <= 6, 1, 2)
    df['periodo_fiscal']= df.anio.astype(str) + '-Q' + df.trimestre.astype(str)
    df['es_feriado']   = False    # Poblar con calendario oficial del país

    return df
```

---

### 3.1.4 Transformaciones específicas por Hecho

```python
import pandas as pd
import numpy as np

# ── Fact_Ventas_Detalle ─────────────────────────────────────────────────────
def transformar_ventas(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_fechas(df, ['fecha_factura'])
    df = normalizar_numericos(df, ['cantidad','precio_unitario','costo_unitario',
                                   'pct_descuento','valor_iva','valor_ice',
                                   'costo_total','margen_bruto'])

    # Calcular % de margen de manera segura
    df['pct_margen'] = np.where(
        df['subtotal_neto'] != 0,
        (df['margen_bruto'] / df['subtotal_neto'] * 100).round(4),
        0.0
    )

    # Eliminar líneas con cantidad cero (errores de data entry)
    df = df[df['cantidad'] != 0].copy()

    # Flag de devolución (renglones con cantidad negativa en kardex VTA)
    df['es_devolucion'] = df['cantidad'] < 0
    df['cantidad']      = df['cantidad'].abs()

    return df

# ── Fact_Inventario_Snapshot ────────────────────────────────────────────────
def calcular_rotacion(df_kardex: pd.DataFrame,
                      dias: int = 30) -> pd.DataFrame:
    """Calcula unidades vendidas en los últimos N días por artículo/almacén."""
    desde = pd.Timestamp.today() - pd.Timedelta(days=dias)
    ventas = (
        df_kardex[
            (df_kardex['tipo_org'] == 'VTA') &
            (df_kardex['fecha_movimiento'] >= desde)
        ]
        .groupby(['codemp','codart','codalm'])['cantidad_movimiento']
        .sum()
        .abs()
        .reset_index()
        .rename(columns={'cantidad_movimiento': f'rotacion_{dias}dias'})
    )
    return ventas
```

---

# 4. ARQUITECTURA DEL CÓDIGO ETL BASE (Python)

## 4.1 Estructura del Proyecto

```
etl_edw/
├── config/
│   ├── settings.py          # Variables de entorno y parámetros
│   └── logging_config.py    # Configuración de logging
├── connectors/
│   ├── sqlany_connector.py  # Conexión SAP SQL Anywhere (ODBC)
│   └── postgres_connector.py # Conexión PostgreSQL (SQLAlchemy)
├── extractors/
│   ├── dim_extractor.py     # Extracción de dimensiones
│   └── fact_extractor.py    # Extracción de hechos
├── transformers/
│   ├── dim_transformer.py   # Transformaciones de dimensiones
│   ├── fact_transformer.py  # Transformaciones de hechos
│   └── dim_tiempo.py        # Generador de Dim_Tiempo
├── loaders/
│   └── pg_loader.py         # Carga hacia PostgreSQL
├── orchestrator.py          # Orquestador principal del pipeline
└── requirements.txt
```

---

## 4.2 Configuración y Conexiones

```python
# config/settings.py
import os
from dataclasses import dataclass

@dataclass
class ETLConfig:
    # ── SAP SQL Anywhere ────────────────────────────────────────────────────
    SQLANY_DSN:      str = os.getenv("SQLANY_DSN",      "MyDSN")
    SQLANY_USER:     str = os.getenv("SQLANY_USER",     "dba")
    SQLANY_PASSWORD: str = os.getenv("SQLANY_PASSWORD", "")
    SQLANY_HOST:     str = os.getenv("SQLANY_HOST",     "localhost")
    SQLANY_PORT:     int = int(os.getenv("SQLANY_PORT", "2638"))
    SQLANY_DB:       str = os.getenv("SQLANY_DB",       "empresa")

    # ── PostgreSQL EDW ──────────────────────────────────────────────────────
    PG_HOST:         str = os.getenv("PG_HOST",     "localhost")
    PG_PORT:         int = int(os.getenv("PG_PORT", "5432"))
    PG_DB:           str = os.getenv("PG_DB",       "edw")
    PG_USER:         str = os.getenv("PG_USER",     "etl_user")
    PG_PASSWORD:     str = os.getenv("PG_PASSWORD", "")
    PG_SCHEMA:       str = "edw"

    # ── Control del pipeline ────────────────────────────────────────────────
    BATCH_SIZE:      int  = int(os.getenv("BATCH_SIZE", "10000"))
    FECHA_DESDE:     str  = os.getenv("FECHA_DESDE",    "2020-01-01")
    MODO_INCREMENTAL:bool = os.getenv("MODO_INCREMENTAL","true").lower()=="true"
    CODEMP:          str  = os.getenv("CODEMP",         "01")
```

---

## 4.3 Conector SAP SQL Anywhere

```python
# connectors/sqlany_connector.py
import pyodbc
import pandas as pd
import logging
from contextlib import contextmanager
from config.settings import ETLConfig

logger = logging.getLogger(__name__)

class SQLAnywhereConnector:
    """Maneja la conexión ODBC a SAP SQL Anywhere."""

    def __init__(self, config: ETLConfig):
        self.config = config
        self._conn: pyodbc.Connection | None = None

    def _build_connection_string(self) -> str:
        return (
            f"DRIVER={{SQL Anywhere 17}};"
            f"HOST={self.config.SQLANY_HOST}:{self.config.SQLANY_PORT};"
            f"DBN={self.config.SQLANY_DB};"
            f"UID={self.config.SQLANY_USER};"
            f"PWD={self.config.SQLANY_PASSWORD};"
            f"CHARSET=UTF-8;"
        )

    def connect(self) -> None:
        connstr = self._build_connection_string()
        self._conn = pyodbc.connect(connstr, autocommit=True, timeout=60)
        logger.info("Conectado exitosamente a SAP SQL Anywhere.")

    def disconnect(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("Conexión a SAP SQL Anywhere cerrada.")

    @contextmanager
    def connection(self):
        self.connect()
        try:
            yield self
        finally:
            self.disconnect()

    def query_to_dataframe(self, sql: str,
                           params: tuple = (),
                           chunksize: int | None = None) -> pd.DataFrame:
        """Ejecuta una consulta SQL y devuelve un DataFrame de pandas."""
        if not self._conn:
            raise RuntimeError("No hay conexión activa a SAP SQL Anywhere.")
        try:
            if chunksize:
                frames = []
                for chunk in pd.read_sql(sql, self._conn, params=params,
                                         chunksize=chunksize):
                    frames.append(chunk)
                return pd.concat(frames, ignore_index=True)
            return pd.read_sql(sql, self._conn, params=params)
        except Exception as e:
            logger.error(f"Error ejecutando query: {e}\nSQL: {sql[:300]}")
            raise
```

---

## 4.4 Conector PostgreSQL (SQLAlchemy)

```python
# connectors/postgres_connector.py
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
import pandas as pd
import logging
from config.settings import ETLConfig

logger = logging.getLogger(__name__)

class PostgresConnector:
    """Administra la conexión y carga hacia el EDW en PostgreSQL."""

    def __init__(self, config: ETLConfig):
        self.config = config
        self._engine: Engine | None = None

    def _build_url(self) -> str:
        c = self.config
        return (f"postgresql+psycopg2://{c.PG_USER}:{c.PG_PASSWORD}"
                f"@{c.PG_HOST}:{c.PG_PORT}/{c.PG_DB}")

    def connect(self) -> Engine:
        if not self._engine:
            self._engine = create_engine(
                self._build_url(),
                pool_size=5, max_overflow=10,
                pool_pre_ping=True,
                connect_args={"options": f"-csearch_path={self.config.PG_SCHEMA}"}
            )
            logger.info("Engine PostgreSQL (EDW) inicializado.")
        return self._engine

    def upsert_dataframe(self, df: pd.DataFrame, tabla: str,
                         claves_negocio: list[str],
                         modo: str = 'upsert') -> int:
        """
        Carga un DataFrame al EDW.
        modo='truncate'  → Trunca y recarga completa (dimensiones pequeñas).
        modo='upsert'    → INSERT ON CONFLICT DO UPDATE (hechos y SCD2).
        modo='append'    → Sólo inserta registros nuevos.
        """
        engine = self.connect()
        schema = self.config.PG_SCHEMA

        if df.empty:
            logger.warning(f"DataFrame vacío para tabla {tabla}. Se omite la carga.")
            return 0

        registros = 0
        with engine.begin() as conn:
            if modo == 'truncate':
                conn.execute(text(f"TRUNCATE TABLE {schema}.{tabla} RESTART IDENTITY CASCADE"))
                df.to_sql(tabla, conn, schema=schema, if_exists='append',
                          index=False, method='multi', chunksize=5000)
                registros = len(df)
                logger.info(f"TRUNCATE+RELOAD {tabla}: {registros} filas.")

            elif modo == 'append':
                df.to_sql(tabla, conn, schema=schema, if_exists='append',
                          index=False, method='multi', chunksize=5000)
                registros = len(df)
                logger.info(f"APPEND {tabla}: {registros} filas nuevas.")

            elif modo == 'upsert':
                # Estrategia: staging table → INSERT ON CONFLICT
                staging = f"_stg_{tabla}"
                df.to_sql(staging, conn, schema=schema, if_exists='replace',
                          index=False, method='multi', chunksize=5000)

                cols     = [c for c in df.columns if c not in claves_negocio]
                set_expr = ", ".join([f"{c}=EXCLUDED.{c}" for c in cols])
                conflict = ", ".join(claves_negocio)
                sql_ups  = text(f"""
                    INSERT INTO {schema}.{tabla} ({','.join(df.columns)})
                    SELECT {','.join(df.columns)} FROM {schema}.{staging}
                    ON CONFLICT ({conflict}) DO UPDATE SET {set_expr}
                """)
                result   = conn.execute(sql_ups)
                registros = result.rowcount
                conn.execute(text(f"DROP TABLE IF EXISTS {schema}.{staging}"))
                logger.info(f"UPSERT {tabla}: {registros} filas procesadas.")

        return registros
```

---

## 4.5 Orquestador Principal del Pipeline ETL

```python
# orchestrator.py
import logging
import pandas as pd
from datetime import datetime

from config.settings import ETLConfig
from connectors.sqlany_connector import SQLAnywhereConnector
from connectors.postgres_connector import PostgresConnector
from transformers.dim_tiempo import generar_dim_tiempo
from transformers.dim_transformer import (
    transformar_clientes, transformar_productos,
    transformar_vendedores, transformar_almacenes,
    transformar_sucursales, transformar_proveedores
)
from transformers.fact_transformer import (
    transformar_ventas, transformar_kardex,
    transformar_compras, transformar_cobros_cxc
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s')

# ─── SQLs de Extracción ────────────────────────────────────────────────────
SQL_CLIENTES = """
SELECT c.codemp, c.codcli, c.nomcli, c.rucced, c.tiprucced, c.codcla,
       cc.nomcla, c.codzona, z.nomzon, c.ciucli, c.dircli, c.telcli,
       c.mail, c.limcre, c.dias, c.lispre, c.codven, c.codcob,
       c.estado, c.sexo, CAST(c.fecnac AS DATE) fecnac, c.parterel, c.fecult
FROM clientes c
LEFT JOIN clasesclientes cc ON cc.codemp=c.codemp AND cc.codcla=c.codcla
LEFT JOIN zona z            ON z.codemp=c.codemp  AND z.codzona=c.codzona
WHERE c.codemp = ?
"""

SQL_PRODUCTOS = """
SELECT a.codemp, a.codart, a.nomart, a.codalt, a.codbar, a.codcla,
       ca.nomcla, a.subcodcla, sc.nomsubcla, a.coduni, u.nomuni,
       a.codiva, iv.poriva, a.prec01, a.prec02, a.prec03, a.prec04,
       a.precio, a.cospro, a.ultcos, a.exiact, a.eximin, a.eximax,
       a.punreo, a.peso, a.estado, a.produ, a.bienser, a.activado, a.fecult
FROM articulos a
LEFT JOIN clasesarticulos   ca ON ca.codemp=a.codemp AND ca.codcla=a.codcla
LEFT JOIN subclasesarticulos sc ON sc.codemp=a.codemp AND sc.subcodcla=a.subcodcla
LEFT JOIN unidades           u  ON u.codemp=a.codemp  AND u.coduni=a.coduni
LEFT JOIN iva               iv  ON iv.codemp=a.codemp AND iv.codiva=a.codiva
WHERE a.codemp = ? AND a.estado <> 'E'
"""

SQL_VENTAS = """
SELECT ef.codemp, ef.numfac, rf.numren, ef.establ, ef.codalm,
       ef.codcli, ef.codven, CAST(ef.fecfac AS DATE) fecha_factura,
       ef.hora, ef.lispre, ef.estado, ef.estadow, ef.codforpag,
       rf.codart, rf.cantid, rf.preuni, rf.cosuni, rf.descue,
       rf.cantid * rf.preuni AS subtotal_bruto,
       CAST(rf.cantid * rf.preuni * (1 - rf.descue/100.0) AS DECIMAL(15,4)) AS subtotal_neto,
       CASE a.codiva WHEN '1'
           THEN CAST(rf.cantid * rf.preuni * (1-rf.descue/100.0) * (iv.poriva/100.0) AS DECIMAL(15,4))
           ELSE 0 END AS valor_iva,
       CAST(rf.cantid * COALESCE(rf.cosuni, a.cospro, a.ultcos, 0) AS DECIMAL(15,4)) AS costo_total
FROM encabezadofacturas ef
JOIN renglonesfacturas rf ON rf.codemp=ef.codemp AND rf.numfac=ef.numfac
JOIN articulos         a  ON a.codemp=ef.codemp  AND a.codart=rf.codart
LEFT JOIN iva         iv  ON iv.codemp=ef.codemp AND iv.codiva=a.codiva
WHERE ef.codemp = ?
  AND ef.estadow = 'A'
  AND CAST(ef.fecfac AS DATE) >= ?
"""

SQL_KARDEX = """
SELECT k.codemp, k.tiporg, k.numdoc, k.numren, k.codart, k.tipdoc,
       k.codalm, CAST(k.fecdoc AS DATE) fecha_movimiento,
       k.hora, k.establ, k.cantot, k.cosuni, k.costot, k.totven,
       k.codcli, k.codven, ktd.sigdoc
FROM kardex k
LEFT JOIN kardex_tipo_doc ktd ON ktd.tipdoc = k.tipdoc
WHERE k.codemp = ?
UNION ALL
SELECT kc.codemp, kc.tiporg, kc.numdoc, kc.numren, kc.codart, kc.tipdoc,
       kc.codalm, CAST(kc.fecdoc AS DATE), kc.hora, kc.establ,
       kc.cantot, kc.cosuni, kc.costot, kc.totven, kc.codcli, kc.codven, ktd.sigdoc
FROM kardex_cerrado kc
LEFT JOIN kardex_tipo_doc ktd ON ktd.tipdoc = kc.tipdoc
WHERE kc.codemp = ?
"""

# ─── Pipeline principal ────────────────────────────────────────────────────
def run_etl(config: ETLConfig) -> None:
    inicio = datetime.now()
    logger.info(f"═══ INICIO DEL PIPELINE ETL — {inicio} ═══")

    sa  = SQLAnywhereConnector(config)
    pg  = PostgresConnector(config)

    with sa.connection():
        # ── 1. Dim_Tiempo (generación algorítmica, sin conexión origen) ────
        logger.info("Generando Dim_Tiempo...")
        df_tiempo = generar_dim_tiempo()
        pg.upsert_dataframe(df_tiempo, 'dim_tiempo',
                            claves_negocio=['fecha_completa'], modo='upsert')

        # ── 2. Dimensiones (SCD Tipo 1 y 2) ───────────────────────────────
        for tabla_destino, sql, params, transform_fn, modo, clave in [
            ('dim_cliente',    SQL_CLIENTES,  (config.CODEMP,),
             transformar_clientes,  'upsert', ['codemp','codcli']),
            ('dim_producto',   SQL_PRODUCTOS, (config.CODEMP,),
             transformar_productos, 'upsert', ['codemp','codart']),
        ]:
            logger.info(f"Extrayendo {tabla_destino}...")
            df_raw = sa.query_to_dataframe(sql, params=params,
                                           chunksize=config.BATCH_SIZE)
            df_tf  = transform_fn(df_raw)
            pg.upsert_dataframe(df_tf, tabla_destino, clave, modo)

        # ── 3. Tabla de Hechos con carga incremental ───────────────────────
        logger.info("Extrayendo Fact_Ventas_Detalle (incremental)...")
        df_ventas_raw = sa.query_to_dataframe(
            SQL_VENTAS,
            params=(config.CODEMP, config.FECHA_DESDE),
            chunksize=config.BATCH_SIZE
        )
        df_ventas = transformar_ventas(df_ventas_raw)
        # Resolución de SKs mediante lookup en memoria
        df_ventas = resolver_sks(df_ventas, pg)
        pg.upsert_dataframe(df_ventas, 'fact_ventas_detalle',
                            claves_negocio=['codemp','num_factura','num_renglon'],
                            modo='upsert')

        # ── 4. Fact_Movimientos_Inventario ─────────────────────────────────
        logger.info("Extrayendo Fact_Movimientos_Inventario...")
        df_kardex_raw = sa.query_to_dataframe(
            SQL_KARDEX, params=(config.CODEMP, config.CODEMP),
            chunksize=config.BATCH_SIZE
        )
        df_kardex = transformar_kardex(df_kardex_raw)
        df_kardex = resolver_sks_kardex(df_kardex, pg)
        pg.upsert_dataframe(df_kardex, 'fact_movimientos_inventario',
                            claves_negocio=['codemp','num_documento','num_renglon',
                                            'tipo_org','codart','codalm'],
                            modo='upsert')

    fin = datetime.now()
    logger.info(f"═══ PIPELINE COMPLETADO — Duración: {fin - inicio} ═══")


def resolver_sks(df: pd.DataFrame, pg: PostgresConnector) -> pd.DataFrame:
    """Resuelve claves sustitutas (SK) haciendo lookup contra las dimensiones."""
    engine = pg.connect()
    schema = pg.config.PG_SCHEMA

    dim_tiempo   = pd.read_sql(f"SELECT tiempo_sk, fecha_completa FROM {schema}.dim_tiempo", engine)
    dim_cliente  = pd.read_sql(f"SELECT cliente_sk, codemp, codcli FROM {schema}.dim_cliente WHERE es_vigente", engine)
    dim_producto = pd.read_sql(f"SELECT producto_sk, codemp, codart FROM {schema}.dim_producto WHERE es_vigente", engine)
    dim_vendedor = pd.read_sql(f"SELECT vendedor_sk, codemp, codven FROM {schema}.dim_vendedor", engine)
    dim_almacen  = pd.read_sql(f"SELECT almacen_sk, codemp, codalm FROM {schema}.dim_almacen", engine)
    dim_sucursal = pd.read_sql(f"SELECT sucursal_sk, codigo_sucursal FROM {schema}.dim_sucursal", engine)

    # Normalizar tipos para el merge
    dim_tiempo['fecha_completa']   = pd.to_datetime(dim_tiempo.fecha_completa).dt.date
    df['fecha_factura']            = pd.to_datetime(df.fecha_factura).dt.date

    df = (df
          .merge(dim_tiempo,   left_on='fecha_factura', right_on='fecha_completa', how='left')
          .merge(dim_cliente,  on=['codemp','codcli'],  how='left')
          .merge(dim_producto, on=['codemp','codart'],  how='left')
          .merge(dim_vendedor, on=['codemp','codven'],  how='left')
          .merge(dim_almacen,  on=['codemp','codalm'],  how='left'))

    df['codigo_sucursal'] = df['codemp'] + df['establ']
    df = df.merge(dim_sucursal, on='codigo_sucursal', how='left')

    # Reemplazar NaN en SKs con -1 (dimensión 'Desconocido')
    for sk in ['tiempo_sk','cliente_sk','producto_sk','vendedor_sk','almacen_sk','sucursal_sk']:
        df[sk] = df[sk].fillna(-1).astype(int)

    return df


def resolver_sks_kardex(df: pd.DataFrame, pg: PostgresConnector) -> pd.DataFrame:
    """Resuelve SKs para el Kardex."""
    engine = pg.connect()
    schema = pg.config.PG_SCHEMA
    dim_tiempo   = pd.read_sql(f"SELECT tiempo_sk, fecha_completa FROM {schema}.dim_tiempo", engine)
    dim_producto = pd.read_sql(f"SELECT producto_sk, codemp, codart FROM {schema}.dim_producto WHERE es_vigente", engine)
    dim_almacen  = pd.read_sql(f"SELECT almacen_sk, codemp, codalm FROM {schema}.dim_almacen", engine)

    dim_tiempo['fecha_completa'] = pd.to_datetime(dim_tiempo.fecha_completa).dt.date
    df['fecha_movimiento']       = pd.to_datetime(df.fecha_movimiento).dt.date

    df = (df
          .merge(dim_tiempo,   left_on='fecha_movimiento', right_on='fecha_completa', how='left')
          .merge(dim_producto, on=['codemp','codart'], how='left')
          .merge(dim_almacen,  on=['codemp','codalm'], how='left'))

    df['es_entrada'] = df['sigdoc'] == '+'
    df['es_salida']  = df['sigdoc'] == '-'
    df['cantidad_movimiento'] = df.apply(
        lambda r: r['cantot'] if r['es_entrada'] else -r['cantot'], axis=1)

    for sk in ['tiempo_sk','producto_sk','almacen_sk']:
        df[sk] = df[sk].fillna(-1).astype(int)

    return df


if __name__ == '__main__':
    cfg = ETLConfig()
    run_etl(cfg)
```

---

## 4.6 requirements.txt

```
pyodbc>=5.0.0
sqlalchemy>=2.0.0
psycopg2-binary>=2.9.0
pandas>=2.0.0
numpy>=1.26.0
python-dotenv>=1.0.0
```

---

## 4.7 Estrategia de Carga Incremental vs. Completa

| Tabla                         | Estrategia             | Criterio de Incremento  | Frecuencia   |
| ----------------------------- | ---------------------- | ----------------------- | ------------ |
| `Dim_Tiempo`                  | Generación algorítmica | N/A                     | Anual        |
| `Dim_Cliente`                 | Upsert SCD-2           | `fecult > último_etl`   | Diaria       |
| `Dim_Producto`                | Upsert SCD-2           | `fecult > último_etl`   | Diaria       |
| `Dim_Vendedor`                | Truncate + Recarga     | Tabla pequeña           | Diaria       |
| `Fact_Ventas_Detalle`         | Upsert por ventana     | `fecfac >= fecha_desde` | Diaria       |
| `Fact_Movimientos_Inventario` | Append incremental     | `fecdoc >= último_etl`  | Cada 4 horas |
| `Fact_Inventario_Snapshot`    | Truncate + Snapshot    | Snapshot completo       | Mensual      |
| `Fact_Cobros_CXC`             | Upsert                 | `fecult > último_etl`   | Diaria       |
| `Fact_Logs_Auditoria`         | Append                 | `fecult > último_etl`   | Cada hora    |

---

## 4.8 Tabla de Control ETL

```sql
-- PostgreSQL: Control de ejecuciones del pipeline
CREATE TABLE edw.etl_control (
    id              SERIAL PRIMARY KEY,
    tabla_destino   VARCHAR(60) NOT NULL,
    ultimo_etl_ok   TIMESTAMP,
    registros_carg  BIGINT DEFAULT 0,
    estado          VARCHAR(15),      -- RUNNING, SUCCESS, FAILED
    duracion_seg    INTEGER,
    mensaje_error   TEXT,
    fecha_ejecucion TIMESTAMP DEFAULT NOW()
);

-- Función para actualizar el control desde Python
-- (llamar con pg_loader.update_control(tabla, registros, estado))
```

---

_Documento generado el 2026-06-29. Versión 1.0._
_Arquitectura: SAP SQL Anywhere (origen) → ETL Python/Pandas → PostgreSQL EDW (destino)_
