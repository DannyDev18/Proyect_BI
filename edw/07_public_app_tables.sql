-- ============================================================
-- TABLAS DE APLICACIÓN — Esquema: public
-- Motor: PostgreSQL 16 | Base: edw (postgres_edw Docker)
-- Separadas del esquema analítico edw.* por diseño
-- Propósito: Autenticación, autorización y acceso a la plataforma web
--
-- REFERENCIA -- la fuente de verdad del esquema `public` es `backend/alembic/`
-- (docs/features/plan_migraciones_esquema_public.md). Este archivo se conserva
-- funcionalmente activo (sigue ejecutándose vía /docker-entrypoint-initdb.d en un
-- volumen Docker nuevo) por dos razones, no por inercia:
--   1. `edw/09_vistas_ml.sql` crea una vista que hace JOIN contra
--      `public.cliente_lookup` en el mismo initdb -- si esta tabla se moviera a
--      "solo Alembic", esa vista fallaría al crear un volumen nuevo (Alembic recién
--      corre cuando arranca el CONTENEDOR DEL BACKEND, después de que Postgres ya
--      terminó su secuencia de initdb).
--   2. Los 3 usuarios de negocio precargados por `edw/08_seed_roles_usuarios.sql`
--      (gerencia/bodega/ventas de ejemplo) son datos de demostración, no algo que
--      Alembic deba versionar.
-- Todo cambio de ESQUEMA (agregar/quitar columnas, índices, constraints) en
-- `public.*` a partir de ahora se hace en `backend/alembic/versions/`, nunca aquí --
-- el backend detecta al arrancar si la BD fue inicializada por este archivo (existe
-- `public.usuarios`, no existe `public.alembic_version`) y la sella con
-- `alembic stamp 0001_baseline_public` antes de aplicar lo pendiente
-- (`backend/scripts/apply_migrations.py`).
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
-- Espejo del DDL para volúmenes nuevos (bootstrap initdb); la fuente de verdad para
-- cambios de esquema es `backend/alembic/versions/0001_baseline_public.py`, que crea
-- estas mismas tablas a partir de `app/models/commission_config.py`.

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
    id_vendedor_origen  VARCHAR(15) NOT NULL,
    tipo                VARCHAR(10) NOT NULL DEFAULT 'externo' CHECK (tipo IN ('externo','interno')),
    factor_tipo         NUMERIC(4,2) NOT NULL DEFAULT 1.0 CHECK (factor_tipo >= 0 AND factor_tipo <= 1.5),
    fecha_ingreso       DATE,
    activo              BOOLEAN NOT NULL DEFAULT TRUE,
    vigente_desde       DATE NOT NULL DEFAULT '1900-01-01',
    vigente_hasta       DATE
);
COMMENT ON TABLE public.comision_config_vendedor IS
    'Tipo (externo/interno) y parámetros de comisión por vendedor -- cubre la brecha B1
     (auditoría 30): edw.dim_vendedor no distingue externo/interno ni tiene fecha de
     ingreso, así que se gestiona en public.* por gerencia, no en el EDW. Con vigencias
     (C-3, docs/features/plan_correcciones_pendientes.md; auditoría 35 H4): nunca se
     edita una fila vigente, se cierra (vigente_hasta) y se inserta una nueva, para que
     una liquidación ya congelada de un período cerrado siga leyendo el tipo/factor con
     el que se calculó.';

CREATE UNIQUE INDEX IF NOT EXISTS uq_comision_config_vendedor_vigente
    ON public.comision_config_vendedor(id_vendedor_origen) WHERE vigente_hasta IS NULL;
CREATE INDEX IF NOT EXISTS idx_comision_config_vendedor_vigencia
    ON public.comision_config_vendedor(id_vendedor_origen, vigente_desde, vigente_hasta);

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

-- ── Notificaciones Inteligentes Segmentadas por Rol ─────────────────────────
-- docs/features/plan_modulo_notificaciones.md, docs/auditoria/31_modulo_notificaciones.md,
-- reglas RN-N1..RN-N4. Solo notificaciones PERSISTIDAS (eventos puntuales con estado de
-- lectura: anomalía detectada, meta generada, liquidación disponible); las calculadas al
-- vuelo (stock, forecast, churn) no tocan esta tabla.
CREATE TABLE IF NOT EXISTS public.notificaciones (
    id              BIGSERIAL PRIMARY KEY,
    tipo_evento     VARCHAR(50) NOT NULL,
    rol_destino     VARCHAR(20) NOT NULL REFERENCES public.roles(nombre) ON DELETE CASCADE,
    usuario_id      INTEGER REFERENCES public.usuarios(id) ON DELETE CASCADE,
    titulo          VARCHAR(200) NOT NULL,
    mensaje         TEXT NOT NULL,
    accion_url      VARCHAR(300),
    prioridad       VARCHAR(10) NOT NULL DEFAULT 'media' CHECK (prioridad IN ('alta','media','baja')),
    contexto        JSONB,
    leida_por       JSONB NOT NULL DEFAULT '[]',
    fecha_creacion  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    fecha_expira    TIMESTAMP WITH TIME ZONE
);
COMMENT ON TABLE public.notificaciones IS
    'Notificaciones persistidas segmentadas por rol/usuario (RN-N1). usuario_id NULL =
     visible a todo el rol_destino; leida_por acumula los ids de usuario que la marcaron
     leída en ese caso (RN-N3). contexto guarda claves de negocio (codart, id_vendedor_origen,
     etc.) usadas para RLS y para el dedupe de 24h (RN-N2). No confundir con las
     notificaciones calculadas de Bodega (warehouse_service.get_notificaciones), que nunca
     se escriben aquí.';

CREATE INDEX IF NOT EXISTS idx_notif_rol_fecha
    ON public.notificaciones(rol_destino, fecha_creacion DESC);
CREATE INDEX IF NOT EXISTS idx_notif_dedupe
    ON public.notificaciones(tipo_evento, rol_destino, fecha_creacion DESC);

-- ── 6. Metas Comerciales Operativas (regla de negocio 10, grano vendedor) ──────
-- docs/auditoria/19_.../20_decomision_goals_rf.md: grano (anio, mes, id_vendedor_origen),
-- NO por sucursal (edw.dim_vendedor no tiene sucursal propia). Espejo de app/models/goal.py
-- (C-4, docs/features/plan_correcciones_pendientes.md): esta tabla se creaba solo vía
-- `Base.metadata.create_all` y faltaba en el DDL versionado -- un despliegue desde cero
-- ejecutando edw/01..09 nunca la generaba.
CREATE TABLE IF NOT EXISTS public.metas_comerciales_operativas (
    id                      SERIAL PRIMARY KEY,
    anio                    INTEGER NOT NULL CHECK (anio >= 2020),
    mes                     INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),
    id_vendedor_origen      VARCHAR(15),
    monto_meta              NUMERIC(15, 4) NOT NULL DEFAULT 0.0000 CHECK (monto_meta >= 0),
    unidades_meta           NUMERIC(15, 4) NOT NULL DEFAULT 0.0000 CHECK (unidades_meta >= 0),
    comision_base_pct       NUMERIC(5, 2) NOT NULL DEFAULT 2.00 CHECK (comision_base_pct BETWEEN 0 AND 100),
    bono_sobrecumplimiento  NUMERIC(15, 4) NOT NULL DEFAULT 100.0000 CHECK (bono_sobrecumplimiento >= 0),
    estado                  VARCHAR(20) NOT NULL DEFAULT 'PROPUESTA'
                             CHECK (estado IN ('PROPUESTA', 'APROBADA', 'RECHAZADA')),
    approved_by             INTEGER REFERENCES public.usuarios(id) ON DELETE SET NULL,
    created_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);
COMMENT ON TABLE public.metas_comerciales_operativas IS
    'Metas comerciales generadas por IQRGoalCalculationEngine (100% estadística, sin ML --
     goals_rf fue decomisionado). Grano (anio, mes, id_vendedor_origen), NO por sucursal.
     updated_at se actualiza a nivel de aplicación (SQLAlchemy onupdate), no vía trigger --
     a diferencia de public.usuarios, esta tabla no tiene trigger de BD equivalente.';

CREATE INDEX IF NOT EXISTS idx_metas_periodo_vendedor
    ON public.metas_comerciales_operativas(anio, mes, id_vendedor_origen);

-- ── 7. Gestión de Cartera 360 (módulo Ventas) ───────────────────────────────
-- docs/features/propuesta_nuevos_modulos_roi.md §4, auditoría 32. Mismo espíritu que
-- la telemetría de Venta Cruzada (public.recomendaciones_eventos): el vendedor marca el
-- resultado de cada contacto. Espejo de app/models/gestion_cartera_evento.py (C-4).
CREATE TABLE IF NOT EXISTS public.gestion_cartera_eventos (
    id          BIGSERIAL PRIMARY KEY,
    fecha       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    usuario_id  INTEGER REFERENCES public.usuarios(id) ON DELETE SET NULL,
    cliente_sk  INTEGER,
    evento      VARCHAR(20) NOT NULL,
    motivo      TEXT,
    CONSTRAINT check_gestion_evento_valido CHECK (evento IN ('contactado', 'recompro', 'perdido'))
);
COMMENT ON TABLE public.gestion_cartera_eventos IS
    'Registro de gestión de Cartera 360: el vendedor marca el resultado de cada contacto
     con un cliente en riesgo, creando el dato de efectividad que antes no existía.
     Deduplicación de doble-click vía CARTERA360_DEDUPE_DOBLE_CLICK_SEGUNDOS (RN-V... ver
     Cartera360Repository.log_gestion).';

CREATE INDEX IF NOT EXISTS idx_gestion_cartera_dedupe
    ON public.gestion_cartera_eventos(usuario_id, cliente_sk, evento, fecha DESC);

-- ── 8. Triage de Anomalías (módulo Admin, Fase 2) ───────────────────────────
-- docs/features/plan_correcciones_pendientes.md §3 Admin item 1; auditoría 36 confirmó
-- que GET /admin/anomalies es una consulta puntual por transacción, no un listado --
-- esta tabla convierte cada detección en un ítem de trabajo con estado, en vez de un
-- resultado que se pierde al cerrar la pantalla. Espejo de app/models/anomalia_revision.py.
CREATE TABLE IF NOT EXISTS public.anomalias_revisiones (
    id              SERIAL PRIMARY KEY,
    transaccion_id  VARCHAR(50) NOT NULL UNIQUE,
    score           NUMERIC(10, 4) NOT NULL,
    estado          VARCHAR(20) NOT NULL DEFAULT 'nueva'
                     CHECK (estado IN ('nueva', 'revisada', 'descartada', 'confirmada')),
    revisor_id      INTEGER REFERENCES public.usuarios(id) ON DELETE SET NULL,
    nota            TEXT,
    fecha_deteccion TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    fecha_revision  TIMESTAMP WITH TIME ZONE
);
COMMENT ON TABLE public.anomalias_revisiones IS
    'Una fila por transacción calificada como anómala por Isolation Forest. Se crea (si
     no existe ya, UNIQUE en transaccion_id) cuando GET /admin/anomalies detecta
     es_anomalia=True. El dashboard de Admin separa "nueva" de las ya trabajadas
     (revisada/descartada/confirmada) -- lo que convierte el detector en herramienta de
     trabajo en vez de un resultado puntual que se pierde al cerrar la pantalla.';

CREATE INDEX IF NOT EXISTS idx_anomalias_revisiones_estado
    ON public.anomalias_revisiones(estado, fecha_deteccion DESC);

-- ── 9. Intentos de login fallidos (módulo Admin, panel de salud, Fase 2) ────────
-- docs/features/plan_correcciones_pendientes.md §3 Admin item 2: antes no se
-- registraban en absoluto. Espejo de app/models/login_intento_fallido.py.
CREATE TABLE IF NOT EXISTS public.intentos_login_fallidos (
    id      BIGSERIAL PRIMARY KEY,
    email   VARCHAR(100) NOT NULL,
    ip      VARCHAR(45),
    fecha   TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);
COMMENT ON TABLE public.intentos_login_fallidos IS
    'Un intento de login con credenciales incorrectas. Best-effort: un fallo al escribir
     aquí no debe tumbar el login (POST /auth/login). Alimenta el conteo de "logins
     fallidos" del panel de salud del sistema (GET /analytics/admin/system-health).';

CREATE INDEX IF NOT EXISTS idx_login_fallidos_fecha ON public.intentos_login_fallidos(fecha DESC);
