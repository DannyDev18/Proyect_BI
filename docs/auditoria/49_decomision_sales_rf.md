# 49 — Decomisión de `sales_rf` y reemplazo del panel de predicción por histórico real

- **Fecha:** 2026-08-04
- **Objetivo:** el usuario pidió (1) quitar el gráfico "Histórico y Predicción de Ventas
  (ML)" del dashboard de Gerencia y reemplazarlo por un gráfico de barras+líneas que
  muestre cómo han sido las ventas reales mes a mes, y (2) **eliminar por completo** el
  modelo `sales_rf` de todo el sistema ("quitar este ML de todo rastro... no es muy
  eficaz con la información presentada y no aporta mucho al análisis"). El usuario
  confirmó explícitamente el alcance vía pregunta directa: decomisión completa (mismo
  criterio que `goals_rf`, auditoría 20), no solo ocultar la UI.
- **Alcance:** `ml/main.py`, `ml/retrain_all.py`, `ml/src/training/train_sales_
  prediction.py` (borrado), `ml/src/data/make_dataset.py` (`fetch_daily_sales` borrado),
  `ml/contracts/models/sales.json` (borrado), `ml/models/{sales.pkl,sales.meta.json}`
  (borrados), `ml/models/registry.json`, `backend/app/ml/{model_loader,inference,
  forecasting}.py` (forecasting.py borrado completo), `backend/app/services/
  {prediction_service,goal_ml_service,notification_service,training_service}.py`,
  `backend/app/repositories/{dataset_repository,analytics_repository}.py`,
  `backend/app/schemas/analytics.py`, `backend/app/api/routes/{analytics,sales}.py`,
  `backend/app/core/config.py`, tests unitarios/integración afectados,
  `frontend/src/{pages/DashboardGerencia.tsx,components/goals/VendorGoalDashboard.tsx,
  hooks/gerencia.ts,services/gerencia.ts,services/ventas.ts,hooks/ventas.ts,
  types/gerencia.ts,types/ventas.ts}`, `CLAUDE.md`.
- **Estado:** ✅ Implementado y validado en vivo contra el EDW real.

---

## 1. Decisión: `sales_rf` decomisionado, panel reemplazado por histórico real (sin ML)

`sales_rf` (RandomForest/serie de tiempo diaria, walk-forward) predecía ventas futuras
para el dashboard de Gerencia y para el panel "Pronóstico de cierre" del vendedor. El
usuario reportó que el gráfico no aportaba valor real al análisis. Se retira por
completo, siguiendo el mismo criterio que `goals_rf` (auditoría 20): no se mantiene como
cifra informativa secundaria, se elimina de entrenamiento y serving.

**Consumidores identificados y su tratamiento:**

1. **Panel "Histórico y Predicción de Ventas (ML)" (Gerencia)** — reemplazado por un
   gráfico de barras (venta neta mensual real) + línea (promedio móvil de 3 meses,
   aritmética simple, no ML) sobre los últimos 24 meses, respetando los filtros de
   vendedor/almacén ya existentes del dashboard.
2. **"Pronóstico de cierre" (panel del vendedor, `VendorGoalDashboard.tsx`)** —
   dependía 100% de `sales_rf` vía el mismo `walk_forward_forecast`. Se retira sin
   reemplazo (no se inventó una alternativa no solicitada): el vendedor sigue viendo su
   meta, cumplimiento real y comisión (paneles no afectados).
3. **Notificación "Desvío del forecast semanal" (Gerencia)** — generador calculado que
   reutilizaba `PredictionService.get_sales_forecast`. Se retira junto con
   `NOTIF_DESVIO_FORECAST_PCT`; el resto de notificaciones de Gerencia (divergencia
   plano-vs-variable de comisiones) no se toca.

## 2. Aplicado

- **Entrenamiento (`ml/`):** borrados `ml/src/training/train_sales_prediction.py`,
  `ml/contracts/models/sales.json`, `ml/models/{sales.pkl,sales.meta.json}` y su versión
  archivada en `ml/models/versions/sales_rf/`. Se quitó `fetch_daily_sales()` de
  `SalesTimeSerieExtractor` (`ml/src/data/make_dataset.py`) -- la clase se conserva
  (sigue sirviendo a demand/segmentation/churn/association/anomaly/cross_sell_ranker) y
  la llamada `train_general_sales_prediction(extractor)` de `ml/main.py::
  run_ml_pipeline()`. `ml/retrain_all.py` pierde la entrada `"sales_rf"` de
  `ENTRENADORES` y el import correspondiente.
- **Serving (`backend/`):** se quitó la clave `'sales_rf': 'sales.pkl'` de
  `_MODEL_FILES` y `MODEL_DISPLAY_NAMES` (`model_loader.py`) y la función `predict_sales`
  de `inference.py`. **`app/ml/forecasting.py::walk_forward_forecast` se CONSERVA sin
  cambios** -- verificado antes de tocarlo que `WarehouseService._forecast_ml_producto`
  (Bodega, predicción de compras por producto) también lo usa con `inference.
  predict_demand`, así que no es sales_rf-exclusivo pese a que la mayoría de sus
  consumidores (Gerencia, Pronóstico de cierre) sí lo eran. `PredictionService.
  get_sales_forecast` y sus 4 helpers privados
  (`_bucket_freq`, `_contar_periodos`, `_build_forecast_series`, `_build_forecast_
  metrics`, `_build_forecast_insights`) se eliminaron. `GoalMLService.forecast_cierre`
  y el dataclass `ForecastCierre` se eliminaron. `DatasetRepository.get_daily_sales_
  history` (sales_rf-only, sin otro consumidor) se eliminó.
- **API:** `GET /gerencia/sales-prediction` (`analytics.py`) y `GET /goals/forecast-
  cierre` (`sales.py`) eliminados, junto a `PrediccionVentasResponse`, `MetricasPrediccion`
  y `ForecastCierreResponse` (`schemas/analytics.py`). `CLAVES_VALIDAS`
  (`training_service.py`, panel MLOps de administrador) pierde `"sales_rf"` -- el panel
  de reentrenamiento ya no ofrece esa clave.
- **Notificaciones:** `NotificationService._generar_gerencia` pierde el bloque
  `desvio_forecast` (llamaba a `get_sales_forecast`); sigue delegando en
  `_generar_divergencia_comisiones()` sin cambios. `NOTIF_DESVIO_FORECAST_PCT`
  eliminado de `config.py`.
- **Nuevo, reemplaza al panel retirado:** `AnalyticsRepository.get_evolucion_mensual_
  ventas(vendedor, almacen, meses=24)` — Venta Neta real (venta bruta - devoluciones,
  mismo criterio G-02 que el resto del dashboard) agregada por mes, sin ningún modelo.
  Expuesto en `AnalyticsService.get_evolucion_mensual_ventas`, schema
  `EvolucionMensualVentasResponse` y `GET /gerencia/evolucion-mensual` (mismo RBAC que
  el resto de Gerencia). El promedio móvil de 3 meses (línea del gráfico) se calcula en
  el frontend sobre esta serie real -- aritmética simple, no un modelo.
- **Frontend:** `DashboardGerencia.tsx` reemplaza el `AreaChart` de histórico+predicción
  por un `ComposedChart` (Bar = venta neta mensual, Line = promedio móvil 3 meses),
  quita el badge "Modelo ML activo" y el panel "Inteligencia Comercial" (insights/
  métricas que eran 100% derivados de `sales_rf`); el sparkline de la tarjeta "Ingresos
  Totales" pasa a alimentarse de la nueva serie mensual real. `VendorGoalDashboard.tsx`
  pierde la tarjeta "Pronóstico de cierre del mes" y el hook `useGoalForecastCierre`.
  `hooks/gerencia.ts::useSalesPrediction`, `services/gerencia.ts::getSalesPrediction`,
  `types/gerencia.ts::{MetricasPrediccion,SalesPredictionResponse,...}` eliminados;
  `hooks/ventas.ts::useGoalForecastCierre`, `services/ventas.ts::getGoalForecastCierre`,
  `types/ventas.ts::ForecastCierre` eliminados. Nuevos: `hooks/gerencia.ts::
  useEvolucionMensualVentas`, `services/gerencia.ts::getEvolucionMensualVentas`,
  `types/gerencia.ts::{EvolucionMensualVentasItem,EvolucionMensualVentasResponse}`.
- **Tests:** `test_inference.py` pierde el test de `predict_sales`; `test_goal_ml_
  service.py` pierde los 2 tests de `forecast_cierre`; `test_goal_ml_integration.py`
  actualizado a 5 modelos (no 6) y `assert not loader.is_loaded("sales_rf")`;
  `test_analytics_ml_endpoints.py` pierde los tests de `/gerencia/sales-prediction`;
  `test_system_service.py`/`test_notification_service.py`/`conftest.py` actualizados
  para no listar `sales_rf` como modelo cargado.

## 3. Validación

- `pytest backend/tests/unit -q` — ver resultado en el cierre de la sesión (sección 4).
- `python -m py_compile main.py retrain_all.py src/data/make_dataset.py` (desde `ml/`)
  — sin errores.
- `tsc --noEmit` / `oxlint` / `npm run build` (frontend) — limpios.
- Backend reiniciado en Docker: arranca con **5 modelos** cargados (`demand_rf,
  churn_rf, segmentation, association, anomaly`), sin `sales_rf` y sin warnings/errores.
- `GET /gerencia/evolucion-mensual` probado en vivo contra el EDW real.

## 4. Pendiente / fuera de este alcance

- `ml/notebooks/*.ipynb` que hicieron EDA sobre `sales_rf` en su momento se dejan
  intactos (artefactos exploratorios históricos, no se ejecutan como parte de ningún
  pipeline) -- mismo criterio que `goals_rf`.
- `docs/auditoria/21_mejora_features_ventas_y_granularidad.md` y
  `docs/features/plan_mejora_modelo_ventas.md` se conservan como historia del modelo ya
  retirado (mismo criterio que la auditoría 20 con los documentos de `goals_rf`).
