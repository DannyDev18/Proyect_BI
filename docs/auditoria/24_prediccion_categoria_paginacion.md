# 24 — Predicción de compras por categoría + paginación global del módulo Bodega

> **Fecha:** 2026-07-12
> **Alcance:** `backend/app/schemas`, `backend/app/services/warehouse_service.py`,
> `backend/app/repositories/warehouse_repository.py`, `backend/app/api/routes/warehouse.py`,
> `backend/app/core/config.py`, `frontend/src/{types,services,hooks,components,pages}`.
> **Método:** lectura de código existente (módulo Bodega, auditoría 23) + diseño de
> extensión siguiendo los mismos patrones ya validados (`_forecast_ml_producto`,
> degradación con gracia, RBAC `bodeguero_checker`, `resolve_sucursal_filter`).
> **Plan de referencia:** `docs/features/plan_prediccion_categoria_paginacion.md`.

## 1. Alcance del cambio

Dos entregables:

1. Endpoint nuevo `GET /analytics/bodega/prediccion-compras-mes` — predicción de
   compras del **siguiente mes calendario**, filtrable por categoría, con drill-down
   a los 20 artículos con más ventas de esa categoría (predicción individual por
   `demand_rf` vía `walk_forward_forecast`, mismo camino que `_forecast_ml_producto`).
2. Paginación genérica reutilizable (`Page[T]` + `PaginationParams`) aplicada a
   `stock-reorden`, `necesidad-compra` (solo `recomendados`), `inventario-matriz` y
   `transferencias-sugeridas`.

## 2. Hallazgos (verificados en código antes de implementar)

| # | Hallazgo | Severidad | Acción |
|---|---|---|---|
| H24-1 | El forecast agregado de `/salidas-forecast` sin `producto_cod` es estadístico, no ML — el requerimiento de "predicción para el próximo mes" necesita un camino nuevo que sí corra `demand_rf` por artículo y agregue. No se reutiliza `get_salidas_forecast` tal cual. | Info | Nuevo método `get_prediccion_compras_mes` en el servicio, reutilizando `_forecast_ml_producto`. |
| H24-2 | No existe infraestructura de paginación en el backend (`backend/app/schemas/`); los 4 endpoints de tabla truncan con `[:limit]` en Python, ya con el dataset completo materializado en memoria. | Medio | `Page[T]` documentado como paginación **en memoria** (no reduce cómputo/IO, sí reduce el payload de red) — limitación declarada explícitamente, no oculta. |
| H24-3 | 20 llamadas a `walk_forward_forecast` por request (una por artículo top) es costoso en CPU (cada una reconstruye features día a día). | Medio | Cache TTL en el servicio (`BODEGA_FORECAST_CACHE_TTL_MIN`) + límite configurable de artículos (`BODEGA_TOP_ARTICULOS_PREDICCION`) + `staleTime` alto en el frontend. |
| H24-4 | Sumar bandas de confianza de 20 series independientes sobreestima la incertidumbre real (no son independientes ni la suma de percentiles es un percentil válido). | Bajo | Se declara explícitamente en el payload (`metodo`) y en la documentación como aproximación conservadora — no se presenta como estadística validada. |

## 3. Regla de negocio nueva

**RN-B7 (compra sugerida del mes, drill-down por categoría):** para cada artículo del
top-20 por ventas de una categoría, `compra_sugerida = max(0, predicción_ML_mes −
stock_actual)`; el costo estimado usa `articulos.ultcos` ya materializado en
`edw.fact_inventario_snapshot.costo_promedio` (mismo campo que usa RN-B4). El método
(`ml_demand_rf` vs `estadistico`) se declara por artículo y a nivel agregado — degradación
parcial no oculta el origen del dato al usuario (mismo principio de H23-6).

## 4. Endpoints de Bodega — estado tras el cambio

Se añade a la lista de `CLAUDE.md`:

```
/analytics/bodega/prediccion-compras-mes
```

Contrato de paginación (`Page[T]`) aplicado a:

```
/analytics/bodega/stock-reorden           (antes: list[...] + limit)
/analytics/bodega/necesidad-compra        (antes: recomendados[:100] / no_comprar[:100])
/analytics/bodega/inventario-matriz       (antes: productos[:300])
/analytics/bodega/transferencias-sugeridas (antes: sugerencias[:100])
```

Sin cambios: `/kpis-inventory`, `/demand-forecasting` (legados, H23-7), `/top-productos`,
`/reportes/{tipo}` y `/reportes/{tipo}/excel` (deben ser completos).

## 5. Validación aplicada

Ver checklist en `plan_prediccion_categoria_paginacion.md` §7; resultado ejecutado
documentado al cierre de esta auditoría (sección 6, se completa tras implementar).

## 6. Resultado de la implementación

- Backend: `Page[T]`/`PaginationParams` genéricos en `app/schemas/pagination.py`;
  paginación aplicada en memoria dentro de `WarehouseService` (después de ordenar,
  antes de devolver), preservando los totales globales (`total_productos_a_comprar`,
  `valor_total_compra`, `ahorro_por_no_comprar`, `ahorro_total_estimado`) que ya
  dependían del dataset completo, no del recorte. Los 4 métodos públicos ahora
  delegan en helpers privados `_stock_reorden_filas` / `_necesidad_compra_completo`
  / `_inventario_matriz_completo` / `_transferencias_completo` que devuelven la lista
  íntegra; los reportes internos (§2) y `get_notificaciones` consumen esos helpers
  directamente, sin paginar (deben seguir siendo completos).
- `pagination_params` valida `page`/`page_size` vía `fastapi.Query(ge=..., le=...)`
  (no construyendo `PaginationParams(...)` a mano dentro del dependency): así un
  `page_size` fuera de rango responde `422` a través del manejo estándar de FastAPI,
  en vez de un `ValidationError` de pydantic sin capturar que los handlers globales
  de `main.py` no traducen (bug encontrado en la verificación con BD real, corregido
  antes de cerrar esta auditoría).
- `GET /prediccion-compras-mes` agregado como router thin en `warehouse.py`, con
  `resolve_sucursal_filter(allow_override=False)` (mismo comportamiento RBAC que el
  resto del módulo Bodega).
- **Bug crítico encontrado y corregido en verificación contra BD real:**
  `DatasetRepository.get_product_sales_history` usaba `with self.db.connection() as
  conn: pd.read_sql(...)`, que cierra explícitamente la conexión ligada a la Session
  ORM al salir del `with`. Mientras esta función se llamaba una sola vez por request
  (p.ej. `/salidas-forecast?producto_cod=...`) el efecto secundario nunca se notaba;
  al llamarla hasta 20 veces por request (`get_prediccion_compras_mes` sin
  `producto_cod`) cualquier `self.db.execute(...)` posterior en el mismo request
  fallaba con `ResourceClosedError: This Connection is closed` — degradando en
  silencio 19 de 20 artículos a predicción vacía (el `try/except` de degradación
  ocultaba el fallo real, no un resultado correcto). Corregido reemplazando el
  patrón por `self.db.execute(text(query), params).mappings().all()` +
  `pd.DataFrame(...)`, sin abrir/cerrar una conexión cruda aparte de la Session.
  Verificado end-to-end contra Postgres real: `categoria=BAT` pasó de
  `unidades_previstas_mes=124.56` (solo 1/20 artículos con predicción real) a
  `1109.3` (20/20 con `metodo=ml_demand_rf`) tras el fix.
- También se endureció `WarehouseService._prediccion_articulo`: el fallback
  estadístico (cuando `demand_rf` degrada) ahora está envuelto en `try/except` —
  un artículo cuyo repositorio falle no debe tumbar la predicción completa de la
  categoría (mismo principio de degradación con gracia que `_forecast_ml_producto`).
- Cache en memoria por proceso (`dict` a nivel de clase, con TTL manual, sin
  dependencia nueva) — verificado: segunda llamada a la misma categoría respondió en
  ~0.04s vs ~7s en frío (20 walk-forward reales contra Postgres). Si el despliegue
  usa múltiples workers el cache no se comparte entre procesos (limitación
  declarada, no bloqueante para el alcance de tesis).
- Frontend: `Pagination.tsx` + `usePagination` reutilizados por `DashboardBodega`
  (G5/G6) y `BodegaAlmacenes` (matriz y transferencias); `PrediccionComprasChart.tsx`
  nuevo, enlazado al filtro global de categoría vía `bodegaFiltersStore`, con
  drill-down a los 20 artículos y botón de regreso.
- Tests: 6 unitarios de `pagination.py` (función pura) + 7 unitarios de la
  agregación mensual del servicio con repos fake (incluye degradación y cache);
  11 de integración contra Postgres real (paginación de los 4 endpoints, límites,
  predicción con/sin categoría, drill-down, RBAC). Suite completa: 87 unit + 26
  integration passed (1 skipped por falta de categorías en el EDW de prueba usado).
  `tsc --noEmit`, `oxlint` y `vite build` del frontend en verde.
