---
name: ml-training-pipeline
description: >-
  Especialista en la capa de entrenamiento ML de este proyecto (`ml/`): los 6 modelos que se
  entrenan desde el EDW PostgreSQL y se publican como `.pkl` + sidecar `.meta.json` + contrato
  JSON hacia el backend. Usar SIEMPRE que la tarea toque `ml/main.py`, `ml/src/data/make_dataset.py`
  (SQL de datasets), `ml/src/features/build_features.py`, `ml/src/training/*`,
  `ml/src/contracts/*`, `ml/contracts/models/*.json`, `ml/src/utils/model_export.py` o
  `ml/publish_models.py` — incluyendo: agregar o corregir features de entrenamiento (en especial
  cuando hay que calcular campos combinando DOS o más tablas de hechos del EDW antes de entrenar),
  cambiar el target o la ventana de entrenamiento, agregar un modelo nuevo, diagnosticar fuga de
  datos (data leakage), métricas degradadas (R2/MAE), o el flujo contrato → entrenamiento →
  validación → publicación. No usar para el serving/inferencia del backend (`backend/app/ml/`) —
  eso es la skill backend-ml-serving; ni para el ETL/EDW en sí — eso es etl-edw-auditor.
---

# ML Training Pipeline

Eres el especialista de la capa de entrenamiento ML de este proyecto (`ml/`, imagen Docker
separada del backend). Tu prioridad es la **validez metodológica del entrenamiento**: sin fuga de
datos, con los filtros de negocio del EDW correctos (centinelas, estado de documento), respetando
el flujo contrato-primero, y produciendo artefactos que el backend pueda consumir sin conocer el
código de `ml/`. Este pipeline ya tuvo bugs metodológicos graves corregidos en auditorías
(circularidad de churn H-05, doble transformación log H-01, centinelas dentro del dataset
H-16/H-21) — no los reintroduzcas y no asumas que el código actual es correcto sin verificarlo.

## Arquitectura de entrenamiento (específica de este proyecto)

```
EDW PostgreSQL (esquema edw.*, host puerto 5433 / contenedor 5432)
        │  SQL en ml/src/data/make_dataset.py (SalesTimeSerieExtractor, SQLAlchemy)
        ▼
ml/src/features/build_features.py (TimeSeriesLagsTransformer: lags, rolling, calendario, exógenas rezagadas)
        ▼
ml/main.py (orquestador: 7 funciones train_*, una por modelo, ejecutadas en secuencia)
  └── ml/src/training/train_<modelo>.py + model_selector.py (competencia RF/XGB/LGBM/CatBoost)
        ▼
ml/src/utils/model_export.py::save_artifact → ml/models/<nombre>.pkl + <nombre>.meta.json
        ▼
python -m src.contracts.contract_validator  (valida .pkl+.meta contra ml/contracts/models/*.json)
        ▼
ml/publish_models.py  (docker compose restart backend — el volumen :ro ya monta ml/models)
```

| Pieza | Archivo | Rol |
|---|---|---|
| Datasets desde el EDW | `ml/src/data/make_dataset.py` | Toda consulta SQL de entrenamiento vive aquí, en métodos `fetch_*` de `SalesTimeSerieExtractor`. Conexión vía env vars `PG_*` (falla explícito sin `PG_PASSWORD`). Parámetros de negocio como constantes con env var (`ML_CHURN_UMBRAL_DIAS`, `ML_MUESTRA_MARKET_BASKET`, etc.), nunca literales enterrados en el SQL. |
| Feature engineering | `ml/src/features/build_features.py` | `TimeSeriesLagsTransformer` (lags 1/7/30, rolling con `shift(1)`, variables de calendario, `es_feriado` aproximado con feriados fijos de Ecuador — deuda documentada: `dim_fecha.es_feriado` nunca se puebla). Las exógenas contemporáneas (`n_clientes`, `n_facturas`, `pct_descuento_prom`) se **rezagan 1 día** (`*_prev`) porque se calculan del mismo día que el target — usarlas sin rezago es fuga de datos. |
| Orquestador | `ml/main.py` | 7 funciones `train_*`, cada una: fetch → features → split cronológico 80/20 → entrenar → evaluar → `save_*`. `VENTANA_ENTRENAMIENTO_VENTAS_ANIOS = 3` para ventas y demanda (quiebre estructural del negocio, R2 −0.03 → +0.21; no la quites sin re-hacer el backtest). |
| Selección de modelo | `ml/src/training/model_selector.py` | `find_best_regression_model` / `find_best_classification_model`: competencia RF/XGBoost/LightGBM/CatBoost con `TimeSeriesSplit` (series de tiempo) o `StratifiedKFold` (clasificación). Se activa con `hyperparameter_search=True` en cada `train_*`. |
| Export de artefactos | `ml/src/utils/model_export.py` | `save_artifact(obj, filename, features=..., metrics=..., data_range=..., ...)`: joblib + sidecar `.meta.json` (algoritmo, features, métricas, versiones de librerías, `contract_name`). El backend lee el sidecar, nunca deserializa para descubrir features. |
| Contratos (lado entrenamiento) | `ml/src/contracts/` + `ml/contracts/models/*.json` | Regla D-2 (auditoría 12): **el contrato se escribe ANTES de entrenar**, desde el diseño del dataset y las reglas de negocio — nunca se deriva de un `.pkl` ni de `feature_names_in_`. `python -m src.contracts.contract_validator` (desde `ml/`) corre antes de publicar: contrato `active` que falla **bloquea**; `draft` solo informa. |
| Publicación | `ml/publish_models.py` | No copia archivos: el volumen Docker `./ml/models:/app/ml_models:ro` ya está montado en el backend; solo hace `docker compose restart backend`. |
| Tests | `ml/tests/test_model_contract.py` | Tests de la capa de contratos. Correr con `pytest` desde `ml/`. |

Los 6 modelos, en orden de `run_ml_pipeline()`: ventas (`sales.pkl`), demanda (`demand.pkl`),
segmentación RFM (`segmentation.pkl`), churn (`churn.pkl`), recomendación (`recommendation.pkl`),
anomalías (`anomalies.pkl`). El 7º modelo, metas (`goals.pkl`, `goals_rf`), fue decomisionado
(2026-07-10, docs/auditoria/20_decomision_goals_rf.md) -- Metas y Comisiones usa 100%
estadística pura (`IQRGoalCalculationEngine` en el backend), sin ML. No lo reintroduzcas en
`ml/main.py`/`ml/contracts/models/` sin una decisión de negocio explícita. Los `*_rf_model.pkl` / `*_best_model.pkl` en
`ml/models/` son artefactos **legacy** — el backend apunta a los nombres bajo contrato
(`_MODEL_FILES` en `backend/app/ml/model_loader.py`); no "corrijas" código para volver a los
nombres viejos.

## Filtros de negocio obligatorios en TODO SQL de dataset

Cualquier consulta nueva o modificada en `make_dataset.py` debe cumplirlos (fuente:
`CLAUDE.md` reglas 1 y 12, y contratos `population_filter`):

1. **Estado de documento**: `JOIN edw.dim_estado_documento ed ON <fact>.estado_documento_sk =
   ed.estado_documento_sk WHERE ed.estado_documento_sk <> -1` (y `NOT ed.es_devolucion` cuando
   las devoluciones no aplican al caso de uso, p.ej. market basket). Es la forma nueva del filtro
   `estado='P'` — `es_devolucion` migró de la fact a esta junk dimension (cambio C-1, auditoría 13).
2. **Centinelas fuera**: excluir `cliente_sk <> -1`, `producto_sk <> -1` (y el centinela de
   cualquier dim que entre al dataset). Un centinela dentro del dataset es un pseudo-cliente/
   pseudo-producto que distorsiona centroides, series y reglas (H-16, H-21 — ya pasó).
3. **Llaves de negocio, no nombres**: agrupar/identificar productos por `codart` y clientes por
   `cliente_sk`, nunca por `nombre_articulo` (SCD2: un cambio de nombre parte la serie en dos).
4. **Muestras deterministas**: si se usa `LIMIT`, siempre con `ORDER BY <sk> DESC` (las N filas
   más recientes) — un `LIMIT` sin orden produce corridas no reproducibles.
5. **Parametrización**: umbrales y tamaños de muestra como constantes módulo-nivel con
   `os.getenv("ML_...")`, siguiendo el patrón existente al inicio de `make_dataset.py`.

## Features que combinan DOS (o más) tablas de hechos

Este es el caso más delicado del pipeline. Las tablas de hechos del EDW tienen **granularidades
distintas** (`fact_ventas_detalle` = línea de factura; `fact_movimientos_inventario` = movimiento
de kardex; `fact_cobros_cxc` = cobro; `fact_inventario_snapshot` = producto/bodega/día), así que
**nunca se JOINean directamente entre sí**: eso multiplica filas (fan-out) e infla las sumas.
El patrón correcto es **agregar cada hecho por separado al grano común y unir los agregados**:

```sql
WITH ventas AS (
    SELECT df.fecha_completa AS ds, SUM(fvd.subtotal_neto) AS y_sales_net, ...
    FROM edw.fact_ventas_detalle fvd
    JOIN edw.dim_fecha df ON fvd.fecha_sk = df.fecha_sk
    JOIN edw.dim_estado_documento ed ON fvd.estado_documento_sk = ed.estado_documento_sk
    WHERE ed.estado_documento_sk <> -1
    GROUP BY df.fecha_completa
),
otro_hecho AS (
    SELECT df.fecha_completa AS ds, SUM(f2.<medida>) AS <feature_agregada>
    FROM edw.fact_<otro> f2
    JOIN edw.dim_fecha df ON f2.fecha_sk = df.fecha_sk
    -- aplicar aquí los filtros de negocio propios de ESTE hecho
    GROUP BY df.fecha_completa
)
SELECT v.ds, v.y_sales_net, ..., COALESCE(o.<feature_agregada>, 0) AS <feature_agregada>
FROM ventas v
LEFT JOIN otro_hecho o ON v.ds = o.ds   -- LEFT desde el hecho del target
ORDER BY v.ds;
```

Reglas de este patrón en este proyecto:

- **El grano común lo definen las dimensiones conformadas** (`dim_fecha` casi siempre; también
  `dim_sucursal`, `dim_producto` según el modelo). Cada CTE agrega su hecho a ese grano ANTES
  del join. Verifica la cardinalidad: el resultado final debe tener las mismas filas que el CTE
  del target (cuéntalo con un `SELECT COUNT(*)` de cada CTE antes de dar el SQL por bueno).
- **`LEFT JOIN` desde el hecho del target** y `COALESCE` explícito para los días/combinaciones
  sin actividad en el segundo hecho — decide conscientemente si el "sin datos" es `0` (no hubo
  movimientos) o `NULL` (dato no disponible, como `costo_total` en anomalías, donde se excluye
  en vez de imputar — H-19).
- **Cada hecho lleva SUS filtros**: el join a `dim_estado_documento` aplica a
  `fact_ventas_detalle`; la dirección de kardex (`tipdoc`: entrada `'EN','AC'`, salida
  `'SA','AD'`, `cantot` siempre positivo) aplica a `fact_movimientos_inventario` — nunca uses el
  signo de la cantidad (regla de negocio 3, CLAUDE.md).
- **Cuidado con la fuga de datos temporal**: una feature agregada del segundo hecho calculada el
  MISMO día/mes que el target no está disponible al momento de predecir. Sigue el patrón de
  `COLUMNAS_EXOGENAS_CONTEMPORANEAS` en `build_features.py`: rezagarla (`shift(1)` → sufijo
  `_prev`) o construirla solo con periodos `< T` (patrón de cortes temporales de
  `fetch_churn_data`, H-05). Pregúntate siempre: "¿esta columna existiría en producción en el
  momento de la predicción?".
- **Antecedente documentado**: `fetch_daily_sales` ya evaluó `fact_cobros_cxc` y
  `fact_inventario_snapshot` como exógenas y las **descartó con evidencia** (snapshot sin
  histórico pre-2026 <1%; `valor_cobrado_dia` empeoró el R2 de −0.02 a −0.11 por colinealidad
  con la tendencia — ver `ml/REPORTE_MEJORA_MODELOS.md`). Si reintroduces alguna, hazlo con un
  backtest nuevo que supere ese resultado, no por intuición.
- **`fact_metas_comerciales` está vacía** y `dim_geografia` también (hallazgos abiertos,
  auditoría 05): no diseñes features sobre ellas sin verificar primero su contenido con un
  `SELECT COUNT(*)`.

Después del SQL, el resto del flujo no cambia: la feature nueva entra al contrato JSON
(**antes** de entrenar), a `build_features.py` si requiere transformación temporal, y a
`preprocessing.py` del backend si el serving debe reconstruirla en vivo (ver "Sincronía con el
backend" abajo).

## Flujo para cambiar cómo se entrena un modelo (seguir en orden)

1. **Auditoría previa** (flujo del CLAUDE.md raíz): si el cambio corrige un problema de datos o
   metodología, documenta primero el hallazgo en `docs/auditoria/` (siguiente número libre) con
   evidencia — consultas SQL contra el EDW, métricas del backtest actual como línea base.
2. **Contrato primero (D-2)**: actualiza `ml/contracts/models/<name>.json` con las features
   nuevas (nombre, dtype, `required`, descripción), el `population_filter` si cambió, y el
   `plausible_range` del output. Si el cambio es experimental, baja `status` a `"draft"` durante
   el desarrollo y súbelo a `"active"` solo al validar.
3. **SQL del dataset** en `make_dataset.py` (respetando los filtros de negocio y, si combina
   hechos, el patrón de CTEs agregados de arriba). Valida el SQL solo contra el EDW
   (`docker exec bi_postgres_edw psql -U etl_user -d edw -c "..."`) — nunca contra SAP
   Producción para esta capa (el entrenamiento SOLO lee del EDW).
4. **Features** en `build_features.py` si hay transformación temporal nueva (lag/rolling/rezago).
5. **Entrenamiento**: ajusta la función `train_*` en `ml/main.py` y/o `ml/src/training/`.
   Mantén el split **cronológico** 80/20 para series de tiempo (nunca `train_test_split`
   aleatorio en series — solo churn usa split aleatorio estratificado porque sus filas son
   cortes temporales ya independientes) y la ventana de 3 años donde aplica.
6. **Backtest comparativo**: corre el entrenamiento y compara métricas contra la línea base del
   paso 1. Un cambio que degrada R2/MAE no se publica; documenta el resultado (positivo o
   negativo) en `ml/REPORTE_MEJORA_MODELOS.md` o en el reporte de auditoría.
7. **Guardado**: usa `save_artifact` (vía la función `save_*` del modelo) pasando `features=`
   (lista real de columnas de entrenamiento), `metrics=` y `data_range=` — el sidecar es la
   fuente de verdad del serving; un sidecar sin `features` rompe la selección de columnas del
   backend.
8. **Validación de contrato**: `cd ml && python -m src.contracts.contract_validator`. Debe salir
   limpio para los contratos `active` antes de publicar. Corre también `pytest tests/` en `ml/`.
9. **Publicación**: `python publish_models.py` (o `docker compose restart backend`) y verifica
   `GET /health` → `modelos_ml_listos: true` y el log de arranque del backend sin
   `WARNING`/`ERROR` de carga.

Cómo ejecutar el pipeline: local con env vars `PG_*` apuntando a `localhost:5433`
(`cd ml && python main.py`), o en Docker con `docker compose run ml python main.py`
(perfil `ml`, monta `./ml:/app`).

## Sincronía con el backend (la parte que más se rompe)

El backend reconstruye en vivo las mismas features de entrenamiento con SU PROPIA copia del
preprocesamiento (`backend/app/ml/preprocessing.py`) — no importa `ml.src.*` (dos imágenes
Docker; la interfaz es el JSON del contrato + el sidecar). Consecuencia: **si cambias las
features de un modelo cuyo serving hace preprocesamiento en vivo (ventas, demanda), tienes que
replicar el cambio en `backend/app/ml/preprocessing.py` y en el repositorio del backend que trae
los datos crudos** (`DatasetRepository`/`PredictionRepository`), o la inferencia fallará con
`ModelContractError` (columnas faltantes) o —peor— predecirá con features mal construidas.
Para ese lado usa la skill `backend-ml-serving`. Los desajustes conocidos y decisiones se
registran en el campo `known_serving_mismatch` del contrato (p.ej. H-14b: ventas entrena global
pero el endpoint filtra por sucursal — pendiente de decisión); si tu cambio crea o cierra un
desajuste, actualiza ese campo.

Además: las versiones de sklearn/xgboost/lightgbm/catboost deben coincidir entre
`ml/requirements.txt` y `backend/requirements.txt` (los `.pkl` de joblib acoplan versiones,
H-20). Si actualizas una librería de entrenamiento, actualiza la del backend en el mismo cambio
y registra las versiones con `library_versions(...)` en `save_artifact`.

## Errores metodológicos a vigilar (todos ya ocurrieron aquí)

- **Circularidad/fuga temporal (H-05)**: calcular features y etiqueta sobre el mismo snapshot.
  Patrón correcto: cortes temporales T — features con datos `<= T`, etiqueta con `(T, T+h]`.
- **Doble transformación del target (H-01)**: el artefacto debe ser autocontenido
  (`TransformedTargetRegressor` con log1p/expm1 interno); nunca exigir que el serving "recuerde"
  aplicar `expm1`.
- **Exógenas contemporáneas sin rezago**: toda columna calculada de las mismas transacciones del
  día del target se rezaga (`_prev`).
- **Centinelas `-1` dentro del dataset (H-16/H-21)** y **agrupar por nombre en vez de llave**.
- **Imputar con `fillna(0)` valores NULL de negocio (H-19)**: un costo NULL no es costo cero;
  decide entre excluir o imputar con justificación, y documéntalo.
- **Split aleatorio en series de tiempo**: siempre cronológico; en CV, `TimeSeriesSplit`.
- **Evaluar contra un régimen estructural distinto**: respeta la ventana de 3 años (o re-haz el
  análisis del quiebre si crees que ya no aplica, con evidencia).
- **Derivar el contrato del `.pkl`** (`feature_names_in_` → JSON): invierte la dirección — el
  contrato es el diseño, el artefacto lo cumple.
- **Publicar sin pasar el contract_validator** o dejar métricas peores sin documentar.
