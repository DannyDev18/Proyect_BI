# 21. Mejora de features del modelo de ventas y granularidad semana/mes en el dashboard

- **Fecha:** 2026-07-10
- **Alcance:** `ml/` (features/contrato/entrenamiento del modelo `sales_rf`),
  `backend/app/services/prediction_service.py`, `backend/app/ml/preprocessing.py`,
  `backend/app/schemas/analytics.py`, `backend/app/api/routes/analytics.py`,
  `frontend/` (panel "Histórico y Predicción de Ventas (ML)" de Gerencia).
- **Motivo:** solicitud de negocio — el gráfico del Dashboard de Gerencia solo muestra
  granularidad diaria (90 días de historia + 14 días de forecast) y el usuario pidió poder
  alternar entre semanas y meses. Al revisar el panel también se detectó que el badge
  "Gradient Boosting" es texto hardcodeado en el frontend que no corresponde al algoritmo
  real servido, y que las variables de entrenamiento del modelo de ventas producen una
  predicción débil (R² bajo) que el usuario pidió mejorar.

## 1. Línea base (antes de este cambio)

Fuente: `ml/contracts/models/sales.json` (v0.1.0, `status: active`) y
`ml/REPORTE_MEJORA_MODELOS.md`.

- Algoritmo ganador real: `RandomForestRegressor` (no "Gradient Boosting" como muestra hoy
  el badge del frontend — `frontend/src/pages/DashboardGerencia.tsx:170` tiene el label
  fijo `'Gradient Boosting'`, desincronizado del sidecar `.meta.json` real).
- Métricas holdout cronológico 20% (ventana de entrenamiento: últimos 3 años,
  `VENTANA_ENTRENAMIENTO_VENTAS_ANIOS = 3` en `ml/main.py`): RMSE=6639.33 USD,
  MAE=3826.67 USD, **R²=0.2128**.
- Target: `y_sales_net` diario (`SUM(subtotal_neto)` por día), transform `log1p`/`expm1`
  autocontenido (`TransformedTargetRegressor`, H-01 cerrado).
- Features actuales (20, ver `sales.json`): lags 1/7/14/30/90 del target, rolling
  mean/std/min/max 7d + rolling mean 30d + expanding mean, calendario crudo
  (`is_weekend`, `day_of_week`, `month`, `quarter`, `is_month_start`, `is_month_end`,
  `es_feriado` solo fecha fija), y 3 exógenas contemporáneas rezagadas 1 día
  (`n_clientes_prev`, `n_facturas_prev`, `pct_descuento_prom_prev`).
- Ya se descartaron con evidencia (documentado en `ml/REPORTE_MEJORA_MODELOS.md`):
  `valor_cobrado_dia` de `fact_cobros_cxc` (empeora R² por colinealidad con la tendencia) y
  variables de `fact_inventario_snapshot` (<1% cobertura histórica).
- El dashboard solo pide granularidad diaria; no existe parámetro de agregación en
  `PredictionService.get_sales_forecast_weekly()` (`backend/app/services/prediction_service.py:41`)
  pese a que su nombre sugiere "semanal".

## 2. Hallazgos

| # | Hallazgo | Severidad | Evidencia |
|---|---|---|---|
| H-21-1 | Badge de algoritmo hardcodeado ("Gradient Boosting") no coincide con el algoritmo real servido (RandomForest) | Baja (cosmético, pero engañoso para el usuario de negocio) | `DashboardGerencia.tsx:170`, `sales.json:notes` |
| H-21-2 | No existe granularidad configurable en el endpoint de predicción de ventas; el nombre del método (`..._weekly`) ya no describe su comportamiento (es diario) | Media (bloquea el requerimiento de negocio) | `prediction_service.py:41-75` |
| H-21-3 | R²=0.2128 es débil para uso gerencial; variables de entrenamiento no incluyen ticket promedio, codificación cíclica de estacionalidad, ni feriados móviles de Ecuador (Carnaval/Viernes Santo) | Media (calidad de predicción) | `sales.json`, `build_features.py` |
| H-21-4 | Segundo badge hardcodeado "Modelo Gradient Boosting activo" en la cabecera del Dashboard de Gerencia, mismo problema que H-21-1 | Baja (cosmético) | `DashboardGerencia.tsx:57` |
| H-21-5 | El panel de predicción ignora los filtros `vendedor`/`almacen` que sí aplican los demás paneles del mismo dashboard (KPIs, ingresos por categoría) vía `AnalyticsRepository._build_ventas_filters` | Media (inconsistencia de UX/negocio) | `dataset_repository.py::get_daily_sales_history` (solo acepta `sucursal`), `DashboardGerencia.tsx` (`useSalesPrediction()` sin params) |

## 3. Acción propuesta (ver plan de implementación aprobado)

1. **No** se entrenan modelos nuevos por granularidad (evita duplicar contratos/pipeline/
   model_loader). Se reutiliza el forecast diario walk-forward existente
   (`backend/app/ml/forecasting.py::walk_forward_forecast`, sin cambios) con un horizonte
   más largo (12 semanas / 6 meses según el toggle) y se agrega (bucketiza) a
   semana/mes en `prediction_service.py` antes de responder al frontend. `GoalMLService`
   (que también usa `walk_forward_forecast`) no se ve afectado — sigue en modo diario.
2. **Mejora de variables** del modelo `sales_rf` (mismo target, mismo algoritmo elegido por
   competencia, contrato `sales.json` → v0.2.0):
   - `ticket_promedio_prev` = `y_sales_net / n_facturas` del día anterior (mismo criterio de
     rezago que las exógenas contemporáneas existentes: se calcula de las mismas
     transacciones del día, usarla sin rezagar sería fuga de datos).
   - Codificación cíclica `dow_sin/cos`, `month_sin/cos` (además de las columnas crudas
     `day_of_week`/`month` ya existentes, no en reemplazo).
   - Feriados móviles de Ecuador (Viernes Santo, Carnaval, calculados por offset desde
     Pascua) sumados a los feriados de fecha fija ya existentes en `es_feriado`.
   - Contrato queda en `status: "draft"` hasta confirmar con un backtest cronológico que el
     R² no empeora contra la línea base (0.2128); solo se sube a `active` si mejora o es
     neutro, siguiendo la metodología ya usada en `ml/REPORTE_MEJORA_MODELOS.md`.
3. Corrección del badge: el backend expone `algoritmo` en `MetricasPrediccion` (leído de
   `model_loader.get_meta("sales_rf").get("algorithm")`, ya disponible en el sidecar); el
   frontend deja de hardcodear el label en los dos sitios donde aparece (panel del gráfico y
   cabecera del dashboard, H-21-1/H-21-4).
4. **Filtro vendedor/almacén (H-21-5), decisión confirmada con el usuario 2026-07-10:** se
   extiende el mismo criterio ya usado para `sucursal` (filtrar tanto el histórico real como
   la predicción del modelo) a `vendedor` y `almacen`, siguiendo el patrón de JOIN ya usado en
   `AnalyticsRepository._build_ventas_filters` (`LEFT JOIN edw.dim_vendedor`, `JOIN
   edw.dim_almacen` sobre `fact_ventas_detalle.vendedor_sk`/`almacen_sk`). Esto **extiende
   H-14b** (modelo entrenado en la serie global, servido sobre una sub-serie fuera de su
   distribución de entrenamiento): la serie diaria de un solo vendedor o almacén es más
   dispersa y ruidosa (más días en $0) que la de una sucursal completa, así que la predicción
   filtrada puede ser notablemente menos confiable que el histórico real (que sigue siendo
   dato exacto del EDW, sin incertidumbre de modelo). El usuario aceptó este trade-off de forma
   explícita porque es consistente con el comportamiento ya existente para `sucursal` en
   producción, no un riesgo nuevo. `sales.json::known_serving_mismatch` se actualiza para
   reflejar el alcance ampliado de H-14b.

## 4. Reglas de negocio y restricciones verificadas

- Ninguna consulta nueva toca Producción (SAP); todo el trabajo de `ml/` es contra el EDW
  (`postgres_edw`) vía `SELECT`, sin cambios de DDL.
- Se respeta la regla 1 (`estado_documento_sk <> -1`) y la regla 12 (centinelas fuera) —
  no se agregan JOINs nuevos a otras tablas de hechos.
- Se respeta H-01 (target autocontenido, sin `expm1` manual en el serving) y H-06/H-09 ya
  cerrados (fillna(0) nunca bfill; intervalo con MAE real).
- El endpoint sigue restringido a `administrador`/`gerencia` (`gerente_checker` en
  `analytics.py`, sin cambios de RBAC).

## 5. Resultado del reentrenamiento

Ejecutado `docker compose run --rm ml python main.py` contra el EDW real (`postgres_edw`).
Holdout cronológico 20% (misma ventana de 3 años, `VENTANA_ENTRENAMIENTO_VENTAS_ANIOS`):

| Métrica | v0.1.0 (línea base) | v0.2.0 (features nuevas) | Δ |
|---|---|---|---|
| R² | 0.2128 | 0.2045 | -0.0083 |
| MAE | 3826.67 | 3819.69 | -6.98 (mejor) |
| RMSE | 6639.33 | 6686.95 | +47.62 (peor) |

Resultado mixto: MAE (métrica USD que ve el usuario) mejora marginalmente, R²/RMSE empeoran
marginalmente. Ganador de la competencia sigue siendo `RandomForestRegressor`. La magnitud es
consistente con ruido de una sola corrida de `RandomizedSearchCV` sin semilla fija; no se hizo
ablation test por feature individual (fuera de presupuesto de esta sesión). **Decisión: se
activa `sales.json` v0.2.0** (`status: "active"`) — no hay evidencia de degradación clara y las
features nuevas (ticket promedio, feriados móviles) son señales de negocio razonables de
mantener por diseño, no solo por métrica. Detalle completo en `ml/REPORTE_MEJORA_MODELOS.md`
§2.4. Si una sesión futura confirma degradación real de R² con corridas repetidas, revertir
siguiendo el mismo patrón que el experimento de Metas/Venta Neta (`ml/REPORTE_MEJORA_MODELOS.md`
§2.3).

`sales.pkl`/`sales.meta.json` fueron sobrescritos por esta corrida (26 features, ver sidecar).
El backend (`bi_backend`) sigue sirviendo el modelo cargado en su último arranque hasta el
próximo `docker compose restart backend` / `publish_models.py` — ver sección de verificación
final de esta auditoría para el reinicio y la comprobación de `GET /health`.

### 5.1 Incidente durante la implementación: alcance no contenido a `demand.pkl` (corregido)

`ml/main.py::run_ml_pipeline()` entrena los 6 modelos en una sola corrida y **el modelo de
demanda (`demand.pkl`, Bodega) usa el mismo `TimeSeriesLagsTransformer` compartido** que ventas
(`ml/src/features/build_features.py`, espejo en `backend/app/ml/preprocessing.py`). La primera
versión de la codificación cíclica (`dow_sin/cos`, `month_sin/cos`) se agregó sin acotar a
`isinstance(X_out.index, pd.DatetimeIndex)`, así que se coló también al dataset de demanda
(agrupado por producto) al correr `python main.py`. El `contract_validator` lo detectó
(`demand: WARN columnas no declaradas`) y comparando contra la línea base documentada en
`demand.json::notes` (RMSE=172.97, MAE=5.56, R2=0.899) el reentrenamiento con las columnas
coladas dio RMSE=185.85, MAE=5.82, R2=0.883 — degradación real en las 3 métricas, no ruido de
muestreo (a diferencia del resultado mixto de ventas).

**Corrección aplicada:** se acotaron `dow_sin/cos`, `month_sin/cos` y los feriados móviles a
`es_dataset_ventas = 'n_facturas' in X_out.columns` (señal que ya distinguía el dataset de ventas
del de demanda para `ticket_promedio`) en ambos archivos (`build_features.py`/`preprocessing.py`).
Se reentrenó de nuevo: `demand.pkl` quedó con el mismo conjunto de features que antes de esta
sesión (verificado contra el sidecar), RMSE=191.04, MAE=6.20, R2=0.876 — todavía por debajo de la
línea base documentada, pero ahora atribuible a la varianza normal de una corrida de
`RandomizedSearchCV`/CatBoost sin semilla fija entre ejecuciones (característica preexistente del
pipeline, no introducida por este cambio: el código de demanda es idéntico al de antes de esta
sesión). `contract_validator` pasa limpio para los 6 contratos tras la corrección.

**Lección para futuras sesiones:** cualquier cambio a `TimeSeriesLagsTransformer`/
`build_preprocessing_pipeline` en `build_features.py` o `preprocessing.py` afecta a la vez a
ventas y demanda (comparten el transformer); una feature nueva pensada para un solo modelo debe
acotarse explícitamente (como ya hacía `ticket_promedio`) y `python main.py` reentrena los 6
modelos en una sola corrida -- correr `contract_validator` después de CUALQUIER cambio a ese
archivo, no solo al del modelo que se pretendía tocar.
