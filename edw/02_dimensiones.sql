-- ============================================================
-- ARQUITECTURA DATA WAREHOUSE — DIMENSIONES (PostgreSQL 16)
-- ============================================================

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
COMMENT ON TABLE edw.Dim_Fecha IS 'Dimensión temporal conformada para agregaciones.';

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
COMMENT ON TABLE edw.Dim_Sucursal IS 'Establecimientos y puntos de venta.';

-- ── 3. DIM_ALMACEN ──
CREATE TABLE edw.Dim_Almacen (
    almacen_sk      SERIAL PRIMARY KEY,
    codemp          VARCHAR(2) NOT NULL,
    codalm          VARCHAR(10) NOT NULL,
    nombre_almacen  VARCHAR(100),
    establ          VARCHAR(3) NOT NULL,
    UNIQUE (codemp, codalm)
);
COMMENT ON TABLE edw.Dim_Almacen IS 'Mapeo de bodegas físicas dentro de sucursales.';

-- ── 4. DIM_PRODUCTO (SCD Tipo 2) ──
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
COMMENT ON TABLE edw.Dim_Producto IS 'Catálogo de artículos desnormalizados con SCD-2.';

-- ── 5. DIM_CLIENTE (SCD Tipo 2) ──
CREATE TABLE edw.Dim_Cliente (
    cliente_sk      SERIAL PRIMARY KEY,
    hash_anonimo    VARCHAR(64) NOT NULL,
    codemp          VARCHAR(2) NOT NULL,
    tipo_id         VARCHAR(20),
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
COMMENT ON TABLE edw.Dim_Cliente IS 'Clientes desnormalizados con vigencia histórica y SCD-2.';

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
COMMENT ON TABLE edw.Dim_Proveedor IS 'Detalle de proveedores del negocio para compras.';

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
COMMENT ON TABLE edw.Dim_Vendedor IS 'Equipo de ventas y agentes de cobranza.';

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
COMMENT ON TABLE edw.Dim_Empleado IS 'Nómina de personal y roles operativos.';

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
COMMENT ON TABLE edw.Dim_Usuario IS 'Usuarios autorizados para control en bitácora de auditoría.';

-- ── 10. DIM_FORMAPAGO ──
CREATE TABLE edw.Dim_FormaPago (
    formapago_sk     SERIAL PRIMARY KEY,
    codemp           VARCHAR(2) NOT NULL,
    codforpag        VARCHAR(10) NOT NULL,
    nombre_forma_pago VARCHAR(100),
    dias_plazo       INTEGER DEFAULT 0,
    UNIQUE (codemp, codforpag)
);
COMMENT ON TABLE edw.Dim_FormaPago IS 'Medios y modalidades de cobros y pagos.';

-- ── 11. DIM_GEOGRAFIA ──
CREATE TABLE edw.Dim_Geografia (
    geografia_sk    SERIAL PRIMARY KEY,
    pais            VARCHAR(60) NOT NULL,
    provincia       VARCHAR(60),
    canton          VARCHAR(60),
    parroquia       VARCHAR(60),
    UNIQUE (pais, provincia, canton, parroquia)
);
COMMENT ON TABLE edw.Dim_Geografia IS 'Variables territoriales desnormalizadas.';
