# Auditoría 23 — Módulo Bodega: Dashboard de Inventario y Abastecimiento

- **Fecha:** 2026-07-10
- **Alcance:** implementación del módulo descrito en `docs/features/modulo_bodega.md` (plan en `docs/features/plan_modulo_bodega.md`). Capas afectadas: backend (`backend/app/`) y frontend (`frontend/src/`). **NO se modifica** `etl/`, `edw/` ni `ml/`.
- **Método:** lectura de requerimientos, inspección del DDL (`edw/02_dimensiones.sql`, `edw/03_hechos.sql`), del backend existente (`warehouse.py`, `analytics_repository.py`, `prediction_service.py`) y del frontend (`DashboardBodega.tsx`). Sin acceso de escritura a Producción (regla: SOLO SELECT).

## Hallazgos previos a la implementación

| # | Hallazgo | Severidad | Acción |
|---|---|---|---|
| H23-1 | El .md de requerimientos referencia objetos inexistentes: `fact_inventario_actual`, `dim_producto.punto_reorden`, `dim_producto.ultcos`, `fact_transferencias`. | Media | Mapear a objetos reales: `fact_inventario_snapshot` (última fecha), `fact_inventario_snapshot.punto_reorden`, `dim_producto.costo_promedio`, pares SA/EN de `fact_movimientos_inventario` (regla de negocio 4). No se crea DDL nuevo. |
| H23-2 | `fact_inventario_snapshot` solo tiene histórico "hacia adelante" (<1% pre-2026, auditoría 05) → tendencias "vs mes anterior" de KPIs de inventario pueden no tener base de comparación. | Media | El repositorio devuelve `None` cuando no hay snapshot del mes anterior; el frontend muestra "—". No se fabrica tendencia. |
| H23-3 | `punto_reorden` del snapshot puede ser 0 (default del DDL) para la mayoría de SKU. | Alta | Regla nueva RN-B1 (abajo): si el punto configurado es 0, se calcula dinámico con la fórmula del requerimiento §6.3. |
| H23-4 | El dashboard de bodega actual (`DashboardBodega.tsx`) consume `MOCK_ALERTS` de `src/services/mocks/bodega.mock` — riesgo ya listado en CLAUDE.md ("verificar que ningún dashboard consuma mocks"). | Alta | La reescritura elimina el consumo de mocks y usa los endpoints reales. |
| H23-5 | El endpoint pedido "aprobar transferencia" no puede escribir en el ERP (Producción SOLO LECTURA) y no existe tabla operativa de transferencias. | Media | La aprobación/rechazo es estado de UI que incluye/excluye la sugerencia del reporte exportado. Documentado en el plan §10. Si a futuro se requiere persistencia, será una tabla `public.*` (fuera de alcance). |
| H23-6 | Predecir salidas por producto con walk-forward ML para muchos SKU en una sola request es costoso. | Media | Forecast ML solo para el producto seleccionado (reutiliza `demand_rf_model`); listados masivos usan proyección estadística (promedio de salidas de 30 días), declarándolo en el payload (`metodo`). |
| H23-7 | El schema `BPKPIBodega` y el repo actual devuelven claves inconsistentes (`items_riesgo_desabasto` en repo vs `items_riesgo_desabastecimiento` en frontend). | Baja | Los contratos nuevos viven en `app/schemas/warehouse.py` con nombres únicos; el endpoint legado `/kpis-inventory` se conserva sin cambios para no romper consumidores. |

## Reglas de negocio nuevas (a registrar también en 02_reglas_negocio_validadas.md)

- **RN-B1 (punto de reorden dinámico):** `punto_reorden_efectivo = punto_reorden_configurado` si > 0; si no, `(salida_prom_diaria_30d × LEAD_TIME_DIAS) + (salida_prom_diaria_30d × STOCK_SEGURIDAD_DIAS)`. Defaults: lead time 7 días, seguridad 5 días (requerimiento §6.3), configurables por env.
- **RN-B2 (estado de stock):** Crítico si `stock < reorden`; Cerca si `reorden ≤ stock ≤ reorden × 1.5`; Seguro si `stock > reorden × 1.5`; Exceso si días de inventario > 90 (§1.3-G5 y §3.1).
- **RN-B3 (transferencia antes de compra):** sugerir transferencia si origen tiene >60 días de inventario y destino <15; cantidad = la necesaria para llevar destino a 30 días sin exceder el excedente del origen (§3.2). Prioridad Alta si destino está en Crítico, Media si <15 días, Baja resto.
- **RN-B4 (cantidad a comprar):** si días de inventario < 20 → `(salida_prom_diaria × HORIZONTE_COMPRA_DIAS) − stock_actual`, horizonte 30 días para necesidad inmediata (§8.2) y 45 para el plan de fin de mes (§3.3).
- **RN-B5 (rotación):** `rotación = costo_de_ventas / inventario_promedio` (mensual y anualizada); semáforo: >4/año buena, 2–4 regular, <2 mala (§1.2-KPI2).
- **RN-B6 (salidas):** toda "salida" se mide con `fact_movimientos_inventario.es_salida = TRUE` (dirección por `tipdoc`, regla 3 vigente), nunca por signo de cantidad.

## Decisiones de arquitectura

1. **Sin ETL/DDL nuevo** — todos los datos salen de hechos ya cargados; además `etl/loaders/` está borrado del working tree (riesgo abierto de CLAUDE.md) y no debe tocarse desde este módulo.
2. **Sin modelos ML nuevos** — se reutiliza `demand_rf_model` (walk-forward, patrón de `get_sales_forecast`); agotamiento/rotación/transferencias son derivaciones estadísticas (precedente: decomisión de `goals_rf`, auditoría 20).
3. **Capas backend:** `warehouse_repository` (SQL) → `warehouse_service` (fórmulas RN-B1..B6, notificaciones, reportes) → `routes/warehouse.py` (thin), contratos en `schemas/warehouse.py`.
4. **Export:** Excel server-side con `openpyxl` (nueva dependencia de runtime del backend); PDF por vista imprimible del frontend.
5. **RBAC:** roles `bodega`/`gerencia`/`administrador` con `bodeguero_checker` existente; el rol bodega queda restringido a su sucursal vía `resolve_sucursal_filter(allow_override=False)`.

## Implementación aplicada (2026-07-10)

**Backend** (prefijo real `/api/v1/analytics/bodega`):
- `app/repositories/warehouse_repository.py` — SQL por codart (colapsa SCD2), snapshot = última fecha, salidas por `es_salida`, centinelas `-1` excluidos.
- `app/services/warehouse_service.py` — RN-B1..B6, KPIs (§1.2), forecast G1 (ML `demand_rf` por producto vía `walk_forward_forecast` + estadístico declarado para top-10), matriz rotación×margen, top-20, categorías, stock vs reorden, necesidad de compra 30/45d, matriz por almacén, transferencias RN-B3, notificaciones §4.2, 3 reportes §2.
- `app/services/warehouse_export.py` — export XLSX (openpyxl, agregado a requirements como dependencia de runtime).
- `app/schemas/warehouse.py` + rutas nuevas en `app/api/routes/warehouse.py` (endpoints legados `/kpis-inventory` y `/demand-forecasting` intactos, H23-7).
- Parámetros `BODEGA_*` en `app/core/config.py` + `.env.example` (sin hardcodes).

**Frontend:**
- `store/bodegaFiltersStore.ts` (Zustand + persist en sessionStorage, §1.1), `types/bodega.ts`, `services/bodega.ts`, `hooks/bodega.ts` (TanStack Query).
- `pages/DashboardBodega.tsx` reescrito: 6 KPIs + 6 gráficos, **sin mocks** (cierra H23-4).
- `pages/BodegaAlmacenes.tsx` (§3: matriz por almacén, transferencias con aprobar/rechazar local H23-5, plan 45 días) y `pages/BodegaReportes.tsx` (§2: JSON renderizado + export Excel + print/PDF).
- `components/bodega/NotificationBell.tsx` en el Header (roles con acceso a bodega), `BodegaFilterBar.tsx`; rutas `/bodega/almacenes` y `/bodega/reportes` con RBAC en `permissions.ts`.

Reglas RN-B1..B6 registradas en `docs/auditoria/02_reglas_negocio_validadas.md` §16.

## Estado

- [x] Auditoría previa creada antes de modificar código
- [x] Implementación aplicada
- [x] Validación: `py_compile` OK; `pytest backend/tests` 74 passed (17 de integración deselected — requieren EDW vivo); frontend `tsc -b && vite build` OK; oxlint sin warnings
- [x] Validación funcional contra el EDW vivo (2026-07-12, ver `docs/auditoria/24_prediccion_categoria_paginacion.md`): confirmado con Postgres real, `fact_inventario_snapshot` con datos.

## Extensión (2026-07-12)

Predicción de compras del próximo mes por categoría (`GET /prediccion-compras-mes`,
RN-B7) y paginación genérica reutilizable en `stock-reorden`, `necesidad-compra`,
`inventario-matriz` y `transferencias-sugeridas` — ver
`docs/auditoria/24_prediccion_categoria_paginacion.md` (incluye un bug real de
conexión de BD encontrado y corregido durante la verificación contra Postgres real).
