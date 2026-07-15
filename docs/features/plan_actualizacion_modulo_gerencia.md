# Plan de Actualización — Módulo Gerencia (Dashboard Gerencial + Forecast)

> **Fecha:** 2026-07-14
> **Estado:** Propuesta (requiere auditoría previa `docs/auditoria/33_actualizacion_modulo_gerencia.md`)
> **Alcance:** `backend/app/api/routes/analytics.py` (prefijo `/analytics`), `analytics_service`, `prediction_service` (forecast `sales_rf` con `walk_forward_forecast`), `frontend/src/pages/DashboardGerencia.tsx`.

## 0. Diagnóstico preliminar (verificado en código)

| # | Hallazgo | Evidencia | Severidad |
|---|---|---|---|
| G-1 | **El forecast ignora fechas y categoría del filtro global.** La barra de filtros maneja `start_date, end_date, vendedor, categoria, almacen`, pero `useSalesPrediction` solo recibe `{granularidad, vendedor, almacen}` (`DashboardGerencia.tsx:29`). El usuario filtra por categoría/fechas y la predicción no cambia — misma clase de bug que Bodega D2. | `DashboardGerencia.tsx:19-33` | Alta |
| G-2 | **Lógica de negocio en el frontend:** los ingresos totales se calculan sumando `ventas_por_sucursal` en el cliente (`DashboardGerencia.tsx:36-37`). Si el backend cambia el shape o una sucursal viene nula, el KPI principal de gerencia queda mal sin que el backend lo sepa. Debe venir calculado del servicio. | `DashboardGerencia.tsx:35-37` | Media |
| G-3 | **Cobertura de filtros desigual por endpoint:** `/gerencia/kpis` y `/gerencia/revenue-by-category` reciben filtros; hay que levantar la matriz endpoint × filtro (fechas, vendedor, categoría, almacén, sucursal) y verificar que cada parámetro llega hasta el SQL del repository (no solo hasta la firma). | `analytics.py:20-84` | A verificar |
| G-4 | **`ProvenanceRail` consume un mock en producción** (`PROVENANCE_FACTS` de `services/mocks/provenance.mock`), riesgo ya listado en CLAUDE.md ("verificar que ningún dashboard consuma mocks"). Si este componente se muestra en Gerencia, presenta datos falsos como reales. | `components/layout/ProvenanceRail.tsx:1` | Alta si visible |

## 1. Fase 0 — Auditoría de caza de bugs (entregable: `33_actualizacion_modulo_gerencia.md`)

1. Matriz endpoint × filtro de los 7 endpoints `/analytics/gerencia/*`: qué acepta la firma, qué llega al repository, qué llega al SQL. Método: lectura de código + pruebas con `pytest`/requests comparando respuestas con y sin filtro sobre datos del EDW.
2. Reconciliación del KPI de ingresos vs EDW: `SUM(venta_neta)` de `fact_ventas_detalle` (con Venta Neta = definición oficial) contra lo que muestra el dashboard, mismos filtros y mismo período. Documentar cualquier desvío (>0.5%).
3. Verificar el contrato del forecast: `sales_rf` entrena con ventana de 3 años (regla 11); confirmar que el horizonte y granularidad que expone la UI coinciden con lo que `walk_forward_forecast` realmente genera, y que la banda de confianza (si se muestra) tiene fundamento y no es decorativa.
4. Inventariar todos los componentes montados en Gerencia que consuman `services/mocks/` (empezando por `ProvenanceRail`).

## 2. Fase 1 — Correcciones

1. **Filtros completos al forecast (G-1):** decidir en auditoría qué filtros tienen sentido para `sales_rf` (¿el modelo soporta segmentar por categoría? — si el dataset de entrenamiento no la incluye, el filtro NO debe ofrecerse para la predicción: deshabilitarlo con tooltip, patrón del plan de Bodega, en vez de fingir que filtra). Propagar los que sí apliquen por `prediction_service` → `preprocessing` respetando `loader.get_features('sales_rf')`.
2. **Mover el cálculo de ingresos totales al backend (G-2):** `analytics_service.get_gerencia_kpis` devuelve `ingresos_totales` calculado en SQL; el frontend solo formatea. Mantener `ventas_por_sucursal` para el desglose (aditivo).
3. **Cerrar gaps de la matriz de filtros (G-3):** completar propagación de parámetros hasta el SQL en `analytics_service`/repository; validación de valores contra catálogos (sucursales/categorías existentes).
4. **Mocks (G-4):** `ProvenanceRail` pasa a consumir un endpoint real (metadatos de `edw.etl_control`: última carga OK, filas cargadas — que es exactamente la procedencia que aparenta mostrar) o se retira del layout. Nunca un mock en build de producción.

## 3. Fase 2 — Mejoras de valor (posteriores a los fixes)

1. KPI de cumplimiento vs metas del período (reutiliza `public.metas_comerciales_operativas` vía `GoalsService` — sin ML).
2. Comparativa período anterior en todos los KPIs (mismo patrón `tendencia_pct` ya usado en Bodega).
3. Export del dashboard (Excel/PDF) reutilizando la infraestructura de reportes que produzca la fase 5 del plan de Bodega — no duplicar exportadores.

## 4. Validación

- `pytest backend/tests/` (unit + integration de analytics); casos nuevos por filtro.
- Reconciliación SELECT contra el EDW documentada en la auditoría 33.
- Forecast: backtest rápido (últimas 8 semanas reales vs predicción) para confirmar que los cambios de filtros no degradan el R² reportado en `ml/REPORTE_MEJORA_MODELOS.md`.
- RBAC: `gerente_checker` intacto; ningún endpoint nuevo sin `PermissionChecker`.

**Reglas transversales:** routers thin; excepciones de dominio; `ModelLoader` inyectado (nunca instanciado en endpoint); degradación con gracia en `prediction_service` intacta; cero hardcodes (umbrales como settings); actualizar auditoría 33 y `02_reglas_negocio_validadas.md` al cierre.
