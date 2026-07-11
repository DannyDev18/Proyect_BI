# 20 — Decomisión de `goals_rf` y metas realistas 100% estadísticas

- **Fecha:** 2026-07-10
- **Objetivo:** el usuario detectó metas irreales para meses futuros (ej. `ALMACEN
  ATAHUALPA` con meta $110K frente a ventas recientes de $42-54K según su referencia;
  `ALMACEN IZAMBA` con meta $2,6K frente a ventas recientes de $8-15K) y pidió: (1) dejar
  de usar cualquier modelo ML para Metas y Comisiones -- solo estadística pura -- y (2)
  **eliminar por completo** el modelo `goals_rf` (entrenamiento, serving, esquemas,
  frontend, tests).
- **Alcance:** `ml/main.py`, `ml/src/training/train_goals_prediction.py` (borrado),
  `ml/src/data/make_dataset.py` (`fetch_goals_data` borrado), `ml/contracts/models/goals.json`
  (borrado), artefactos `.pkl`/`.meta.json` de metas (borrados),
  `backend/app/ml/{model_loader,inference}.py`, `backend/app/services/{goals_service,
  goal_ml_service,goal_calculation_engine}.py`, `backend/app/repositories/goal_repository.py`,
  `backend/app/schemas/{analytics,commission,goal}.py`, `backend/app/api/dependencies.py`,
  `backend/app/api/routes/sales.py`, tests unitarios/integración afectados,
  `frontend/src/{types/ventas.ts,components/goals/VendorGoalDashboard.tsx,hooks/ventas.ts,
  services/ventas.ts}`, `CLAUDE.md`, skills de proyecto (`backend-ml-serving`,
  `ml-training-pipeline`).
- **Skills usadas:** `backend-ml-serving` (deregistrar un modelo del `ModelLoader` sin
  romper los otros 6) y `ml-training-pipeline` (retirar un modelo del orquestador de
  entrenamiento sin romper el `contract_validator`).
- **Estado:** ✅ Implementado y validado en vivo contra el EDW real.

---

## 1. Decisión: `goals_rf` decomisionado, generador 100% estadístico

`goals_rf` (CatBoostRegressor, R²=0.126, MAE=0.322 en espacio ratio) ya no aportaba valor
sobre el motor estadístico (`IQRGoalCalculationEngine`), que desde la auditoría 19 es el
generador oficial de la meta persistida. Mantenerlo solo como cifra informativa
(`meta_sugerida_ia`) añadía complejidad (una segunda fuente de verdad, un segundo set de
features, un segundo canal de fallo) sin beneficio medible. Se retira por completo:

- **Entrenamiento (`ml/`):** borrados `ml/src/training/train_goals_prediction.py`,
  `ml/contracts/models/goals.json`, `ml/models/{goals.pkl,goals.meta.json,
  goals_best_model.pkl,goals_rf_model.pkl}` y su copia en `backend/ml_models/`. Se quitó
  `fetch_goals_data()` de `ml/src/data/make_dataset.py` (144 líneas de SQL que solo
  alimentaban las features de `goals_rf`) y la llamada `train_goals_prediction_pipeline`
  de `ml/main.py::run_ml_pipeline()`. `ml/src/contracts/contract_validator.py` no
  necesitó cambios: descubre contratos recorriendo el directorio, no tiene una lista
  hardcodeada de 7 modelos.
- **Serving (`backend/`):** se quitó la clave `'goals_rf': 'goals.pkl'` de `_MODEL_FILES`
  (`model_loader.py`) y la función `predict_goal_growth_ratio` de `inference.py`.
  `GoalsService.predict_goal_amount` (el capping 0.8-1.2 que consumía el modelo) se
  eliminó junto con las constantes `GROWTH_RATIO_*`/`META_VS_*`; `GoalsService` quedó
  reducido a operaciones simples sobre `metas_comerciales_operativas` (`get_periods`,
  `get_commission_tracking`, `review_goal`) y ya no depende de `ModelLoader`.
  `GoalMLService` perdió la dependencia a `GoalsService` y el método `_meta_sugerida_ia`;
  `SugerenciaMeta` ya no tiene el campo `meta_sugerida_ia`.
- **`GoalRepository.get_sales_trend_for_goals`** (144 líneas de CTEs de estacionalidad/
  tendencia que solo existían para armar las 6 features de `goals_rf`) se reemplazó por
  `get_vendors_with_recent_sales` (10 líneas): solo vendedor + unidades del mes anterior,
  lo mínimo que `GoalMLService.generate_proposals` necesita para saber a quién generarle
  una meta. `VendorSalesTrend` se reemplazó por `VendorRecentSales`.
- **Frontend:** `MetaSugerida.meta_sugerida_ia` fuera del tipo; el panel "Meta sugerida"
  del dashboard del vendedor pasó de comparar IA-vs-estadística (2 columnas) a mostrar
  solo la cifra estadística con su trazabilidad (meses de histórico, atípicos excluidos).
- **Tests:** `test_goals_generation.py` (integración, probaba `GoalsService.
  generate_proposals`, ya inexistente) se borró; `test_goal_ml_integration.py` se
  reescribió para verificar explícitamente `assert not loader.is_loaded("goals_rf")`.

## 2. Causa raíz #1 (ya identificada en auditoría 19, reconfirmada): ventana de tendencia

`_calcular_base_siguiente_mes` (motor estadístico) tenía el mismo bug de ventana que ya
se había corregido en el lado `goals_rf` de `get_sales_trend_for_goals` (auditoría 19),
pero no se había replicado aquí: la tendencia usaba "los meses del año calendario en
curso" (`r.anio == ultimo.anio`), 0 meses en enero y 11 en diciembre. Se reemplazó por
una ventana **rodante de `RECENT_TREND_MONTHS=4` meses** terminando en el último dato
disponible, consistente todo el año.

## 3. Causa raíz #2 (nueva): techo/piso de sanidad ausente

El componente estacional (histórico de años previos) podía dominar la meta sin límite si
divergía mucho de la tendencia reciente real. Se agregó `_limitar_contra_tendencia`: la
base estadística (antes de aplicar los factores de negocio de estacionalidad/presión
comercial, que sí son un ajuste deliberado de gerencia) se acota a
`[LIMITE_VS_TENDENCIA_MIN=0.7, LIMITE_VS_TENDENCIA_MAX=1.3] × componente_tendencia`.

## 4. Causa raíz #3 (nueva, la más importante): IQR sobre 24 meses mezcla regímenes distintos

Verificado contra el EDW real (`VEN17 ALMACEN IZAMBA`, histórico completo 2020-2026):
2 años de venta casi nula (2024-2025, ~$300-900/mes) seguidos de una recuperación real y
sostenida desde enero 2026 (~$2.700 → ~$9.100/mes, 6 meses seguidos). Calcular los
cuartiles de Tukey sobre los 24 meses completos calcula `Q3≈1.358`, límite superior
`≈2.795` -- **toda la recuperación de 2026 queda fuera de ese límite** y se excluye
completa como "outlier alto", dejando la meta anclada al régimen muerto ya no
representativo (`ALMACEN IZAMBA` salía en $2.618-3.708 pese a vender $8-9K/mes reales).

**Corrección:** los cuartiles de Tukey ahora se calculan solo sobre los últimos
`VENTANA_RECIENTE_OUTLIERS=12` meses (`IQRGoalCalculationEngine._indices_sin_outliers`),
no sobre los 24 meses completos. Una recuperación sostenida de varios meses define sus
propios cuartiles y ya no se autoexcluye; un pico de un solo mes dentro de esos 12 meses
se sigue detectando igual (sin cambio de comportamiento para el caso ya cubierto por
`test_pico_extraordinario_no_domina_la_meta`).

## 5. Resultado verificado en vivo (Docker, EDW real, `POST /gerencia/goals/generate`)

| Vendedor | Antes (auditoría 19) | Después (esta corrección) | Venta Neta reciente real (EDW) |
|---|---|---|---|
| `ALMACEN ATAHUALPA` (VEN13) | $105.986,93 | $110.327,22 | ~$88-98K/mes (abr-jun 2026) -- meta ya razonable, sin cambio material |
| `ALMACEN IZAMBA` (VEN17) | $2.618,06 | $5.118,07 | ~$6-9K/mes (abr-jun 2026, recuperación sostenida) |

`ALMACEN IZAMBA` mejoró significativamente (de $2.618 a $5.118) al no descartar ya su
recuperación como outlier, aunque sigue algo por debajo del promedio reciente estricto
($6-9K) -- ver limitación §6.

**Nota importante sobre la tabla de referencia del usuario:** al validar contra el EDW
(ver también auditoría 19 §1) se confirmó que los valores por vendedor de la tabla que
compartió el usuario (columnas "EL REY", "IZAMBA", "ATAHUALPA", etc.) no coinciden 1:1
con los códigos de vendedor reales del EDW en el mismo orden -- varios valores de la
tabla coinciden en monto con OTRO vendedor bajo un encabezado distinto (ej. el valor de
la columna "SALCEDO" de enero coincide exactamente con la Venta Neta real de `L.LOPEZ`
en el EDW, no con la de "Salcedo"). Es decir, `ALMACEN ATAHUALPA` (VEN13) vende
genuinamente ~$88-98K/mes en el EDW -- la cifra "$42-54K" que el usuario asoció a
"Atahualpa" probablemente corresponde a otro vendedor de su tabla. Se corrigió el
algoritmo igual (era un problema real de diseño, confirmado con `ALMACEN IZAMBA`), pero
se deja constancia de que la comparación original vendedor-por-vendedor tenía un desfase
de encabezados en el archivo de origen del usuario, no en el EDW.

## 6. Limitación conocida, no corregida en este cambio

Al generar/regenerar la meta de un mes que YA tiene datos parciales (ej. generar la meta
de julio a mitad de julio, como se hizo aquí para verificar en vivo), `get_vendor_monthly_
history` incluye ese mes parcial como si fuera "el último mes completo", lo que corre el
`mes_objetivo` calculado un mes hacia adelante y castiga la tendencia con un dato
artificialmente bajo (mes a medias). En el flujo de negocio real (`docs/modulo_metas.md`
Fase 0: gerencia genera la meta del mes siguiente entre los días 25-30 del mes anterior,
cuando ese mes aún no tiene ninguna venta) este caso no se presenta. No se corrigió aquí
para no ampliar el alcance -- queda documentado para una futura iteración si se detecta
en producción (la corrección natural sería que `GoalMLService.generate_proposals`/
`suggest_goal` acepten el período objetivo explícito y `get_vendor_monthly_history`
excluya meses `>=` ese período).

## 7. Validación

- `cd backend && python -m pytest tests/unit -q` → **74/74 passed** (se eliminaron 4 tests
  de `predict_goal_amount`/`GROWTH_RATIO` ya sin código que probar; sin tests nuevos
  rotos por el cambio de ventana de outliers).
- `npx tsc -b --noEmit` (frontend) → limpio (mismo error preexistente y ajeno,
  `DashboardGerencia.tsx:12`).
- `python -m py_compile main.py src/data/make_dataset.py` (desde `ml/`) → sin errores.
- Backend reiniciado en Docker: arranca con **6 modelos** cargados (`sales_rf, demand_rf,
  churn_rf, segmentation, association, anomaly`), sin `goals_rf` y sin warnings/errores.
- `POST /gerencia/goals/generate` (2026-07) → 9 filas (una por vendedor, sin
  duplicación), montos verificados contra la Venta Neta real reciente de cada vendedor en
  el EDW (tabla §5).

## 8. Pendiente / fuera de este alcance

- Limitación §6 (mes objetivo con datos parciales) -- documentada, no corregida.
- `ml/src/prediction/predict_model.py` (módulo legacy, ya señalado como muerto en la
  skill `backend-ml-serving` antes de esta sesión) todavía referencia `goals_rf` en su
  diccionario de archivos; no se tocó porque ya no lo importa nada activo (reemplazado
  por `ModelLoader` hace varias fases) -- limpiarlo es una tarea de limpieza de deuda
  técnica aparte, no relacionada con este cambio.
- `ml/notebooks/06-goals-prediction.ipynb` (EDA histórico) se dejó intacto -- es un
  artefacto exploratorio, no se ejecuta como parte de ningún pipeline.
