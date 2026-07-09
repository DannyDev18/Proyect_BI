# Patrones SQL de validación — Producción vs EDW

Adaptar nombres de tablas/columnas al caso. Regla de oro: **comparar con el mismo recorte en
ambos lados** — misma empresa (`codemp='01'`), mismo rango de fechas, mismo filtro de estado
(`estado='P'`), mismo criterio de inventariable (`desinv='S'` cuando aplique costo). La mayoría
de las "diferencias" reportadas resultan ser recortes distintos; descarta eso primero.

Contra SAP: solo `SELECT` (sin `INTO`, sin procedimientos). Contra el EDW:
`docker exec bi_postgres_edw psql -U etl_user -d edw -c "..."` o SQLAlchemy con credenciales de `.env`.

## 1. Conteo y sumatorias (reconciliación básica)

Producción (SAP — sintaxis SQL Anywhere):

```sql
SELECT COUNT(*)            AS filas,
       SUM(r.cantidad)     AS unidades,
       SUM(r.total)        AS monto,
       MIN(e.fecemi)       AS fecha_min,
       MAX(e.fecemi)       AS fecha_max
FROM renglonesfacturas r
JOIN encabezadofacturas e
  ON e.codemp = r.codemp AND e.establ = r.establ
 AND e.puntoemi = r.puntoemi AND e.numdoc = r.numdoc
WHERE e.codemp = '01' AND e.estado = 'P'
  AND e.fecemi BETWEEN '2024-01-01' AND '2024-12-31';
```

EDW (mismo recorte, resolviendo la fecha real vía dim_fecha):

```sql
SELECT COUNT(*)              AS filas,
       SUM(f.cantidad)       AS unidades,
       SUM(f.total_linea)    AS monto,
       MIN(d.fecha_completa) AS fecha_min,
       MAX(d.fecha_completa) AS fecha_max
FROM edw.fact_ventas_detalle f
JOIN edw.dim_fecha d ON d.fecha_sk = f.fecha_sk
WHERE d.fecha_completa BETWEEN '2024-01-01' AND '2024-12-31'
  AND f.estado_factura = 'A' IS NOT TRUE;  -- verificar qué guarda realmente el ETL aquí
```

Si difieren, **bisecar por periodo** (año → mes → día) hasta aislar las fechas exactas con
diferencia, y luego comparar documentos individuales (`num_factura`) de ese día.

## 2. Diferencia a nivel documento (encontrar EXACTAMENTE qué falta o sobra)

Extraer del EDW los documentos del día problemático y compararlos contra el listado de SAP
(mismo día, mismo recorte). Documentos en SAP que no están en el EDW = pérdida en
extracción/filtro; documentos en el EDW que no están en SAP = duplicado, carga no idempotente o
documento anulado después de cargado.

```sql
-- EDW: documentos y montos del día
SELECT f.num_factura, COUNT(*) AS lineas, SUM(f.total_linea) AS monto
FROM edw.fact_ventas_detalle f
JOIN edw.dim_fecha d ON d.fecha_sk = f.fecha_sk
WHERE d.fecha_completa = '2024-03-15'
GROUP BY f.num_factura ORDER BY f.num_factura;
```

## 3. Duplicados (contra el grain declarado)

```sql
-- El grain de fact_ventas_detalle es línea de factura:
SELECT num_factura, producto_sk, COUNT(*) AS n
FROM edw.fact_ventas_detalle
GROUP BY num_factura, producto_sk
HAVING COUNT(*) > 1
ORDER BY n DESC LIMIT 50;
```

Ojo: puede haber >1 línea legítima del mismo producto en una factura (precios distintos). Antes
de declarar duplicado, verifica contra SAP si el documento origen realmente tiene esas líneas.
Duplicado real típico de este proyecto: cargas repetidas sin idempotencia (comparar
`fecha_carga` de las filas repetidas — si difieren entre corridas, es re-carga).

## 4. Llaves huérfanas / centinela -1

```sql
-- % de hechos que cayeron al registro desconocido, por dimensión:
SELECT 'cliente' AS dim, COUNT(*) FILTER (WHERE cliente_sk = -1) AS al_centinela,
       COUNT(*) AS total,
       ROUND(100.0 * COUNT(*) FILTER (WHERE cliente_sk = -1) / COUNT(*), 2) AS pct
FROM edw.fact_ventas_detalle
UNION ALL
SELECT 'producto', COUNT(*) FILTER (WHERE producto_sk = -1), COUNT(*),
       ROUND(100.0 * COUNT(*) FILTER (WHERE producto_sk = -1) / COUNT(*), 2)
FROM edw.fact_ventas_detalle;
```

Un % creciente entre cargas indica dimensiones desactualizadas (orden de carga) o business keys
nuevas en el origen no contempladas por el extractor de la dimensión.

## 5. Integridad referencial y SCD2

```sql
-- FKs rotas (no debería haber ninguna, hay FKs físicas — verificar igualmente tras cargas masivas):
SELECT COUNT(*) FROM edw.fact_ventas_detalle f
LEFT JOIN edw.dim_producto p ON p.producto_sk = f.producto_sk
WHERE p.producto_sk IS NULL;

-- SCD2: más de una versión vigente por business key (corrupción de historial):
SELECT codemp, codart, COUNT(*) AS vigentes
FROM edw.dim_producto WHERE es_vigente = TRUE
GROUP BY codemp, codart HAVING COUNT(*) > 1;

-- SCD2: solapamiento de vigencias:
SELECT a.codart, a.producto_sk, b.producto_sk
FROM edw.dim_producto a
JOIN edw.dim_producto b
  ON a.codemp = b.codemp AND a.codart = b.codart AND a.producto_sk < b.producto_sk
WHERE a.fecha_inicio_vigencia <= COALESCE(b.fecha_fin_vigencia, '9999-12-31')
  AND b.fecha_inicio_vigencia <= COALESCE(a.fecha_fin_vigencia, '9999-12-31');

-- Hechos apuntando a la versión equivocada (fecha del hecho fuera de la vigencia de la dim):
SELECT COUNT(*)
FROM edw.fact_ventas_detalle f
JOIN edw.dim_fecha d    ON d.fecha_sk = f.fecha_sk
JOIN edw.dim_producto p ON p.producto_sk = f.producto_sk
WHERE p.producto_sk <> -1
  AND (d.fecha_completa < p.fecha_inicio_vigencia
       OR d.fecha_completa > COALESCE(p.fecha_fin_vigencia, '9999-12-31'));
```

## 6. Fechas fuera de rango y códigos inexistentes

```sql
-- Fechas del hecho sin resolver o fuera del rango de dim_fecha:
SELECT MIN(fecha_completa), MAX(fecha_completa) FROM edw.dim_fecha;
SELECT COUNT(*) FROM edw.fact_ventas_detalle WHERE fecha_sk = -1;

-- Fechas futuras (sospechoso salvo pedidos programados):
SELECT COUNT(*) FROM edw.fact_ventas_detalle f
JOIN edw.dim_fecha d ON d.fecha_sk = f.fecha_sk
WHERE d.fecha_completa > CURRENT_DATE;
```

## 7. Volumen entre cargas (etl_control)

```sql
SELECT tabla_destino, fecha_ejecucion::date AS dia, estado, registros_carg, duracion_seg
FROM edw.etl_control
ORDER BY fecha_ejecucion DESC LIMIT 40;

-- Saltos anómalos de volumen por tabla (comparar cargas consecutivas SUCCESS):
SELECT tabla_destino, fecha_ejecucion, registros_carg,
       registros_carg - LAG(registros_carg) OVER (PARTITION BY tabla_destino ORDER BY fecha_ejecucion) AS delta
FROM edw.etl_control WHERE estado = 'SUCCESS'
ORDER BY tabla_destino, fecha_ejecucion DESC;
```

## 8. Kardex / inventario (reglas específicas del proyecto)

```sql
-- La dirección debe venir de tipdoc, no del signo. Verificar el balance de transferencias en SAP:
SELECT tipdoc, COUNT(*) FROM kardex
WHERE codemp = '01' AND tiporg = 'TRA'
GROUP BY tipdoc;  -- EN y SA deben estar perfectamente pareados

-- En el EDW, entradas vs salidas jamás simultáneas:
SELECT COUNT(*) FROM edw.fact_movimientos_inventario
WHERE es_entrada = es_salida;  -- 0 esperado (ni ambas TRUE ni ambas FALSE)
```

## 9. Aislar la etapa donde nace una diferencia

Cuando origen y destino difieren, ejecuta la misma métrica en cada etapa del pipeline:

1. **SAP crudo** (consulta del extractor renderizada a mano con los tokens del `.env`).
2. **DataFrame post-transformer** (script local: correr extractor + transformer sin cargar,
   imprimir conteos/sumas).
3. **EDW final** (consulta equivalente).

La etapa donde el número cambia es donde está el bug. Documenta las tres cifras como evidencia.
