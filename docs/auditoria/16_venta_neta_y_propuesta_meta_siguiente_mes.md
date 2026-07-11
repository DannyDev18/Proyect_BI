# 16 — Venta Neta por vendedor y propuesta inteligente de meta para el siguiente mes

- **Fecha:** 2026-07-10
- **Objetivo:** dentro del módulo de Metas y Comisiones (`docs/auditoria/14_...`, `15_...`),
  calcular la **Venta Neta** de cada vendedor (ventas - devoluciones) y usarla como base de un
  algoritmo robusto que proponga la meta comercial del mes siguiente, considerando
  estacionalidad, tendencia, variabilidad y valores atípicos.
- **Alcance:** `backend/app/repositories/goal_repository.py`,
  `backend/app/services/goal_calculation_engine.py`, `backend/app/services/goal_ml_service.py`,
  `backend/app/schemas/analytics.py`, tests unitarios de ambos.
- **Método:** revisión estática del módulo Metas existente (docs 14/15) + lectura de las skills
  de proyecto `ml-training-pipeline` y `backend-ml-serving` para respetar la frontera
  entrenamiento/serving. Sin escrituras a Producción ni al EDW; solo cambios de código y tests.
- **Estado:** ✅ Implementado.

---

## 1. Decisión de diseño: Venta Neta solo alimenta el motor estadístico, no el modelo `goals_rf`

El módulo ya tenía **dos canales de sugerencia de meta** en paralelo
(`GoalMLService.suggest_goal` → `SugerenciaMeta.meta_sugerida_ia` y `.meta_sugerida_estadistica`):

- `meta_sugerida_ia`: `GoalsService.predict_goal_amount` (modelo `goals_rf`, capping 0.8-1.2),
  con features calculadas por `GoalRepository.get_sales_trend_for_goals` sobre venta **bruta**
  (`subtotal_neto`, sin restar devoluciones) — mismas features con las que se entrenó el modelo
  (`ml/src/data/make_dataset.py::fetch_goals_data`).
- `meta_sugerida_estadistica`: `IQRGoalCalculationEngine` sobre el histórico de
  `GoalRepository.get_vendor_monthly_history`.

Se decidió aplicar la Venta Neta **solo al segundo canal** (`get_vendor_monthly_history` →
motor estadístico), sin tocar `get_sales_trend_for_goals` ni el modelo `goals_rf`. Cambiar las
features de un modelo ya entrenado sin reentrenarlo introduce sesgo entrenamiento/servicio
(train/serve skew) — exactamente el tipo de error que la skill `ml-training-pipeline` señala
como ya ocurrido en este proyecto (contratos declarativos, `known_serving_mismatch`). Reentrenar
`goals_rf` con Venta Neta como target queda fuera de este alcance (requeriría actualizar
`ml/contracts/models/goals.json`, `ml/src/data/make_dataset.py::fetch_goals_data` y
`ml/main.py::train_goals_prediction_pipeline` — flujo de la skill `ml-training-pipeline`, no
solicitado en este pedido).

## 2. Venta Neta: `GoalRepository.get_vendor_monthly_history`

```sql
Venta Neta = SUM(fact_ventas_detalle.subtotal_neto) - SUM(fact_devoluciones.total_linea_devolucion)
```

agregada por separado a grano vendedor×sucursal×mes (`fact_ventas_detalle` filtrada por
`dim_estado_documento <> -1`; `fact_devoluciones` no tiene esa columna, no aplica el filtro) y
combinada con `LEFT JOIN` + `COALESCE` — patrón de CTEs agregados obligatorio cuando se combinan
dos hechos de grano distinto (ver skill `ml-training-pipeline`, sección "Features que combinan
DOS tablas de hechos"): un `JOIN` directo entre las dos facts multiplicaría filas (fan-out).

Efecto: cualquier consumidor de `get_vendor_monthly_history` (el motor estadístico y el
detector de anomalías vía `get_vendor_transactions_history`, que usa el primer mes de este
histórico como punto de corte) ahora trabaja sobre venta neta real, no bruta.

## 3. Algoritmo de propuesta para el siguiente mes (`IQRGoalCalculationEngine`)

Se extendió el motor existente (no se reemplazó: sigue exponiendo `calcular()` con la misma
firma e interfaz `GoalCalculationStrategy`) con una descomposición estacionalidad+tendencia
sobre el histórico ya limpio de outliers (Tukey IQR, sin cambios):

| Requisito del enunciado | Cómo lo cubre el algoritmo |
|---|---|
| Meses anteriores del mismo año | `componente_tendencia`: promedio ponderado de los meses del año en curso (o, si hay <2, los últimos hasta 3 meses disponibles como "momentum" — vendedor nuevo/histórico corto) |
| Mismo mes de años anteriores | `componente_estacional`: promedio ponderado de los registros cuyo mes coincide con el mes objetivo (el siguiente al último dato) en años previos dentro de la ventana; `None` si no hay ninguno |
| Estacionalidad | `base = (componente_estacional + componente_tendencia) / 2` cuando hay señal estacional (mismo criterio 50/50 que ya usa `get_sales_trend_for_goals` para las features de `goals_rf` — consistencia de criterio entre ambos canales); si no hay señal, `base = componente_tendencia` |
| Tendencia de crecimiento/decrecimiento | `_factor_tendencia_bruto`: mediana de las razones intermensuales (`v[i+1]/v[i]`) del segmento de tendencia, acotada a `[0.85, 1.20]` (mismo espíritu que el capping 0.8-1.2 ya validado de `GoalsService`) |
| Variabilidad del desempeño histórico | `_peso_estabilidad`: atenúa el factor de tendencia hacia 1.0 según el coeficiente de variación (CV) del histórico limpio — un vendedor errático no recibe el mismo empuje de crecimiento que uno estable con la misma tendencia nominal; piso 0.3 (nunca se anula del todo) |
| Robustez a valores atípicos (outliers) | Reutiliza la limpieza IQR/Tukey existente (excluye meses fuera de `[Q1-1.5·IQR, Q3+1.5·IQR]`) antes de calcular cualquier componente — un pico puntual no contamina ni la estacionalidad ni la tendencia, sin importar en qué mes cayó |
| Poca información histórica / vendedores nuevos / meses sin ventas | Ya no se lanza `ValidationError` con 1-2 meses de histórico (antes sí); se degrada con gracia: sin resolución de cuartiles usa la serie completa, sin señal estacional usa solo tendencia, sin suficientes pares para razón intermensual el factor de tendencia queda neutro (1.0). Solo se lanza error si el histórico llega completamente vacío (nada sobre qué calcular) |

Resultado expuesto con trazabilidad completa en `ResultadoCalculoMeta` (campos nuevos:
`componente_estacional`, `componente_tendencia`, `factor_tendencia_aplicado`,
`coeficiente_variacion`) y propagado hasta la API vía `SugerenciaMeta` →
`MetaSugeridaResponse` (`GET /api/v1/analytics/ventas/goals/meta-sugerida`).

### Cambio de comportamiento documentado (rompe un test anterior a propósito)

`test_lanza_validation_error_con_menos_de_3_meses` esperaba que el motor rechazara histórico
con menos de 3 meses. Es exactamente el escenario que el enunciado pide resolver sin error
("vendedores nuevos... sin generar errores"), así que se reemplazó por
`test_vendedor_nuevo_con_pocos_meses_no_lanza_error` y `test_un_solo_mes_de_historico_no_lanza_error`,
documentando la evolución de la regla en vez de dejarla como una regresión silenciosa.

## 4. Archivos modificados

| Archivo | Cambio |
|---|---|
| `backend/app/repositories/goal_repository.py` | `get_vendor_monthly_history`: SQL con CTEs `Ventas`/`Devoluciones` agregados por separado + `LEFT JOIN`; docstring de `VendorMonthlySales` actualizado |
| `backend/app/services/goal_calculation_engine.py` | Nuevos métodos `_calcular_base_siguiente_mes`, `_factor_tendencia_bruto`, `_peso_estabilidad`, `_coeficiente_variacion`; nuevas constantes `FACTOR_TENDENCIA_MIN/MAX`, `CV_ALTO`, `PESO_ESTABILIDAD_MIN`; `ResultadoCalculoMeta` con 4 campos nuevos; guardia de longitud mínima relajada de `< 3` a `no ventana` |
| `backend/app/services/goal_ml_service.py` | `SugerenciaMeta` con los 4 campos nuevos, poblados en `suggest_goal`; docstring del módulo aclara la decisión de venta neta vs. bruta (§1) |
| `backend/app/schemas/analytics.py` | `MetaSugeridaResponse` con los 4 campos nuevos |
| `backend/tests/unit/test_goal_calculation_engine.py` | Reemplaza el test de error por 2 tests de degradación con gracia; agrega 6 tests nuevos para estacionalidad, tendencia, variabilidad y su efecto combinado en `meta_ventas_total` |

## 5. Validación

- `cd backend && python -m pytest tests/unit -q` → 58/58 passed (incluye los 20 tests de
  `test_goal_calculation_engine.py` y los de `test_goal_ml_service.py`/`test_goals_service.py`
  sin modificar, confirmando que el canal `meta_sugerida_ia`/`goals_rf` no cambió de
  comportamiento).
- `python -m py_compile` sobre los 4 archivos de producción modificados → sin errores de
  sintaxis.
- No se corrieron los tests de integración (`tests/integration/test_goal_ml_integration.py`,
  `test_goals_generation.py`) en esta sesión porque requieren el EDW real (`bi_postgres_edw`) y
  los `.pkl` publicados corriendo localmente — pendiente de correr contra el entorno Docker antes
  de publicar el cambio, siguiendo el flujo estándar del `CLAUDE.md` raíz (paso 7, "Validar").

## 6. Pendiente / fuera de este alcance

- Reentrenar `goals_rf` sobre Venta Neta (si el negocio decide que la IA también debe partir de
  venta neta) es un cambio de la capa de entrenamiento (`ml/`), no de esta sesión — seguir el
  flujo de la skill `ml-training-pipeline` (contrato primero, backtest comparativo).
- Las preguntas de negocio abiertas en `docs/requirements/preguntas_metas_comisiones.md`
  (tramos de comisión, sobrecumplimiento, transferencias a mitad de mes, tope de comisión) siguen
  sin resolver — no se asumió ninguna de ellas en este cambio.

---

## 7. Adendo (2026-07-10, mismo día): reentrenamiento de `goals_rf` sobre Venta Neta

A pedido explícito de negocio, se reentrenó `goals_rf` para que el canal de IA (`meta_sugerida_ia`)
también parta de Venta Neta, cerrando la asimetría que el §1 de este documento había dejado
deliberadamente abierta.

- `ml/src/data/make_dataset.py::fetch_goals_data()`: `MonthlySales` ahora resta devoluciones
  (CTEs `VentasBrutas` + `Devoluciones`, patrón de agregados por separado).
- `backend/app/repositories/goal_repository.py::get_sales_trend_for_goals`: mismo cambio en el
  lado de servicio (`VentaBruta` + `DevolucionMensual` → `VentaMensual` neta), para no abrir un
  mismatch entrenamiento/servicio en sentido inverso.
- `ml/contracts/models/goals.json`: versión `0.1.0` → `0.2.0`, `status: "active"` → `"draft"`
  (D-2: contrato actualizado antes de reentrenar), descripciones de features/target aclaran
  "Venta Neta" explícitamente.
- Reentrenado contra el EDW real (`docker compose run --rm ml python -c "..."`, 2 068 muestras
  vendedor-sucursal-mes 2018-2026): **R² 0.126 → 0.043, MAE 0.322 → 0.348** (ambas métricas
  empeoraron). Detalle y 3 opciones de decisión en `ml/REPORTE_MEJORA_MODELOS.md` §2.3.
- `python -m src.contracts.contract_validator` → pasa (contrato `draft` no bloquea).
- **No se reinició el backend** (`docker compose restart backend` / `publish_models.py`): el
  artefacto nuevo ya está en `ml/models/goals.pkl`, pero el backend sigue sirviendo el modelo
  cargado en su último arranque hasta que se decida publicar. `backend/tests/unit` (58/58) sigue
  en verde porque no dependen de los `.pkl` reales.

**Pendiente de decisión del usuario antes de publicar** (§2.3 de `REPORTE_MEJORA_MODELOS.md`):
aceptar el R² más bajo por corrección de negocio, agregar `devoluciones_historicas` como feature
explícita, o mantener `goals_rf` sobre venta bruta y dejar la Venta Neta solo en el motor
estadístico.

### 7.1 Decisión final del usuario (mismo día): revertir, `goals_rf` se queda en venta bruta

Presentadas las 3 opciones de `REPORTE_MEJORA_MODELOS.md` §2.3, el usuario eligió **mantener
`goals_rf` sobre venta bruta**. Se revirtió el experimento por completo:

- `ml/src/data/make_dataset.py::fetch_goals_data()` — `git checkout` a la versión original
  (`MonthlySales` sobre `subtotal_neto`, sin CTE de devoluciones).
- `ml/src/training/train_goals_prediction.py` — `contract_version` de vuelta a `"0.1.0"`.
- `ml/contracts/models/goals.json` — `git checkout` a `version: "0.1.0"`, `status: "active"`,
  descripciones originales (venta bruta).
- `backend/app/repositories/goal_repository.py::get_sales_trend_for_goals` — revertido a
  `subtotal_neto` sin CTE de devoluciones; docstring actualizado para dejar constancia de que
  se evaluó y descartó la migración a Venta Neta, con referencia a esta sección y al reporte de
  métricas (para que una futura sesión no repita el mismo experimento sin ver este resultado).
  `get_vendor_monthly_history` (motor estadístico) **no se tocó** — sigue sobre Venta Neta, que
  es el alcance que sí se mantiene de este cambio.
- Se **reentrenó `goals_rf` una vez más** sobre la SQL revertida para regenerar
  `ml/models/goals.pkl` (el archivo del experimento anterior ya lo había sobrescrito, no está
  versionado en git). Resultado: CatBoostRegressor, R²=0.126, MAE=0.322 -- coincide con las
  métricas originales documentadas (dentro de la variabilidad esperada de
  `RandomizedSearchCV`, sin semilla fija).
- `python -m src.contracts.contract_validator` → los 7 contratos `OK`, `goals` de vuelta a
  `[ACTIVE] goals (v0.1.0)`.
- `pytest tests/unit` → 58/58 passed.

**Estado final:** `goals_rf` sirve sobre venta bruta (sin cambios respecto al inicio de esta
sesión); `IQRGoalCalculationEngine` (motor estadístico, `meta_sugerida_estadistica`) sí usa
Venta Neta real, como se implementó en las secciones 1-5 de este documento. No se reinició el
backend (no hubo necesidad: el `.pkl` final es equivalente al que ya estaba en memoria).
