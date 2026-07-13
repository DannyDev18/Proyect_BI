# Auditoría 25 — Módulo de Venta Cruzada (Cross-Selling)

- **Fecha:** 2026-07-13
- **Alcance:** implementación del módulo descrito en `docs/features/modulo_cross_selling_requerimientos.md` (plan en `docs/features/plan_modulo_cross_selling.md`). Capas afectadas: ML (`ml/`), backend (`backend/app/`), frontend (`frontend/src/`). **NO se modifica** `etl/` (sin extractores/transformers nuevos: el dato ya está en `fact_ventas_detalle`).
- **Método:** lectura del contrato existente (`ml/contracts/models/recommendation.json` v0.1.0), del motor actual (`ml/src/training/train_recommendation_engine.py`, `ml/src/data/make_dataset.py::fetch_market_basket`), del serving (`backend/app/ml/model_loader.py`, `inference.py`, `prediction_service.py`) y validaciones **SOLO SELECT** contra el EDW vivo (`postgres_edw`, esquema `edw`).

## 0. Mapeo origen → EDW (Fase 0 del requerimiento)

El requerimiento pedía auditar `renglonesfacturas`/`encabezadofacturas`/`kardex`/`articulos` en SAP. Se descarta: el EDW ya es la fuente oficial (CLAUDE.md) y contiene el mapeo completo:

| Origen SAP (solo referencia histórica) | EDW (fuente real usada) |
|---|---|
| `renglonesfacturas` (codart, cantidad, precio) | `edw.fact_ventas_detalle` (grano línea de venta) |
| `encabezadofacturas` (num_factura, codcli, fecfac) | `fact_ventas_detalle.num_factura` + `dim_fecha` + `dim_cliente` |
| `articulos` (codart, nombre, codgrupo, precio, ultcos) | `edw.dim_producto` (SCD2): `codart`, `nombre_articulo`, `clase`/`subclase` (equivalen a `codgrupo`), `precio_oficial`, `costo_promedio` |
| `kardex` | no aplica a este módulo (es demanda/inventario, ya cubierto por `demand_rf`) |

Flujo de la aplicación / punto de integración: el vendedor (rol `ventas`) opera en `DashboardVentas.tsx`; hoy ya existe una tarjeta de recomendaciones por cliente (`GET /analytics/ventas/recommendations`). El punto de integración nuevo es un **Asistente de Venta Cruzada** (canasta simulada) dentro del mismo dashboard — no un carrito transaccional (el ERP SAP sigue siendo el único sistema que factura).

## 1. Validaciones ejecutadas contra el EDW (SOLO SELECT, 2026-07-13)

Ventana de datos vigente: `fact_ventas_detalle` cubre 2018-01-02 a 2026-07-13. "Último trimestre" = `>= 2026-04-13`.

| Validación | Resultado |
|---|---|
| Facturas válidas totales (estado <> anulado) | 235.276 |
| Facturas con 2+ productos distintos (universo de canastas útiles) | 104.929 (44,6%) |
| `codart` únicos con venta válida | 6.340 |
| Reglas activas en `recommendation.pkl` v0.1.0 | 494 (247 pares × 2 direcciones) |
| `codart` únicos que aparecen como antecedente (`item_A`) en v0.1.0 | 78 |
| Facturas del último trimestre con 2+ productos | 4.264 |
| **Cobertura v0.1.0** (≥1 sugerencia posible, ≥1 producto de la canasta con regla) | **3.749 / 4.264 = 87,9%** — línea base a superar en Fase 3 |
| `dim_producto` vigente (`es_vigente`, sin centinela `-1`) | 8.146 filas |
| Con `precio_oficial` > 0 | 8.144 / 8.146 (99,98%) |
| Con `costo_promedio` > 0 | 7.506 / 8.146 (92,1%) |
| Categorías (`clase`) distintas vigentes | 22 |

**Conclusión de datos:** margen es derivable de forma confiable para ~92% del catálogo vigente vía `precio_oficial − costo_promedio` (`dim_producto`); el 8% restante sin costo usa fallback (ordenar solo por lift, sin factor margen — documentado, no se inventa un costo). La cobertura base (87,9%) es más alta de lo esperado con solo 78 productos con regla — son los de mayor rotación — pero el 12,1% de canastas sin sugerencia justifica el fallback por categoría (§2.1 del plan) y motiva revisar `min_support` en el re-análisis de Fase 3.

## 2. Hallazgos previos a la implementación

| # | Hallazgo | Severidad | Acción |
|---|---|---|---|
| H25-1 | El requerimiento pide extraer de SAP (`renglonesfacturas` etc.) y guardar el dataset como CSV. | Baja | Se usa el EDW exclusivamente (ya validado arriba) y dataset efímero en memoria (patrón `fetch_*` existente), sin CSVs versionados. |
| H25-2 | El requerimiento pide un endpoint suelto `POST /recomendar_productos` en `main.py` con motor que carga el `.pkl` por su cuenta. | Media | Se reutiliza `ModelLoader` singleton (clave `association`, ya cargado en el lifespan) + capas routes→services→repositories bajo `/analytics/ventas/cross-selling/*`. |
| H25-3 | El contrato v0.1.0 no tiene `lift`/`confidence` mínimos ni fallback: 12,1% de canastas del último trimestre quedarían sin sugerencia. | Media | Fallback por categoría/popularidad (§2.4 del plan); umbrales `CROSS_SELL_MIN_LIFT` configurables. |
| H25-4 | `costo_promedio` nulo en 7,9% de productos vigentes → margen no derivable para ese subconjunto. | Baja | La heurística de margen se omite (no se sustituye por un valor inventado) cuando `costo_promedio` es NULL o 0; se ordena solo por lift para esos productos, documentado en el contrato v0.2.0. |
| H25-5 | El requerimiento pide instalar `surprise` para filtrado colaborativo. | Baja | Descartado (dependencia pesada sin mantenimiento activo); el candidato item-item se implementa con `scikit-learn` (cosine similarity), ya presente en `ml/requirements.txt`. |
| H25-6 | No existe tabla de telemetría de aceptación/rechazo de sugerencias. | Media | Tabla nueva `public.recomendaciones_eventos` (DDL en `edw/07_public_app_tables.sql` + modelo SQLAlchemy, patrón de `metas_comerciales_operativas`). |

## 3. Regla de negocio nueva (a registrar en `02_reglas_negocio_validadas.md`)

- **RN-CS1 (formato de sugerencia):** Top-N configurable (`CROSS_SELL_TOP_N`, default 5); cada sugerencia expone `codart`, `nombre`, `precio` (`precio_oficial` vigente), `categoria` (`clase`), `score` (lift o score combinado del ganador de backtest) y `motivo` textual ("Los clientes que llevan X suelen llevar Y" para reglas de asociación; "Popular en esta categoría" para el fallback). Se excluyen productos ya presentes en la canasta simulada y, si hay `cliente_id`, los ya comprados por ese cliente en el histórico. Fallback por categoría cuando ningún producto de la canasta tiene regla con score ≥ `CROSS_SELL_MIN_LIFT`.
- **RN-CS2 (telemetría):** cada sugerencia mostrada genera un evento `mostrada` en `public.recomendaciones_eventos`; el clic en "Agregar" genera `aceptada`. La tasa de conversión = `aceptadas / mostradas` en la ventana consultada.

## 4. Decisiones de arquitectura

1. **Sin ETL/DDL nuevo en `edw.*`** — el dato de ventas y catálogo ya está cargado; el ETL roto (`etl/loaders/` borrado, riesgo abierto de CLAUDE.md) no bloquea este módulo.
2. **Modelo re-analizado, no descartado a priori** (decisión del usuario, alta prioridad): se compite co-ocurrencia re-tuneada vs Apriori/FP-Growth (`mlxtend`, solo en `ml/requirements.txt`) vs item-item (`scikit-learn`) vs híbrido, con selección por backtest temporal (Precision@K/Recall@K/Hit-Rate/cobertura) — detalle en §2.3 del plan. Contrato-primero: v0.2.0 en `draft` antes de entrenar.
3. **Capas backend:** `catalog`/`recomendaciones` repositorios (SQL) → `prediction_service.get_basket_recommendations` (heurísticas + fallback) + `recommendation_event_service` (telemetría) → `routes/sales.py` bajo `/analytics/ventas/cross-selling/*`, RBAC `vendedor_checker` (KPIs también accesibles a `gerencia`).
4. **Sin dependencia nueva en el backend** salvo que gane el híbrido/colaborativo (H-20): el diseño prioriza artefactos-DataFrame precomputados para que el runtime del backend no cambie.

## 5. Estado

- [x] Auditoría previa creada antes de modificar código
- [x] Validaciones SELECT ejecutadas contra el EDW vivo (§1)
- [ ] EDA + grid experimental + contrato v0.2.0 draft (Fase 2)
- [ ] Backtest y selección del modelo ganador (Fase 3)
- [ ] Implementación backend (Fase 4)
- [ ] Implementación frontend (Fase 5)
- [ ] KPIs + documentación + cierre (Fase 6)
