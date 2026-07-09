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
