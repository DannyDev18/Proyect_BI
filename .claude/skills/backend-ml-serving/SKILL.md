---
name: backend-ml-serving
description: >-
  Especialista en el backend FastAPI de este proyecto y en cómo sirve los 6 modelos ML ya
  entrenados (ModelLoader, contratos, endpoints por rol). Usar SIEMPRE que la tarea toque
  `backend/app/ml/` (model_loader, inference, preprocessing, forecasting, contract_validation),
  `backend/app/services/prediction_service.py`, `backend/app/services/goal_ml_service.py`,
  `backend/app/services/training_service.py`, cualquier router bajo `backend/app/api/routes/`
  que exponga predicciones (analytics, sales, warehouse, admin, admin_ml, goals), o cuando se
  pida agregar/exponer un endpoint nuevo que consuma un modelo `.pkl`, cambiar el contrato de
  entrada/salida de un modelo, diagnosticar `ModelNotLoadedError`/`ModelContractError`, o tocar
  el volumen Docker que monta `ml/models` y `ml/contracts/models` en el backend. No usar para
  el propio entrenamiento (`ml/main.py`, `ml/src/training/`) — eso es otro contenedor/imagen;
  esta skill es del lado del serving (backend), no del entrenamiento.
---

# Backend ML Serving

Eres el especialista del backend FastAPI de este proyecto, específicamente en la capa que **sirve
inferencia de los 7 modelos ML ya entrenados** a los dashboards por rol. Tu prioridad es la
**integridad de los contratos entre `ml/` y `backend/`**: el backend nunca reentrena ni importa
código de `ml/src/` en producción, solo consume artefactos (`.pkl` + sidecar `.meta.json` +
contrato `.json`) a través de un volumen Docker de solo lectura. Cualquier cambio que rompa esa
frontera (importar `ml.*` en runtime, hardcodear columnas, asumir que `feature_names_in_` existe)
es un defecto, no una libertad de implementación.

## Arquitectura de serving (específica de este proyecto)

```
Docker: ml/models/*.pkl + *.meta.json  ──┐
Docker: ml/contracts/models/*.json      ──┤ (volúmenes :ro, ver docker-compose.yml)
                                          ▼
app/main.py (lifespan) → ModelLoader(models_dir=ML_MODELS_DIR, contracts_dir=ML_CONTRACTS_DIR)
                          .load_all() → app.state.model_loader (Singleton, un solo request de disco)
                                          ▼
app/api/dependencies.py → ModelLoaderDep (Depends(get_model_loader)) inyectado a servicios
                                          ▼
app/services/{prediction_service,goal_ml_service}.py  (orquestación: repo → preprocessing → inference → formateo)
                                          ▼
app/ml/inference.py (funciones puras, sin I/O) ← app/ml/contract_validation.py (2ª barrera)
                                          ▼
app/api/routes/{analytics,sales,warehouse,admin,goals}.py  (routers, prefijo /api/v1/...)
```

| Pieza | Archivo | Rol |
|---|---|---|
| Carga/caché de modelos | `backend/app/ml/model_loader.py` | `_MODEL_FILES` (dict clave→`.pkl`) es el único punto de extensión para un modelo nuevo. Lee sidecar `.meta.json` (features, metrics, cluster_to_segment) y contrato `.json`. Tolera archivos faltantes (WARNING, no crash) — cada `.get()` falla explícito con `ModelNotLoadedError`. |
| Inferencia pura | `backend/app/ml/inference.py` | Una función `predict_*`/`detect_*`/`get_*` por modelo. Recibe `ModelLoader` + `DataFrame`, sin DB/HTTP — así se testea con un loader fake (`backend/tests/unit/test_inference.py`). Selecciona columnas vía `loader.get_features(key)`, nunca `model.feature_names_in_` (no todos los estimadores lo exponen: CatBoost envuelto en `TransformedTargetRegressor`, `Pipeline` de segmentación). |
| Contratos (2 barreras) | `backend/app/ml/contract_validation.py` | Relee el mismo JSON de `ml/contracts/models/*.json` con un parser propio (`ModelContractLite`), sin importar `ml.src.contracts.*` — el backend de producción no tiene ese código. Valida columnas requeridas y rango plausible de la predicción. Solo **bloquea** (`ModelContractError`) si `status == "active"`; un contrato `draft` o ausente solo loguea WARNING. |
| Forecasting iterativo | `backend/app/ml/forecasting.py` | `walk_forward_forecast`: genera N días hacia adelante re-alimentando cada predicción como input del siguiente paso (usado por ventas). |
| Preprocessing en vivo | `backend/app/ml/preprocessing.py` | Reconstruye a partir del historial (repos) las mismas features de entrenamiento (`build_preprocessing_pipeline`, `select_features_and_target`) — debe permanecer en sync con `ml/src/features/build_features.py` del lado de entrenamiento. |
| Orquestación por caso de uso | `backend/app/services/prediction_service.py` | 6 casos de uso (ventas, demanda, churn, anomalías, recomendaciones, segmentación RFM). Patrón fijo: repository → preprocessing → inference → reglas de formateo. Todo método público **degrada con gracia** (`try/except` + `logger.error` + valor neutro) para no tumbar un dashboard completo por un modelo caído — no "arregles" esto quitando el try/except. |
| Integración Metas | `backend/app/services/goal_ml_service.py` | Compone `GoalRepository` + `DatasetRepository` + `ModelLoader` + `GoalsService` (reutiliza el capping de `GoalsService`, no lo reimplementa). |
| MLOps (reentrenar) | `backend/app/services/training_service.py` + `app/api/routes/admin_ml.py` | Dispara el pipeline de `ml/src/training/` como subprocess externo. Solo funciona si `ML_SOURCE_DIR` existe (montado por `docker-compose.override.yml`, solo dev); en producción-like (`docker-compose.yml` base) falla con mensaje claro — no está montado a propósito. |
| Inyección de dependencias | `backend/app/api/dependencies.py` | `ModelLoaderDep = Annotated[ModelLoader, Depends(get_model_loader)]` — el loader vive en `request.app.state.model_loader` (un solo objeto para todo el proceso, cargado en el `lifespan`). Nunca instancies `ModelLoader()` dentro de un endpoint/servicio: siempre inyecta la dependencia existente. |
| Config de rutas de modelos | `backend/app/core/config.py` | `ML_MODELS_DIR` (`.pkl`), `ML_CONTRACTS_DIR` (JSON de contrato), `ML_SOURCE_DIR` (código `ml/`, solo dev). Vienen de env vars — nunca hardcodear rutas de modelos en código. |
| Excepciones de dominio | `backend/app/core/exceptions.py` | `ModelNotLoadedError`, `ModelContractError`, `ExternalDataError` — los servicios lanzan estas, nunca `HTTPException`; los handlers globales en `main.py` las traducen a HTTP (400 para dominio, 404/409/403 para las específicas). |

## Los 6 modelos y sus claves (`_MODEL_FILES` en `model_loader.py`)

Nota (2026-07-10): el 7º modelo, `goals_rf` (metas y comisiones), fue **decomisionado**
(`docs/auditoria/20_decomision_goals_rf.md`) -- Metas y Comisiones ahora usa 100%
estadística pura (`IQRGoalCalculationEngine`, sin ML). No lo reintroduzcas en
`_MODEL_FILES` ni en `ml/contracts/models/` sin una decisión de negocio explícita.

| Clave interna | Archivo `.pkl` | Función de inferencia | Consumidor (rol/dashboard) |
|---|---|---|---|
| `sales_rf` | `sales.pkl` | `predict_sales` (vía `walk_forward_forecast`) | Gerencia — forecast semanal |
| `demand_rf` | `demand.pkl` | `predict_demand` | Bodega — reposición |
| `churn_rf` | `churn.pkl` | `predict_churn` | Ventas — riesgo de fuga |
| `segmentation` | `segmentation.pkl` | `predict_segmentation` + `get_cluster_to_segment` | Ventas — RFM interactivo |
| `association` | `recommendation.pkl` | `get_recommendations` | Ventas — venta cruzada |
| `anomaly` | `anomalies.pkl` | `detect_anomalies` | Admin — auditoría/fraude |

No inventes una séptima clave ni renombres estas sin verificar `ml/contracts/models/*.json` (el
nombre de archivo sin extensión debe coincidir con `contract_name`) y sin coordinar con el lado de
entrenamiento (`ml/main.py`).

## Cómo agregar un endpoint nuevo que consuma un modelo existente

1. **No reinventes la capa de acceso al modelo.** Si el caso de uso ya tiene una función en
   `app/ml/inference.py`, resta usarla desde un servicio (o método nuevo en un servicio existente
   si el caso de uso es una variación del mismo dominio).
2. **Repository → Service → Route**, siempre en ese orden de capas (regla del `CLAUDE.md` raíz):
   el router no arma DataFrames ni llama `inference.*` directamente.
3. En el servicio: obtén los datos vía un repository (`PredictionRepository`/`DatasetRepository`),
   arma el `DataFrame` con las columnas que el modelo espera (`model_loader.get_features(key)` es
   la fuente de verdad, no supongas el orden), llama la función de `inference.py`, y envuelve en
   `try/except` con `logger.error` + degradación a un valor neutro — sigue el patrón exacto de los
   6 métodos existentes en `prediction_service.py`.
4. Inyecta el servicio en el router vía una nueva entrada en `app/api/dependencies.py`
   (`get_<algo>_service`) — no instancies el servicio a mano dentro del endpoint.
5. Registra el router en `app/api/routes/api.py` con el prefijo correcto
   (`/analytics`, `/analytics/bodega`, `/analytics/ventas`, `/analytics/admin`, `/gerencia/goals`)
   según el rol dueño del dashboard, y aplica el `PermissionChecker` correspondiente
   (`app/core/deps.py`) — nunca un endpoint de predicción sin control RBAC.
6. Si el endpoint expone un dato agregado nuevo del contrato (ej. una métrica del sidecar
   `.meta.json` que hoy no se usa), pásalo a través del servicio, no lo leas directo en el router.
7. Actualiza `backend/tests/unit/test_inference.py` (si tocaste `inference.py`, con un
   `ModelLoader` fake) y `backend/tests/integration/test_analytics_ml_endpoints.py` (si agregaste
   endpoint) — ver la sección de tests abajo.

## Cómo agregar un modelo nuevo (octavo modelo)

1. Coordina primero con el lado de entrenamiento: debe existir `ml/models/<nombre>.pkl` +
   `<nombre>.meta.json` + `ml/contracts/models/<nombre>.json` con `contract_name` coincidente.
2. Agrega la entrada en `_MODEL_FILES` de `model_loader.py` (clave interna → nombre de archivo).
3. Escribe la función `predict_*`/`get_*` correspondiente en `inference.py` siguiendo el patrón:
   `_select_features` → `_validate_features_or_raise` → `model.predict(...)` →
   `_validate_prediction_or_raise` por cada valor (si el output es numérico continuo).
4. Verifica que el volumen Docker ya monta esos dos directorios (`ml/models`,
   `ml/contracts/models`) — normalmente sí, porque es genérico por directorio, no por archivo.
5. Escribe el caso de uso en el servicio correspondiente y el endpoint siguiendo la sección
   anterior.
6. Nunca actives el contrato (`status: "active"` en el JSON) hasta que el equipo de `ml/` lo
   confirme — un contrato activo bloquea la inferencia (`ModelContractError`) ante cualquier
   desvío; uno `draft` solo informa.

## Errores comunes a vigilar en este proyecto

- **Instanciar `ModelLoader()` fuera del `lifespan`**: rompe el patrón Singleton y recarga modelos
  en cada request (I/O de disco innecesario, y dos instancias con caché desincronizada).
- **Usar `model.feature_names_in_`** en vez de `loader.get_features(key)`: falla silenciosamente o
  con `AttributeError` para CatBoost/`TransformedTargetRegressor`/`Pipeline` (H-07, ya corregido
  una vez — no reintroducir el patrón viejo).
- **Envolver `HTTPException` en un servicio**: los servicios lanzan excepciones de dominio
  (`app/core/exceptions.py`); solo `main.py` traduce a HTTP.
- **Quitar el `try/except` de degradación en `prediction_service.py`** creyendo que es manejo de
  errores superfluo: es una decisión de producto — un modelo caído no debe tumbar el dashboard
  completo, solo ese widget (siempre logueado en `ERROR`, nunca silencioso).
- **Hardcodear rutas `/app/ml_models` o `/app/ml_contracts`**: siempre vía `settings.ML_MODELS_DIR`
  / `settings.ML_CONTRACTS_DIR` (`app/core/config.py`), nunca literal en código.
- **Asumir que `ML_SOURCE_DIR` existe en producción**: solo está montado en
  `docker-compose.override.yml` (dev). `TrainingService` debe fallar con mensaje claro si no
  existe, no asumir que el reentrenamiento siempre es posible.
- **Reordenar o renombrar claves de `_MODEL_FILES`** sin verificar que el `contract_name` del JSON
  y el nombre de archivo `.pkl` reconstruido bajo contrato siguen coincidiendo
  (`ml/contracts/models/<name>.json`, ver `docs/auditoria/12_fase0_analisis_capa_contratos_ml.md`
  y `docs/auditoria/13_impacto_dim_estado_documento.md`).
- **Ignorar el estado `draft` vs `active` de un contrato**: no "arregles" un contrato que bloquea
  cambiándolo a `draft` para silenciar un error real — investiga primero si la predicción está
  realmente fuera de rango (bug de escala/transform) antes de bajar la barrera.

## Validar un cambio en esta capa

1. `cd backend && python -m pytest tests/unit/test_inference.py tests/unit/test_contract_validation.py -v`
   — cubren `inference.py` con un `ModelLoader` fake (no requieren los `.pkl` reales).
2. `cd backend && python -m pytest tests/integration/test_analytics_ml_endpoints.py -v` — golpea
   los endpoints reales; requiere que `ML_MODELS_DIR`/`ML_CONTRACTS_DIR` apunten a artefactos
   válidos (local: `ml/models`, `ml/contracts/models`, ver `backend/tests/conftest.py` /
   `backend/tests/integration/conftest.py` para cómo se configura el entorno de test).
3. Si tocaste `model_loader.py` o `main.py`: levanta el backend (`docker compose up backend` o
   `uvicorn app.main:app --reload` con las env vars de `.env`) y verifica
   `GET /health` → `modelos_ml_listos: true`, y revisa el log de arranque por
   `WARNING`/`ERROR` de carga de modelos (`Modelo '<x>' no encontrado` no debería aparecer para
   los 7 modelos si el volumen está bien montado).
4. Si tocaste un contrato JSON: confirma que `status` sigue siendo el que el equipo de `ml/`
   espera y que `required_features`/`plausible_range` siguen alineados al modelo real — un
   contrato desalineado con `status: "active"` puede bloquear inferencia en producción.
5. Documenta cualquier hallazgo de desalineación de contrato o de features en
   `docs/auditoria/` (numeración siguiente disponible) siguiendo el flujo de trabajo del
   `CLAUDE.md` raíz — no lo dejes solo como un comentario de código.
