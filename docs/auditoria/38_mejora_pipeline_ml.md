# Auditoría 38 — Fase 0 del plan de mejora del pipeline ML

> **Fecha:** 2026-07-20.
> **Alcance:** línea base congelada de los 6 modelos vigentes, backtest reproducible del modelo
> de demanda por SKU, verificación de paridad de filtros entrenamiento↔serving, y conteo de
> filas por SKU/almacén para dimensionar la Fase 2 (`docs/features/plan_mejora_pipeline_ml.md`).
> **Método:** `SELECT` contra `postgres_edw` (Docker, puerto host 5433, contenedor `bi_postgres_edw`
> ya corriendo) vía `sqlalchemy`/`psycopg2` desde el host, y ejecución local del pipeline de
> features + `demand.pkl` reconstruyendo exactamente el flujo de `ml/main.py::train_demand_forecasting`.
> Ningún `INSERT`/`UPDATE`/`DELETE` — solo lectura.
> **No toca código todavía** — este reporte es el "antes" contra el que se medirán las fases 1-5.

---

## 1. Línea base congelada de métricas (2026-07-20)

Copiada de `ml/models/*.meta.json` en el estado actual del repositorio (sin re-entrenar nada):

| Proceso | Clave | Archivo campeón | Algoritmo | Métricas | Ventana | Nº features |
|---|---|---|---|---|---|---|
| Ventas (Gerencia) | `sales_rf` | `sales.pkl` | RandomForestRegressor | R²=0.297, RMSE=6285, MAE=3789 | 2023-07→2026-07 (3 a) | 26 |
| Demanda (Bodega) | `demand_rf` | `demand.pkl` | CatBoostRegressor | R²=0.876, RMSE=191.04, MAE=6.20 | 2023-07→2026-07 (3 a) | 18 |
| Churn (Ventas) | `churn_rf` | `churn.pkl` | CatBoostClassifier | accuracy=0.784, roc_auc=0.758 | 2025-01→2026-04 | 3 |
| Segmentación RFM (Ventas) | `segmentation` | `segmentation.pkl` | Pipeline(StandardScaler+KMeans) | silhouette=0.608 | — | 3 |
| Recomendación (Ventas) | `association` | `recommendation.pkl` | Item-item coseno | precision@5=0.077, recall@5=0.262, hit_rate@5=0.358, cobertura=0.979 | 2 años | 6 |
| Anomalías (Admin) | `anomaly` | `anomalies.pkl` | IsolationForest | pct_flagged=1.0% | 16.431 filas | 4 |

Este es el "antes" congelado. Cualquier mejora de las Fases 1-5 se compara contra esta tabla, no
contra intuición.

---

## 2. Backtest reproducible del modelo de demanda por SKU (D-1)

**Objetivo:** el `.meta.json` de `demand.pkl` reporta un R² global de 0.876 con `RMSE=191.04` vs
`MAE=6.20` — una brecha de ~30x entre ambas métricas de error que solo se explica si unos pocos
SKU concentran errores absolutos enormes. El R² global no lo muestra. Este backtest lo cuantifica
reproduciendo EXACTAMENTE el flujo de entrenamiento (mismo `fetch_sales_by_dimension('producto')`,
mismo `build_preprocessing_pipeline(target_col='y_quantity')`, misma ventana de 3 años, mismo
split cronológico 80/20), pero conservando la columna `producto` **solo para agrupar el error**
después de predecir — nunca se la pasa al modelo (así es como se entrena hoy: `producto` se
descarta en `select_features_and_target`, que es precisamente D-1).

Script: `ml/scripts/backtest_demand_por_sku.py` (nuevo, entregable de esta fase — reutilizable
para futuros backtests, no se borra tras esta auditoría).

### 2.1 Resultado (corrida real contra el EDW, 2026-07-20)

```
Filas crudas (fecha, producto): 275,404
Ventana entrenamiento: 2023-07-17 -> 2026-07-16
Filas train: 81,233 | Filas test (hold-out 20%): 20,309
Corte cronológico train/test: 2025-12-31

MÉTRICA GLOBAL (recalculada hoy, dataset actualizado 10 días desde el entrenamiento vigente):
R2=0.8668  MAE=5.6569  RMSE=176.5923  n=20,309
```

(La pequeña diferencia frente a `demand.meta.json` — R²=0.876 vs 0.867 — es esperable: el EDW
tiene 10 días más de datos que cuando se entrenó el 2026-07-10; no es un re-entrenamiento, es la
misma arquitectura evaluada sobre un dataset fresco.)

**MAE / RMSE por decil de volumen histórico del SKU** (decil 0 = SKU de menor volumen en train,
decil 9 = mayor volumen):

| Decil | Filas test | SKUs | Volumen medio train | MAE | RMSE |
|---|---|---|---|---|---|
| 0 | 2,074 | 873 | 3.71 | 1.01 | 3.96 |
| 1 | 2,008 | 356 | 31.32 | 0.90 | 2.29 |
| 2 | 2,013 | 164 | 94.61 | 1.55 | 15.45 |
| 3 | 2,051 | 78 | 179.54 | 1.41 | 4.46 |
| 4 | 2,010 | 60 | 317.60 | 1.84 | 7.10 |
| 5 | 2,098 | 43 | 545.31 | 1.55 | 3.37 |
| 6 | 1,987 | 32 | 846.74 | 2.37 | 7.56 |
| 7 | 2,056 | 25 | 1,410.83 | 2.72 | 8.58 |
| 8 | 2,004 | 17 | 2,542.07 | 3.54 | 7.46 |
| **9** | **2,008** | **17** | **9,802.68** | **40.15** | **561.14** |

**Confirmado cuantitativamente:** el decil de mayor volumen (9) tiene un MAE 40x peor y un RMSE
150x peor que los deciles bajos. El modelo global apilado predice razonablemente bien los SKU de
bajo/medio volumen (la mayoría, 873+356+164 = 1,393 SKU en los deciles 0-2) pero falla gravemente
en los pocos SKU de alto volumen — justo los que más importan para evitar quiebres de stock caros.

**Un solo SKU concentra la mayor parte del error del decil 9:**

| producto | n (test) | MAE | volumen train total |
|---|---|---|---|
| `Z-9001` | 8 | **6,469.07** | 750,426.30 |
| `LT-U1P-10155-1` | 122 | 36.25 | 8,829.00 |
| `LT-U1P-10189-1` | 122 | 35.98 | 9,468.00 |
| `2825` | 106 | 18.96 | 10,878.00 |
| `7528` | 139 | 18.15 | 10,999.00 |
| … (10 SKU más con MAE 10-33) | | | |

`Z-9001` por sí solo (volumen histórico ~3.6x el segundo SKU más vendido) es casi con certeza un
código agregado/consolidado o un artículo atípico (posible SKU de "servicio"/"varios" o error de
captura en el ERP) que no debería competir por el mismo modelo estadístico que artículos de rotación
normal — se recomienda **excluirlo explícitamente en Fase 2 (tratarlo aparte o filtrarlo)** y
confirmarlo con `SELECT * FROM edw.dim_producto WHERE codart = 'Z-9001'` antes de decidir.

**SKUs distintos en toda la ventana de 3 años:** 3,628. **SKUs distintos en el hold-out de test:**
1,665 (no todos los SKU tienen actividad en el último 20% cronológico — otro síntoma de series
ralas, ver §3).

**Nota metodológica:** la métrica "% de combinaciones (producto, mes) con demanda mensual = 0"
calculada sobre este dataset dio 0.00% — pero es un artefacto de cómo se construye
`fetch_sales_by_dimension`: el SQL solo devuelve pares `(fecha, producto)` donde **hubo** venta
(no genera un grid calendario completo por producto), así que nunca puede observar un mes en
cero dentro de este dataset. La intermitencia real se mide en §3 con una consulta que sí
construye el grid mensual completo por combinación.

---

## 3. Conteo de filas por SKU/almacén — dimensionamiento de la Fase 2 (grano producto×almacén)

Consulta sobre `edw.fact_movimientos_inventario` (salidas, `es_salida = true`, dirección dada por
esa columna booleana ya precalculada — no por el signo de `cantidad_movimiento`, que siempre es
magnitud positiva, regla de negocio 3), excluyendo centinelas (`producto_sk <> -1`,
`almacen_sk <> -1`), últimos 3 años reales de datos (`max(fecha_completa)` de movimientos reales,
no de `dim_fecha` que está generada hasta 2030 — un primer intento de esta consulta usando
`max(dim_fecha.fecha_completa)` como tope dio 0 filas por este motivo, corregido tomando el máximo
real de fechas con movimiento).

| Métrica | Valor |
|---|---|
| Combinaciones `(codart, almacen_sk)` distintas con al menos una salida en 3 años | **12,654** |
| SKUs distintos involucrados | 4,502 |
| Almacenes distintos involucrados | 12 |
| Filas de movimiento (líneas de salida) | 246,860 |
| Meses con actividad por combinación — media | **5.63 de 36** |
| Meses con actividad por combinación — mediana | **2 de 36** |
| % de combinaciones con actividad en ≤ 3 de los 36 meses | **66.5%** |

**Conclusión para Fase 2:** el riesgo de series ralas señalado en el plan (§4.1) se confirma con
evidencia dura, no es hipotético — **dos de cada tres combinaciones `(producto, almacén)` tienen
actividad en 3 meses o menos de los últimos 36**. Un modelo de regresión directo sobre este grano
sin las mitigaciones ya previstas en el plan fallaría de forma similar (o peor) a como falla hoy
la serie global en los SKU de alto volumen. Esto valida como **obligatorias, no opcionales**:

1. El umbral mínimo de historia (`ML_DEMANDA_MIN_MESES_VENTA`) para decidir qué combinaciones
   entran al modelo vs. a un fallback estadístico simple.
2. La evaluación seria de un **modelo de dos etapas** (clasificador de "¿hay salida este período?"
   + regresor de cantidad condicionada) — con 66.5% de combinaciones mayormente inactivas, un
   solo regresor tenderá a sub-predecir sistemáticamente cualquier salida real esporádica.

---

## 4. Verificación de paridad de filtros entrenamiento ↔ serving (demanda)

Comparación línea por línea entre el SQL de entrenamiento (`ml/src/data/make_dataset.py::fetch_sales_by_dimension`)
y el SQL de serving (`backend/app/repositories/dataset_repository.py::get_product_sales_history`,
usado por `PredictionService.predict_demand` y por la predicción de compras del mes de Bodega):

| Filtro | Entrenamiento | Serving | ¿Coincide? |
|---|---|---|---|
| Estado de documento válido | `JOIN dim_estado_documento ed ... WHERE ed.estado_documento_sk <> -1` | Idéntico (`ed.estado_documento_sk <> -1`) | ✅ |
| Centinela de producto | `fvd.producto_sk <> -1` | No aplica un filtro explícito — pero filtra por `p.codart = :prod`, un código de producto real conocido de antemano (nunca el centinela, que no tiene `codart` real de negocio) | ✅ (equivalente en la práctica) |
| Agrupación | `GROUP BY df.fecha_completa, p.codart` (serie completa, todos los productos) | `GROUP BY f.fecha_completa` (un solo producto ya filtrado) | ✅ (mismo grano fecha×producto, solo que el serving ya fija el producto) |
| Orden / muestreo | `ORDER BY df.fecha_completa` (todo el histórico) | `ORDER BY f.fecha_completa DESC LIMIT :limit_days` (los N días más recientes) | Diferencia esperada e intencional (serving trae solo la ventana reciente que necesita el modelo en producción) |

**No se encontró sesgo entrenamiento↔serving en demanda.** Ambos excluyen consistentemente
documentos no válidos y, en la práctica, nunca incluyen el centinela de producto.

---

## 5. Criterio de salida (cumplido)

- ✅ Línea base de los 6 modelos congelada (§1).
- ✅ Backtest reproducible del modelo de demanda por SKU, con script reutilizable
  (`ml/scripts/backtest_demand_por_sku.py`) y hallazgo cuantificado: el error se concentra en
  ~17 SKU de alto volumen, con `Z-9001` como outlier extremo a tratar aparte.
- ✅ Verificación de paridad de filtros de negocio entrenamiento↔serving — sin hallazgos.
- ✅ Conteo de filas por SKU/almacén — confirma que el grano `producto × almacén` decidido en
  §4.1 del plan tiene series mayoritariamente intermitentes (66.5% con actividad en ≤3 de 36
  meses), validando como obligatorias las mitigaciones ya previstas (umbral mínimo de historia,
  modelo de dos etapas a evaluar en Fase 2).

**Siguiente paso (completado el mismo día, ver §6):** Fase 1 del plan (`ml/models/registry.json`, versionado, limpieza de legacy), seguida de Fase 2 (rediseño de demanda).

---

## 6. Fase 2 — Resultado (implementada y validada, 2026-07-20)

Rediseño del modelo de demanda de serie global apilada a grano `(fecha, codart, almacén)`,
según lo decidido en §4.1 del plan y la evidencia de §3 de este reporte.

### 6.1 Cambios aplicados

- **Dataset nuevo** (`ml/src/data/make_dataset.py::fetch_demand_by_product_warehouse`): agrega
  `fact_movimientos_inventario` (salidas físicas, `es_salida`) por `(fecha, codart, nombre_almacen,
  almacen_sk)`, excluyendo centinelas y la clase `Z-999` (chatarra — el único SKU con esa clase,
  `Z-9001` "BATERIAS CHATARRAS", era el de mayor error absoluto del backtest de §2).
- **Umbral mínimo de historia** (`ML_DEMANDA_MIN_MESES_VENTA`, default 6): de las 12.653
  combinaciones `(producto, almacén)` en la ventana de 3 años, solo 3.183 (25%) tienen actividad
  en >= 6 de 36 meses y entran al modelo; el resto sigue cubierto por el pronóstico estadístico
  ya existente en `WarehouseService._forecast_estadistico`.
- **Features**: `almacen_sk` (nueva) + lags/rolling/expanding agrupados por `(producto, almacen)`
  en vez de solo `producto` (`ml/src/features/build_features.py`); `expanding_mean` funciona como
  codificación histórica de la combinación sin fuga de datos (expanding + shift(1), mismo
  principio que los cortes temporales de churn).
- **Hiperparámetros**: `hyperparameter_search=True` (revierte D-2; antes demanda era el único de
  los 3 regresores que entrenaba sin búsqueda).
- **Contrato** (`ml/contracts/models/demand.json`): v0.1.0 → v0.2.0, `plausible_range` ajustado de
  `[0, 100000]` a `[0, 5000]` (p99.9 real del nuevo grano: 130 unidades/día).
- **Serving sincronizado**: `backend/app/repositories/dataset_repository.py::get_product_sales_history`
  gana `almacen` opcional; `backend/app/ml/preprocessing.py` agrupa por `(producto, almacen)` igual
  que el entrenamiento; `backend/app/ml/forecasting.py::walk_forward_forecast` corregido para
  preservar la identidad (producto/almacén) al simular días futuros (antes ponía toda la fila en
  `0.0`, lo que habría roto `almacen_sk` en el walk-forward); `WarehouseService._forecast_ml_producto`
  y sus dos callers (`get_salidas_forecast`, `_prediccion_articulo`) ahora pasan el `almacen` ya
  disponible en el dashboard de Bodega. El endpoint legado `/demand-forecasting` (H23-7, sin
  almacén en su contrato, y confirmado sin consumidores en el frontend actual — `getDemandForecast`
  existe en `hooks/bodega.ts` pero ningún page/component lo usa) degrada a `0.0` en vez de dar una
  predicción ML, documentado como trade-off deliberado en `known_serving_mismatch` del contrato.

### 6.2 Backtest comparativo (mismo método que §2, script nuevo `ml/scripts/backtest_demand_producto_almacen.py`)

| Decil de volumen | MAE antes (global, §2) | MAE ahora (producto×almacén) | RMSE antes | RMSE ahora |
|---|---|---|---|---|
| 0 (más bajo) | 1.01 | 0.79 | 3.96 | 2.58 |
| 5 | 1.55 | 1.56 | 3.37 | 4.34 |
| **9 (más alto)** | **40.15** | **11.98** | **561.14** | **40.46** |

Mejora en (casi) todos los deciles, con la mayor ganancia exactamente donde más importaba: el
decil de mayor volumen, antes el punto débil del modelo. El R² global cae de 0.876 a 0.133 —
**esperado, no una regresión**: el R² anterior estaba inflado por unos pocos SKU de volumen
enorme (encabezados por `Z-9001`, ahora excluido) donde acertar la escala explica casi toda la
varianza aunque el error absoluto fuera gigantesco.

### 6.3 Validación end-to-end

- `python -m src.contracts.contract_validator`: los 6 contratos activos, incluido `demand` v0.2.0,
  pasan.
- `pytest` en `ml/tests/` (16 tests, incluido `test_registry.py`): verde.
- `pytest` en `backend/tests/` (170 tests): verde salvo 1 falla preexistente y no relacionada
  (`test_get_management_kpis_propaga_filtros_al_repositorio`, dependiente de la fecha del sistema,
  no toca código de este plan).
- Backend reconstruido y probado en vivo contra `bi_backend`: `GET /analytics/bodega/salidas-forecast?producto_cod=ANTI 557-012&almacen=EL REY` responde `"metodo": "ml_demand_rf"` con predicciones en rango plausible (3.5-6.3 u/día, consistente con el histórico de 5-16 u/día de esa combinación); el mismo producto sin almacén (`/demand-forecasting`, legado) degrada a `0.0` como está documentado, sin excepción no controlada.

**Siguiente paso (completado el mismo día, ver §7):** Fase 3 del plan (gating/promoción
automática, tabla `ml_model_runs`, endpoints `retrain`/`promote`/`rollback`) — el panel
MLOps del **frontend** queda pendiente (no existe ninguno hoy, ver §7.4).

---

## 7. Fase 3 — Resultado (implementada y validada, 2026-07-20)

### 7.1 Gating de campeón único

`ml/src/training/promotion.py::evaluar_y_promover` se invoca después de que `train_*` ya
entrenó y guardó (Fase 1 siempre sobrescribe el archivo estable + archiva una versión).
Compara candidato vs. campeón anterior con el `metric_gate` declarado en `registry.json`
(unifica `maximize`/`minimize`/`target` con una noción de "mejora con signo"); si rechaza,
**revierte** el archivo estable a la versión anterior copiando desde
`versions/<clave>/<version>.*` — corrige D-3 (cada reentrenamiento sobrescribía sin
comparar). Deja traza en `public.ml_model_runs` (migración Alembic `0004_ml_model_runs`,
append-only) y en `ml/REPORTE_MEJORA_MODELOS.md`.

### 7.2 Bug encontrado: el reentrenamiento nunca entrenaba nada

`TrainingService.trigger_retraining_pipeline` (antes de esta fase) ejecutaba
`python <script>.py` sobre cada archivo de `ml/src/training/` como subprocess. Ninguno de
esos módulos tiene un bloque `if __name__ == "__main__":` — solo definen funciones que
`ml/main.py` orquesta. El "pipeline" reportaba éxito en cada corrida sin entrenar
absolutamente nada. `ml/retrain_all.py` (nuevo) es el entrypoint real: importa y llama la
función `train_*` correspondiente, luego aplica el gating.

### 7.3 `docker run` vs. `docker compose run` (hallazgo de infraestructura)

Probado en vivo en este entorno (Docker Desktop / Windows): invocar
`docker compose run --rm ml ...` desde DENTRO de un contenedor (backend, vía el socket de
Docker compartido) falla con `env file .../.env not found`. Causa: Compose necesita LEER
localmente tanto el YAML (`-f`) como el `.env` que auto-carga para interpolación de
variables — ambas lecturas son 100% client-side, y el contenedor backend no tiene ninguna
ruta local que corresponda a `HOST_PROJECT_DIR` (`C:\Proyect_BI`, con backslashes de
Windows). `docker run -v "<HOST_PROJECT_DIR>\ml:/app" --network proyect_bi_default ...`
en cambio solo necesita que el DAEMON (que sí corre en el host real) resuelva el string
del bind-mount — comprobado que Docker Desktop acepta rutas estilo Windows ahí sin que el
cliente (el contenedor Linux que emite el comando) necesite verlas localmente.
`TrainingService` usa `docker run` directo contra la imagen `proyect_bi-ml` ya construida,
reenviando `PG_HOST`/`PORT`/`USER`/`DB`/`PASSWORD` como `-e` explícitos (tomados del propio
entorno del backend) en vez de depender de `env_file: .env`.

### 7.4 Validación end-to-end (corrida real, no simulada)

Vía la API HTTP real (`POST /admin/modelos/retrain`, login con el admin sembrado):
reentrenamiento de `segmentation` con gating automático, verificado con
`GET /admin/modelos/runs` (6 filas acumuladas durante las pruebas: promociones automáticas,
un rechazo forzado con `min_delta` imposible que **revirtió el `.pkl` a bytes idénticos**
al de antes del intento — mismo hash MD5 —, y una promoción manual vía `ml/promote.py`) y
`GET /admin/modelos/{clave}/versions`. Un valor con tilde ("campeón") en el texto de
`razon` generó una falsa alarma de mojibake durante la verificación — se confirmó
rigurosamente (bytes UTF-8 correctos en Postgres, en la respuesta HTTP y en el objeto
Python decodificado, `ord()` = `0xf3`) que era solo un problema de renderizado de la
terminal Windows usada para probar, no un bug real; no se tocó código por esto.

**Bug adicional encontrado (Fase 1, no exclusivo de esta fase):** la retención de
versiones en `save_artifact`/`_save_version_snapshot` (`ml/src/utils/model_export.py`)
calculaba el "stem" de cada archivo con `os.path.splitext`, que para `<version>.meta.json`
da `<version>.meta` (dos extensiones) en vez de `<version>` — duplicaba el conteo de
versiones y podía borrar un lado del par `.pkl`/`.meta.json` dejando el otro huérfano
(reproducido en vivo al forzar un rechazo). Corregido normalizando `.meta.json` como una
sola extensión antes de aplicar `splitext`.

`pytest` verde en `ml/tests/` (16) y `backend/tests/` (170, misma falla preexistente no
relacionada de siempre, dependiente de la fecha del sistema).

**Pendiente:** Vía B (tarea programada de Windows, solo documentación, decisión ya
tomada); panel MLOps del **frontend** — confirmado que hoy no existe ninguno visible (el
hook `hooks/admin.ts` existe y expone `getMLOpsStatus`/`getModelsStatus`, pero ningún
page/component lo consume, mismo patrón huérfano que se encontró con `/demand-forecasting`
en la Fase 2); Fase 5 (model cards).

## 8. Fase 4 — Resultado (revisión de los 6 modelos con buenas prácticas, 2026-07-20)

Checklist del §6 del plan aplicado a los 6 modelos. Cambios por modelo:

**Ventas y Demanda (baseline `statsmodels`, D-8 parcial):** nuevo módulo
`ml/src/utils/stats_baseline.py::fit_ols_baseline` (`smf.ols(...).fit()` sobre el MISMO
split de entrenamiento, nunca el holdout) + `guardar_diagnostico_ols` (escribe el
`summary()` completo a `ml/models/diagnostics/<clave>_ols_baseline.txt`, referenciado desde
el `.meta.json` en `statsmodels_baseline.summary_path`). Corrida real (2026-07-20):

- **Ventas:** RF (500 árboles) R²=0.2907, WAPE=0.287 vs. **OLS R²_ajustado=0.3126**
  (F_pvalue=6.9e-52, significativo). El OLS iguala o supera ligeramente al RF —señal de
  alerta explícita del plan ("un modelo ML que no supere claramente al OLS es una señal de
  alerta")— documentada aquí para la model card (Fase 5), no resuelta en esta pasada (no
  se cambia el algoritmo ganador sin una nueva competencia formal, ver `docs/auditoria/
  22_plan_mejora_modelo_ventas.md`).
- **Demanda:** mismo baseline aplicado sobre el dataset producto×almacén de la Fase 2.

**Métrica WAPE (regresión):** agregada a `evaluate_reg` (`ml/src/training/model_selector.py`)
para ventas y demanda — MAE/R² no distinguen bien entre series de magnitudes muy distintas
(un día de USD 200 vs. USD 200.000); WAPE = Σ|error| / Σ|real| es el estándar de forecasting
de demanda para eso.

**Churn (D-7, petición explícita del usuario):** se agregó **`recency`** como 4ª feature
(`ml/src/data/make_dataset.py::fetch_churn_data` ya la calculaba sin fuga —H-05— pero nunca
se usaba para entrenar, pese a ser típicamente la señal RFM más predictiva de abandono).
`evaluate_churn_classifier` ahora devuelve matriz de confusión (TN/FP/FN/TP), precision,
recall, F1, PR-AUC (además de accuracy/ROC-AUC) y una calibración de umbral (F1 óptimo sobre
el holdout) — reportada **solo como diagnóstico**: el serving real sigue filtrando
`churn_probability` contra `settings.CHURN_UMBRAL_RIESGO_ALTO` (umbral de negocio, pregunta
distinta a la calibración estadística de F1). Contrato `churn.json` v0.1.0→v0.2.0 (agrega
`recency`); sincronizado el serving: `ChurnFeatures` (`backend/app/repositories/
prediction_repository.py`) y sus dos queries (`get_churn_features`/`_batch`) ganan
`recency = EXTRACT(DAY FROM (now() - MAX(fecha_completa)))`, `prediction_service.py` pasa la
columna nueva. Corrida real: ROC-AUC=0.7835, PR-AUC=0.9805 (fuerte desbalance de clases:
94.8%/5.2%), matriz `[[TN=1921, FP=1162],[FN=10977, TP=45455]]` con el umbral 0.5 de
`predict()`; probado en vivo contra `bi_backend` reconstruido con 3 `cliente_id` reales de
`public.cliente_lookup` (probabilidades 47.74%, 10.14%, 58.60% — el tercero cruza el umbral
de riesgo alto).

**Segmentación (estabilidad de K):** nuevo `evaluar_estabilidad_k` (barrido K=2..8: inertia +
silhouette + Davies-Bouldin) corrido antes del entrenamiento final y guardado en el sidecar
(`extra.estabilidad_k`) — evidencia de que K=4 no es arbitrario (K=4 no es el silhouette más
alto en términos absolutos —K=2 lo es, esperable porque separa en solo 2 grupos muy amplios—
pero sí el mejor Davies-Bouldin de K>=3, y K=4 sigue siendo la decisión de negocio: 4
segmentos accionables para Ventas). `perfil_clusters` (centroides RFM reales por segmento) y
`davies_bouldin` se agregan al sidecar. Corrida real: silhouette=0.6081,
davies_bouldin=0.4818, mapeo `{Campeones, Leales, En Riesgo, Perdidos}`.

**Anomalías (criterio de `contamination`):** nuevo `estimar_contamination_iqr` — regla IQR
clásica sobre `margen` (mismo criterio que `IQRGoalCalculationEngine` usa para metas),
acotada a `[0.005, 0.05]`, reemplaza el valor fijo `0.01` sin evidencia. Corrida real: tasa de
outliers IQR observada=5.71% → `contamination=0.05` (tope del rango); documentado en el
sidecar (`extra.criterio_contamination`). No se consiguió un conjunto etiquetado manualmente
de fraude/error real para validar precisión contra ground truth (limitación conocida del
no-supervisado, ya señalada en la línea base §1 — no resuelta en esta pasada).

**Asociación / Recomendación (D-3 real, no solo "formalizar"):** se encontró que
`train_recommendations` (`ml/main.py`) entrenaba **co-ocurrencia** (`min_support=0.005`, sin
ventana) — un algoritmo DISTINTO al ganador documentado y realmente publicado
(**item-item**, ventana 2 años, vía un script aparte `ml/notebooks/
publicar_ganador_cross_selling.py`). Como `train_recommendations` es la función que invoca el
reentrenamiento automático (`ml/retrain_all.py::ENTRENADORES`, Fase 3), un reentrenamiento
real de `association` habría intentado sobrescribir el artefacto ganador con uno peor — el
daño quedaba neutralizado *por accidente* solo porque `metrics` nunca incluía
`precision_at_5` y `promotion.py::evaluar_gate` rechaza por seguridad cualquier candidato sin
la métrica del `metric_gate` (nunca promovía, pero tampoco medía nada real). Corregido:
`train_recommendations` ahora entrena item-item (`construir_item_item`, ventana 2 años,
top-20 vecinos) igual que el ganador, corre el mismo backtest temporal (`split_temporal` +
`construir_canastas` + `evaluar_estrategia`) para poblar `precision_at_5`/`recall_at_5`/
`hit_rate_5`/`cobertura` reales, y entrena el artefacto de producción final sobre toda la
ventana (sin holdout, igual que documenta `recommendation.json`). Corrida real (reentrenamiento
completo vía `retrain_all.py --model association`): precision_at_5=0.0767 (vs. 0.0769 del
campeón anterior, dentro del `min_delta=-0.005` del gate) — **PROMUEVE**, resultado
consistente con el backtest original de Fase 3 del módulo de venta cruzada.

**Validación end-to-end (2026-07-20):** reconstruida la imagen `ml` (agrega `statsmodels` a
`ml/requirements.txt`); corrido `python retrain_all.py --model all` (contenedor `ml` efímero,
mismo patrón `docker run` de la Fase 3) — **6/6 modelos promovidos**, ninguno rechazado.
`pytest` verde en `ml/tests/` (16) tras el reentrenamiento (el test de contrato para churn
fallaba antes de reentrenar porque el `.pkl` en disco aún no tenía `recency`, esperado en un
flujo contrato-primero). `python -m src.contracts.contract_validator` limpio (6/6 activos).
Backend reconstruido/reiniciado: `GET /health` → `modelos_ml_listos: true`, sin
WARNING/ERROR de carga; `GET /analytics/ventas/churn-risk` probado con 3 `cliente_id` reales
del EDW, inferencia con la feature `recency` nueva funcionando end-to-end. `pytest` en
`backend/tests/` (169 passed, 1 falla preexistente no relacionada — `test_get_management_kpis_
propaga_filtros_al_repositorio`, dependiente de la fecha del sistema, confirmada sin relación
con estos cambios).

**Pendiente:** Fase 3b (panel MLOps del frontend), Vía B (documentación de tarea programada
de Windows), Fase 5 (`ml/model_cards/*.md` + generador + índice) — no implementadas en esta
fase.
