-- ============================================================
-- SEED INICIAL — Roles y Usuario Administrador
-- Motor: PostgreSQL 16 | Esquema: public
-- ON CONFLICT DO NOTHING → idempotente, safe para re-runs
--
-- REFERENCIA -- solo para bootstrap de un volumen Docker NUEVO (initdb). En
-- producción, el seed de catálogo (roles) + admin inicial lo aplica la migración
-- Alembic `backend/alembic/versions/0002_seed_roles.py`
-- (docs/features/plan_migraciones_esquema_public.md), que además NO usa el hash
-- bcrypt fijo de abajo -- toma la contraseña de `ADMIN_INITIAL_PASSWORD` (env var) y
-- la hashea en el momento. El hash fijo aquí es solo para el dataset de desarrollo/
-- demo (los 3 usuarios de negocio de ejemplo: gerencia/bodega/ventas).
-- ============================================================

-- ── 1. Insertar los 4 Roles del Negocio ──────────────────────
INSERT INTO public.roles (nombre, descripcion) VALUES
    ('gerencia',      'Gerente de la empresa. Acceso total de solo lectura a todos los dashboards y KPIs globales.'),
    ('administrador', 'Administrador del sistema. Gestiona usuarios, roles y configuración de la plataforma.'),
    ('ventas',        'Vendedor asignado. Accede solo a dashboards de ventas filtrados por su sucursal y código SAP.'),
    ('bodega',        'Jefe de Bodega. Accede a dashboards de inventario y stock por sucursal asignada.')
ON CONFLICT (nombre) DO NOTHING;

-- ── 2. Insertar Usuario Administrador Inicial ─────────────────
-- IMPORTANTE: La contraseña debe cambiarse en el primer inicio de sesión.
-- Hash bcrypt de: Admin2024!Seguro (generado con bcrypt rounds=12)
-- Para generar uno nuevo: python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('TuNuevaPassword'))"
INSERT INTO public.usuarios (nombre, email, hashed_password, rol_id, sucursal, id_vendedor_origen, es_activo)
SELECT
    'Administrador Sistema',
    'admin@empresa.com',
    '$2b$12$mmzvCt9xjovV0kyHuh0ytuHJxE/OgETn6VLTC2y6OPDBrcZMn2eMa',  -- Admin2024!Seguro (passlib+bcrypt 3.2.2),
    r.id,
    NULL,  -- El administrador no tiene sucursal específica
    NULL,  -- El administrador no corresponde a un vendedor SAP
    TRUE
FROM public.roles r
WHERE r.nombre = 'administrador'
ON CONFLICT (email) DO NOTHING;

-- ── 3. Insertar Usuarios de Negocio Faltantes ─────────────────
-- Hash replicado: Admin2024!Seguro

-- Usuario Gerencia (Acceso global analítico, sin sucursal fija)
INSERT INTO public.usuarios (nombre, email, hashed_password, rol_id, sucursal, id_vendedor_origen, es_activo)
SELECT
    'Gerente Nacional',
    'gerencia@empresa.com',
    '$2b$12$mmzvCt9xjovV0kyHuh0ytuHJxE/OgETn6VLTC2y6OPDBrcZMn2eMa',
    r.id,
    NULL,
    NULL,
    TRUE
FROM public.roles r
WHERE r.nombre = 'gerencia'
ON CONFLICT (email) DO NOTHING;

-- Usuario Bodega (Sucursal específica)
INSERT INTO public.usuarios (nombre, email, hashed_password, rol_id, sucursal, id_vendedor_origen, es_activo)
SELECT
    'Bodeguero Matriz',
    'bodega_quito@empresa.com',
    '$2b$12$mmzvCt9xjovV0kyHuh0ytuHJxE/OgETn6VLTC2y6OPDBrcZMn2eMa',
    r.id,
    'Matriz Quito', -- Limita los reportes de inventario a esta sucursal (a menos que actúe el Rol global)
    NULL,
    TRUE
FROM public.roles r
WHERE r.nombre = 'bodega'
ON CONFLICT (email) DO NOTHING;

-- Usuario Ventas (Sucursal específica, asumiendo codven/id origen SAP)
INSERT INTO public.usuarios (nombre, email, hashed_password, rol_id, sucursal, id_vendedor_origen, es_activo)
SELECT
    'Vendedor Costa',
    'ventas_gye@empresa.com',
    '$2b$12$mmzvCt9xjovV0kyHuh0ytuHJxE/OgETn6VLTC2y6OPDBrcZMn2eMa',
    r.id,
    'Sucursal Guayaquil',
    102, -- ID numérico de vendedor (codven/SAP)
    TRUE
FROM public.roles r
WHERE r.nombre = 'ventas'
ON CONFLICT (email) DO NOTHING;


-- ── 4. Mensaje de verificación ───────────────────────────────
DO $$
BEGIN
    RAISE NOTICE '=== SEED COMPLETADO ===';
    RAISE NOTICE 'Roles creados:';
    RAISE NOTICE '  ID 1: gerencia';
    RAISE NOTICE '  ID 2: administrador';
    RAISE NOTICE '  ID 3: ventas';
    RAISE NOTICE '  ID 4: bodega';
    RAISE NOTICE 'Usuarios semilla insertados (password: Admin2024!Seguro).';
END $$;
