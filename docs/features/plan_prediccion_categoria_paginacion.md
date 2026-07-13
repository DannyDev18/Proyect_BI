# Plan de integración — Predicción de compras por categoría + Paginación global

> **Fecha:** 2026-07-12
> **Módulo afectado:** Bodega (`/api/v1/analytics/bodega`, `DashboardBodega.tsx`)
> **Base:** módulo Bodega existente (auditoría 23, `docs/features/modulo_bodega.md`).
> **Estado:** PLAN — pendiente de aprobación antes de implementar (flujo CLAUDE.md: crear
> reporte en `docs/auditoria/` al iniciar la implementación).

---

## 1. Objetivo

Dos entregables independientes pero coordinados:

1. **Predicción de compras del próximo mes enlazada al filtro de categorías.**
   Al seleccionar una categoría en el filtro global (§1.1), el gráfico de predicción
   muestra la proyección de demanda/compra del **siguiente mes calendario** para esa
   categoría, y permite hacer **drill-down dentro del gráfico** a cada uno de los
   **20 artículos con más ventas de esa categoría**, cada uno con su predicción
   individual del modelo `demand_rf`.
2. **Paginación global reutilizable en el backend** (esquema genérico `Page[T]` +
   parámetros `page`/`page_size` como dependencia FastAPI), aplicada a todos los
   endpoints de Bodega que devuelven listas/tablas, con su contraparte en el frontend
   (componente de paginación + hooks con `placeholderData: keepPreviousData`).

## 2. Estado actual (verificado en código)

| Pieza | Estado |
|---|---|
| `GET /salidas-forecast` | Ya acepta `categoria`, pero el forecast agregado (sin `producto_cod`) es **estadístico** (promedio 7 días); el ML `demand_rf` solo corre por producto individual ([warehouse_service.py:216-320](backend/app/services/warehouse_service.py#L216-L320)). |
| Selector de producto en G1 | Existe (`<select>` en [DashboardBodega.tsx:141-151](frontend/src/pages/DashboardBodega.tsx#L141-L151)), pero lista el top-20 **global**, no el top-20 de la categoría filtrada. |
| Top productos | `GET /top-productos` ya filtra por `categoria` y ordena por salidas — reutilizable para el drill-down. |
| Paginación | **No existe** ningún esquema de paginación en `backend/app/schemas/`. Los endpoints de tabla usan `limit` fijo con truncado (`[:limit]`): `stock-reorden` (100/500), `necesidad-compra` (100), `inventario-matriz` (300), `transferencias-sugeridas` (100). El frontend trae todo y hace scroll. |
| Modelo ML | `demand_rf` (`demand.pkl`) servido vía `ModelLoader` singleton + `walk_forward_forecast`; degrada con gracia a estadístico. **No se entrena ningún modelo nuevo** — se reutiliza el existente (H23-6). |

## 3. Diseño — Parte A: predicción de compras del próximo mes por categoría

### 3.1 Backend

**Nuevo endpoint** (patrón routes → services → repositories, RBAC `bodeguero_checker`,
sucursal forzada para rol bodega):

```
GET /api/v1/analytics/bodega/prediccion-compras-mes
    ?categoria=<str|null>          # filtro principal (enlace con §1.1)
    &producto_cod=<str|null>       # drill-down: predicción individual de un artículo
    &sucursal / &almacen / &proveedor   # filtros globales existentes
```

**Response (`PrediccionComprasMesResponse`, nuevo en `app/schemas/warehouse.py`):**

```jsonc
{
  "mes_objetivo": "2026-08",            // siguiente mes calendario completo
  "categoria": "REP",                    // null = todas
  "metodo": "ml_demand_rf",              // o "estadistico" si el ML degrada (patrón H23-6)
  "serie": [                             // agregado diario del mes siguiente (para el gráfico)
    {"fecha": "2026-08-01", "unidades": 132.4, "banda_superior": 158.1, "banda_inferior": 106.7},
    ...
  ],
  "resumen": {
    "unidades_previstas_mes": 3960.0,
    "costo_estimado_compra": 18240.55,   // unidades previstas × ultcos, neteado contra stock actual
    "productos_incluidos": 20
  },
  "top_articulos": [                     // los 20 con más ventas de la categoría (drill-down)
    {
      "codart": "REP-0012", "nombre": "…", "categoria": "REP",
      "unidades_vendidas_periodo": 812.0,   // ranking por ventas (fact_ventas_detalle)
      "stock_actual": 40.0, "punto_reorden": 55.0,
      "prediccion_mes": 260.3,              // suma del forecast diario del artículo
      "compra_sugerida": 220.3,             // max(0, predicción − stock_actual), redondeada
      "metodo": "ml_demand_rf"
    },
    ...
  ]
}
```

**Lógica del servicio (`WarehouseService.get_prediccion_compras_mes`):**

1. Calcular el rango del **mes siguiente** (primer→último día del mes calendario
   posterior a hoy); `dias_horizonte` = días desde mañana hasta el fin de ese mes
   (el walk-forward arranca en el día siguiente al último dato).
2. Obtener el **top-20 por ventas** de la categoría vía el repo existente
   `get_salidas_por_producto` (ranking por `fact_ventas_detalle`, no por kardex —
   el requerimiento pide "artículos con más ventas").
3. Por cada artículo del top-20, correr `_forecast_ml_producto` (ya existente:
   `walk_forward_forecast` + `demand_rf` + banda con MAE del sidecar); recortar
   la serie a los días del mes objetivo y sumar → `prediccion_mes`.
4. Agregar las 20 series diarias en una sola serie de categoría (suma por fecha;
   bandas sumadas — declarado en docs como aproximación conservadora).
5. `compra_sugerida = max(0, prediccion_mes − stock_actual)` por artículo;
   `costo_estimado_compra = Σ compra_sugerida × ultcos` (coherente con RN-B4/RN-B6:
   costo desde `articulos.ultcos` ya materializado en el EDW).
6. Si un artículo falla el ML → forecast estadístico para ese artículo y `metodo`
   individual lo declara; si TODOS degradan, `metodo` global = `"estadistico"`.
   **No quitar el try/except de degradación** (regla del serving ML).
7. Con `producto_cod` presente: responder solo la serie de ese artículo (drill-down
   individual dentro del gráfico), reutilizando el mismo camino.

**Rendimiento / mitigación (riesgo principal):** 20 productos × ~31 días de
walk-forward es costoso. Mitigaciones incluidas en el plan:

- Cache en memoria del resultado por `(categoria, sucursal, almacen, proveedor)` con
  TTL configurable `BODEGA_FORECAST_CACHE_TTL_MIN` (default 60) en
  `backend/app/core/config.py` — el EDW se carga por lotes, no cambia intra-hora.
- Límite `BODEGA_TOP_ARTICULOS_PREDICCION` (default 20) también en config —
  sin hardcodes (regla CLAUDE.md).
- En el frontend, `staleTime` alto en el hook (30 min) para no repetir la llamada
  al alternar drill-downs.

**Archivos backend a tocar:**

| Archivo | Cambio |
|---|---|
| `backend/app/schemas/warehouse.py` | `PrediccionComprasMesResponse`, `ArticuloPrediccionMes`, `PuntoForecast` (reusar si ya existe el shape del forecast). |
| `backend/app/services/warehouse_service.py` | `get_prediccion_compras_mes(...)` + helper de agregación + cache TTL. |
| `backend/app/repositories/warehouse_repository.py` | Solo si `get_salidas_por_producto` necesita variante (ya soporta `categoria` y `limit`; probablemente sin cambios). |
| `backend/app/api/routes/warehouse.py` | Endpoint `GET /prediccion-compras-mes` (router thin). |
| `backend/app/core/config.py` | `BODEGA_TOP_ARTICULOS_PREDICCION`, `BODEGA_FORECAST_CACHE_TTL_MIN`. |
| `backend/tests/unit/` | Test del servicio con `ModelLoader` fake (agregación, mes objetivo, degradación). |
| `backend/tests/integration/test_analytics_ml_endpoints.py` | Test del endpoint (RBAC + shape). |

### 3.2 Frontend

**Nuevo gráfico** "Predicción de Compras — Próximo Mes" en `DashboardBodega.tsx`
(ChartCard nuevo, no reemplaza G1 que es histórico+forecast del rango filtrado):

- Enlazado al **filtro global de categoría** (`bodegaFiltersStore` → `toQueryFilters`):
  al cambiar la categoría en `BodegaFilterBar`, el gráfico se refetchea solo
  (query key incluye los filtros).
- **Drill-down dentro del gráfico:** con categoría seleccionada, se muestra la lista
  de los 20 artículos (barra lateral o selector, mismo patrón del `<select>` de G1
  pero alimentado por `top_articulos` de la respuesta); clic en un artículo → la
  serie del gráfico cambia a la predicción individual (`producto_cod=…`), con botón
  "← Volver a la categoría".
- Badge de método (`ML demand_rf` / `Proyección estadística`) — misma convención de G1.
- Tabla resumen bajo el gráfico: los 20 artículos con `prediccion_mes`,
  `compra_sugerida`, stock, ranking de ventas (esta tabla usa la paginación de la
  Parte B si se decide mostrar más de 20 en el futuro; con 20 fijos basta sin paginar).

**Archivos frontend a tocar:**

| Archivo | Cambio |
|---|---|
| `frontend/src/types/bodega.ts` | `PrediccionComprasMes`, `ArticuloPrediccionMes`. |
| `frontend/src/services/bodega.ts` | `getPrediccionComprasMes(filters, productoCod?)`. |
| `frontend/src/constants/queryKeys.ts` | `qk.bodega.prediccionComprasMes(filters, productoCod)`. |
| `frontend/src/hooks/bodega.ts` | `usePrediccionComprasMes(...)` con `staleTime` alto. |
| `frontend/src/components/bodega/PrediccionComprasChart.tsx` | Componente nuevo (gráfico + drill-down + tabla) para no seguir engordando `DashboardBodega.tsx` (406 líneas). |
| `frontend/src/pages/DashboardBodega.tsx` | Montar el componente nuevo. |

## 4. Diseño — Parte B: paginación global reutilizable

### 4.1 Backend — infraestructura genérica (nueva, reutilizable por TODOS los módulos)

**Nuevo archivo `backend/app/schemas/pagination.py`:**

```python
class PaginationParams(BaseModel):        # dependencia FastAPI: Depends(pagination_params)
    page: int = 1                          # ge=1
    page_size: int = 25                    # ge=1, le=200 (tope anti-abuso)

class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int                             # total de filas SIN paginar (para el paginador)
    page: int
    page_size: int
    total_pages: int                       # ceil(total / page_size)

def paginar(items: Sequence[T], params: PaginationParams) -> Page[T]:
    """Paginación en memoria para listas ya calculadas/ordenadas en el servicio."""
```

Dos niveles de aplicación, ambos detrás del mismo contrato `Page[T]`:

- **Nivel repositorio (LIMIT/OFFSET + COUNT):** para endpoints cuyo orden se resuelve
  en SQL. Se agrega `limit/offset` a la consulta y un `COUNT(*)` de la misma condición.
- **Nivel servicio (`paginar()` en memoria):** para endpoints que **necesitan** el
  dataset completo para ordenar/derivar estado en Python (`stock-reorden`,
  `necesidad-compra`, `inventario-matriz`, `transferencias-sugeridas` ordenan por
  estado/prioridad calculados). El payload al cliente se reduce igual (objetivo del
  usuario: "no traer todo el listado"); el costo de cómputo interno no cambia — se
  documenta como limitación honesta, optimizable después si hace falta.

### 4.2 Endpoints de Bodega a paginar (cambio de contrato)

| Endpoint | Hoy | Pasa a | Nivel |
|---|---|---|---|
| `GET /stock-reorden` | `list[ProductoStockReorden]` + `limit` | `Page[ProductoStockReorden]` | servicio (orden por estado calculado) |
| `GET /necesidad-compra` | dict con `recomendados[:100]` / `no_comprar[:100]` | `recomendados: Page[...]` (paginado) + `no_comprar` (resumen, primeras N) + totales intactos | servicio |
| `GET /inventario-matriz` | `productos[:300]` | `productos: Page[...]` + `almacenes` | servicio |
| `GET /transferencias-sugeridas` | `sugerencias[:100]` + totales | `sugerencias: Page[...]` + totales intactos | servicio |
| `GET /top-productos` | `list` con `limit=20` | **sin cambios** (es un gráfico top-N, no un listado) | — |
| Reportes `/reportes/{tipo}` y Excel | listas completas | **sin cambios** (un reporte imprimible/Excel debe ser completo) | — |

Los KPIs, forecast, rotación-matriz y salidas-categoría no se paginan (son gráficos
agregados). Los `limit` truncadores actuales se eliminan al quedar cubiertos por
`page_size` con tope.

**Compatibilidad:** el frontend es el único consumidor de estos 4 endpoints y se
actualiza en el mismo cambio → se cambia el contrato directamente, sin versión dual.
Los endpoints legados (`/kpis-inventory`, `/demand-forecasting`) no se tocan (H23-7).

### 4.3 Frontend — infraestructura reutilizable

| Archivo | Cambio |
|---|---|
| `frontend/src/types/pagination.ts` | `Page<T>`, `PaginationQuery { page; page_size }` (espejo del backend). |
| `frontend/src/components/ui/Pagination.tsx` | Componente global: « ‹ 1 … n › » + "X–Y de Z" + selector de tamaño (10/25/50). Estilo consistente con las cards existentes (slate/cyan). |
| `frontend/src/hooks/usePagination.ts` | Hook de estado `page/pageSize` con reset automático al cambiar filtros (evita quedar en página 7 de un resultado de 2 páginas). |
| `frontend/src/services/bodega.ts` | Los 4 servicios afectados aceptan `PaginationQuery` y tipan `Page<T>`. |
| `frontend/src/hooks/bodega.ts` | Query keys incluyen `page/page_size`; `placeholderData: keepPreviousData` (TanStack v5) para que la tabla no parpadee al cambiar de página. |
| `frontend/src/pages/DashboardBodega.tsx` | Tablas G5 (stock-reorden) y G6 (necesidad de compra) con `<Pagination>`; se elimina el `max-h + scroll` como mecanismo principal. |
| `frontend/src/pages/BodegaAlmacenes.tsx` | Matriz de inventario y transferencias con `<Pagination>`. |

## 5. Orden de ejecución propuesto

| # | Fase | Entregable | Depende de |
|---|---|---|---|
| 0 | Auditoría previa | Reporte `docs/auditoria/24_prediccion_categoria_paginacion.md` (flujo CLAUDE.md paso 4) | — |
| 1 | Paginación backend | `schemas/pagination.py` + 4 endpoints migrados + tests | 0 |
| 2 | Paginación frontend | `Pagination.tsx` + `usePagination` + tablas migradas | 1 |
| 3 | Predicción backend | Endpoint `/prediccion-compras-mes` + config + cache + tests | 0 (independiente de 1–2) |
| 4 | Predicción frontend | `PrediccionComprasChart.tsx` + drill-down enlazado al filtro | 3 (y 2 si la tabla del gráfico usa `Pagination`) |
| 5 | Validación y docs | Checklist §7; actualizar `docs/auditoria/02_reglas_negocio_validadas.md` §16 (nueva regla RN-B7: compra del mes = predicción − stock), `23_modulo_bodega.md` y `CLAUDE.md` (lista de endpoints de Bodega) | 1–4 |

Fases 1–2 y 3–4 son paralelizables.

## 6. Riesgos y decisiones

| Riesgo | Mitigación |
|---|---|
| Latencia: 20 × walk-forward `demand_rf` por request | Cache TTL en servicio + `staleTime` en frontend + límite configurable. Si aun así excede ~5 s en datos reales, fallback: ML solo para el drill-down individual y agregado estadístico para la serie de categoría (declarado en `metodo`). |
| Bandas de confianza al sumar 20 series | Suma directa de bandas = aproximación conservadora (sobreestima). Se declara en el payload/docs; no se inventa estadística no validada. |
| Cambio de contrato en 4 endpoints | Único consumidor es el frontend propio, migrado en el mismo PR; smoke test manual de los 4 dashboards. |
| Paginación en memoria ≠ menos cómputo en BD | Documentado como limitación; el objetivo declarado (payload chico al cliente) sí se cumple. Optimización SQL futura si el inventario crece. |
| Rol bodega multi-sucursal | `resolve_sucursal_filter(allow_override=False)` se mantiene en el endpoint nuevo — sin fuga de datos entre sucursales. |

## 7. Checklist de validación (fase 5)

- [ ] `cd backend && python -m pytest tests/unit tests/integration -v` en verde.
- [ ] `GET /health` → `modelos_ml_listos: true`; sin `ERROR` de carga de `demand_rf` en logs.
- [ ] Endpoint nuevo con y sin `categoria`, con `producto_cod`, y con rol `bodega` (sucursal forzada).
- [ ] Degradación: renombrar temporalmente `demand.pkl` en dev → `metodo: "estadistico"`, sin 500.
- [ ] Paginación: `page` fuera de rango → página vacía con `total` correcto (no error); `page_size` > tope → 422.
- [ ] Frontend: `npx oxlint` + `tsc --noEmit`; cambiar categoría en el filtro actualiza el gráfico; drill-down a los 20 artículos y regreso; paginar G5/G6 sin parpadeo (keepPreviousData).
- [ ] Docs actualizadas (auditoría 24, reglas de negocio §16, CLAUDE.md).
