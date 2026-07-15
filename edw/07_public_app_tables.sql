-- ============================================================
-- TABLAS DE APLICACIÓN — Esquema: public
-- Motor: PostgreSQL 16 | Base: edw (postgres_edw Docker)
-- Separadas del esquema analítico edw.* por diseño
-- Propósito: Autenticación, autorización y acceso a la plataforma web
-- ============================================================

-- ── 1. Tabla de Roles (catálogo cerrado) ─────────────────────
CREATE TABLE IF NOT EXISTS public.roles (
    id              SERIAL PRIMARY KEY,
    nombre          VARCHAR(50) NOT NULL UNIQUE,
    descripcion     VARCHAR(200),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE public.roles IS
    'Catálogo de roles del sistema web. 4 roles fijos del negocio: 
     gerencia, administrador, ventas, bodega.';

COMMENT ON COLUMN public.roles.nombre IS
    'Identificador único del rol. Valores: gerencia, administrador, ventas, bodega';

-- ── 2. Tabla de Usuarios (acceso a la plataforma web) ────────
CREATE TABLE IF NOT EXISTS public.usuarios (
    id                      SERIAL PRIMARY KEY,
    nombre                  VARCHAR(100) NOT NULL,
    email                   VARCHAR(100) NOT NULL UNIQUE,
    hashed_password         VARCHAR(255) NOT NULL,
    rol_id                  INTEGER NOT NULL REFERENCES public.roles(id) ON DELETE RESTRICT,
    sucursal                VARCHAR(50),          -- Filtro de seguridad a nivel de fila (row-level security)
    id_vendedor_origen      VARCHAR(15) UNIQUE,   -- Código SAP del vendedor para filtros analíticos en JWT
    codalm                  VARCHAR(10),          -- Código de almacén (edw.Dim_Almacen.codalm) para usuarios rol bodega; NULL = todos los almacenes
    es_activo               BOOLEAN NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE public.usuarios IS
    'Usuarios con acceso a la plataforma web BI. INDEPENDIENTE de edw.Dim_Usuario 
     (que es analítica). Aquí solo viven los empleados autorizados a usar el dashboard.';

COMMENT ON COLUMN public.usuarios.id_vendedor_origen IS
    'Código del vendedor en el sistema SAP origen (codven). Se inyecta en el JWT para 
     que el backend filtre automáticamente dw.fact_ventas sin consultar la BD en cada request.';

COMMENT ON COLUMN public.usuarios.sucursal IS
    'Sucursal asignada al usuario (filtro row-level-security).
     Se inyecta en JWT para restricciones analíticas automáticas.';

COMMENT ON COLUMN public.usuarios.codalm IS
    'Código de almacén (edw.Dim_Almacen.codalm) para usuarios con rol bodega.
     NULL = acceso a todos los almacenes (panel Administrador).';

-- ── Índices ───────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_usuarios_email ON public.usuarios(email);
CREATE INDEX IF NOT EXISTS idx_usuarios_rol_id ON public.usuarios(rol_id);
CREATE INDEX IF NOT EXISTS idx_usuarios_es_activo ON public.usuarios(es_activo);

-- ── Trigger: updated_at automático ───────────────────────────
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_usuarios_updated_at ON public.usuarios;
CREATE TRIGGER trg_usuarios_updated_at
    BEFORE UPDATE ON public.usuarios
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ── 3. Tabla Cliente Lookup (PII) ───────────────────────────
CREATE TABLE IF NOT EXISTS public.cliente_lookup (
    hash_anonimo VARCHAR(64) PRIMARY KEY,
    id_cliente_transaccional VARCHAR(50) NOT NULL,
    nombre_cliente VARCHAR(200),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE public.cliente_lookup IS
    'Tabla aislada para mapeo y desanonimización de clientes.';

-- ── 4. Telemetría del módulo Venta Cruzada (Cross-Selling) ───
-- Ver docs/auditoria/25_modulo_cross_selling.md y regla de negocio RN-CS2
-- (02_reglas_negocio_validadas.md §17). Grano: un evento por sugerencia mostrada/aceptada.
CREATE TABLE IF NOT EXISTS public.recomendaciones_eventos (
    id                      BIGSERIAL PRIMARY KEY,
    fecha                   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    usuario_id              INTEGER REFERENCES public.usuarios(id) ON DELETE SET NULL,
    cliente_sk              INTEGER,
    producto_origen_cod     VARCHAR(20) NOT NULL,
    producto_sugerido_cod   VARCHAR(20) NOT NULL,
    score_lift              NUMERIC(12, 6),
    motivo                  TEXT,
    evento                  VARCHAR(20) NOT NULL,
    fecha_carga             TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT check_evento_valido CHECK (evento IN ('mostrada', 'aceptada', 'rechazada'))
);

COMMENT ON TABLE public.recomendaciones_eventos IS
    'Telemetría del módulo de Venta Cruzada: registra cada sugerencia mostrada/aceptada/
     rechazada al vendedor para calcular la tasa de conversión (RN-CS2). No es un hecho
     analítico del EDW -- vive en public.* como metas_comerciales_operativas.';

CREATE INDEX IF NOT EXISTS idx_recomendaciones_eventos_fecha ON public.recomendaciones_eventos(fecha);
CREATE INDEX IF NOT EXISTS idx_recomendaciones_eventos_evento ON public.recomendaciones_eventos(evento);

-- ── 5. Comisiones Variables (docs/features/plan_integracion_comisiones_variables.md,
-- docs/auditoria/30_comisiones_variables.md) ─────────────────────────────────────
-- Espejo del DDL para volúmenes nuevos; en desarrollo estas tablas también se crean
-- vía `Base.metadata.create_all` (app/models/commission_config.py) al arrancar el
-- backend -- ambos caminos deben mantenerse sincronizados.

CREATE TABLE IF NOT EXISTS public.comision_matriz_categorias (
    id                  SERIAL PRIMARY KEY,
    clase               VARCHAR(5)  NOT NULL,      -- edw.dim_producto.clase; '*' = default
    subclase            VARCHAR(5),                -- NULL = toda la clase
    grupo               VARCHAR(1)  NOT NULL CHECK (grupo IN ('A','B','C','S','X')),
    tasa_pct            NUMERIC(6,3) NOT NULL CHECK (tasa_pct >= 0 AND tasa_pct <= 100),
    base                VARCHAR(10) NOT NULL DEFAULT 'margen' CHECK (base IN ('margen','valor')),
    factor_estrategico  NUMERIC(4,2) NOT NULL DEFAULT 1.0 CHECK (factor_estrategico >= 0.5 AND factor_estrategico <= 1.5),
    vigente_desde       DATE NOT NULL,
    vigente_hasta       DATE,
    creado_por          INTEGER REFERENCES public.usuarios(id) ON DELETE SET NULL,
    fecha_creacion      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
COMMENT ON TABLE public.comision_matriz_categorias IS
    'Matriz de tasas por categoría (grupo A/B/C/S/X) del esquema de Comisiones Variables.
     Indexada por código clase/subclase (edw.dim_producto.nombre_clase está 100% vacío en
     el catálogo actual, ver auditoría 30 H2). Con vigencias: nunca se edita historia.';

CREATE INDEX IF NOT EXISTS idx_comision_matriz_vigencia
    ON public.comision_matriz_categorias(clase, subclase, vigente_desde, vigente_hasta);

CREATE TABLE IF NOT EXISTS public.comision_factores_credito (
    id                  SERIAL PRIMARY KEY,
    dias_desde          INTEGER NOT NULL CHECK (dias_desde >= 0),
    dias_hasta          INTEGER,                   -- NULL = sin tope superior
    factor              NUMERIC(4,2) NOT NULL CHECK (factor >= 0 AND factor <= 1.5),
    pct_al_facturar     NUMERIC(5,2) NOT NULL DEFAULT 100.0,  -- reservado fase 2 (split cobranza)
    vigente_desde       DATE NOT NULL,
    vigente_hasta       DATE
);
COMMENT ON TABLE public.comision_factores_credito IS
    'Factores de ajuste por plazo de crédito de la venta. Auditoría 30 (H4): el EDW actual
     solo tiene tráfico real en 0 y 30 días -- los tramos > 30 días son configuración
     latente sin datos históricos que la respalden todavía.';

CREATE TABLE IF NOT EXISTS public.comision_config_vendedor (
    id                  SERIAL PRIMARY KEY,
    id_vendedor_origen  VARCHAR(15) NOT NULL UNIQUE,
    tipo                VARCHAR(10) NOT NULL DEFAULT 'externo' CHECK (tipo IN ('externo','interno')),
    factor_tipo         NUMERIC(4,2) NOT NULL DEFAULT 1.0 CHECK (factor_tipo >= 0 AND factor_tipo <= 1.5),
    fecha_ingreso       DATE,
    activo              BOOLEAN NOT NULL DEFAULT TRUE
);
COMMENT ON TABLE public.comision_config_vendedor IS
    'Tipo (externo/interno) y parámetros de comisión por vendedor -- cubre la brecha B1
     (auditoría 30): edw.dim_vendedor no distingue externo/interno ni tiene fecha de
     ingreso, así que se gestiona en public.* por gerencia, no en el EDW.';

CREATE TABLE IF NOT EXISTS public.comision_liquidaciones (
    id                  SERIAL PRIMARY KEY,
    anio                INTEGER NOT NULL,
    mes                 INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),
    id_vendedor_origen  VARCHAR(15) NOT NULL,
    esquema             VARCHAR(10) NOT NULL CHECK (esquema IN ('plana','variable')),
    modo                VARCHAR(10) NOT NULL CHECK (modo IN ('sombra','oficial')),
    comision_total      NUMERIC(15,4) NOT NULL,
    detalle_json        JSONB NOT NULL,
    fecha_calculo       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (anio, mes, id_vendedor_origen, esquema, modo)
);
COMMENT ON TABLE public.comision_liquidaciones IS
    'Snapshot congelado de una liquidación mensual (piloto en sombra y cierre oficial).
     detalle_json guarda el desglose línea/categoría/crédito/bonos completo -- salvaguarda
     6 (transparencia total): el vendedor ve exactamente cómo se calculó cada peso.';

CREATE INDEX IF NOT EXISTS idx_comision_liquidaciones_periodo
    ON public.comision_liquidaciones(anio, mes, id_vendedor_origen);
