# Plan de implementación — Mejora del pipeline de ML: campeón único por proceso, reentrenamiento automático y buenas prácticas de entrenamiento

> **Estado:** propuesta (pendiente de aprobación e implementación).
> **Fecha:** 2026-07-20.
> **Alcance:** capa de entrenamiento (`ml/`) + capa de serving (`backend/app/ml/`, `backend/app/services/`) + MLOps (`backend/app/services/training_service.py`, `admin_ml.py`) + documentación de modelos.
> **Skills aplicadas:** `ml-training-pipeline` (entrenamiento), `backend-ml-serving` (inferencia), `etl-edw-auditor` (calidad de datos del EDW).
> **NO toca:** SAP Producción (solo lectura), el esquema `edw.*`/`ml.*` (territorio del ETL) salvo `SELECT` de validación.

---

## 0. Motivación y diagnóstico (línea base real, 2026-07-20)

El usuario reporta tres problemas concretos:

1. **La predicción de reposición de artículos (Bodega, `demand_rf`) no funciona bien.**
2. **No hay reentrenamiento automático** — hoy es un disparo manual (`POST /admin/modelos/retrain`) que requiere `ML_SOURCE_DIR` montado (solo dev), sin scheduling.
3. **No hay un criterio de "un solo modelo campeón" por proceso** — conviven artefactos legacy (`demand_rf_model.pkl`, `demand_best_model.pkl`, `sales_best_model.pkl`, `sales_rf_model.pkl`, `churn_best_classifier.pkl`, `churn_classifier.pkl`, `isolation_forest_model.pkl`, `kmeans_rfm_model.pkl`, `association_rules.pkl`) junto a los nombres bajo contrato (`demand.pkl`, `sales.pkl`, …), sin que nada indique cuál es el vigente.

### 0.1 Línea base de métricas (leída de `ml/models/*.meta.json`)

| Proceso | Clave | Archivo campeón | Algoritmo | Métricas actuales | Ventana | Nº features | Problema detectado |
|---|---|---|---|---|---|---|---|
| Ventas (Gerencia) | `sales_rf` | `sales.pkl` | RandomForestRegressor | **R²=0.297**, RMSE=6285, MAE=3789 | 2023-07→2026-07 (3 a) | 26 | R² bajo (quiebre estructural conocido, regla 11); no se probó búsqueda de hiperparámetros a fondo |
| **Demanda (Bodega)** | `demand_rf` | `demand.pkl` | CatBoostRegressor | R²=0.876, **RMSE=191 vs MAE=6.2** | 2023-07→2026-07 (3 a) | 18 | **Modelo global multi-SKU: la brecha RMSE≫MAE revela error enorme en SKUs de alto volumen; no distingue producto (H-08b abierto); `hyperparameter_search=False`; no aplica mejoras de calendario de ventas (deliberado)** |
| Churn (Ventas) | `churn_rf` | `churn.pkl` | CatBoostClassifier | accuracy=0.784, roc_auc=0.758 | 2025-01→2026-04 | **3** | Solo 3 features; **no se guarda matriz de confusión, precision, recall ni F1**; sin umbral calibrado |
| Segmentación RFM (Ventas) | `segmentation` | `segmentation.pkl` | Pipeline(StandardScaler+KMeans) | silhouette=0.608 | — | 3 | No aplica train/test (no supervisado); falta documentar estabilidad de K y perfil de clústeres |
| Recomendación (Ventas) | `association` | `recommendation.pkl` | Item-item coseno | precision@5=0.077, recall@5=0.262, hit_rate@5=0.358, cobertura=0.979 | 2 años | 6 | El más sano; solo falta formalizar el gating y la doc |
| Anomalías (Admin) | `anomaly` | `anomalies.pkl` | IsolationForest | pct_flagged=1.0% | 16.431 filas | 4 | No supervisado; sin etiquetas de validación; contamination fija |

### 0.2 Hallazgos de metodología / MLOps (a resolver en este plan)

- **D-1 (crítico, demanda):** `train_demand_forecasting` entrena una **serie global apilada de todos los SKU** y `select_features_and_target` descarta la columna `producto` (`preprocessing.py`), así que el modelo solo distingue artículos por sus propios lags/rolling. Para reposición por artículo esto es insuficiente (documentado como H-08b abierto en `demand.json`). La brecha RMSE=191 vs MAE=6.2 lo confirma cuantitativamente.
- **D-2 (demanda):** `hyperparameter_search=False` para demanda (`ml/main.py`) — se entrena sin optimización de hiperparámetros, a diferencia de lo que sugiere el motor `find_best_regression_model`.
- **D-3 (todos):** **no hay gating de campeón**: cada reentrenamiento **sobrescribe** el `.pkl` aunque el modelo nuevo sea peor (el R² de demanda ya se degradó de 0.899 a 0.876 en un reentrenamiento sin que nada lo bloqueara).
- **D-4 (todos):** **no hay versionado ni rollback**: `save_artifact` pisa el `.pkl`/`.meta.json` vigente; no queda copia del anterior.
- **D-5 (todos):** **no hay scheduling**: el reentrenamiento es 100% manual y solo funciona en dev.
- **D-6 (limpieza):** artefactos legacy huérfanos en `ml/models/` sin consumidor — ambigüedad sobre "cuál es el campeón".
- **D-7 (churn):** métricas de clasificación incompletas — falta matriz de confusión, precision/recall/F1 y calibración de umbral (petición explícita del usuario).
- **D-8 (documentación):** no existe una ficha por modelo ("model card") que documente variables, parámetros, split 80/20, limpieza de datos, métricas y diagnósticos estadísticos.

---

## 1. Objetivos del plan

1. **Un campeón único, inequívoco, por proceso** — un registro de modelos (`model registry`) que declare qué artefacto está en producción para cada uno de los 6 procesos, y limpieza de los legacy.
2. **Reentrenamiento automático con gating** — el pipeline reentrena, compara el candidato contra el campeón vigente con métricas fijas, y **solo promueve si mejora** (o al menos no degrada más de un margen configurable); versionado + rollback.
3. **Arreglar la reposición de Bodega** — pasar de un modelo global a una estrategia que prediga bien por artículo (o por artículo×almacén), con features estáticas de producto y búsqueda de hiperparámetros.
4. **Revisar y mejorar los 6 modelos** con buenas prácticas: limpieza de datos, split 80/20 cronológico, CV temporal, matriz de confusión y métricas completas donde aplique, diagnósticos estadísticos con `statsmodels`.
5. **Documentar cada modelo en una ficha `.md`** (model card) con todo lo exigido: variables, parámetros, split, matriz de confusión, métricas, limpieza y baseline estadístico.

---

## 2. Fase 0 — Auditoría previa (obligatoria antes de tocar código)

Siguiendo el flujo del `CLAUDE.md` raíz (auditoría **antes** de modificar código):

- **Crear `docs/auditoria/38_mejora_pipeline_ml.md`** con:
  - Línea base congelada de las métricas actuales de los 6 modelos (tabla §0.1) — es el "antes" contra el que se medirá cada mejora.
  - Backtest reproducible del modelo de demanda **por SKU** (no global): calcular MAE/RMSE segmentando por producto y por decil de volumen, para cuantificar el problema real de reposición y tener contra qué comparar.
  - Verificación `SELECT` contra el EDW de que `dataset_repo.get_product_sales_history` (serving) aplica **los mismos filtros** que `fetch_sales_by_dimension` (entrenamiento): `estado_documento_sk <> -1`, `producto_sk <> -1`. Si difieren, es un sesgo entrenamiento↔serving a documentar y corregir.
  - Conteo de filas del EDW por SKU/mes para decidir la granularidad viable de reposición (§4.1).

**Criterio de salida:** el reporte 38 existe, con la línea base y el backtest por-SKU de demanda, antes de la Fase 1.

---

## 3. Fase 1 — Registro de modelos y campeón único (D-3, D-4, D-6)

### 3.1 Registro declarativo (`ml/models/registry.json`)

Fuente única de verdad de qué artefacto es el campeón por proceso. Ejemplo:

```json
{
  "sales_rf":     { "champion": "sales.pkl",         "version": "2026-07-11T00:28",  "metric_gate": {"name": "R2",       "direction": "maximize", "min_delta": -0.01} },
  "demand_rf":    { "champion": "demand.pkl",        "version": "2026-07-10T21:11",  "metric_gate": {"name": "MAE",      "direction": "minimize", "min_delta":  0.0 } },
  "churn_rf":     { "champion": "churn.pkl",         "version": "2026-07-10T21:12",  "metric_gate": {"name": "roc_auc",  "direction": "maximize", "min_delta": -0.01} },
  "segmentation": { "champion": "segmentation.pkl",  "version": "2026-07-10T21:11",  "metric_gate": {"name": "silhouette","direction": "maximize","min_delta": -0.02} },
  "association":  { "champion": "recommendation.pkl","version": "2026-07-13T19:53",  "metric_gate": {"name": "precision_at_5","direction":"maximize","min_delta": -0.005} },
  "anomaly":      { "champion": "anomalies.pkl",     "version": "2026-07-10T21:12",  "metric_gate": {"name": "pct_flagged","direction": "target", "target": 0.01, "tolerance": 0.005} }
}
```

- El backend (`model_loader.py`) lee `registry.json` para resolver el campeón, en vez de nombres fijos en `_MODEL_FILES`. Fallback al nombre actual si el registro no existe (compatibilidad).
- El `metric_gate` es lo que la promoción automática usa (§5).

### 3.2 Versionado + rollback

- `save_artifact` deja de sobrescribir: escribe a `ml/models/versions/<clave>/<timestamp>.pkl` + `.meta.json`, y **la promoción** (no el entrenamiento) actualiza el puntero `champion` en `registry.json` (copiando/enlazando al nombre estable `demand.pkl` que el volumen Docker ya expone).
- **Rollback** = cambiar el puntero `champion` a una versión anterior (comando CLI `python -m ml.promote --model demand_rf --to <timestamp>` y endpoint admin `POST /admin/modelos/rollback`). No requiere reentrenar.
- Retención: conservar las últimas N versiones (`ML_RETENCION_VERSIONES`, default 5); `ml/models/versions/` va a `.gitignore` (ya lo están los `.pkl`).

### 3.3 Limpieza de legacy (D-6)

- Mover `*_rf_model.pkl`, `*_best_model.pkl`, `association_rules.pkl`, `isolation_forest_model.pkl`, `kmeans_rfm_model.pkl` a `ml/models/versions/_legacy/` (no borrado destructivo de entrada; se retiran tras confirmar que ningún código los referencia — `predict_model.py` legacy).
- Test de guardia: `ml/tests/test_registry.py` falla si un `.pkl` en `ml/models/` (raíz) no está referenciado por `registry.json`.

---

## 4. Fase 2 — Arreglar la reposición de Bodega (D-1, D-2) — **prioridad alta**

### 4.1 Granularidad: **producto × almacén** (decisión confirmada, 2026-07-20)

El modelo global no sirve para reposición por artículo. **Decisión del negocio: la reposición se decide por bodega**, por lo que el modelo predice la cantidad al grano **`(fecha, codart, almacen)`**. Implicaciones de diseño:

- **Dataset (`make_dataset.py`):** nuevo `fetch_demand_by_product_warehouse` que agrega `fact_ventas_detalle` (o `fact_movimientos_inventario` de salida, según qué mida mejor la reposición — a decidir en Fase 0 con `SELECT`) por `(df.fecha_completa, p.codart, a.almacen_sk)`. Cada hecho lleva sus filtros (estado `<> -1`, centinelas `-1` fuera; para kardex la dirección la da `tipdoc`, nunca el signo — regla 3). El grano común lo definen las dimensiones conformadas `dim_fecha` × `dim_producto` × `dim_almacen`.
- **Riesgo de series ralas (crítico en este grano):** partir por almacén multiplica las combinaciones y muchas `(codart, almacen)` tendrán demanda intermitente (muchos ceros). **Mitigaciones obligatorias:**
  - Umbral mínimo de historia por combinación (`ML_DEMANDA_MIN_MESES_VENTA`, similar a `BODEGA_MIN_MESES_VENTA`): las combinaciones bajo el umbral caen a un fallback (media móvil / demanda de la clase de producto), no al modelo.
  - Si tras Fase 0 la intermitencia es alta, **modelo de dos etapas** (clasificador "¿habrá salida en el periodo?" + regresor de cantidad condicionada) — es el patrón estándar para demanda intermitente de inventario. Se decide con evidencia del backtest, no a priori.
- **Features que hacen distinguir la combinación:**
  - `producto_sk`/`codart` y `almacen_sk` vía **target encoding out-of-fold** (media de demanda histórica de esa combinación calculada solo con datos `< T`, sin fuga — patrón de cortes temporales H-05).
  - Atributos estáticos de `dim_producto` (`clase`, `subclase`, `linea`, precio/costo unitario, rotación histórica) y de `dim_almacen`/`dim_sucursal`.
  - Lags y rolling **por combinación** (`groupby(['producto','almacen'])` en el transformer — hoy se descarta la columna `producto`; hay que **conservar ambas como claves de agrupación**, no como features crudas).
  - `hyperparameter_search=True` para demanda (revertir D-2), con `TimeSeriesSplit`.
- **Un solo artefacto sigue vigente:** aunque el grano sea ×almacén, es **un único modelo** (`demand.pkl`) que recibe `almacen_sk` como feature — se mantiene "un modelo por proceso". No se entrena un modelo por bodega.

### 4.2 Métrica correcta para reposición

- Reportar **MAE y RMSE por combinación `(codart, almacen)` y por decil de volumen** (no solo el R² global que infla el resultado).
- Añadir métrica de negocio: **error de cobertura** (¿la cantidad sugerida evita quiebre sin sobre-stock?) y **WAPE/MASE** (robustas ante combinaciones de distinta escala, estándar en forecasting de demanda intermitente).
- Endurecer `plausible_range` del contrato `demand.json` (hoy `[0, 100000]`, demasiado laxo) al percentil real observado por combinación.

### 4.3 Sincronía con el serving (crítico)

Cualquier feature nueva de demanda debe replicarse en `backend/app/ml/preprocessing.py` y en el repository que trae los datos crudos (`get_product_sales_history`) — si no, `ModelContractError` o predicción con features mal construidas (skill `backend-ml-serving`). El contrato `demand.json` se actualiza **antes** de entrenar (regla D-2 contrato-primero) y el `known_serving_mismatch` H-08b se cierra o se re-documenta.

---

## 5. Fase 3 — Reentrenamiento automático con gating (D-3, D-4, D-5)

### 5.1 Promoción con gating (el corazón del "campeón único automático")

Nuevo módulo `ml/src/training/promotion.py`:

1. Entrena el candidato → lo guarda en `versions/<clave>/<ts>`.
2. Lee el campeón vigente del `registry.json` y su métrica.
3. Evalúa **candidato y campeón sobre el mismo hold-out** (el 20% más reciente, split cronológico).
4. Aplica el `metric_gate`: promueve solo si el candidato mejora (o no degrada más de `min_delta`). Si no, **descarta el candidato y conserva el campeón** (esto es lo que hoy no existe y causó la degradación de demanda).
5. Registra el resultado (promovido/rechazado + métricas ambas) en `ml/REPORTE_MEJORA_MODELOS.md` y en una tabla `public.ml_model_runs` (auditoría de MLOps).

### 5.2 Dos vías de disparo del reentrenamiento (decisión confirmada, 2026-07-20)

El reentrenamiento se dispara de **dos formas**, ambas contra el mismo flujo con gating (§5.1):

- **Vía A — Panel de administración (se implementa ahora):** botón en la UI del administrador. Es la vía operativa real hoy. Detallada en §5.2.1.
- **Vía B — Tarea programada (solo se documenta en un `.md`, no se implementa aún):** ejecución desatendida según la cadencia (§5.2.2). El servidor de producción es **Windows Server** y **todavía no hay acceso a él**, así que en esta iteración **solo se entrega la guía en Markdown** para configurar la tarea cuando el acceso esté disponible — no se crea la tarea ni scripts activos en producción.

#### 5.2.1 Vía A — Disparo desde el frontend del administrador

**Se lanza y se monitorea desde dentro de la app**, en el módulo Administrador. Diseño:

- **UI (frontend, rol administrador):** una pantalla "MLOps / Modelos" (extiende lo que hoy consume `/admin/modelos`) con:
  - Tabla de los 6 modelos: campeón vigente, versión, fecha de entrenamiento, métricas actuales y estado.
  - Botón **"Reentrenar"** por modelo y **"Reentrenar todos"** → `POST /admin/modelos/retrain` (ya existe; se extiende con el flujo de gating de §5.1).
  - Botón **"Promover" / "Rollback"** a una versión concreta del registro (§3.2).
  - Estado en vivo del job (encolado/corriendo/promovido/rechazado) leyendo `public.ml_model_runs`.
  - **Recordatorio de cadencia dentro de la app** (no ejecución automática): una notificación (módulo de Notificaciones, regla 20) que avisa al administrador cuando toca reentrenar según la cadencia elegida — **mensual** para ventas y demanda (tras la carga ETL del mes), **trimestral** para churn, segmentación, recomendación y anomalías. El administrador decide y pulsa el botón; por esta vía la app no reentrena sola. Esto da la disciplina de cadencia sin depender aún del servidor de producción.

- **Restricción de producción a resolver (bloqueante — hoy el reentrenamiento NO funciona fuera de dev):** `TrainingService` ejecuta los scripts de `ml/src/` como subprocess y **requiere `ML_SOURCE_DIR`, que solo monta `docker-compose.override.yml` (dev)**; en producción-like falla a propósito. Para que el botón funcione en el despliegue real hay que elegir **una** de estas vías (decisión de infraestructura, recomendada la primera):
  1. **(Recomendada) Contenedor de entrenamiento bajo demanda:** el backend, al recibir `POST /retrain`, lanza el servicio `ml` del compose (`docker compose run --rm ml python -m ml.retrain_all --model <clave>`) en vez de un subprocess local. El código de `ml/` vive en su propia imagen (como ya es hoy para el perfil `ml`); el backend solo orquesta. Requiere que el backend pueda hablar con el daemon de Docker (socket montado) — patrón ya usado por `publish_models.py`.
  2. **Montar `ml/` también en el backend de producción** (revertir la separación deliberada) — **no recomendado**: rompe la frontera backend↔entrenamiento que la arquitectura protege a propósito (el backend de producción no debe tener el código de entrenamiento).
  - Se elige la opción 1: mantiene la frontera, y el "dentro de la app" se cumple porque el disparo, el monitoreo y la promoción ocurren en la UI del administrador; solo la **ejecución** corre en el contenedor `ml` efímero.

- El endpoint `POST /admin/modelos/retrain` se conserva y ahora invoca el flujo con gating (§5.1); se añaden `POST /admin/modelos/promote` y `POST /admin/modelos/rollback`, y `GET /admin/modelos/runs` (historial paginado desde `public.ml_model_runs`).
- **Nota:** hay skills de Astronomer/Airflow en el entorno, pero un orquestador externo es sobredimensionado para 6 modelos; se descarta.

#### 5.2.2 Vía B — Tarea programada en Windows Server (solo documentación en esta iteración)

El servidor de producción es **Windows Server** y **aún no hay acceso**, así que esta vía **NO se implementa ahora**: el único entregable es una guía en Markdown, `docs/mlops/reentrenamiento_tarea_programada_windows.md`, que quedará lista para aplicarse cuando se tenga acceso. La guía documentará:

- **Mecanismo:** Programador de tareas de Windows (`Task Scheduler` / `schtasks.exe`) — no cron (no aplica en Windows). La tarea ejecutará un script (`ml/scripts/retrain_scheduled.ps1` / `.bat`, entregado como plantilla junto a la guía, pero **inerte** hasta que se registre la tarea) que corre el **mismo flujo con gating** que la Vía A: `docker compose run --rm ml python -m ml.retrain_all` (o el comando equivalente que se defina al tener el servidor).
- **Cadencia sugerida (§10 decisión 2):** una tarea mensual (ventas + demanda, después de la ventana de carga del ETL) y una trimestral (churn, segmentación, recomendación, anomalías). Se documentan los comandos `schtasks /Create ...` exactos, con horario, usuario de servicio y política de reintento.
- **Traza:** la tarea programada, además de dejar el resultado en `public.ml_model_runs` (igual que la Vía A), **escribe un resumen en un `.md`** (por ejemplo `docs/mlops/historial_reentrenamiento.md` o un log en la ruta que defina el servidor): fecha, modelos reentrenados, candidato promovido/rechazado y métricas antes/después. Esto cubre el requisito de "solo debe escribir en un `.md`" mientras no haya acceso al servidor: hoy el entregable tangible es la documentación + la plantilla del log, no una tarea corriendo.
- **Requisitos de entorno a validar al obtener acceso:** Docker (o el runtime que use el servidor), el socket/daemon disponible para el usuario de la tarea, las rutas de volúmenes de `ml/models` y contratos, y las variables `PG_*`/`ML_*`. Se listan como checklist en la guía.
- **Prerrequisito compartido con la Vía A:** la habilitación de la ejecución de `ml/` en producción (contenedor `ml` bajo demanda, restricción descrita arriba) aplica igual a la tarea programada.

### 5.3 Rollback y observabilidad

- `POST /admin/modelos/rollback` (rol administrador) → cambia el puntero del `registry.json`.
- Panel/notificación (reutilizar el módulo de Notificaciones existente, regla 20): alerta al administrador cuando un reentrenamiento **rechaza** el candidato o cuando una métrica cae bajo umbral (deriva de modelo).

---

## 6. Fase 4 — Revisión y mejora de los 6 modelos (buenas prácticas)

Checklist transversal aplicado a cada modelo (documentado en su model card, §7):

- **Limpieza de datos:** filtros de negocio obligatorios (estado de documento `<> -1`, centinelas `-1` fuera, llaves de negocio no nombres, NULL de negocio no imputados con 0 sin justificar — H-19). Detección y tratamiento de outliers documentado (IQR, como ya hace `IQRGoalCalculationEngine`).
- **Split 80/20 cronológico** (nunca aleatorio en series de tiempo) + **CV temporal** (`TimeSeriesSplit`) para regresión; `StratifiedKFold` para churn.
- **Búsqueda de hiperparámetros** activada donde hoy está apagada (demanda).
- **Baseline estadístico con `statsmodels`** (`import statsmodels.formula.api as smf`): para ventas y demanda, ajustar un OLS/GLM de referencia y reportar el `summary()` (coeficientes, p-values, R² ajustado, F-test) — sirve como (a) baseline honesto contra el modelo ML y (b) diagnóstico de significancia y multicolinealidad (VIF) de las features. Un modelo ML que no supere claramente al OLS es una señal de alerta.
- **Métricas completas por tipo:**
  - Regresión (ventas, demanda): MAE, RMSE, R², WAPE/MASE, y para demanda desglose por SKU/decil.
  - Clasificación (churn): **matriz de confusión**, accuracy, precision, recall, F1, ROC-AUC, PR-AUC, y **calibración de umbral** (hoy solo accuracy+roc_auc; añadir el resto — petición explícita del usuario).
  - Clustering (segmentación): silhouette, Davies-Bouldin, estabilidad de K (método del codo ya documentado), perfil de negocio de cada clúster.
  - No supervisado (anomalías): % marcado, distribución del score, y validación contra un conjunto de casos etiquetados manualmente si se consigue.

Mejoras específicas ya identificadas por modelo:

| Modelo | Acción de mejora |
|---|---|
| Demanda | §4 completo (granularidad + features de producto + hiperparámetros). |
| Ventas | Revisar el quiebre estructural (regla 11) con evidencia fresca; probar features exógenas rezagadas nuevas; activar búsqueda de hiperparámetros; comparar contra OLS `smf`. R²=0.30 es mejorable. |
| Churn | Ampliar de 3 a un set de features RFM+comportamiento; matriz de confusión + calibración de umbral; revisar horizonte de la etiqueta (cortes temporales, sin circularidad H-05). |
| Segmentación | Documentar estabilidad de K y perfiles; no requiere cambio de algoritmo. |
| Recomendación | El más sano; formalizar solo el gating (precision@5) y la model card. |
| Anomalías | Fijar `contamination` con criterio; construir un mini-set etiquetado para validar precisión, no solo % marcado. |

---

## 7. Fase 5 — Documentación: ficha de modelo (`.md`) por proceso (D-8)

Crear `ml/model_cards/<clave>.md` (una por modelo) **y** un índice `ml/model_cards/README.md`. Cada ficha, generada semi-automáticamente desde el `.meta.json` + contrato, contiene exactamente lo que pidió el usuario:

1. **Proceso y consumidor** (rol/dashboard) y clave interna.
2. **Variables de entrenamiento (features):** lista completa con dtype, origen (tabla/columna del EDW), transformación (lag/rolling/encoding) y si es `required`.
3. **Variable objetivo (target)** y su transformación (p. ej. `log1p`/`expm1` interno).
4. **Limpieza de datos aplicada:** filtros de negocio, exclusión de centinelas, tratamiento de outliers y de NULLs.
5. **Split:** 80/20 cronológico (con fechas de corte reales) + esquema de CV.
6. **Algoritmo y parámetros:** familia, hiperparámetros del modelo ganador, librería y versión.
7. **Baseline estadístico (`statsmodels`):** `smf.ols(...).fit().summary()` — coeficientes, p-values, R² ajustado, VIF.
8. **Métricas de medición:** tabla completa según tipo (§6), con la línea base y la última corrida.
9. **Matriz de confusión** (churn; y para cualquier clasificador futuro) — imagen/tabla.
10. **Rango plausible del output** (del contrato) y desalineaciones conocidas con el serving.
11. **Fecha de entrenamiento, ventana de datos, nº de filas.**

Script generador: `ml/src/utils/generate_model_card.py` (lee `registry.json` + `.meta.json` + contrato + un artefacto opcional de diagnóstico `statsmodels`/matriz de confusión guardado por el `train_*`).

---

## 8. Orden de ejecución y entregables

| Fase | Entregable | Depende de |
|---|---|---|
| 0 | `docs/auditoria/38_mejora_pipeline_ml.md` (línea base + backtest demanda por SKU) | — |
| 1 | `ml/models/registry.json`, versionado en `save_artifact`, `model_loader.py` lee registro, limpieza legacy, `test_registry.py` | 0 |
| 2 | Demanda re-diseñada (dataset+features+contrato+serving en sync), backtest que supere la línea base por-SKU | 0, 1 |
| 3 | `promotion.py` (gating), `retrain_all`, `public.ml_model_runs` (migración Alembic), endpoints `retrain`/`promote`/`rollback`/`runs`, ejecución vía contenedor `ml` bajo demanda (opción 1 §5.2) | 1 |
| 3b | **Frontend admin (MLOps) — Vía A:** pantalla de modelos con reentrenar/promover/rollback, estado en vivo del job, y recordatorio de cadencia vía Notificaciones | 3 |
| 3c | **Vía B (solo documentación):** `docs/mlops/reentrenamiento_tarea_programada_windows.md` (guía Task Scheduler) + plantilla inerte `retrain_scheduled.ps1` + plantilla de log `.md`. No se registra ninguna tarea (sin acceso al Windows Server) | 3 |
| 4 | Los 6 modelos revisados con el checklist, métricas completas (matriz de confusión en churn), baseline `statsmodels` | 1, 2 |
| 5 | `ml/model_cards/*.md` + generador + índice | 4 |

**Rollback global del plan:** todo es aditivo. Si el gating o el registro dan problemas, el backend cae al comportamiento actual (nombres fijos en `_MODEL_FILES`) y el reentrenamiento vuelve a ser manual — no se rompe ninguna instalación existente.

---

## 9. Validación (criterios de aceptación)

- **Demanda:** MAE/WAPE **por SKU** (deciles medio y alto de volumen) mejora medible vs. la línea base del reporte 38 — no basta el R² global.
- **Gating:** un reentrenamiento con un candidato deliberadamente peor **NO** promueve (test de integración que lo demuestre).
- **Campeón único:** `registry.json` resuelve un único `.pkl` por proceso; `ml/models/` (raíz) no tiene artefactos huérfanos (`test_registry.py` verde).
- **Reentrenamiento automático:** el perfil `ml-cron` ejecuta el flujo completo con gating y deja traza en `public.ml_model_runs`.
- **Contratos:** `python -m src.contracts.contract_validator` limpio para los `active`; `pytest` verde en `ml/` y en `backend/tests/{unit,integration}` de ML.
- **Documentación:** una model card `.md` por proceso con las 11 secciones, incluida la matriz de confusión de churn y el `summary()` de `statsmodels`.
- **Salud del serving:** `GET /health` → `modelos_ml_listos: true` sin WARNING de carga tras publicar.

---

## 10. Decisiones tomadas (confirmadas 2026-07-20)

1. **Granularidad de reposición (§4.1): `producto × almacén`.** El negocio repone por bodega. Grano `(fecha, codart, almacen)`, un único artefacto con `almacen_sk` como feature. Riesgo asumido: series ralas → umbral mínimo de historia + posible modelo de dos etapas (se decide con el backtest de Fase 0).
2. **Cadencia (§5.2): mensual + trimestral.** Ventas y demanda cada mes (tras la carga ETL); churn, segmentación, recomendación y anomalías cada trimestre. Se materializa como **recordatorio in-app**, no como ejecución automática.
3. **Orquestación (§5.2): dos vías.** (A) **Panel de administración**, se implementa ahora: disparo, monitoreo, promoción y rollback desde la UI del admin; la ejecución corre en el contenedor `ml` efímero para preservar la frontera backend↔entrenamiento. (B) **Tarea programada en Windows Server**, solo se documenta en un `.md` (Task Scheduler) más plantillas inertes de script y de log — no se registra ninguna tarea porque aún no hay acceso al servidor; escribirá su resultado en un `.md` y en `public.ml_model_runs` cuando se active. **Pendiente de infraestructura (ambas vías):** habilitar la ejecución de `ml/` en el despliegue real (contenedor `ml` bajo demanda / socket Docker); hoy solo funciona en dev.
4. **`statsmodels`: sí, baseline + diagnóstico.** Se añade a `ml/requirements.txt` como dependencia de **entrenamiento** (OLS/GLM de referencia + p-values/R² ajustado/VIF en ventas y demanda). **No** entra al backend ni se sirve como modelo.

## 11. Riesgo abierto restante

- **Habilitación del reentrenamiento en producción (decisión 3):** requiere exponer el socket de Docker al backend o un servicio equivalente. Es la única pieza que no es puramente de código de la app; debe validarse en el entorno de despliegue real antes de prometer el botón "Reentrenar" en producción. En dev funciona con `docker-compose.override.yml`.
