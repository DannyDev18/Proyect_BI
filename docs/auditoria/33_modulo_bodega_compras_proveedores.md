# Auditoría 33 — Validación de datos para el módulo Bodega: Compras y Proveedores

> **Estado (2026-07-14):** el módulo se implementó y se retiró después por decisión de producto
> (no por un problema de datos). El resto del contenido queda como registro histórico de la
> validación, incluido el hallazgo H1 (lead time real no medible con los datos actuales), útil
> si el módulo se retoma en el futuro.

- **Fecha:** 2026-07-14
- **Alcance:** `edw.fact_compras`, `edw.fact_movimientos_inventario`, `edw.dim_proveedor`,
  `edw.dim_producto`, y el código existente de "necesidad de compra"
  (`backend/app/repositories/warehouse_repository.py`, `backend/app/services/warehouse_service.py`).
  Validación previa al diseño del módulo propuesto en
  `docs/features/propuesta_nuevos_modulos_roi.md` §3 (Compras y Proveedores, Bodega).
- **Método:** `SELECT` puro contra el EDW. **No se ejecutó ninguna escritura contra Producción
  ni contra el EDW.**

## Hallazgos

### 🔴 Alta — H1: el "lead time real" propuesto (días entre compra y entrada a kardex) no es medible — `fact_compras` ES el evento de recepción, no de pedido

- **Evidencia:**
  ```sql
  -- Pareo fact_compras <-> kardex CPA por (num_factura = num_documento, producto_sk)
  -- 131,590 pares emparejados (77.2% de 170,514 compras)
  SELECT (fm.fecha_sk - fc.fecha_sk) AS delta_fecha_sk, COUNT(*)
  FROM edw.fact_compras fc
  JOIN edw.fact_movimientos_inventario fm
    ON fm.tipo_movimiento = 'CPA' AND fm.num_documento = fc.num_factura AND fm.producto_sk = fc.producto_sk
  GROUP BY 1;
  -- delta_fecha_sk = 0 para el 100% de los pares emparejados
  ```
  `fact_compras.fecha_sk` (factura de compra) y la entrada `CPA` correspondiente en el kardex
  caen en la **misma fecha, siempre, sin excepción**, sobre 131,590 pares verificados. Esto
  confirma que `fact_compras` en este EDW captura el evento de **recepción/facturación de la
  mercadería**, no la fecha en que se colocó la orden de compra al proveedor — el ERP extraído
  no tiene una tabla de cabecera de orden de compra con fecha de pedido separada de la fecha de
  factura/ingreso.
- **Impacto:** el deliverable "lead time real por proveedor y artículo" tal como está en la
  propuesta §3.2 **no se puede calcular** con los datos actuales — el resultado sería
  literalmente 0 días para todo, sin información real. Este era exactamente el riesgo que la
  propia propuesta anticipaba en su tabla de viabilidad §3.5 ("Validar primero... si el pareo
  documento a documento no existe").
- **Riesgos:** presentar un "lead time" que en realidad mide 0 días todo el tiempo sería
  engañoso para bodega/gerencia — parecería que todos los proveedores entregan instantáneamente.
- **Recomendación:** **retirar el deliverable de lead time del alcance de fase 1.** Sustituir por
  una métrica que sí es medible y útil: **"tasa de documentación completa"** — % de compras
  (`fact_compras`) que tienen su contraparte de entrada en el kardex el mismo día
  (`es_entrada = true`, `tipo_movimiento = 'CPA'`, mismo `num_documento`/`num_factura` y
  `producto_sk`). Hoy es 77.2% documento+producto, 82.7% solo documento (el resto son compras con
  `producto_sk = -1`, servicios, o ajustes contables sin contraparte física de kardex) — es una
  señal de calidad de datos legítima (¿la mercadería facturada realmente ingresó a bodega?), no
  de tiempo de entrega. Si en el futuro el ERP incorpora una tabla de orden de compra con fecha
  de pedido, el lead time real se vuelve calculable — documentar esto como trabajo futuro, no
  como limitación permanente.

### 🔴 Alta — H2: `es_entrada`/`tipo_movimiento`, no `tipdoc` — corrección de referencia a la regla de negocio 3

- **Evidencia:** `edw.fact_movimientos_inventario` no tiene columna `tipdoc` (ese es el nombre
  de la columna **origen** en SAP, consumida solo dentro del ETL —
  `etl/transformers/fact_transformer.py:110-117`). El EDW ya expone el booleano derivado
  `es_entrada`; el subconjunto de entradas por compra es `tipo_movimiento = 'CPA'` (129,595
  filas, 2018-01-02 a 2026-07-13) — confirmado por formato de documento compartido con
  `fact_compras.num_factura`. Otros tipos de entrada (`TRA` transferencia-entrada, `DEV`
  devolución, `BOD` ajuste, `ING` ingreso con formato de documento totalmente distinto:
  `H0000143`, `IG001575`) **no** son compras y deben excluirse del pareo.
- **Impacto:** ninguno sobre los datos; es una corrección de referencia para que el código del
  módulo filtre `tipo_movimiento = 'CPA'` (no busque una columna `tipdoc` inexistente en el EDW).
- **Recomendación:** usar `fm.tipo_movimiento = 'CPA'` en todas las consultas del módulo.

### 🟡 Media — H3: concentración de gasto extrema en un solo proveedor (92.8%) — validar con el negocio antes de presentar el scorecard

- **Evidencia:**
  ```sql
  SELECT nombre_proveedor, SUM(total_factura) AS spend
  FROM edw.fact_compras fc JOIN edw.dim_proveedor pr ON fc.proveedor_sk = pr.proveedor_sk
  GROUP BY nombre_proveedor ORDER BY spend DESC LIMIT 3;
  -- TECNOVA S.A.: $483,383,523 (92.78% del gasto total)
  -- ROBERT BOSCH SOCIEDAD ANONIMA ECUABOSCH: $11,510,039 (2.21%)
  -- TRICO PRODUCTS CORPORATION: $4,192,501 (0.80%)
  ```
  Top-15 proveedores = 97.9% del gasto total; un solo proveedor concentra 92.78%.
- **Impacto:** un scorecard de concentración de gasto mostraría un HHI degenerado (prácticamente
  monopolio de un proveedor) — puede ser la realidad del negocio (un distribuidor mayorista
  central) o un artefacto de cómo se registra la compra en SAP (código genérico/holding en vez
  del fabricante real). No se puede determinar cuál de las dos sin contexto de negocio.
  Presentarlo sin esa aclaración podría malinterpretarse como un hallazgo de auditoría cuando es
  simplemente cómo opera hoy la cadena de abastecimiento.
- **Recomendación:** mostrar el KPI de concentración tal cual (es honesto reflejar los datos),
  pero con una nota explícita en el UI/documentación de que se debe validar con el área de
  Compras si "TECNOVA S.A." es el mayorista real o un código administrativo agregador — no
  bloquea el desarrollo del módulo, sí condiciona cómo se interpreta el resultado en el comité.

### 🟢 Informativo — H4: variación de precio de compra es medible y confiable

- **Evidencia:** `fact_compras.costo_unitario` (numeric 15,4) es el costo unitario por línea.
  Verificado con drift real observable en pares proveedor+producto con suficiente historial
  (ej. `proveedor_sk=836, producto_sk=1746`: 3,894 líneas de compra, salto de $137.85 → $145.00
  el 2018-01-15).
- **Recomendación:** ninguna acción bloqueante; usar `costo_unitario` directamente para el
  componente de variación de precio del scorecard.

### 🟢 Informativo — H5: 22.7% de `fact_compras` tiene `producto_sk = -1` (no resuelto)

- **Evidencia:** 38,712 de 170,514 filas (22.7%) tienen el centinela `-1` en `producto_sk`.
- **Impacto:** estas filas no pueden participar en ningún cálculo a nivel de producto (pareo con
  kardex, variación de precio por artículo), solo en agregados por proveedor/fecha.
- **Recomendación:** ninguna acción bloqueante para este módulo (ya es el comportamiento
  documentado de la regla de negocio 12 — centinela, no fallback arbitrario); reportar el % de
  cobertura junto al scorecard para que bodega sepa qué parte del gasto queda fuera del análisis
  por producto.

### 🟢 Informativo — H6: inferencia de proveedor por producto ya existe, reutilizable sin cambios

- **Evidencia:** `warehouse_repository.py:69-78` ya infiere "qué artículos vende cada proveedor"
  desde `fact_compras` (el ERP no guarda proveedor en el artículo, `dim_producto` no tiene ese
  campo). El mismo patrón sirve para poblar "proveedor sugerido" en `/necesidad-compra`.
- **Recomendación:** extender `ProductoCompra` (schema) con un campo opcional
  `proveedor_sugerido` poblado dentro de `WarehouseService._fila_compra()` / el loop de
  `_necesidad_compra_completo()` — aditivo, no rompe el contrato existente (mismo criterio que
  las extensiones aditivas ya aplicadas en Comisiones Variables, regla de negocio 13).

## Resumen de recomendaciones por prioridad

| Prioridad | Hallazgo | Acción |
|---|---|---|
| 🔴 Alta | H1 | Retirar "lead time real" del alcance; sustituir por "tasa de documentación completa" (compra↔kardex mismo día) |
| 🔴 Alta | H2 | Usar `tipo_movimiento = 'CPA'` / `es_entrada`, nunca `tipdoc` (no existe en el EDW) |
| 🟡 Media | H3 | Mostrar concentración de gasto con nota de validación de negocio sobre "TECNOVA S.A." |
| 🟢 Info | H4, H5, H6 | Sin acción bloqueante |

**Veredicto de viabilidad (actualiza §3.5 de la propuesta):** 🟡 viable en fase 1 con alcance
reducido: scorecard de proveedores (variación de precio + concentración de gasto, ambos
confiables), inflación de costo por categoría (`costo_unitario` vs `dim_producto.precio_oficial`)
y "proveedor sugerido" en `/necesidad-compra`. El "lead time real" — el deliverable que la
propuesta señalaba como el insumo más valioso para el punto de reorden — **no es viable con los
datos actuales**; el punto de reorden sigue usando el lead time configurado (`BODEGA_LEAD_TIME_DIAS`)
sin cambios, tal como hoy.
