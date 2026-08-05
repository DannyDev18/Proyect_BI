# Auditoría 51 — Decomisión del modelo `anomaly` y `churn_rf` a un solo algoritmo

**Fecha:** 2026-08-04
**Alcance:** petición explícita del usuario, dos cambios independientes:
1. Retirar por completo el modelo `anomaly` (Isolation Forest, detección de fraude/anomalías transaccionales del panel de Administrador).
2. `churn_rf` debe entrenarse con **un solo algoritmo**, no una competencia entre 4 familias (RF/XGBoost/LightGBM/CatBoost).

Confirmado con el usuario antes de tocar código (`AskUserQuestion`): la decomisión de `anomaly` es completa —mismo criterio que `sales_rf`/`goals_rf` (auditorías 49/20)— sin reemplazo funcional; el cambio de `churn_rf` es "reducir la competencia de entrenamiento a un solo algoritmo".

## 1. Decomisión de `anomaly`

### 1.1 Modelos ML del proyecto: de 5 a 4

`demand_rf`, `churn_rf`, `segmentation`, `association`. Retirado `anomaly` (Isolation Forest).

### 1.2 Retirado de punta a punta

**Entrenamiento (`ml/`):**
- `ml/src/training/train_anomaly_detection.py` — borrado (contenía `estimar_contamination_iqr`, `train_isolation_forest`, `save_anomaly_model`).
- `ml/main.py` — función `train_anomaly_detection`, su import y su llamada en `run_ml_pipeline()` removidas.
- `ml/retrain_all.py` — entrada `"anomaly"` retirada de `ENTRENADORES`.
- `ml/src/data/make_dataset.py` — `fetch_transactions_for_anomalies` (dataset exclusivo) y la constante `MUESTRA_ANOMALIAS` removidas.
- `ml/contracts/models/anomalies.json` — contrato borrado.
- `ml/models/registry.json` — entrada `"anomaly"` retirada.
- `ml/models/anomalies.pkl`, `ml/models/anomalies.meta.json` y `ml/models/versions/anomaly/` — artefactos borrados.
- `ml/tests/test_model_contract.py` — mapeo legacy `"anomalies": "anomalies.pkl"` retirado.

**Serving backend:**
- `backend/app/ml/inference.py::detect_anomalies` — removida.
- `backend/app/ml/model_loader.py` — `_MODEL_FILES`/`MODEL_DISPLAY_NAMES` pierden la entrada `anomaly`.
- `backend/app/services/prediction_service.py::get_anomaly_status` — removido (5 casos de uso, no 6).
- `backend/app/repositories/prediction_repository.py` — `AnomalyFeatures`/`get_transaction_features` removidos.

**Subsistema de triage del panel de Administrador (Fase 2, `docs/features/plan_correcciones_pendientes.md` §3), retirado por completo, no solo ocultado:**
- `backend/app/api/routes/admin.py` — endpoints `GET /anomalies`, `GET /anomalies/revisiones`, `PATCH /anomalies/revisiones/{id}` removidos; el router queda con `/resumen`, `/system-health`, `/audit-logs`.
- `backend/app/models/anomalia_revision.py`, `backend/app/repositories/anomalia_revision_repository.py`, `backend/app/services/anomalia_revision_service.py` — archivos borrados.
- `backend/app/api/dependencies.py` — wiring de `AnomaliaRevisionRepository`/`AnomaliaRevisionService` retirado.
- `backend/app/schemas/analytics.py` — `AnomaliaResponse`/`AnomaliaRevisionResponse`/`AnomaliaRevisionUpdate` removidos.
- `backend/app/database/base.py` — import de `AnomaliaRevision` retirado (ya no debe registrarse en `Base.metadata`).
- **Migración `0018_quitar_anomalias`** — `DROP TABLE public.anomalias_revisiones` (creada en la baseline `0001`, único consumidor real ya eliminado). El `downgrade()` recrea la tabla con el DDL original, por si se necesita revertir.

**Integración ML de Metas y Comisiones (`GoalMLService`):** el único INSUMO real del modelo `anomaly` fuera del panel de Admin era `GoalMLService._detectar_meses_atipicos` (corría el modelo sobre transacciones del vendedor para pesar menos los meses con comportamiento atípico, `PESO_MES_ATIPICO_ML=0.5` en `goal_calculation_engine.py`). Removido:
- `_detectar_meses_atipicos` y las constantes `FACTOR_UMBRAL_ANOMALIA_MENSUAL`/`FRACCION_MINIMA_ANOMALIA` — borrados de `goal_ml_service.py`.
- La llamada en `suggest_goal` ya no pasa `meses_atipicos_ml`; el motor v2 recibe el default vacío.
- `GoalRepository.get_vendor_transactions_history` y el NamedTuple `VendorTransactionFeatures` (exclusivos de esta señal) — borrados de `goal_repository.py`.
- **Decisión de diseño:** `goal_calculation_engine.py` **conserva** el parámetro genérico `meses_atipicos_ml` y `PESO_MES_ATIPICO_ML` — es un mecanismo del motor v2 (pesar menos un mes marcado como atípico sin excluirlo), no exclusivo de este modelo. Queda documentado en el código que hoy no tiene ningún emisor real (inerte hasta que otra fuente de meses atípicos lo alimente); retirarlo del motor habría sido un cambio de contrato más amplio que decomisionar el modelo en sí, y el campo `meses_atipicos_ml_detectados` expuesto en la API simplemente queda siempre en `0`.

**`training_service.py`:** `"anomaly"` retirado de `CLAVES_VALIDAS` — el panel MLOps de administrador ya no lo ofrece para reentrenar/promover/rollback.

**Conteos de modelos documentados** actualizados de "6"/"5" a "4" en `system.py`, `system_service.py`, `admin_ml.py` (2 docstrings) y `dependencies.py`.

**Frontend:** `DashboardAdmin.tsx` pierde la tarjeta "Detector de Anomalías Transaccionales" y la sección "Triage de Anomalías" (sin reemplazo); `hooks/admin.ts` pierde `useAnomalyDetector`/`useAnomaliaRevisiones`/`useActualizarAnomaliaRevision`; `services/admin.ts` pierde `detectAnomaly`/`getAnomaliaRevisiones`/`actualizarAnomaliaRevision`; `types/admin.ts` pierde `AnomaliaResponse`/`AnomaliaEstado`/`AnomaliaRevision`. Bundle de producción bajó de 1.232 kB a 1.224 kB tras retirar el código muerto.

**Tests:** `backend/tests/integration/test_anomalia_revision_repository.py` borrado; `test_admin_actualizacion.py` pierde 5 tests de triage; `test_analytics_ml_endpoints.py` pierde 2 tests del endpoint `/anomalies`; `test_goal_ml_integration.py` actualizado (4 modelos, `anomaly` confirmado como no cargable, mismo patrón que `goals_rf`/`sales_rf`); `test_goal_ml_service.py` pierde los 2 tests de `_detectar_meses_atipicos` (método borrado) y actualiza el test de "sin señal ML"; `test_inference.py` pierde `test_detect_anomalies_...`; `test_system_service.py` usa `churn_rf` en vez de `anomaly` como ejemplo de modelo no cargado (evita un `KeyError` contra `MODEL_DISPLAY_NAMES`, que ya no tiene esa clave); `conftest.py` pierde `_DummyAnomalyDetector` y la entrada `anomaly` de `fake_model_loader`.

### 1.3 No tocado deliberadamente

- `ml/notebooks/05-anomaly-detection.ipynb` — artefacto exploratorio histórico, mismo criterio que los notebooks de `sales_rf` conservados en la auditoría 49.
- `ml/src/prediction/predict_model.py` — módulo legacy ya reemplazado por `ModelLoader`/`inference.py` (ver docstring de `model_loader.py`), sin consumidores reales; fuera de alcance de esta decomisión.
- `ml/src/contracts/model_contract.py::VALID_TASKS` conserva `"anomaly_detection"` como tipo de tarea genérico del catálogo de contratos (no ata a ningún modelo concreto).

## 2. `churn_rf`: de competencia multi-algoritmo a un solo algoritmo fijo

### 2.1 Situación previa

`train_churn_model` (`ml/src/training/train_churn_prediction.py`) llamaba a `find_best_classification_model` (`ml/src/training/model_selector.py`), que entrena y compara 4 familias (RandomForest/XGBoost/LightGBM/CatBoost) vía `RandomizedSearchCV` + `StratifiedKFold`, publicando el ganador por ROC-AUC. Según `ml/models/churn.meta.json` y `ml/REPORTE_MEJORA_MODELOS.md`, el campeón real y consistente ya era **CatBoostClassifier**.

`find_best_classification_model` es **compartida** con `ml/src/training/train_cross_sell_ranker.py` (7º modelo del proyecto, contrato en `status: draft`, nunca promovido — ver auditoría 40).

### 2.2 Decisión de diseño

En vez de modificar `find_best_classification_model` (rompería/afectaría también al ranker de venta cruzada, que sí sigue en competencia real por no tener campeón fijo), se escribió un entrenamiento dedicado para churn directamente en `train_churn_prediction.py::train_churn_model`: un solo `RandomizedSearchCV` sobre `CatBoostClassifier` (mismo espacio de hiperparámetros que tenía dentro de la competencia — `iterations`/`learning_rate`/`depth` — mismo `cv=StratifiedKFold(3)`, `scoring='roc_auc'`, `n_jobs=1` por el mismo motivo de paralelismo anidado documentado en `model_selector.py`).

`model_selector.py::find_best_classification_model` queda **intacta**, sigue sirviendo a `train_cross_sell_ranker.py`.

### 2.3 Validado

- `python -m ast` (syntax check) de todos los archivos tocados: sin errores.
- `pytest backend/tests/unit`: **363 passed**, sin regresiones.
- `tsc --noEmit` / `oxlint` / `npm run build` del frontend: limpios (bundle reducido).
- No se corrió un reentrenamiento real de `churn_rf` en esta sesión (requiere conectividad al EDW/contenedor `ml`, no disponible en este entorno de edición) — el cambio queda validado por lectura de código y por la suite de tests unitarios existente; el próximo reentrenamiento real (`docker run ... python retrain_all.py --model churn_rf`) ejercitará el nuevo camino de entrenamiento por primera vez.

## 3. Migración pendiente de aplicar

`0018_quitar_anomalias` (`DROP TABLE public.anomalias_revisiones`) fue creada pero **no aplicada** contra `bi_postgres_edw` real en esta sesión (no se reconstruyó `bi_backend`, que es lo que la dispara automáticamente vía `entrypoint.sh`/`apply_migrations.py`). Queda para la próxima reconstrucción del contenedor backend.

## Reglas de negocio afectadas

Ninguna regla nueva — esta sesión es una decomisión (retiro de funcionalidad), no una adición de reglas. Se actualiza la sección "Modelos ML" del `CLAUDE.md` (5→4 modelos) y la lista de endpoints de `/analytics/admin`.
