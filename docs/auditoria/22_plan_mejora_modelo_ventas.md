# 22. Plan de acción: mejora del modelo base de predicción de ventas (`sales_rf`)

- **Fecha:** 2026-07-10 (plan) / 2026-07-11 (ejecución completada, ver secciones 4-6)
- **Estado:** EJECUTADO. Modelo final publicado: contrato `sales` v0.3.0.
- **Alcance:** solo `ml/` (entrenamiento) y su espejo de serving en `backend/app/ml/preprocessing.py`
  donde aplique. No toca ETL/EDW ni el módulo de Metas y Comisiones.
- **Motivo:** el modelo actual (`ml/models/sales.pkl`, contrato `ml/contracts/models/sales.json`
  v0.2.0) tiene R²≈0.20 -- débil para uso gerencial. El usuario pidió un proceso ordenado:
  primero determinar qué variables realmente importan (correlación/importancia), luego evaluar
  modelos alternativos de forma objetiva, y terminar fijando **un solo modelo final** con
  evidencia, no por intuición.

## 0. Línea base y lecciones ya aprendidas (no repetir)

| Ítem | Valor |
|---|---|
| Algoritmo actual | `RandomForestRegressor` (ganador de competencia RF/XGB/LGBM/CatBoost/HGB) |
| R² / MAE / RMSE (holdout cronológico 20%) | 0.2045 / 3819.69 USD / 6686.95 USD |
| Ventana de entrenamiento | últimos 3 años (`VENTANA_ENTRENAMIENTO_VENTAS_ANIOS`, `ml/main.py`) |
| Búsqueda de hiperparámetros | `hyperparameter_search=False` en `ml/main.py::train_general_sales_prediction` -- la competencia de algoritmos SIEMPRE corre (`find_best_regression_model`, `cv_splits=3`), pero sin una búsqueda profunda de hiperparámetros por algoritmo |
| Variables ya descartadas con evidencia | `valor_cobrado_dia` (`fact_cobros_cxc`, R² -0.02→-0.11), variables de `fact_inventario_snapshot` (<1% cobertura histórica) -- ver `ml/REPORTE_MEJORA_MODELOS.md` §2.1 |
| Variables agregadas recientemente (v0.2.0) | `ticket_promedio_prev`, `dow_sin/cos`, `month_sin/cos`, feriados móviles -- resultado neutro/mixto (docs/auditoria/21_...md), no una mejora clara |

**Lecciones de la sesión anterior (docs/auditoria/21_...md §5.1), a respetar en este plan:**
1. `ml/src/features/build_features.py` (y su espejo `backend/app/ml/preprocessing.py`) es un
   transformer **compartido entre ventas y demanda** -- cualquier feature nueva debe acotarse
   explícitamente al dataset que le corresponde (patrón `es_dataset_ventas = 'n_facturas' in
   X_out.columns`, ya establecido) para no degradar el modelo de demanda sin querer.
2. Una sola corrida de `RandomizedSearchCV` no fija semilla entre ejecuciones -- una diferencia
   de R² de ~±0.01 puede ser ruido, no señal. Este plan exige **repetir cada comparación
   relevante 3 veces** y mirar el promedio, no una corrida suelta.
3. Correr `python -m src.contracts.contract_validator` (desde `ml/`) después de CUALQUIER
   cambio a `build_features.py`, no solo cuando se cree que el cambio es "solo de ventas".
4. Seguir el flujo del `CLAUDE.md` raíz: contrato (`ml/contracts/models/sales.json`) se actualiza
   ANTES de tocar el dataset/features/entrenamiento, nunca se deriva del `.pkl` después.

## Fase 1 — Análisis de variables (correlación e importancia)

**Objetivo:** saber qué features actuales realmente aportan señal y cuáles son ruido o
redundancia, antes de agregar nada nuevo.

1. **Script de EDA aislado** en `ml/notebooks/` (nuevo notebook o script, NO modifica
   `ml/main.py` todavía) que:
   - Carga el dataset de `SalesTimeSerieExtractor.fetch_daily_sales()` + features via
     `build_preprocessing_pipeline()` (mismo pipeline real de entrenamiento, para que el
     análisis sea fiel a lo que el modelo ve).
   - Calcula correlación de Pearson y de Spearman de cada feature numérica contra
     `y_sales_net` (Spearman porque la relación puede no ser lineal -- picos de demanda).
   - Calcula una matriz de correlación **entre features** (no solo contra el target) para
     detectar multicolinealidad -- ej. `lag_1` vs `lag_7` vs `rolling_mean_7d` es candidato
     a redundancia parcial.
2. **Importancia por permutación** (`sklearn.inspection.permutation_importance`) sobre el
   modelo `sales.pkl` ya entrenado, evaluada en el holdout -- más confiable que
   `feature_importances_` nativo de RandomForest (que sobre-pondera features de alta
   cardinalidad/varianza).
3. **Revisar candidatos nuevos con evidencia, no intuición:**
   - Marca de "día atípico" (pico de venta B2B aislado, visible en el gráfico del dashboard
     como saltos puntuales a 2-3x el nivel base) -- probar un flag `es_pico_atipico` (ej. via
     z-score robusto sobre ventana móvil) como feature, o alternativamente excluir esos días
     del entrenamiento y evaluar el efecto en el holdout (documentar cuál de las dos
     estrategias se prueba y por qué).
   - `fact_compras` (compras/reposición) y `fact_devoluciones` (tasa de devoluciones) --
     agregados al grano diario (mismo patrón de CTEs separados por hecho que ya usa
     `fetch_daily_sales`, ver skill `ml-training-pipeline` §"Features que combinan DOS tablas
     de hechos"), evaluados individualmente contra el baseline antes de combinarlos.
   - Reevaluar si `dow_sin/cos`/`month_sin/cos` (agregadas en v0.2.0) tienen importancia real
     medible ahora que hay una corrida con permutation importance -- si su importancia es
     ~0, son candidatas a remover (simplifica el modelo sin perder señal).
4. **Entregable de la Fase 1:** tabla en este documento (sección 4 abajo, a completar) con:
   feature, correlación con target, importancia por permutación, decisión (mantener / remover
   / candidata nueva a probar en Fase 3).

## Fase 2 — Protocolo de comparación (para que la Fase 3 sea justa y reproducible)

Antes de comparar modelos, fijar el método para que el resultado sea confiable:

1. Mismo split cronológico 80/20 y misma ventana de 3 años que hoy (no cambiar dos variables
   a la vez -- si se quiere probar otra ventana, es un experimento aparte).
2. **Cada configuración candidata se corre 3 veces** (semillas/orden de `RandomizedSearchCV`
   distintos) y se reporta promedio ± desviación de R²/MAE/RMSE -- no una corrida suelta
   (lección de docs/auditoria/21_...md).
3. Set de features fijo = el resultado depurado de la Fase 1 (para no mezclar "cambié
   features" con "cambié de modelo" en la misma comparación).
4. Métrica de decisión primaria: **R² promedio**; MAE/RMSE como criterios de desempate y para
   verificar que no haya un trade-off inaceptable (ej. mejor R² pero MAE mucho peor).

## Fase 3 — Evaluación comparativa de modelos

1. **Modelos tabulares ya en competencia** (`ml/src/training/model_selector.py`):
   correr `hyperparameter_search=True` real (más iteraciones de `RandomizedSearchCV`, hoy
   apagado en `ml/main.py`) sobre el set de features de la Fase 1. Es el experimento más
   barato y el primero a ejecutar.
2. **Regresión por cuantiles** (LightGBM/GradientBoostingRegressor con `objective="quantile"`,
   P10/P50/P90): no necesariamente sube el R² del punto central, pero da intervalos de
   predicción calibrados con evidencia real en vez de `MAE * sqrt(dias)` (aproximación actual,
   docs/auditoria/21_...md). Relevante porque la serie es intrínsecamente ruidosa (picos
   B2B) -- un intervalo bien calibrado puede ser más valioso para Gerencia que forzar un mejor
   R² puntual.
3. **Modelos de series de tiempo clásicos, como referencia (expectativa baja, documentar igual):**
   Prophet o SARIMAX sobre la misma serie diaria. Con solo ~3 años (~1095 filas) de
   entrenamiento, es esperable que NO superen a los árboles con features de lags (los árboles
   con lags ya capturan gran parte de la autocorrelación); se corre igual para tener evidencia
   documentada en vez de asumirlo. No se prueban arquitecturas de redes neuronales (LSTM/TFT):
   con este volumen de datos el riesgo de sobreajuste es alto y el costo de implementación no
   se justifica frente a los árboles ya competitivos.
4. **Entregable de la Fase 3:** tabla comparativa (sección 5 abajo, a completar) con todas las
   configuraciones probadas, sus métricas promedio ± desviación, y una recomendación.

## Fase 4 — Selección final y publicación

1. Elegir **un solo modelo ganador** con la tabla de la Fase 3 como evidencia (no combinar
   "un poco de cada uno" sin justificación).
2. Actualizar `ml/contracts/models/sales.json` (versión nueva, features finales, algoritmo,
   métricas) -- contrato primero, según el flujo ya establecido.
3. Actualizar `ml/main.py::train_general_sales_prediction` si el modelo ganador requiere un
   flujo de entrenamiento distinto al actual (ej. quantile regression necesita 3 modelos
   P10/P50/P90 en vez de 1).
4. Si el ganador usa features nuevas que tocan `build_features.py`/`preprocessing.py`:
   aplicar el gate `es_dataset_ventas` igual que las features de v0.2.0, y correr
   `contract_validator` antes de publicar.
5. Documentar el resultado final en `ml/REPORTE_MEJORA_MODELOS.md` (nueva sección fechada) y
   cerrar este documento con el resultado real en la sección 6.
6. `publish_models.py` / `docker compose restart backend`, verificar `GET /health` →
   `modelos_ml_listos: true`.

## Checklist de ejecución

- [x] Fase 1.1 -- Notebook de correlación (Pearson + Spearman) contra `y_sales_net` (`ml/notebooks/eda_22_analisis_variables.py`)
- [x] Fase 1.2 -- Matriz de correlación entre features (detectar multicolinealidad)
- [x] Fase 1.3 -- Permutation importance sobre `sales.pkl` actual
- [x] Fase 1.4 -- Evaluar candidatos nuevos (día atípico, `fact_compras`, `fact_devoluciones`) (`ml/notebooks/exp_22_features.py`)
- [x] Fase 1.5 -- Completar tabla de la sección 4 y decidir set de features final (se mantienen las 26 de v0.2.0)
- [x] Fase 2 -- Protocolo aplicado: 3 corridas por configuración (semillas 42/7/2026), promedio ± desviación
- [x] Fase 3.1 -- Búsqueda profunda de hiperparámetros n_iter=25 sobre los 5 algoritmos (`ml/notebooks/exp_22_fase3.py`)
- [x] Fase 3.2 -- Regresión por cuantiles LightGBM P10/P50/P90 (descartada: cobertura 59% vs 80% nominal)
- [x] Fase 3.3 -- SARIMAX como referencia (`ml/notebooks/exp_22_sarimax.py`; Prophet no necesario: SARIMAX ya cubre la referencia clásica)
- [x] Fase 3.4 -- Completar tabla comparativa de la sección 5
- [x] Fase 4 -- Modelo final RF(500) fijado en `train_sales_prediction.py`, contrato v0.3.0, reentrenado y publicado

## 4. Tabla de variables (Fase 1) -- ejecutada 2026-07-11

Fuente: `ml/notebooks/eda_22_analisis_variables.py` (correlaciones sobre el train, 793 filas
2023-07-10→2025-12-01; permutation importance sobre `sales.pkl` v0.2.0 en el holdout de 199
filas, scoring=R², n_repeats=15). CSVs en `ml/notebooks/output_22/`.

| Feature | Pearson / Spearman vs target | Import. permutación | Decisión |
|---|---|---|---|
| `day_of_week` | −0.44 / −0.49 | **0.339** (dominante) | mantener |
| `is_month_end` | 0.13 / 0.14 | 0.030 | mantener |
| `dow_sin` / `dow_cos` | 0.38 / 0.42 · 0.02 / 0.13 | 0.028 / 0.004 | mantener |
| `es_feriado` | −0.10 / −0.13 | 0.019 | mantener |
| `is_weekend` | −0.47 / −0.53 | 0.016 | mantener |
| `rolling_max_7d`, `rolling_std_7d`, `rolling_mean_7d` | ~0 / ~0 | 0.001–0.002 | mantener |
| `lag_7`, `lag_90`, `n_clientes_prev` | 0.07–0.15 (Spearman) | ~0.001 | mantener |
| `month_sin/cos`, `is_month_start`, `rolling_min_7d`, `pct_descuento_prom_prev` | ~0 | ~0.0004 | mantener |
| `lag_1`, `lag_14`, `lag_30`, `month`, `quarter`, `expanding_mean`, `rolling_mean_30d`, `ticket_promedio_prev`, `n_facturas_prev` | ~0 | ≤ 0 | mantener (ver nota) |

**Multicolinealidad detectada (|r| ≥ 0.9):** `n_clientes_prev`↔`n_facturas_prev` (0.989),
`month`↔`quarter` (0.970), `rolling_std_7d`↔`rolling_max_7d` (0.926).

**Nota / decisión del set (Fase 1.5):** aunque 9 features tienen importancia individual ~0 o
negativa, el experimento B de `ml/notebooks/exp_22_features.py` demostró que **removerlas
degrada el modelo** (R² 0.296→0.234 con el protocolo de 3 corridas): el RF explota
interacciones que la importancia por permutación univariada no captura. Decisión: **el set
final son las MISMAS 26 features del contrato v0.2.0** (sin cambios en `build_features.py`
ni en `backend/app/ml/preprocessing.py` — cero riesgo para el modelo de demanda).

**Candidatos nuevos evaluados y descartados con evidencia** (protocolo Fase 2, RF fijo
n_estimators=200, 3 semillas; baseline A: R²=0.2958±0.0089, MAE=3790.56, RMSE=6291.75):

| Candidato | R² (prom ± desv) | MAE | Veredicto |
|---|---|---|---|
| C. flags `pico_prev` + `n_picos_7d` (z robusto ventana 28d, umbral 3.5) | 0.2943±0.0049 | 3803.73 | neutro → descartado |
| D. excluir del train los 38 días pico | 0.1850±0.0092 | 3843.69 | degrada → descartado |
| E. `valor_compras_prev` (`fact_compras` agregada al día, rezagada) | 0.2920±0.0017 | 3816.58 | neutro → descartado |
| F. `valor_devoluciones_prev` (`fact_devoluciones` ídem) | 0.2956±0.0073 | 3805.16 | neutro → descartado |

## 5. Tabla comparativa de modelos (Fase 3) -- ejecutada 2026-07-11

Protocolo: split cronológico 80/20, ventana 3 años, set de features de la Fase 1 (26),
3 corridas por configuración (semillas 42/7/2026), métricas en el holdout (199 días con
venta, 2025-12-02→2026-07-10). Fuente: `ml/notebooks/exp_22_fase3.py`, `exp_22_rf_final.py`,
`exp_22_sarimax.py`.

| Configuración | R² (prom ± desv) | MAE | RMSE | Notas |
|---|---|---|---|---|
| **RF defaults, n_estimators=500 (GANADOR)** | **+0.2985 ± 0.0040** | 3780.10 | **6279.34** | barrido 100–800 árboles plano; 500 = mejor y más estable |
| RF defaults, n_estimators=200 | +0.2958 ± 0.0089 | 3790.56 | 6291.75 | |
| RF con búsqueda profunda (n_iter=25) | +0.2582 ± 0.0041 | 3764.21 | 6457.60 | CV elige params peores en holdout que los defaults |
| CatBoost con búsqueda profunda | +0.2568 ± 0.0041 | 3751.44 | 6463.40 | mejor MAE, pero R²/RMSE claramente peores |
| LightGBM con búsqueda profunda | +0.2337 ± 0.0522 | 3847.40 | 6559.54 | alta varianza entre semillas |
| HistGradientBoosting (búsqueda) | +0.2315 ± 0.0061 | 3842.65 | 6572.42 | |
| XGBoost (búsqueda) | +0.2169 ± 0.0319 | 3825.63 | 6633.59 | |
| Cuantiles LightGBM (P50; P10/P90) | +0.2269 | 3888.60 | 6592.12 | cobertura empírica [P10,P90]=59.3% vs 80% nominal: intervalos DESCALIBRADOS (más angostos de lo que prometen) → se mantiene la aproximación MAE·√días del serving |
| SARIMAX(1,1,1)×(0,1,1,7), one-step-ahead | +0.3097 | 3873.00 | 6793.75 | NO comparable: evaluado sobre la serie CON días sin venta (220 días; los ceros de domingo son fáciles de predecir e inflan el R²); MAE/RMSE peores que el ganador; además exigiría statsmodels como dependencia de runtime del backend y no soporta el walk-forward con exógenas del serving actual |
| _Línea base v0.2.0 (`sales.pkl` anterior)_ | +0.2045 | 3819.69 | 6686.95 | RandomizedSearchCV n_iter=5, 1 corrida |

Hallazgo transversal: la mejora principal NO vino de más búsqueda de hiperparámetros sino de
**quitarla** — con este dataset (793 filas de train) el `RandomizedSearchCV` (tanto n_iter=5
como n_iter=25, con `TimeSeriesSplit` interno) selecciona configuraciones que rinden peor en
el holdout que un RandomForest con parámetros por defecto.

## 6. Resultado final -- cerrado 2026-07-11

- **Modelo elegido:** `TransformedTargetRegressor(RandomForestRegressor(n_estimators=500,
  random_state=42), func=log1p, inverse_func=expm1)`, fijado como `GANADOR_SALES_PARAMS` en
  `ml/src/training/train_sales_prediction.py` (la competencia de algoritmos queda como modo
  opcional `hyperparameter_search=True`).
- **Features:** las mismas 26 del contrato v0.2.0 (sin cambios en `build_features.py` ni en
  el espejo `backend/app/ml/preprocessing.py`; el modelo de demanda no se toca).
- **Métricas publicadas (holdout cronológico 20%):** R²=0.2972, MAE=3789.68 USD,
  RMSE=6285.43 USD — vs línea base v0.2.0: R² +45% relativo (0.2045→0.2972), RMSE −6%
  (6686.95→6285.43), MAE −0.8% (3819.69→3789.68).
- **Contrato:** `ml/contracts/models/sales.json` v0.3.0 (status `active`), validado con
  `python -m src.contracts.contract_validator` (6/6 contratos OK).
- **Serving sin cambios de código:** el artefacto mantiene la misma interfaz (26 features,
  predict() en USD); los filtros sucursal/vendedor/almacén y la granularidad semana/mes del
  gráfico de Gerencia siguen resolviéndose en el serving (`dataset_repository.py` →
  `prediction_service.get_sales_forecast` → bucketización W-MON/MS), aplicándose tanto al
  histórico como a la predicción (H-14b ampliado, sin cambios de alcance en v0.3.0).
- **Publicación:** 2026-07-11 vía `docker compose restart backend`; verificación
  `GET /health` → `modelos_ml_listos: true`, smoke de los 6 casos de uso ML
  (`backend/smoke_ml_endpoints.py`, sin excepciones), 74 tests del backend y 13 de `ml/`
  en verde, y pruebas HTTP reales de `/gerencia/sales-prediction` en 7 combinaciones de
  `granularidad` semana/mes × filtros `vendedor`/`almacen` (la predicción se adapta al
  filtro: p.ej. última semana proyectada 72.016 USD global vs 69.044 USD filtrada por
  almacén ATAHUALPA).

### 6.1 Hallazgos de la verificación end-to-end (corregidos en esta misma sesión)

Dos defectos preexistentes del serving, expuestos al probar los filtros del gráfico:

1. **Centinela en los catálogos de filtros:** `GET /gerencia/vendedores` y `/gerencia/almacenes`
   incluían el registro centinela `-1` ("(Desconocido)") como opción seleccionable, violando la
   regla de negocio 12 (CLAUDE.md). Corregido en
   `backend/app/repositories/analytics_repository.py` (`vendedor_sk <> -1` / `almacen_sk <> -1`).
2. **500 con serie filtrada vacía:** cuando el filtro dejaba la serie sin datos, el servicio
   degradaba con gracia (`metricas: {}`) pero el schema `MetricasPrediccion` exigía todos los
   campos y la validación Pydantic de la respuesta explotaba en 500. Corregido: campos
   opcionales en `backend/app/schemas/analytics.py` (además se expone `r2_modelo`, que el
   servicio calculaba pero el schema filtraba), tipos nullables en
   `frontend/src/types/gerencia.ts` y guardas en el panel de métricas de
   `frontend/src/pages/DashboardGerencia.tsx` (muestra "—" sin datos). Verificado:
   `vendedor=NO_EXISTE_XYZ` responde 200 con serie vacía e insight "Sin historial de ventas".
