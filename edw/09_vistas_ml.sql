-- ============================================================
-- VISTAS PARA MACHINE LEARNING — Esquema: ml
-- ============================================================

CREATE SCHEMA IF NOT EXISTS ml;

-- Vista para uso en Notebooks (EDA y Entrenamiento)
CREATE OR REPLACE VIEW ml.v_ventas_cruzadas_desanonima AS
SELECT 
    f.fecha_sk,
    f.cliente_sk,
    c.hash_anonimo,
    l.nombre_cliente,
    p.nombre_articulo,
    f.cantidad
FROM edw.fact_ventas_detalle f
JOIN edw.dim_cliente c ON f.cliente_sk = c.cliente_sk
JOIN public.cliente_lookup l ON c.hash_anonimo = l.hash_anonimo
JOIN edw.dim_producto p ON f.producto_sk = p.producto_sk;
