# 11 — Auditoría Técnica de los Modelos de Machine Learning (`ml/`)

- **Fecha:** 2026-07-09
- **Alcance:** módulo `ml/` completo (extracción `src/data/`, features `src/features/`, entrenamiento `src/training/`, exportación `src/utils/`, predicción `src/prediction/`) y su **contrato de serving** con el backend (`backend/app/ml/`, `backend/app/services/prediction_service.py`, `backend/app/repositories/prediction_repository.py`).
- **Método:** revisión estática de código (sin ejecución), contraste entrenamiento ↔ inferencia columna por columna, contraste con el EDW documentado (`docs/arquitectura_dw.md`, auditoría 05) y con las reglas de negocio validadas (auditoría 02).
- **Objetivo:** decidir qué debe corregirse **antes** de regenerar los `.pkl` oficiales que consumirá el backend.
- **Restricción respetada:** solo lectura; no se modificó código.

---

## 1. Resumen ejecutivo

El pipeline de entrenamiento (`ml/main.py`) es razonable en su diseño (competencia multi-algoritmo, `TimeSeriesSplit`, ventana de 3 años justificada, semillas fijas, sidecar de metadatos). **El problema dominante no está en el entrenamiento sino en el contrato entrenamiento ↔ serving: 4 de los 7 modelos no pueden producir una predicción válida en el backend tal como están.**

| # | Modelo | Estado | Problema dominante |
|---|--------|--------|--------------------|
| 1 | Ventas (`sales_best_model.pkl`) | 🔴 Inválido en serving | Predice en escala `log1p` y el backend lo sirve como dólares sin `expm1` (H-01) |
| 2 | Demanda (`demand_best_model.pkl`) | 🔴 Inválido en serving | Mismo bug de escala log (H-01) + sin ventana de 3 años (H-08) |
| 3 | Segmentación RFM (`kmeans_rfm_model.pkl`) | 🔴 Roto en serving | El `.pkl` es un `dict {'model','scaler'}` y el backend llama `.predict()` sobre el dict (H-02) |
| 4 | Churn (`churn_best_classifier.pkl`) | 🔴 Roto en serving + metodología | Features de serving distintas a las de entrenamiento (H-03) y etiqueta circular (H-05) |
| 5 | Anomalías (`isolation_forest_model.pkl`) | 🔴 Roto en serving | Features de serving distintas a las de entrenamiento (H-04) |
| 6 | Venta cruzada (`association_rules.pkl`) | 🟡 Funciona con pérdidas | Reglas sin confianza/lift y filtro solo por `item_A` (H-10) |
| 7 | Metas (`goals_best_model.pkl`) | 🟡 Funciona con riesgos | `anio` como feature (no extrapola), evaluación silenciada (H-13) |

Todos los fallos de serving hoy quedan **enmascarados** por los `try/except` de degradación del `PredictionService` (el dashboard muestra 0.0 / "Error" en vez de un 500), por lo que el sistema *parece* funcionar.

---

## 2. Análisis por criterio (los 20 puntos solicitados)

### 2.1 Objetivo y variable objetivo por modelo

| Modelo | Objetivo | Target | Evaluación del target |
|---|---|---|---|
| Ventas | Serie diaria de venta neta total (Gerencia) | `y_sales_net` = `SUM(subtotal_neto)` por día, transformado `log1p` en entrenamiento | Correcto como definición; **la transformación log no viaja dentro del `.pkl`** (H-01) |
| Demanda | Unidades vendidas por producto/día (Bodega) | `y_quantity` (`log1p`) | Correcto; mismo problema de transformación externa |
| Segmentación | Clusters RFM K=4 | No supervisado | K fijo sin selección justificada (H-12) |
| Churn | Riesgo de fuga | `is_churn = recency > 90 días` | **Etiqueta circular** derivada del mismo snapshot que las features (H-05) |
| Venta cruzada | Pares comprados juntos | Co-ocurrencia por `num_factura` | Definición de transacción correcta (corregida en auditoría previa) |
| Anomalías | Outliers transaccionales | No supervisado, `contamination=0.01` | Supuesto del 1% no validado contra `fact_logs_auditoria` |
| Metas | Ratio de crecimiento mes siguiente | `y_ventas_futuras` = ratio `LEAST(b/a, 1.5)` | Cap 1.5 razonable y documentado; ratio bien construido sin fuga |

### 2.2 Variables predictoras y calidad de features

- **Ventas/Demanda** (`build_features.py`): lags (1,7,14,30,90), rolling 7/30d (mean/std/min/max), expanding mean, calendario (día de semana, mes, trimestre, inicio/fin de mes, feriado aproximado), exógenas rezagadas 1 día (`n_clientes_prev`, `n_facturas_prev`, `pct_descuento_prom_prev`). Set sólido para modelos de tabla. Deuda documentada: `es_feriado` hardcodeado porque `dim_fecha.es_feriado` nunca se puebla en el EDW (raíz del problema en el ETL, no en ML).
- **Demanda:** tras generar lags por producto, `select_features_and_target` **elimina la columna `producto`** — el modelo global no puede distinguir un tornillo de una llanta más allá de sus lags. Funciona como "modelo de perfil de serie", pero limita la precisión por SKU (H-08b).
- **Churn:** solo 3 features (`frequency`, `monetary_value`, `average_ticket = monetary/frequency` — colineal por construcción). Pobre, y además inválido por H-03/H-05.
- **Metas:** buen trabajo de features en SQL (estacionalidad interanual, tendencia sin pico, lag 12m, índice estacional relativo) con exclusión justificada de la feature colineal. Pero **`anio` y `mes` quedan como features numéricas**: los árboles no extrapolan a `anio` futuros nunca vistos (H-13).

### 2.3 Data leakage

| Caso | Veredicto |
|---|---|
| Exógenas contemporáneas (`n_clientes`, `n_facturas`, `pct_descuento`) | ✅ Correctamente rezagadas 1 día (fue corregido; comentario lo documenta) |
| Lags/rolling con `shift(1)` antes de rolling | ✅ Correcto |
| `fit_transform` del pipeline sobre TODO el dataset antes del split | ✅ Aceptable aquí: el transformer es stateless (solo shifts); no aprende nada del test |
| **`bfill()` en la imputación** (`build_features.py:83`) | 🔴 **Fuga real**: rellena los NaN iniciales de los lags con valores **futuros**. En demanda, además, el `bfill` global puede cruzar filas de **otro producto** (el DataFrame está ordenado por fecha, no por producto) (H-06) |
| **Etiqueta de churn** | 🔴 `is_churn` se deriva de `recency` del mismo snapshot con el que se calculan `frequency`/`monetary_value` (histórico completo, incluido el periodo "muerto"). No hay ventana de observación + horizonte de predicción: el modelo aprende a reproducir una regla determinista, no a anticipar abandono (H-05) |
| `estacionalidad_mes_objetivo` en metas | ✅ Solo usa años `< b.anio`; el comentario que lo justifica es correcto |
| Split temporal ventas/demanda/metas | ✅ Cronológico sin shuffle |

### 2.4 Preprocesamiento, nulos, escalado, codificación

- **Nulos:** `bfill().fillna(0)` en series (fuga, H-06); `fillna(0.0)` en anomalías — un `costo_total` NULL se convierte en costo 0 y produce un "margen" del 100% que el IsolationForest aprenderá como patrón, no como anomalía real (H-19); `fillna(0)` en metas. No hay `SimpleImputer` dentro de pipelines: la imputación vive fuera del artefacto serializado.
- **Escalado:** correcto no escalar para árboles/boosting. K-Means sí escala con `StandardScaler` ✅ — pero el scaler **no se aplica en el serving** (H-02). IsolationForest sin escalar: tolerable, con features de magnitudes muy dispares (`subtotal_neto` vs `cantidad`) los cortes se concentran en las columnas de mayor rango.
- **Codificación categórica:** no hay variables categóricas en ningún modelo final (se eliminan `producto`/`sucursal`). No hay `OneHotEncoder`/`OrdinalEncoder` en el repo. Coherente, aunque renuncia a señal (2.2).
- **Ningún modelo se serializa como `Pipeline` completo** (preprocesamiento + estimador): la receta de features vive duplicada en `backend/app/ml/preprocessing.py` (riesgo de desincronización reconocido en su docstring). Es la causa raíz de la familia de bugs H-01…H-04.

### 2.5 Balance del dataset

- **Churn:** único caso con clases. Bien manejado en lo mecánico: `stratify=y` en el split, `class_weight='balanced'` (RF/LGBM), `scale_pos_weight` (XGB), `auto_class_weights` (CatBoost), scoring `roc_auc`. Sin embargo el balance real depende del umbral de 90 días y nunca se loguea la proporción de clases; y `scale_pos_weight=counts[0]/counts[1]` lanzaría `KeyError` si alguna clase tuviera 0 casos (guard de ≥20 filas no lo garantiza).
- Resto: regresión / no supervisado — no aplica.

### 2.6 División Train/Test y Cross-Validation

- **Ventas/Demanda:** split cronológico 80/20 ✅ + `TimeSeriesSplit(3)` dentro de `RandomizedSearchCV` ✅. Buen patrón.
- **Demanda:** el `TimeSeriesSplit` opera sobre un **panel** producto-fecha ordenado por fecha; los folds cortan dentro del mismo día entre productos. Aceptable como aproximación, no es un CV por serie.
- **Metas:** panel vendedor-sucursal-mes ordenado por `(anio, mes)` con `shuffle=False` ✅; mismo matiz de panel en el CV.
- **Churn:** `train_test_split` aleatorio estratificado + `StratifiedKFold` — correcto para datos de corte transversal (aunque moot mientras la etiqueta sea circular).
- **Segmentación/Anomalías/Reglas:** sin holdout — normal en no supervisado, pero anomalías no valida contra ningún caso conocido de `fact_logs_auditoria`.

### 2.7 Overfitting / Underfitting

- Mitigación estructural correcta: CV temporal, competencia de 5 algoritmos, grids con regularización (`max_depth`, `min_samples_leaf`, `learning_rate`, `subsample`).
- Con `n_iter=5` sobre grids de 12–36 combinaciones, la búsqueda es superficial (asumido conscientemente por costo).
- **No se comparan métricas train vs test** en ningún modelo: no hay forma de diagnosticar overfitting desde los logs. El R² reportado de +0.21 en ventas (REPORTE_MEJORA_MODELOS) sugiere más bien **underfitting/techo de señal** — honesto para una serie diaria agregada, pero debería quedar registrado en el `.meta.json` (hoy `main.py` calcula métricas y **no las pasa** a `save_model`, así que el sidecar queda con `metrics: {}`).

### 2.8 Métricas

- Regresión: RMSE/MAE/R² con des-transformación `expm1` correcta en `evaluate_reg` ✅ (solo en evaluación offline; el serving no la hace — H-01).
- Selección por `neg_root_mean_squared_error` **en espacio log** — de facto optimiza error relativo; defendible pero no documentado.
- Clasificación: `roc_auc` + classification report ✅.
- Clustering: silhouette informativo ✅ (no decide K).
- **Dashboard:** `mae_modelo=165842.12`, `nivel_confianza=95.0` e intervalos ±15% **hardcodeados** en `prediction_service.py` — métricas fabricadas presentadas a Gerencia (H-09). Para una tesis esto es indefendible: deben venir del `.meta.json` real.

### 2.9 Hiperparámetros

- Grids razonables por algoritmo. Problemas puntuales: `use_label_encoder=False` en `XGBClassifier` (parámetro eliminado en xgboost ≥ 2.0, genera warning/ruido), `optuna` importado y declarado en requirements pero **nunca usado** (el README/plan lo promete), `n_iter=4–5` bajo, y `contamination=0.01` / `n_clusters=4` / umbral churn 90 días son supuestos de negocio sin validación documentada en auditoría 02.

### 2.10 Reproducibilidad

- ✅ `random_state=42` consistente en todos los estimadores, splits y búsquedas; muestras SQL deterministas (`ORDER BY venta_sk DESC LIMIT n`); umbrales por env var.
- 🟡 Faltan en el sidecar: versiones de librerías (crítico porque los `.pkl` acoplan versiones ml↔backend), hash/rango de datos de entrenamiento, y métricas reales (ver 2.7). `ml/requirements.txt` usa `>=` sin pin superior: dos instalaciones en fechas distintas pueden producir `.pkl` incompatibles con el backend.

### 2.11 Compatibilidad con el EDW actual

Premisa de la auditoría: **el EDW (`edw.*`) es la fuente oficial y única de entrenamiento** (regla del proyecto). Todo `SELECT` de `make_dataset.py` se contrastó contra el modelo dimensional (11 dims + 11 facts, SCD2, centinelas, `etl_control`) documentado en `docs/arquitectura_dw.md` y la auditoría 05.

- Consultas alineadas con el modelo dimensional (joins por `*_sk`, `dim_fecha`), exclusión del centinela `pct_margen=-9999` ✅, exclusión de devoluciones en market basket ✅. Ningún extractor ML lee del ERP directamente ✅.
- **Sin control de frescura del EDW:** ninguna función de `make_dataset.py` ni `ml/main.py` consulta `edw.etl_control` antes de entrenar. Si la última carga ETL falló o está desactualizada, los 7 modelos entrenan silenciosamente con datos viejos/parciales y publican `.pkl` "nuevos" sobre datos incompletos (H-22).
- El esquema `ml.*` del EDW (p.ej. `ml.v_ventas_cruzadas_desanonima`) existe justamente como capa de consumo para ML, pero el pipeline no lo usa: todo el SQL vive embebido en `make_dataset.py` contra `edw.*` crudo (H-22b, arquitectural).
- **Inconsistencia de filtros entre extractores:** `fetch_goals_data` filtra `estado_factura != 'I'`; `fetch_daily_sales`, `fetch_rfm_metrics` y `fetch_transactions_for_anomalies` **no filtran nada** ni excluyen `es_devolucion`. El backend (`dataset_repository`/`prediction_repository`) sí filtra `estado_factura != 'I'` — el modelo entrena con una población distinta a la que se le da en inferencia (H-15).
- `fetch_sales_by_dimension` agrupa por `nombre_articulo` sobre `dim_producto` SCD2 sin filtrar `es_vigente`: si un artículo cambió de nombre, su serie se parte en dos (menor).
- Registros centinela: las facts con `cliente_sk=-1` entran al RFM como un "cliente desconocido" gigante que distorsiona los centroides de K-Means (no se excluye `cliente_sk = -1`).

### 2.12 Compatibilidad con el backend (contrato de serving)

Es el bloque más grave; ver hallazgos H-01 a H-04, H-07, H-14, H-16. Resumen del contraste columna a columna:

| Modelo | Entrena con | Backend le envía | ¿Compatible? |
|---|---|---|---|
| Ventas | features de `build_features.py`, target log1p | mismas features (copia sincronizada) pero **consume la salida sin `expm1`** | 🔴 escala |
| Demanda | ídem + lags por producto | serie por producto sin col. `producto` (rama global) | 🔴 escala |
| Segmentación | RFM **escalado**; `frequency` = días distintos de compra | dict sin desempaquetar; `frequency` = nº facturas; sin escalar; `recency` vs `now()` en vez de vs max del dataset | 🔴 triple |
| Churn | `frequency, monetary_value, average_ticket` | `inactivity_days, average_ticket, total_orders, discount_ratio` | 🔴 columnas |
| Anomalías | `subtotal_neto, cantidad, costo_total, margen` | `discount_pct, total_amount, refund_flag` | 🔴 columnas |
| Reglas | DataFrame `item_A/item_B/co_occurrences/support` | espera opcionalmente `score` (fallback a `support` ✅), filtra solo `item_A` | 🟡 |
| Metas | features del SQL de `fetch_goals_data` | `goals_service` arma `df_pred` (no auditado línea a línea aquí; verificar nombres al implementar) | 🟡 verificar |

Adicional: el modelo de ventas entrena con la serie **global** (todas las sucursales), pero `get_sales_forecast_weekly(sucursal=...)` lo aplica a series por sucursal — cambio de escala/distribución que el modelo nunca vio (H-14b).

### 2.13 Compatibilidad de serialización (joblib/pickle)

- `joblib.dump/load` simétrico y versiones de xgboost/lightgbm/catboost declaradas como runtime del backend ✅ (bien documentado en `backend/requirements.txt`).
- 🔴 Si gana **CatBoost**, el serving rompe: `CatBoostRegressor/Classifier` no expone `feature_names_in_` (usa `feature_names_`), y `inference.predict_*` hace `X[model.feature_names_in_]` → `AttributeError`. Verificar también LightGBM según versión instalada (H-07).
- 🟡 Exportación inconsistente: ventas/demanda/churn/anomalías usan `save_artifact` (pkl + `.meta.json`); **segmentación, reglas y metas** usan `joblib.dump` directo sin sidecar de metadatos.
- 🟡 `ml/src/prediction/predict_model.py` (`MultiModelPredictor`) es un duplicado muerto del `ModelLoader` del backend, con los mismos bugs (dict de segmentación, sin expm1). Confunde sobre cuál es el punto de consumo real.

---

## 3. Tabla de hallazgos

Prioridad: 🔴 Crítica (bloquea generar los .pkl) · 🟠 Alta · 🟡 Media · ⚪ Baja.

| ID | Archivo | Función | Problema | Riesgo | Prioridad | Recomendación |
|----|---------|---------|----------|--------|-----------|---------------|
| H-01 | `ml/src/training/train_sales_prediction.py` / `train_demand_forecasting.py` (entrena `log1p`); `backend/app/ml/inference.py` `predict_sales`/`predict_demand`; `backend/app/services/prediction_service.py` `get_sales_forecast_weekly` | Modelo entrenado sobre `np.log1p(y)` pero el serving consume `model.predict()` crudo, sin `np.expm1`. Además el walk-forward re-inyecta el valor log como "venta del día" y corrompe los lags de los días siguientes. | El forecast de Gerencia muestra ~12 en vez de ~160.000; la simulación de 14 días colapsa toda la proyección. Los dos modelos estrella de la tesis producen números sin sentido. | 🔴 | Envolver el estimador en `TransformedTargetRegressor(func=np.log1p, inverse_func=np.expm1)` antes de serializar, para que el `.pkl` sea autocontenido y ninguna capa de serving deba "recordar" la transformación. |
| H-02 | `ml/src/training/train_customer_segmentation.py` `save_segmentation_model`; `backend/app/ml/inference.py` `predict_segmentation` | El `.pkl` es `{'model': KMeans, 'scaler': StandardScaler}`; el backend llama `.predict()` sobre el dict → `AttributeError` en el 100% de las llamadas (capturado y degradado a "Error"). Aunque se desempaquetara, faltaría `scaler.transform` antes de predecir. | La segmentación RFM nunca funciona en el dashboard de Ventas. | 🔴 | Serializar `Pipeline([('scaler', StandardScaler()), ('kmeans', KMeans(...))])` — un solo objeto con `.predict()` que escala internamente. |
| H-03 | `ml/main.py` `train_customer_churn` (features `frequency, monetary_value, average_ticket`); `backend/app/repositories/prediction_repository.py` `get_churn_features` (envía `inactivity_days, average_ticket, total_orders, discount_ratio`) | Esquema de features de serving ≠ entrenamiento (nombres y semántica). Bug ya reconocido en comentario de `prediction_service.py:202`. | Churn devuelve siempre 0.0 / riesgo falso-negativo para todos los clientes. | 🔴 | Definir UN contrato de features (mismo SQL/semántica en `make_dataset.py` y `prediction_repository.py`) y validar en un test de integración que `feature_names_in_` del pkl == columnas del repositorio. |
| H-04 | `ml/src/data/make_dataset.py` `fetch_transactions_for_anomalies` (entrena `subtotal_neto, cantidad, costo_total, margen`); `backend/app/repositories/prediction_repository.py` `get_transaction_features` (envía `discount_pct, total_amount, refund_flag`) | Mismo mismatch de columnas que H-03; además `get_anomaly_status` devuelve un score hardcodeado (−0.85 / 0.15) en vez de `decision_function`. | El detector de anomalías (Admin) nunca evalúa nada real; el "score" mostrado es ficticio. | 🔴 | Unificar contrato de features; exponer `decision_function()` como score real. |
| H-05 | `ml/src/data/make_dataset.py` `fetch_churn_data`; `ml/main.py` `train_customer_churn` | Etiqueta circular: `is_churn = recency > 90` se deriva del mismo snapshot que las features, sin ventana de observación + horizonte. `average_ticket` es además colineal por construcción (`monetary/frequency`). | El clasificador aprende una regla determinista disfrazada de ML; AUC alto pero sin capacidad predictiva real. Metodológicamente indefendible en la tesis. | 🔴 | Rediseñar el dataset con corte temporal: features calculadas hasta la fecha T, etiqueta = "¿compró en (T, T+90]?". Añadir features de tendencia (frecuencia últimos 3m vs históricos). |
| H-06 | `ml/src/features/build_features.py` `TimeSeriesLagsTransformer.transform` (línea 83) | `X_out.bfill()` imputa los NaN iniciales de lags/rolling con valores **futuros**; en el dataset de demanda (ordenado por fecha, multi-producto) puede rellenar con filas de otro producto. | Fuga de datos en las primeras ~90 filas de cada serie; métricas de validación levemente optimistas. | 🟠 | Reemplazar por `fillna(0)` + flag binaria `lag_disponible`, o descartar las primeras `max(lags)` filas por serie antes de entrenar. |
| H-07 | `ml/src/training/model_selector.py` `find_best_regression_model`/`find_best_classification_model`; `backend/app/ml/inference.py` | El ganador puede ser CatBoost, que no expone `feature_names_in_` → `X[model.feature_names_in_]` rompe el serving. (Verificar LightGBM según versión.) | Un reentrenamiento donde gane CatBoost rompe silenciosamente ventas/demanda/churn en producción. | 🟠 | Estandarizar el acceso a features vía el `.meta.json` (`features`) en lugar del atributo del estimador, o excluir del torneo estimadores sin `feature_names_in_`, o envolver todo en `Pipeline` sklearn. |
| H-08 | `ml/main.py` `train_demand_forecasting`; `ml/src/data/make_dataset.py` `fetch_sales_by_dimension` | (a) No aplica la ventana de 3 años que sí usa ventas, pese a que la justificación (quiebre estructural) aplica igual. (b) Se elimina `producto` de las features: modelo global ciego al SKU. | Demanda entrenada contra un régimen de negocio obsoleto; precisión por producto limitada. | 🟠 | Aplicar `VENTANA_ENTRENAMIENTO_VENTAS_ANIOS` también a demanda; evaluar codificar el producto (target encoding o features estáticas del SKU). |
| H-09 | `backend/app/services/prediction_service.py` `_build_forecast_metrics` / `_build_forecast_series` | `mae_modelo=165842.12`, `nivel_confianza=95.0` e intervalos ±15% hardcodeados y presentados como métricas del modelo. | Métricas fabricadas ante Gerencia y ante el tribunal de tesis; contradice el sidecar `.meta.json` diseñado justo para esto. | 🟠 | Leer MAE/R² reales del `.meta.json` del modelo cargado; derivar intervalos de los residuos de validación (p.ej. cuantiles del error). Requiere corregir antes que `main.py` pase `metrics=` a los `save_*` (hoy no lo hace y el sidecar queda vacío). |
| H-10 | `ml/src/training/train_recommendation_engine.py` `train_association_rules`; `backend/app/ml/inference.py` `get_recommendations` | Reglas simétricas con solo soporte (sin confianza ni lift); los pares se ordenan alfabéticamente y el backend filtra solo `rules['item_A'].isin(historial)` → se pierden todas las reglas donde el ítem comprado quedó como `item_B`. Además entrena con `nombre_articulo` pero el response del backend espera `producto_cod`. | ~50% de recomendaciones perdidas; ranking por popularidad bruta (soporte) en vez de afinidad (lift); el frontend recibe nombres donde espera códigos. | 🟠 | Emitir reglas direccionales A→B y B→A con `confidence` y `lift` (o usar `mlxtend.association_rules`, ya declarado en requirements); usar `codart` como clave y el nombre solo para display. |
| H-11 | `ml/src/training/model_selector.py` (líneas 82, 137) | Si los 5 algoritmos fallan, `best_model_info` es `None` y `best_model_info[0]` lanza `TypeError`; `use_label_encoder=False` es un parámetro eliminado en xgboost ≥ 2.0; `optuna` importado y nunca usado; `n_iter=5` > tamaño efectivo útil de algunos grids. | Crash confuso en vez de error claro; warnings de librería; dependencia muerta que engorda la imagen Docker. | 🟡 | Guard explícito con mensaje si nadie ganó; retirar `use_label_encoder` y el import de optuna (o usarlo de verdad, como promete el plan). |
| H-12 | `ml/src/training/train_customer_segmentation.py` `train_rfm_segmentation`; `backend/app/services/prediction_service.py` `get_customer_segment` | K=4 fijo sin análisis (silhouette solo se loguea); el backend mapea `cluster_id → nombre de negocio` con un dict fijo, pero las etiquetas de K-Means son arbitrarias: tras cada reentrenamiento el cluster 3 puede dejar de ser "Campeones". | Clientes "En Riesgo" etiquetados como "Alto Valor" tras un reentrenamiento, sin que nadie lo note. | 🟠 | Tras entrenar, ordenar clusters por centroides (p.ej. por `monetary` desc / `recency` asc) y persistir el mapeo cluster→segmento dentro del artefacto o su `.meta.json`. Documentar la elección de K con silhouette/elbow en el reporte. |
| H-13 | `ml/src/training/train_goals_prediction.py` `train_goals_prediction` | (a) `anio` queda como feature: árboles no extrapolan a años futuros (2027 será "igual que 2026" en el mejor caso). (b) `except: pass` silencia la evaluación del test. (c) Guarda con `joblib.dump` directo, sin `.meta.json`. | Metas degradadas en cambio de año; sin trazabilidad de calidad del modelo que fija comisiones (sensible para vendedores). | 🟡 | Excluir `anio` (o transformarlo a "años de antigüedad relativa"); loguear la excepción; migrar a `save_artifact`. |
| H-14 | `ml/src/data/make_dataset.py` `fetch_rfm_metrics` vs `backend/app/repositories/prediction_repository.py` `get_rfm_features`; `ml/main.py` `train_general_sales_prediction` vs `prediction_service.get_sales_forecast_weekly(sucursal=...)` | (a) `frequency` de entrenamiento = días distintos de compra; en serving = nº de facturas. (b) `recency` de entrenamiento relativa al max del dataset; en serving relativa a `now()`. (c) Ventas entrena con la serie global pero se sirve filtrada por sucursal. | Aun corrigiendo H-02, el cliente se ubicaría en el cluster equivocado; el forecast por sucursal opera fuera de la distribución de entrenamiento. | 🟠 | Unificar la semántica RFM en una sola consulta compartida/documentada; para sucursales, entrenar por sucursal o incluirla como feature; si no, restringir el endpoint al agregado global. |
| H-15 | `ml/src/data/make_dataset.py` `fetch_daily_sales`, `fetch_rfm_metrics`, `fetch_transactions_for_anomalies` | No filtran `estado_factura != 'I'` ni excluyen devoluciones, mientras `fetch_goals_data` y todos los repositorios del backend sí filtran. Población de entrenamiento ≠ población de inferencia. | Sesgo sistemático entre lo aprendido y lo servido; inconsistencia con las reglas de negocio validadas (auditoría 02: solo estado 'P'). | 🟡 | Homologar los filtros de estado/devolución en TODOS los extractores de `make_dataset.py` y documentar la decisión en `02_reglas_negocio_validadas.md`. |
| H-16 | `ml/src/data/make_dataset.py` `fetch_rfm_metrics` (cliente_sk sin excluir centinela) | Las ventas con `cliente_sk = -1` (desconocido) entran al RFM como un pseudo-cliente de valor monetario enorme. | Distorsiona centroides de K-Means y el dataset de churn. | 🟡 | `WHERE cliente_sk <> -1` en RFM/churn (regla 12 de CLAUDE.md: los centinela son para integridad, no para análisis). |
| H-17 | `ml/src/prediction/predict_model.py` | `MultiModelPredictor` duplica al `ModelLoader` del backend y arrastra los mismos bugs (dict de segmentación, sin expm1). Código muerto desde el refactor del backend. | Confusión sobre el punto de consumo real; riesgo de "corregir" el archivo equivocado. | 🟡 | Eliminarlo o reducirlo a CLI de smoke-test post-entrenamiento que valide el contrato de los .pkl. |
| H-18 | `ml/main.py` (todas las `train_*`); `ml/src/utils/model_export.py` | Las métricas calculadas se loguean pero no se pasan a `save_*` → todos los `.meta.json` quedan con `metrics: {}`; el sidecar tampoco registra versiones de librerías ni rango de fechas de los datos. | Sin trazabilidad MLOps real; imposible auditar regresiones de calidad entre reentrenamientos; el acoplamiento de versiones .pkl↔backend queda sin control. | 🟡 | Pasar `metrics=metrics` en cada `save_*`; añadir al sidecar `sklearn/xgboost/lightgbm/catboost.__version__`, nº de filas y `fecha_min/max` de entrenamiento. |
| H-19 | `ml/main.py` `train_anomaly_detection` | `fillna(0.0)`: un `costo_total` NULL se vuelve costo 0 → margen 100% artificial que el IsolationForest normaliza como patrón. `contamination=0.01` es un supuesto sin validación. | Anomalías reales enmascaradas por artefactos de imputación; tasa de alertas arbitraria. | 🟡 | Excluir filas sin costo o imputar con mediana por producto; contrastar `contamination` contra casos conocidos de `fact_logs_auditoria`. |
| H-20 | `ml/requirements.txt` | Rangos `>=` sin tope superior en las 4 librerías que serializan los `.pkl`, mientras el backend sí acota (`<3.0.0`, etc.). | Un `pip install` futuro en `ml/` puede producir `.pkl` ilegibles para el backend (incompatibilidad joblib entre versiones mayores). | 🟡 | Alinear los rangos de `scikit-learn/xgboost/lightgbm/catboost/joblib` con los del backend (idealmente pin exacto compartido). |
| H-21 | `ml/src/data/make_dataset.py` `fetch_sales_by_dimension` | Join a `dim_producto` (SCD2) sin filtrar `es_vigente`, agrupando por `nombre_articulo`: si un artículo cambió de nombre, su serie histórica se parte en dos series independientes. | Lags/rolling truncados para productos renombrados; demanda subestimada. | ⚪ | Agrupar por la llave de negocio (`codart`) y resolver el nombre vigente solo para display. |
| H-22 | `ml/main.py` `run_ml_pipeline`; `ml/src/data/make_dataset.py` (todos los `fetch_*`) | El pipeline entrena sin verificar la frescura/éxito de la última carga en `edw.etl_control` (la tabla de idempotencia/trazabilidad del ETL, diseñada para esto); tampoco consume las vistas del esquema `ml.*` del EDW — todo el SQL vive embebido contra `edw.*` crudo. | Si el ETL falló o está desactualizado, se publican `.pkl` "recientes" entrenados con datos viejos o parciales, sin ninguna alerta; la lógica de consumo del EDW queda dispersa en Python en vez de versionada como vistas en `edw/09_vistas_ml.sql`. | 🟡 | Al inicio de `run_ml_pipeline`, validar `estado='SUCCESS'` y fecha de la última corrida en `edw.etl_control` (abortar o advertir si supera un umbral de antigüedad); migrar los `SELECT` estables de `make_dataset.py` a vistas del esquema `ml.*` y registrar en el `.meta.json` la fecha máxima de datos usada. |

---

## 4. Orden de implementación recomendado

**Bloque 1 — Bloqueantes de la generación de `.pkl` (todo lo 🔴):**
1. H-01: `TransformedTargetRegressor` en ventas y demanda (artefacto autocontenido).
2. H-02: Pipeline `scaler+kmeans` para segmentación.
3. H-03 / H-04: unificar contratos de features churn y anomalías (entrenamiento ↔ repositorios del backend) + test de integración de contrato (`feature_names_in_` vs columnas del repo).
4. H-05: rediseño temporal del dataset de churn (es el único rediseño metodológico, no solo de plomería).

**Bloque 2 — Antes de dar por oficiales los artefactos (🟠):**
H-06 (bfill), H-07 (CatBoost/feature_names_in_), H-08 (ventana + producto en demanda), H-09 (métricas reales al dashboard), H-10 (lift/confianza y doble dirección en reglas), H-12 (mapeo estable cluster→segmento), H-14 (semántica RFM y sucursal).

**Bloque 3 — Higiene y trazabilidad (🟡/⚪):**
H-11, H-13, H-15, H-16, H-17, H-18, H-19, H-20, H-21, H-22 (guard de frescura contra `edw.etl_control` + vistas `ml.*`).

**Regla transversal:** todo artefacto nuevo debería ser un objeto único con `.predict()` autocontenido (pipeline sklearn), y debería existir un smoke-test post-entrenamiento que cargue cada `.pkl` y le pase una fila con las columnas exactas que produce el repositorio del backend. Ese test habría detectado H-01…H-04 y H-07 automáticamente.

---

## 5. Lo que está bien (no tocar sin razón)

- Ventana de 3 años en ventas con justificación empírica documentada (R² −0.03 → +0.21).
- Rezago de exógenas contemporáneas (fuga corregida y comentada).
- Muestreo determinista (`ORDER BY venta_sk DESC`) y exclusión del centinela `pct_margen=-9999`.
- `random_state=42` consistente; umbrales por variable de entorno.
- Competencia multi-algoritmo con `TimeSeriesSplit` y splits cronológicos sin shuffle.
- Manejo de desbalance en churn (stratify + class weights) — mecánica correcta, pendiente el rediseño de la etiqueta.
- `save_artifact` con sidecar `.meta.json` (extenderlo, no reemplazarlo) y la decisión documentada de joblib sobre ONNX.
- La separación backend/entrenamiento (backend no importa `ml/`) es correcta; lo que falta es el contrato verificable entre ambos.
