-- ============================================================
-- SCRIPT DE VERIFICACIÓN DE DESPLIEGUE — DATA WAREHOUSE
-- Motor: PostgreSQL 16 | Schema: edw
-- ============================================================

\echo 'Iniciando verificación del Data Warehouse...'

-- 1. Verificar existencia del esquema
SELECT schema_name 
FROM information_schema.schemata 
WHERE schema_name = 'edw';

-- 2. Reportar todas las tablas cargadas en el esquema edw y contar sus columnas
SELECT 
    table_name AS "Tabla",
    (SELECT count(*) FROM information_schema.columns WHERE table_schema = 'edw' AND table_name = t.table_name) AS "Cant. Columnas"
FROM information_schema.tables t
WHERE table_schema = 'edw' AND table_type = 'BASE TABLE'
ORDER BY table_name;

-- 3. Resumen y validación exhaustiva de Dimensiones vs Hechos esperadas
WITH tablas_esperadas AS (
    SELECT unnest(ARRAY[
        -- Dimensiones (11)
        'dim_fecha', 'dim_sucursal', 'dim_almacen', 'dim_producto', 'dim_cliente', 
        'dim_proveedor', 'dim_vendedor', 'dim_empleado', 'dim_usuario', 'dim_formapago', 
        'dim_geografia',
        -- Hechos (11)
        'fact_ventas_detalles', 'fact_ventas_detalle', 'fact_inventario_snapshot', 'fact_movimientos_inventario',
        'fact_compras', 'fact_cobros_cxc', 'fact_pagos_cxp', 'fact_nomina', 
        'fact_movimientos_caja', 'fact_metas_comerciales', 'fact_logs_auditoria', 
        'fact_devoluciones', 'etl_control'
    ]) AS tabla
),
tablas_existentes AS (
    SELECT table_name AS tabla 
    FROM information_schema.tables 
    WHERE table_schema = 'edw' AND table_type = 'BASE TABLE'
)
SELECT 
    te.tabla AS "Tabla Requerida",
    CASE 
        WHEN tx.tabla IS NOT NULL THEN '¡COMPLETA! (Creada en BD)'
        ELSE 'FALTA'
    END AS "Estado"
FROM tablas_esperadas te
LEFT JOIN tablas_existentes tx ON LOWER(te.tabla) = LOWER(tx.tabla)
-- Excluir variaciones de nombres obsoletos si no corresponden
WHERE te.tabla <> 'fact_ventas_detalles' OR tx.tabla IS NOT NULL
ORDER BY te.tabla;

-- 4. Validar integridad de relaciones (Conteo de Llaves Foráneas)
SELECT 
    tc.table_name AS "Tabla Hecho/Origen", 
    kcu.column_name AS "Columna Llave Foránea", 
    ccu.table_name AS "Tabla Dimensión Referenciada"
FROM 
    information_schema.table_constraints AS tc 
    JOIN information_schema.key_column_usage AS kcu
      ON tc.constraint_name = kcu.constraint_name
      AND tc.table_schema = kcu.table_schema
    JOIN information_schema.constraint_column_usage AS ccu
      ON ccu.constraint_name = tc.constraint_name
      AND ccu.table_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'edw'
ORDER BY tc.table_name, kcu.column_name;
