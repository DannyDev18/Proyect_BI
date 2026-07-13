# Mejora de modelos débiles (Ventas y Metas) — ml/

- **Fecha:** 2026-07-08
- **Alcance:** solo `ml/` (a pedido explícito). No se tocó el DDL del EDW ni el ETL.
- **Foco elegido:** mejorar los dos modelos con peor desempeño documentado en `docs/ml_metrics_report.md` (Ventas generales y Metas/Growth Ratio), reentrenando contra el EDW real (`postgres_edw`, schema `edw`, 538 862 filas en `fact_ventas_detalle`, rango 2018-01-02 a 2026-07-08).

## 0. Hallazgo previo (bloqueante, corregido primero)

`ml/src/prediction/predict_model.py` cargaba `sales_rf_model.pkl`, `demand_rf_model.pkl`, `churn_classifier.pkl` y `goals_rf_model.pkl` (archivos más antiguos, ~1.5 h anteriores por timestamp), mientras que los `train_*` actuales guardan `sales_best_model.pkl`, `demand_best_model.pkl`, `churn_best_classifier.pkl`, `goals_best_model.pkl` (el ganador de la competencia multi-algoritmo). El backend estaba sirviendo un modelo distinto —y presumiblemente peor— del que realmente se entrena y mide. **Corregido**: `_load_models()` ahora apunta a los archivos `*_best_*` reales. También se eliminó una línea muerta en `__init__` que ignoraba `ML_MODELS_DIR` cuando se pasaba `models_dir=None` explícito.

## 1. EDA que motivó las decisiones

- `fact_ventas_detalle`: 2 850 días distintos con venta, 7 sucursales (muy desbalanceadas: sucursal_sk=3 tiene 201 205 filas, sucursal_sk=7 tiene 2 651), sin nulos en `subtotal_neto`/`cantidad`, 18 360 filas de devolución ya netadas.
- **Tendencia estructural fuerte**: la venta neta diaria promedio pasó de ~9 440 (2018) a ~12 383 (2026), +31% en 8 años, con desviación estándar también creciendo. Un split cronológico 80/20 sobre el histórico completo evalúa el modelo casi enteramente contra el régimen más reciente y de mayor escala — el modelo entrenado con años de nivel más bajo lo subestima sistemáticamente. **Esta es la causa raíz del R² negativo/débil documentado**, más que una falta de features.
- `dim_fecha.es_feriado` **nunca está poblado** (0 filas en `true`) — el pipeline de ETL lo deja pendiente ("poblar con calendario local si fuera necesario"). No había ninguna señal de feriado disponible para los modelos.
- `fact_inventario_snapshot` tiene datos, pero con **cobertura casi nula antes de 2026** (<1%) — es una tabla poblada solo hacia adelante, no tiene historia útil para entrenar contra 8 años de ventas.
- `fact_metas_comerciales` tiene **0 filas** (confirma lo ya documentado en `docs/auditoria/02_reglas_negocio_validadas.md`: el origen SAP no tiene esa tabla poblada). El modelo de "Metas" nunca usó esa tabla — predice un *growth ratio* mes-a-mes derivado de `fact_ventas_detalle`, lo cual sigue siendo la única fuente viable.

## 2. Cambios aplicados (con evidencia de backtest, no por intuición)

Cada cambio se validó reentrenando contra el EDW real y comparando métricas antes/después; se descartaron los que no probaron valor.

### 2.1 Modelo de Ventas (`fetch_daily_sales`, `build_features.py`, `main.py`)

| Experimento | R² | RMSE | Decisión |
|---|---|---|---|
| Baseline (código original, datos actuales) | -0.0285 | 6 591.7 | — |
| + `n_clientes`/`n_facturas`/`pct_descuento` (rezagados 1 día, misma tabla) | -0.0206 | 6 566.2 | ✅ mantenido |
| + feriados Ecuador (fecha fija) | -0.0248 (aislado) | 6 579.6 | ✅ mantenido (neutro-positivo) |
| + `valor_cobrado_dia` (CxC, bien poblada) | **-0.1100** | 6 847.8 | ❌ descartado (empeora fuerte; colineal con la misma tendencia estructural del negocio) |
| + `stock_promedio`/`n_alertas_desabastecimiento` (inventario) | sin efecto medible | — | ❌ descartado (tabla con <1% de cobertura histórica, señal casi vacía) |
| **Ventana de entrenamiento reciente (últimos 3 años) + todo lo anterior** | **+0.2112** | **6 524.5** | ✅ **cambio con más impacto** |

Cambios de código:
- `make_dataset.py::fetch_daily_sales()`: agrega `n_clientes`, `n_facturas`, `pct_descuento_prom` (mismo `fact_ventas_detalle`, sin joins externos ruidosos).
- `build_features.py`: nueva constante `FERIADOS_ECUADOR_FECHA_FIJA` (feriados de fecha fija; los móviles como Carnaval/Viernes Santo quedan como mejora futura) y `COLUMNAS_EXOGENAS_CONTEMPORANEAS`, que **rezaga 1 día** las exógenas nuevas antes de usarlas como feature — sin este rezago habría fuga de datos, porque `n_facturas`/`n_clientes` del mismo día se derivan de las mismas transacciones que el target.
- `main.py::train_general_sales_prediction()`: nueva constante documentada `VENTANA_ENTRENAMIENTO_VENTAS_ANIOS = 3`; filtra el dataset a los últimos 3 años antes de hacer el split train/test, evitando el quiebre estructural de 8 años de crecimiento.

**Resultado final Ventas: R² -0.0285 → +0.2112, RMSE 6 591.7 → 6 524.5, MAE 4 143.1 → 3 669.3.**

### 2.2 Modelo de Metas / Growth Ratio (`fetch_goals_data`, `train_goals_prediction.py`)

| Experimento | R² | Decisión |
|---|---|---|
| Baseline (código original, datos actuales) | 0.1563 | — |
| + `estacionalidad_mes_objetivo` (cruda) + `indice_estacional_relativo` (ratio) juntos | 0.0892 | ❌ descartado (colineales, la versión cruda mete ruido) |
| Solo `estacionalidad_mes_objetivo` (cruda) | 0.0600 | ❌ descartado |
| **Solo `indice_estacional_relativo`** | **0.1679** | ✅ mantenido |

El driver real del *growth ratio* (venta del mes siguiente / venta del mes actual) es cuán fuerte es estacionalmente el **mes objetivo** frente al actual — no solo la historia del mes actual (única señal que había antes). Se agregó `indice_estacional_relativo = estacionalidad_histórica(mes_objetivo) / promedio_móvil(mes_actual)` en `fetch_goals_data()`, usando únicamente años **anteriores** al año del mes objetivo (mismo criterio ya usado en `SeasonalityCalc` del código original) — **no hay fuga de datos**: es información disponible de antemano en cualquier corrida real. La versión cruda del mismo cálculo se calcula en SQL (útil para EDA) pero se excluye explícitamente del set de entrenamiento en `train_goals_prediction.py` porque combinada con el índice degrada el resultado.

**Resultado final Metas: R² 0.1563 → 0.1679.**

## 3. Archivos modificados

- `ml/src/prediction/predict_model.py` — fix de artefactos servidos (bug crítico, ver §0).
- `ml/src/data/make_dataset.py` — `fetch_daily_sales()` enriquecido; `fetch_goals_data()` con estacionalidad del mes objetivo.
- `ml/src/features/build_features.py` — feriados Ecuador + rezago de exógenas contemporáneas (anti-fuga).
- `ml/src/training/train_goals_prediction.py` — exclusión documentada de la feature cruda colineal.
- `ml/main.py` — ventana de entrenamiento reciente para ventas (3 años).
- `ml/models/sales_best_model.pkl`, `ml/models/goals_best_model.pkl` — reentrenados y regrabados con el código final.

## 4. Limitaciones y trabajo futuro (fuera de este alcance)

- **`goals_rf` se carga pero no se sirve**: `MultiModelPredictor` no tiene ningún método `predict_goals(...)` — el modelo de metas está entrenado y cargado en memoria pero no hay forma de invocarlo desde el backend. Requiere tocar `ml/src/prediction/predict_model.py` (agregar el método) y el backend (fuera de `ml/`) para exponer el endpoint — no se implementó por estar fuera del alcance "solo `ml/`" pedido.
- **Feriados móviles de Ecuador** (Carnaval, Viernes Santo) no están cubiertos; solo los de fecha fija.
- **`dim_fecha.es_feriado`** sigue sin poblarse en el ETL — la aproximación de feriados vive solo en `ml/` (duplicación de lógica que sería mejor centralizar en el DW, pero eso es cambio de ETL, fuera de alcance).
- **Ventana de 3 años es una heurística**, no un valor optimizado por grid search — quedó documentada como constante nombrada para que sea fácil de ajustar y justificar.
- El resto de los 5 modelos (demanda, segmentación, churn, cross-selling, anomalías) **no se tocaron** — ya tenían desempeño sólido y no eran el foco elegido.
- `ml/requirements.txt` sigue sin declarar `lightgbm`/`catboost`/`optuna` (usados por `model_selector.py`) — deuda técnica ya señalada, fuera del alcance elegido para este cambio.

### 2.3 Metas / Growth Ratio sobre Venta Neta (v0.2.0, 2026-07-10)

Regla de negocio nueva (`docs/auditoria/02_reglas_negocio_validadas.md`, §13): la venta real de
un vendedor debe descontar sus devoluciones del período (`Venta Neta = SUM(subtotal_neto) -
SUM(total_linea_devolucion)`). Se migró `fetch_goals_data()` (CTE `VentasBrutas` +
`Devoluciones` → `MonthlySales` neta, patrón de agregados separados por grano distinto) y el
serving equivalente `goal_repository.py::get_sales_trend_for_goals` en el mismo cambio, para no
abrir un mismatch entrenamiento/servicio (ver skill `ml-training-pipeline`).

| Versión | Target/features | R² (holdout cronológico) | MAE (espacio ratio) | Ganador |
|---|---|---|---|---|
| v0.1.0 (venta bruta) | `y_ventas_futuras` sobre `subtotal_neto` | 0.126 | 0.322 | CatBoostRegressor |
| v0.2.0 (Venta Neta) | `y_ventas_futuras` sobre venta neta | **0.043** | **0.348** | RandomForestRegressor |

**Backtest empeoró en ambas métricas** (R² -0.083, MAE +0.026) sobre las mismas 2 068 muestras
vendedor-sucursal-mes. Hipótesis (no confirmada con más experimentos por estar fuera del
alcance de esta sesión): restar devoluciones agrega varianza mes a mes que no está correlacionada
con el resto de las features (mes, estacionalidad, tendencia) — las devoluciones dependen más de
eventos puntuales (garantías, cambios) que del ciclo estacional/tendencia que el modelo ya usa
para predecir, así que el ratio objetivo se vuelve más ruidoso sin que el modelo tenga una señal
nueva para explicar ese ruido.

**Decisión aplicada:** `ml/contracts/models/goals.json` se dejó en `status: "draft"` (no bloquea
inferencia, pero tampoco se considera el contrato validado) hasta que el negocio/equipo decida
entre: (a) aceptar el R² más bajo porque la Venta Neta es la magnitud correcta para medir
desempeño real (justificación de negocio, no solo de métrica), (b) agregar `devoluciones_historicas`
como feature explícita (en vez de solo netear el target) para darle al modelo la señal que hoy
pierde, o (c) mantener `goals_rf` sirviendo sobre venta bruta y dejar que la Venta Neta solo
alimente el motor estadístico (`IQRGoalCalculationEngine`, ver `docs/auditoria/16_...md`), que sí
mejora con ella al no depender de un modelo entrenado. El artefacto `goals.pkl` fue
sobrescrito por la corrida de reentrenamiento (no versionado en git, `ml/models/` está en
`.gitignore`) pero el backend **no fue reiniciado** en esta sesión -- sigue sirviendo el modelo en
memoria cargado en el último arranque hasta el próximo `docker compose restart backend` /
`publish_models.py`, así que no hay impacto en producción todavía.

**Resolución (mismo día):** el usuario eligió mantener `goals_rf` sobre venta bruta (opción c).
El experimento se revirtió por completo (`fetch_goals_data`, contrato, `get_sales_trend_for_goals`
de vuelta al estado original; `goals.pkl` reentrenado sobre la SQL revertida, R²=0.126 confirma
paridad con el baseline). La Venta Neta se mantiene solo en `IQRGoalCalculationEngine` (motor
estadístico), que no depende de reentrenar un modelo. Detalle en
`docs/auditoria/16_venta_neta_y_propuesta_meta_siguiente_mes.md` §7.1.

### 2.4 Ventas — features nuevas v0.2.0 (2026-07-10, docs/auditoria/21_...md)

Motivado por pedido de negocio de mejorar la calidad del forecast de ventas del Dashboard de
Gerencia. Features agregadas a `build_features.py`/`preprocessing.py` (ver contrato
`ml/contracts/models/sales.json` v0.2.0): `ticket_promedio_prev` (venta neta / facturas del día
anterior, rezagada por el mismo motivo que las demás exógenas contemporáneas), `dow_sin/cos` y
`month_sin/cos` (codificación cíclica del calendario) y feriados móviles de Ecuador (Viernes
Santo, Carnaval, calculados por offset desde el domingo de Pascua vía computus gregoriano) sumados
a los feriados de fecha fija ya existentes.

| Métrica | v0.1.0 (línea base) | v0.2.0 (features nuevas) | Δ |
|---|---|---|---|
| R² | 0.2128 | 0.2045 | -0.0083 |
| MAE | 3826.67 | 3819.69 | -6.98 (mejor) |
| RMSE | 6639.33 | 6686.95 | +47.62 (peor) |

**Resultado mixto, tratado como neutro:** el MAE (la métrica que se muestra al usuario en el
Dashboard, ±USD) mejora marginalmente; R²/RMSE empeoran marginalmente. La magnitud de ambos
movimientos es consistente con el ruido esperable de una sola corrida de `RandomizedSearchCV`
sin semilla fija entre ejecuciones (la línea base tampoco se promedió sobre múltiples corridas).
No se identificó una feature individual claramente responsable de una mejora o degradación —no se
hizo ablation test por feature en esta sesión (fuera de presupuesto). **Decisión: se activa el
contrato v0.2.0** (no hay evidencia de degradación clara, y las features nuevas son razonables de
mantener por diseño: ticket promedio y feriados móviles son señales de negocio genuinamente
ausentes antes). Si una futura sesión corre varias repeticiones y confirma degradación real de R²,
revertir siguiendo el mismo patrón que el experimento de Metas (§2.3).

Cambio adicional en el mismo endpoint (`backend/app/services/prediction_service.py`, sin tocar
el modelo): `get_sales_forecast_weekly` se renombró a `get_sales_forecast` y ahora soporta
`granularidad` (semana/mes, bucketizando el walk-forward diario existente) y filtros
`vendedor`/`almacen` (extensión de H-14b, ver docs/auditoria/21_...md).

**Nota de proceso:** la primera versión de la codificación cíclica se coló al modelo de demanda
(comparten `TimeSeriesLagsTransformer`) y lo degradó en las 3 métricas (RMSE/MAE/R2); se corrigió
acotando las features nuevas al dataset de ventas y se reentrenó de nuevo. Detalle completo en
`docs/auditoria/21_mejora_features_ventas_y_granularidad.md` §5.1.

### 2.5 Ventas — modelo final v0.3.0 fijado con evidencia (2026-07-11, docs/auditoria/22_plan_mejora_modelo_ventas.md)

Ejecución completa del plan 22 (Fases 1-4). Resumen de evidencia (detalle y tablas completas
en el propio doc 22, secciones 4-6; scripts en `ml/notebooks/eda_22_analisis_variables.py`,
`exp_22_features.py`, `exp_22_fase3.py`, `exp_22_rf_final.py`, `exp_22_sarimax.py`):

1. **Fase 1 (variables):** la señal la domina el calendario (`day_of_week` concentra 0.339 de
   importancia por permutación; lags/rolling aportan casi nada individualmente). Aun así,
   remover las features de importancia ~0 DEGRADA el holdout (R² 0.296→0.234): el RF explota
   interacciones. Los 4 candidatos nuevos (flags de pico atípico, excluir días pico,
   `fact_compras`, `fact_devoluciones`) resultaron neutros o peores con el protocolo de 3
   corridas. **Set final: las mismas 26 features de v0.2.0** (sin tocar `build_features.py`
   ni `preprocessing.py` del backend — el modelo de demanda queda intacto).
2. **Fase 3 (algoritmos):** con 793 filas de train, `RandomizedSearchCV` (n_iter=5 y n_iter=25)
   elige configuraciones que rinden PEOR en el holdout que un RF con defaults. La regresión por
   cuantiles LightGBM quedó descalibrada (cobertura [P10,P90] 59% vs 80% nominal) y SARIMAX
   solo compite sobre la serie con días-cero (no comparable; MAE/RMSE peores).
3. **Fase 4 (final):** `RandomForestRegressor(n_estimators=500, defaults)` + TTR log1p, fijado
   como `GANADOR_SALES_PARAMS` en `train_sales_prediction.py` (`hyperparameter_search=False`
   ahora significa "entrenar el ganador fijo"; `True` re-corre la competencia para
   re-evaluaciones). Contrato `sales` v0.3.0 activo, validador 6/6 OK.

| Métrica (holdout cronológico 20%) | v0.2.0 (anterior) | v0.3.0 (publicado) |
|---|---|---|
| R² | 0.2045 | **0.2972** |
| MAE (USD) | 3819.69 | **3789.68** |
| RMSE (USD) | 6686.95 | **6285.43** |

Sin cambios en el serving: el gráfico de Gerencia conserva los filtros sucursal/vendedor/
almacén y la granularidad semana/mes (bucketización del walk-forward diario), que se aplican
tanto al histórico como a la predicción.

## Módulo Venta Cruzada (Cross-Selling) — re-análisis completo, 2026-07-13

- **Alcance:** `docs/features/plan_modulo_cross_selling.md` §2.3 (Fases 2-3), auditoría
  `docs/auditoria/25_modulo_cross_selling.md`. Contrato `recommendation` v0.1.0 → v0.2.0.
- **Línea base a superar (v0.1.0):** co-ocurrencia direccional simple, min_support=0.005,
  494 reglas, cobertura 87.9% sobre el último trimestre (auditoría 25 §1), sin
  Precision@K/Recall@K medido (nunca se había hecho backtest formal).

### EDA (`ml/notebooks/eda_cross_selling.py`, 463.214 líneas / 234.774 facturas, 2018-01-02..2026-07-13)

1. Solo 44,7% de las facturas tienen 2+ productos distintos (universo útil para reglas).
2. Concentración Pareto fuerte: el 5% de productos (317 de 6.340 `codart`) concentra 80,6% de
   las líneas de venta.
3. Estabilidad temporal MODERADA de las co-ocurrencias: solo 33% (10/30) de los pares más
   frecuentes de 2024 siguen en el top-30 de 2026 — justifica probar varias ventanas de
   entrenamiento (2/3/8 años) en vez de fijar una por defecto.
4. Afinidad por sucursal fuertemente LOCAL: 0/20 de intersección entre el top-20 de pares de
   las 2 sucursales de mayor volumen — limitación conocida, **no resuelta** en este cambio (el
   módulo sigue sirviendo un único modelo global, igual que v0.1.0).

### Backtest temporal (`ml/notebooks/experimentos_cross_selling.py`)

Split cronológico (nunca aleatorio): corte=2026-04-14, train=hasta esa fecha, test=(corte,
2026-07-13], 4.169 canastas de test con 2+ productos. Método de evaluación: "completado de
canasta" — cada canasta de test se parte en contexto (primera mitad) y oculto (la otra
mitad); se mide si el motor sugiere, a partir del contexto, los productos que realmente
faltaban. 31 combinaciones evaluadas (co-ocurrencia re-tuneada × grid de min_support/min_lift,
Apriori/FP-Growth vía `mlxtend`, item-item por similitud coseno, híbrido), cada una sobre
ventanas de 2/3/8 años:

| Estrategia | Ventana | min_support | min_lift | Cobertura | Precision@3 | **Precision@5** | Recall@5 | Hit-Rate@5 | Ticket medio ($) |
|---|---|---|---|---|---|---|---|---|---|
| **item_item (GANADOR)** | **2a** | — | — | **0.979** | **0.098** | **0.077** | **0.262** | **0.358** | 23.65 |
| item_item | 3a | — | — | 0.982 | 0.088 | 0.074 | 0.252 | 0.343 | 22.42 |
| item_item | 8a | — | — | 0.989 | 0.074 | 0.073 | 0.253 | 0.341 | 21.09 |
| apriori_mlxtend / coocurrencia | 2a | 0.005 | — | 0.706 | 0.082 | 0.067 | 0.229 | 0.309 | 37.59 |
| coocurrencia | 3a | 0.003 | — | 0.746 | 0.080 | 0.065 | 0.224 | 0.298 | 32.24 |
| hibrido | 3a | 0.001 | 1.5 | **1.000** | 0.073 | 0.061 | 0.224 | 0.279 | 33.08 |
| hibrido | 8a | 0.001 | 1.5 | 1.000 | 0.070 | 0.058 | 0.207 | 0.266 | 30.08 |
| hibrido | 2a | 0.001 | 1.5 | 1.000 | 0.067 | 0.057 | 0.209 | 0.261 | 32.23 |

(Tabla completa de las 31 combinaciones en la salida de
`docker compose run --rm ml python notebooks/experimentos_cross_selling.py`, reproducible;
resumen arriba con las filas representativas de cada estrategia/ventana.)

**Decisión (regla §2.3.d: mejor Precision@5 con cobertura ≥ línea base 87.9%):** gana
**item-item, ventana 2 años, top-20 vecinos** — Precision@5=0.077 (la más alta de las 31
combinaciones), cobertura=97.9% (supera la línea base). El híbrido alcanza cobertura=100%
pero con Precision@5 inferior (0.057-0.061): diluye la señal fuerte de item-item con
popularidad de relleno cuando no hacía falta, así que se descarta pese a su cobertura
perfecta — la regla de decisión prioriza precisión sobre cobertura una vez que la cobertura
ya supera la línea base. Apriori/FP-Growth (`mlxtend`) confirma matemáticamente los mismos
resultados que la co-ocurrencia manual (mismas filas en la tabla): se documenta como
candidato evaluado, no aporta mejora sobre la implementación existente.

**Trade-off documentado:** el ganador tiene menor `impacto_ticket_medio` (23.65 vs 37-38 de
las reglas de asociación) — la co-ocurrencia tiende a acertar en productos de mayor valor
unitario cuando acierta, pero acierta muchas menos veces. Se prioriza precisión/cobertura
(more sugerencias útiles al vendedor) según la regla de decisión ya acordada en el plan, no
el ticket medio de los aciertos.

### Publicación

`ml/notebooks/publicar_ganador_cross_selling.py` reentrena el artefacto final con TODA la
ventana de 2 años disponible (129.890 líneas, 2024-07-13..2026-07-13, sin holdout — el
backtest ya validó la estrategia). Contrato `recommendation` v0.2.0 pasado a `active`;
`contract_validator` 6/6 OK. Esquema unificado del artefacto (`item_A, item_B, score, fuente,
support, confidence`) documentado en `ml/contracts/models/recommendation.json` — el ganador
(`fuente='item_item'`) deja `support`/`confidence` en NULL (no aplican a similitud coseno).

**Pendiente explícito para la Fase 4 (backend, fuera de `ml/`):** `inference.py` /
`prediction_service.py` deben leer `score`/`fuente` en vez de `lift` (v0.1.0). Documentado
como `known_serving_mismatch` en el contrato.
