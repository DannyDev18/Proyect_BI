# 15 — Fase: Integración del módulo Metas y Comisiones con los modelos ML

- **Fecha:** 2026-07-09
- **Objetivo:** incorporar los 7 modelos ML ya reentrenados y publicados (Fase 3 de la capa de contratos, docs 12/13) dentro del flujo funcional del módulo de Metas y Comisiones, respetando completamente la arquitectura de contratos ML existente. No se reentrenó ningún modelo, no se modificó el pipeline de entrenamiento (`ml/src/training/*`) ni se regeneraron artefactos.
- **Alcance:** `backend/app/ml/*`, `backend/app/repositories/goal_repository.py`, `backend/app/services/{goal_ml_service.py, goals_service.py, prediction_service.py}`, `backend/app/api/routes/{sales.py, goals.py}`, `backend/app/schemas/{analytics.py, goal.py}`, `docker-compose.yml`/`docker-compose.override.yml`, frontend (`VendorGoalDashboard.tsx`, `GoalsConsole` + nuevo `GoalsAISummaryPanel.tsx`).
- **Método:** lectura del código real (`ModelLoader`, `inference.py`, `ml/src/contracts/*`, `ml/contracts/models/*.json`) antes de implementar; consultas `SELECT` contra el EDW real para diseñar el SQL nuevo; `py_compile`/`tsc -b`/`pytest` para validar.
- **Estado:** ✅ Implementado. Ver §7 para los entregables completos.

---

## 1. Hallazgo de análisis previo (bloqueante, resuelto en §2)

`ml/src/contracts/contract_validator.py` es la barrera de calidad del lado del **entrenamiento** (`ml/`, otra imagen Docker). El backend de producción **no tiene acceso al código fuente de `ml/`** (solo a los `.pkl` vía volumen de solo lectura, confirmado en `docker-compose.yml`: `./ml/models:/app/ml_models:ro`, y en CLAUDE.md). Por lo tanto, la instrucción "ModelLoader → ContractValidator → Modelo → validación de salida" **no puede implementarse importando `ml.src.contracts.*` desde `backend/`** sin romper la separación de imágenes Docker ya documentada (decisión R-4, auditoría 12).

**Resolución:** se construyó una segunda barrera, nativa del backend (`backend/app/ml/contract_validation.py`), que relee el **mismo JSON declarativo** (`ml/contracts/models/*.json`) — la interfaz ya documentada entre ambos lados — sin importar ningún paquete de `ml.*`. Se montó el directorio de contratos como volumen de solo lectura adicional (`./ml/contracts/models:/app/ml_contracts:ro`), igual que ya se hace con los `.pkl`.

---

## 2. Arquitectura implementada

```
EDW (PostgreSQL)
   │  goal_repository.py (histórico mensual, transacciones, top productos)
   │  dataset_repository.py (serie diaria por sucursal, ya existente)
   ▼
ModelLoader.load_all()
   │  carga <modelo>.pkl + <modelo>.meta.json (ya existía)
   │  NUEVO: carga ml_contracts/<contract_name>.json → ModelContractLite
   ▼
app/ml/inference.py (predict_sales, predict_demand, detect_anomalies,
                      predict_goal_growth_ratio, get_recommendations)
   │  1. selecciona columnas vía loader.get_features(key)          (ya existía)
   │  2. NUEVO: contract_validation.validate_features(...)  → enforce()
   │  3. model.predict(X) / decision_function(X)                    (ya existía)
   │  4. NUEVO: contract_validation.validate_prediction(...) → enforce()
   ▼  (ModelContractError si el contrato ACTIVE falla -- no se degrada en silencio)
GoalMLService (nuevo, backend/app/services/goal_ml_service.py)
   │  compone: GoalRepository + DatasetRepository + ModelLoader + GoalsService
   │  - suggest_goal()              → goals_rf (reutiliza GoalsService.predict_goal_amount)
   │                                   + IQRGoalCalculationEngine (estadístico + anomaly)
   │  - forecast_cierre()           → sales_rf vía app/ml/forecasting.py (walk-forward)
   │  - get_commercial_recommendations() → association (item_history = top productos del vendedor)
   │  - get_category_recommendations()   → association global + dim_producto.nombre_clase
   │  - classify_vendor_risk()      → dato real (ranking_vendedores) + ritmo temporal
   ▼
Endpoints (sales.py: vendedor · goals.py: gerencia)
   ▼
Frontend (VendorGoalDashboard.tsx · GoalsAISummaryPanel.tsx)
```

---

## 3. Modelos integrados y qué proceso usa cada uno

| Proceso (enunciado) | Modelo | Contrato | Cómo se integra |
|---|---|---|---|
| **Generación de metas** | `goals_rf` (CatBoost, ratio de crecimiento) | `ml/contracts/models/goals.json` (`active`, `plausible_range=[0,1.5]`) | `GoalMLService._meta_sugerida_ia` reutiliza `GoalsService.predict_goal_amount` (ya validado, con capping 0.8-1.2) — **no se reimplementa**. Se muestra junto a la meta estadística. |
| **Detección de valores atípicos** | `anomaly` (IsolationForest) | `ml/contracts/models/anomalies.json` (`active`, features = línea de transacción: `subtotal_neto, cantidad, costo_total, margen`) | `GoalMLService._detectar_meses_atipicos` corre el modelo al grano **correcto** (transacción, no mes agregado — alimentar agregados mensuales violaría el contrato de features). Agrupa por mes la fracción de transacciones anómalas y pasa los meses con fracción > 2× la mediana del propio vendedor a `IQRGoalCalculationEngine`, que los **pesa a la mitad** (no los elimina — instrucción explícita del enunciado). |
| **Recomendación comercial** | `association` (reglas direccionales) | `ml/contracts/models/recommendation.json` (`active`) | `get_commercial_recommendations` reutiliza `inference.get_recommendations` (misma función que ya usa el caso de uso de churn/cross-sell) con `item_history` = productos más vendidos del vendedor. `get_category_recommendations` agrega las reglas globales por `dim_producto.nombre_clase` para el panel gerencial. |
| **Pronóstico de cierre** | `sales_rf` (RandomForest, TransformedTargetRegressor) | `ml/contracts/models/sales.json` (`active`, `plausible_range=[0,5000000]`) | `forecast_cierre` reutiliza el walk-forward **extraído** de `PredictionService.get_sales_forecast_weekly` (nuevo `app/ml/forecasting.py`, elimina la duplicación) con horizonte = días restantes del mes. Probabilidad de alcanzar la meta: aproximación estadística explícita (normal con σ = MAE real del holdout × √días, `statistics.NormalDist` de la stdlib) — documentada como aproximación, no como un clasificador calibrado. |

**No integrado a este módulo (fuera de alcance deliberado):** `churn_rf`, `segmentation` — no tienen relación funcional con metas/comisiones y ya están integrados en sus propios casos de uso (`sales.py::churn-risk`, `.../clientes/{id}/segmento`).

---

## 4. Validaciones de contrato aplicadas

Implementadas en `backend/app/ml/contract_validation.py` + wiring en `backend/app/ml/inference.py`:

1. **Features**: antes de `model.predict(X)`, se comparan las columnas de `X` contra `contract.required_features`. Si faltan columnas y el contrato está `active` → `ModelContractError` (no se ejecuta la inferencia).
2. **Salida (plausible_range)**: después de predecir, cada valor se compara contra `contract.output.plausible_range`. Si está fuera de rango y el contrato está `active` → `ModelContractError`.
3. **Metadata de compatibilidad**: `ModelContractLite.is_active` determina si una violación bloquea (contrato `active`) o solo se registra como advertencia (contrato `draft` o ausente) — mismo comportamiento que `ml/src/contracts/contract_validator.py`, reimplementado sin depender de él.

**Dos políticas de fallo, documentadas explícitamente en `goal_ml_service.py`:**
- Pronóstico de cierre y recomendaciones son el entregable directo de su llamada → un `ModelContractError` se **propaga** (ya es `DomainError` → HTTP 400 vía el handler catch-all existente en `main.py`, sin cambios ahí).
- La señal de anomalías es un insumo secundario del cálculo de metas → si su contrato falla, se **registra el error y se continúa** sin esa señal (la meta se sigue calculando solo con IQR).

Los 7 contratos verificados están en `status: "active"` (confirmado por lectura directa de `ml/contracts/models/*.json`, Fase 3 ya completada según CLAUDE.md).

---

## 5. Endpoints nuevos

| Endpoint | Rol | Servicio | Modelo(s) |
|---|---|---|---|
| `GET /api/v1/analytics/ventas/goals/forecast-cierre` | ventas, gerencia, administrador | `GoalMLService.forecast_cierre` | `sales_rf` |
| `GET /api/v1/analytics/ventas/goals/meta-sugerida` | ventas, gerencia, administrador | `GoalMLService.suggest_goal` | `goals_rf` + `anomaly` (interno) |
| `GET /api/v1/analytics/ventas/goals/recomendaciones` | ventas, gerencia, administrador | `GoalMLService.get_commercial_recommendations` | `association` |
| `GET /api/v1/gerencia/goals/ai-summary` | gerencia, administrador | `GoalMLService.classify_vendor_risk` + `get_category_recommendations` | `association` (ranking real ya existente en `AnalyticsService.get_sales_kpis`, sin modelo) |

Los dos primeros usan `id_vendedor_origen`/`sucursal` del usuario autenticado (`current_user`), no un parámetro libre — mismo patrón RBAC que el resto del módulo (`resolve_sucursal_filter`, `PermissionChecker`).

---

## 6. Componentes frontend actualizados

- **`frontend/src/components/goals/VendorGoalDashboard.tsx`**: las secciones "Última semana" y "Facturas post-meta" (antes con datos parciales o placeholder, ver auditoría 14) ahora consumen `forecast-cierre` (días restantes, proyección de cierre, % esperado, probabilidad real) y se agregó "Meta sugerida (IA vs. estadística)" y "Productos recomendados". "Comisión" y el detalle de "Facturas post-meta" siguen en estado "Próximamente" — no existe módulo de liquidación de comisiones (hallazgo R-1, auditoría 14), fuera de alcance de esta fase (solo integración ML, no se pidió crear ese módulo).
- **`frontend/src/components/goals/GoalsAISummaryPanel.tsx`** (nuevo): vendedores en riesgo / alta probabilidad (ritmo real vs. tiempo transcurrido) y recomendaciones por categoría — montado en `DashboardMetas.tsx` junto a `GoalsConsole`.
- Tipos/servicios/hooks nuevos en `types/ventas.ts`, `services/ventas.ts`, `hooks/ventas.ts` (vendedor) y `types/goals.ts`, `services/goals.ts`, `hooks/goals.ts` (gerencia), siguiendo el patrón ya establecido (página → hook → servicio → tipos → `queryKeys`).

---

## 7. Entregables

### 7.1 Archivos creados
- `backend/app/ml/contract_validation.py`
- `backend/app/ml/forecasting.py`
- `backend/app/services/goal_ml_service.py`
- `backend/tests/unit/test_contract_validation.py`
- `backend/tests/unit/test_goal_ml_service.py`
- `backend/tests/integration/test_goal_ml_integration.py`
- `frontend/src/components/goals/GoalsAISummaryPanel.tsx`
- `docs/auditoria/15_fase_integracion_ml_metas_comisiones.md` (este documento)

### 7.2 Archivos modificados
- Backend: `app/ml/model_loader.py`, `app/ml/inference.py`, `app/core/config.py`, `app/core/exceptions.py`, `app/main.py`, `app/api/dependencies.py`, `app/api/routes/{sales.py, goals.py}`, `app/schemas/{analytics.py, goal.py}`, `app/repositories/goal_repository.py`, `app/services/{goals_service.py, prediction_service.py}` (refactor de `get_sales_forecast_weekly` para reutilizar `forecasting.walk_forward_forecast`, sin cambio de comportamiento), `tests/unit/{test_goals_service.py, test_goal_calculation_engine.py}` (rename `_predict_goal_amount`→`predict_goal_amount`; nuevos casos de señal ML).
- Infra: `docker-compose.yml`, `docker-compose.override.yml` (nuevo volumen `ml_contracts`, solo lectura).
- Frontend: `pages/DashboardMetas.tsx`, `components/goals/VendorGoalDashboard.tsx`, `types/{ventas.ts, goals.ts}`, `services/{ventas.ts, goals.ts}`, `hooks/{ventas.ts, goals.ts}`, `constants/queryKeys.ts`.

### 7.3 Modelos ML integrados
`goals_rf`, `anomaly`, `association`, `sales_rf` (ver §3 para el detalle de cada uno).

### 7.4 Servicios que consumen cada modelo
`GoalMLService` (nuevo, orquestador de los 4 modelos) + `GoalsService.predict_goal_amount` (reutilizado, no duplicado) + `app/ml/inference.py` (capa de invocación + validación de contrato, ya existente, extendida).

### 7.5 Endpoints afectados
Ver tabla §5 (3 nuevos en `sales.py`, 1 nuevo en `goals.py`). Ningún endpoint existente cambió su contrato de respuesta.

### 7.6 Componentes frontend actualizados
Ver §6.

### 7.7 Riesgos encontrados

| # | Riesgo | Detalle | Mitigación aplicada / pendiente |
|---|---|---|---|
| R-1 | El volumen `ml/contracts/models` debe montarse en producción para que la validación de contrato tenga `plausible_range` real | Sin el volumen, `ModelLoader.get_contract()` devuelve `None` y la validación degrada a "sin bloquear" (ver `contract_validation.enforce`) — no rompe, pero pierde la barrera de calidad | Mitigado: se agregó el mount en `docker-compose.yml` y `docker-compose.override.yml`. **Pendiente**: aplicar `docker compose up` con el volumen nuevo en el entorno real (no se reinició ningún contenedor en esta fase). |
| R-2 | `sales_rf` entrena con la serie **global** (todas las sucursales), no por vendedor (H-14b, ya documentado en `sales.json`) | El pronóstico de cierre es por **sucursal**, nunca por vendedor individual -- se decidió explícitamente no ofrecer un "cierre por vendedor" con este modelo porque sería una inferencia fuera de la distribución de entrenamiento | Documentado en el código y aquí; no se inventó una probabilidad por vendedor con un modelo que no tiene ese grano (ver R-3 del panel gerencial). |
| R-3 | "Vendedores en riesgo/alta probabilidad" en el panel gerencial usa una clasificación por **ritmo** (ventas reales vs. tiempo transcurrido), no una probabilidad calibrada por modelo | Es la alternativa honesta dado R-2 -- inventar una probabilidad ML por vendedor sin que el modelo tenga ese grano habría sido exactamente el antipatrón que la auditoría 11 documentó (predicciones fabricadas) | Documentado explícitamente en `goal_ml_service.py` (constante `UMBRAL_RIESGO_RITMO`). Próximo paso si se requiere probabilidad real: reentrenar `sales_rf` (o un modelo nuevo) con grano por vendedor -- fuera de alcance de esta fase (no reentrenar). |
| R-4 | El emparejamiento "vendedor en el ranking" es por **nombre** (`ranking_vendedores[].nombre`), no por `codven` | Ya señalado en la auditoría 14 (R-4 análogo) — `AnalyticsRepository.get_sales_performance` no expone `codven` en el ranking | No corregido en esta fase (tocar `analytics_repository.py` para agregar `codven` al ranking es un cambio de bajo riesgo pero fuera del alcance ML de esta fase). |
| R-5 | `_detectar_meses_atipicos` ejecuta una consulta + una inferencia por cada `suggest_goal()` (no cacheada) | Costo aceptable para un dashboard interactivo (24 meses de transacciones de un vendedor, no de toda la empresa), pero se vuelve costoso si se llama para **todos** los vendedores en batch | El endpoint gerencial (`ai-summary`) NO llama `suggest_goal` por vendedor (evita el N+1) -- usa el ranking ya agregado. `meta-sugerida` es por-vendedor, bajo demanda, aceptable. |
| R-6 | La probabilidad de "alcanzar la meta" en `forecast_cierre` es una aproximación estadística (normal, σ=MAE·√días), no un intervalo calibrado | Documentado explícitamente en el docstring de `_probabilidad_alcanzar_meta` | Aceptado como aproximación explícita, igual espíritu que el intervalo ±MAE que Gerencia ya usa (H-09). |
| R-7 | La comisión (estimada/ganada) y el detalle de "facturas post-meta" siguen sin implementar | Ya documentado como hallazgo R-1 en la auditoría 14 -- esta fase integra los 4 modelos pedidos, no construye el módulo de liquidación de comisiones (no fue parte del encargo de esta fase) | Sin cambios; sigue como "Próximamente" en el frontend, sin datos inventados. |

### 7.8 Próximos pasos para optimizar el módulo de Metas y Comisiones

1. Aplicar `docker compose up` (o el despliegue equivalente) con el volumen `ml_contracts` nuevo, y correr `pytest -m integration` contra el entorno real para confirmar que `ModelLoader.get_contract()` resuelve los 7 contratos en producción (hoy solo verificado localmente).
2. Agregar `codven` al `ranking_vendedores` de `AnalyticsRepository.get_sales_performance` (R-4) para dejar de emparejar vendedores por nombre en `classify_vendor_risk`.
3. Evaluar si vale la pena reentrenar `sales_rf` (o un modelo nuevo) con grano por vendedor para ofrecer una probabilidad de cierre calibrada por vendedor, no solo por sucursal (R-2/R-3) -- requeriría una fase de entrenamiento nueva, fuera de este alcance.
4. Diseñar el módulo de liquidación de comisiones (tabla `bi_comisiones` propuesta en la auditoría 14 §5) para cerrar "Comisión estimada/ganada" y "Facturas post-meta" en el dashboard vendedor.
5. Cachear `_detectar_meses_atipicos` (o materializarlo en una tabla/vista) si el uso del endpoint `meta-sugerida` crece (R-5).
6. Considerar exponer `known_serving_mismatch` de cada contrato (ya existe en el JSON) en el panel de administración ML (`admin_ml.py`), para que MLOps vea en un solo lugar las limitaciones conocidas de cada modelo en producción (H-14b, etc.), no solo en los `.json` del repo.
