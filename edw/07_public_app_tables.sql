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
