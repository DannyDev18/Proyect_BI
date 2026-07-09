# Auditoría 05 — Pipeline ML y Calidad de Datos del EDW

**Fecha:** 2026-07-08
**Alcance:** esquema `edw` (PostgreSQL en Docker, `bi_postgres_edw`), código de entrenamiento `ml/`, integración de inferencia en `backend/app/ml/`.
**Método:** exclusivamente `SELECT` sobre el EDW (la base de producción no fue tocada) + revisión estática de código.

---

## 1. Inventario del Data Warehouse

Esquema estrella con integridad referencial completa (FKs de todas las facts hacia las dims).

| Tabla | Filas | Observación |
|---|---:|---|
| `fact_ventas_detalle` | 538,862 | Tabla de hechos principal (2018-01-02 → 2026-07-08, 247,604 facturas) |
| `fact_movimientos_inventario` | 947,996 | |
| `fact_movimientos_caja` | 253,640 | |
| `fact_cobros_cxc` | 211,954 | |
| `fact_compras` | 170,201 | |
| `fact_inventario_snapshot` | 114,016 | Solo poblada "hacia adelante" (<1% histórico pre-2026) |
| `fact_pagos_cxp` | 113,682 | |
| `fact_devoluciones` | 18,360 | |
| `dim_cliente` | 73,264 | Anonimizada vía `hash_anonimo` + `public.cliente_lookup` |
| `dim_producto` | 8,142 | |
| `dim_proveedor` | 1,935 | |
| `dim_fecha` | 7,670 | `es_feriado` **nunca poblado** (workaround hardcodeado en código ML) |
| `dim_geografia` | **0** | ⚠️ Vacía — sin utilidad actual |
| `fact_metas_comerciales` | **0** | ⚠️ Vacía — las metas operan solo en `public.metas_comerciales_operativas` (9 filas) |

## 2. Hallazgos de calidad de datos (`fact_ventas_detalle`)

| # | Hallazgo | Magnitud | Impacto en ML | Severidad |
|---|---|---:|---|---|
| DQ-1 | `pct_margen = -9999.9999` (valor centinela del ETL) | 11,971 filas | Cualquier modelo que use `pct_margen` directo queda envenenado; promedio anual de margen da −190% cuando la mediana real es **+24.1%** | **Alta** |
| DQ-2 | `costo_unitario = 0` | 72,557 filas (13.5%) | `margen_bruto`/`pct_margen` no confiables en esas filas; el detector de anomalías las consume vía `costo_total` | **Alta** |
| DQ-3 | Duplicados exactos (`num_factura`+`producto_sk`+`fecha_sk`+`cantidad`+`total_linea`) | 576 grupos | Doble conteo marginal en agregados diarios (~0.1%) | Media |
| DQ-4 | `estado_factura = 'P'` en el **100%** de las filas | 538,862 | El filtro `estado_factura != 'I'` en `fetch_goals_data()` es inocuo hoy, pero el comentario de `docker-compose.yml` y el default de la columna asumen `'A'`. Regla de negocio sin documentar | Media |
| DQ-5 | `costo_unitario > precio_unitario` en ventas no-devolución | 2,821 filas | Margen negativo legítimo (¿remates?) o error de costeo — regla de negocio sin documentar | Media |
| DQ-6 | `precio_unitario = 0` | 226 filas | Posibles regalos/promociones sin documentar | Baja |
| DQ-7 | `dim_fecha.es_feriado` nunca poblado | 7,670 | Duplicación del calendario de feriados hardcodeada en `ml/` y `backend/` | Media |
| DQ-8 | Devoluciones modeladas como filas negativas (`es_devolucion=true`, cantidad ≤ 0, 18,360 filas) y además en `fact_devoluciones` | — | Correcto para venta neta; hay que excluirlas explícitamente en market-basket y RFM | Info |

**Tendencia (sanidad):** la venta anual crece de $2.98M (2018) a $3.82M (2025), +31% en monto diario promedio — consistente con lo documentado en `ml/REPORTE_MEJORA_MODELOS.md` y con la ventana de entrenamiento de 3 años de `ml/main.py`.

## 3. Hallazgos en código `ml/`

| # | Archivo | Hallazgo | Severidad |
|---|---|---|---|
| ML-1 | `ml/requirements.txt` | **No declara `lightgbm`, `catboost`, `optuna`, `mlxtend`**, importados por `model_selector.py` y `train_recommendation_engine.py`. La imagen Docker `bi_ml` reconstruida desde cero no puede ejecutar `main.py` (no reproducible) | **Alta** |
| ML-2 | `make_dataset.py::fetch_market_basket` | `LIMIT 50000` **sin `ORDER BY`** → muestra no determinista entre corridas; `transaction_id` sintético (`fecha_cliente_sucursal`) en lugar de `num_factura`, que es la transacción real | **Alta** |
| ML-3 | `make_dataset.py::fetch_transactions_for_anomalies` | `LIMIT 20000` sin `ORDER BY` → mismo problema de no-determinismo | **Alta** |
| ML-4 | `make_dataset.py::fetch_churn_data` | Umbral de churn (90 días) hardcodeado sin constante nombrada ni documentación de la regla de negocio | Media |
| ML-5 | `eda_audit.py` | Credenciales hardcodeadas (`pwd = "CHANGE_ME"`, host/puerto fijos) y query ad-hoc con `LIKE '%REY%'` — script de depuración personal, no un EDA | Media |
| ML-6 | `train_*.py::save_*` | Los modelos se exportan como `.pkl` "pelados": **sin metadatos** (features, métricas, versión, fecha, algoritmo). Incumple trazabilidad mínima de MLOps | **Alta** |
| ML-7 | `make_dataset.py` | Fallback de password `"CHANGE_ME"` — falla silenciosa si falta la env var | Baja |
| ML-8 | Market basket / RFM | No excluyen `es_devolucion = true` (las devoluciones entran como "compras") | Media |

## 4. Hallazgos en `backend/`

La integración es correcta en su diseño: `ModelLoader` singleton en el `lifespan`, funciones de inferencia puras (`app/ml/inference.py`), preprocesamiento internalizado (`app/ml/preprocessing.py`) que replica los lags `(1,7,14,30,90)` del entrenamiento.

| # | Hallazgo | Severidad |
|---|---|---|
| BE-1 | `app/ml/preprocessing.py` es una **copia manual** de `ml/src/features/build_features.py` (riesgo documentado de desincronización). Mitigante requerido: los `.meta.json` de ML-6 permiten validar `feature_names_in_` al cargar | Media |
| BE-2 | No hay validación al cargar el `.pkl` de que las features del modelo coincidan con las que genera el preprocesador de serving | Media |

## 5. Decisiones tomadas en esta intervención

1. **Corregir ML-1** (requirements) — prerequisito para todo lo demás con Docker.
2. **Corregir ML-2, ML-3, ML-8** — muestreo determinista (`ORDER BY venta_sk DESC`, ventana reciente), `num_factura` como transacción real, exclusión de devoluciones donde aplica; límites como constantes nombradas configurables por env var.
3. **Corregir ML-4, ML-7** — constantes nombradas + documentación de la regla de negocio.
4. **Corregir ML-6** — cada `save_*` escribe un sidecar `<modelo>.meta.json` con: algoritmo ganador, features, métricas, fecha de entrenamiento y versión. El backend puede leerlo sin cargar el pkl.
5. **Reemplazar ML-5** — `eda_audit.py` pasa a ser un auditor real de calidad de datos (credenciales por env vars) que genera el informe de calidad reproducible.
6. **Filtrado de centinelas (DQ-1/DQ-2)** — el detector de anomalías excluye el centinela `-9999.9999`; documentado como regla.
7. **No se corrige en esta intervención** (requiere decisión de negocio / ETL):
   - Repoblar `dim_geografia` y `fact_metas_comerciales` (o eliminarlas del diseño).
   - Corregir el centinela `pct_margen=-9999.9999` en el ETL (debería ser `NULL`).
   - Poblar `dim_fecha.es_feriado` desde el calendario oficial (elimina el hardcode duplicado ML/backend).
   - Deduplicar las 576 líneas repetidas en el ETL (clave natural `num_factura`+línea).
   - Documentar la semántica de `estado_factura='P'` con el dueño del sistema fuente.

## 6. Definición de los problemas de ML (validada contra los datos)

| Modelo | Tipo | Target | Justificación |
|---|---|---|---|
| Ventas generales | Regresión sobre serie temporal tabular | `y_sales_net` diario | 3,106 días de historia; RF/GBM con lags supera a ARIMA/Prophet en series con exógenas de calendario (validado en `REPORTE_MEJORA_MODELOS.md`) |
| Demanda por producto | Regresión | `y_quantity` diario por producto | Reposición de bodega necesita unidades, no dinero |
| Segmentación clientes | Clustering (K-Means, k=4) | — (no supervisado) | RFM clásico; 73K clientes con historial |
| Churn | Clasificación binaria | `recency > 90 días` | Proxy razonable sin campo de baja explícito; el umbral es regla de negocio configurable |
| Venta cruzada | Reglas de asociación (Apriori) | — | Market basket sobre facturas reales |
| Anomalías | Detección no supervisada (IsolationForest) | — | Sin etiquetas de fraude disponibles |
| Metas | Regresión de ratio de crecimiento | `y_ventas_futuras` (acotado a 1.5) | Cap documentado en el SQL para evitar outliers de vendedores nuevos |
