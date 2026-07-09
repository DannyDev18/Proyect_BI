# 12 — Fase 0: Análisis previo a la Capa de Contratos ML

- **Fecha:** 2026-07-09 (revisión 2 — reenfocado a reconstrucción sobre el EDW actualizado)
- **Objetivo:** **definir la arquitectura de contratos ML que permitirá reconstruir, validar y publicar nuevos modelos entrenados sobre el EDW actualizado, asegurando compatibilidad entre entrenamiento y serving.**
- **Alcance:** análisis (sin código) de: arquitectura ML actual, impacto de los cambios del EDW sobre los datasets/features, clasificación legacy vs nuevo, diseño de contratos y estrategia de reconstrucción modelo por modelo.
- **Método:** lectura del código real del repositorio + `git diff` de los DDL de `edw/` (cambios aún no commiteados). Complementa la auditoría [11_auditoria_tecnica_modelos_ml.md](11_auditoria_tecnica_modelos_ml.md).
- **Estado:** ⏸️ **Pendiente de confirmación antes de implementar (Fase 1).**

> **Cambio de enfoque respecto a la revisión 1:** los `.pkl` actuales NO son la fuente de verdad ni el objeto a validar. Son **artefactos legacy** (la auditoría 11 documentó 6/7 contratos rotos entre entrenamiento y serving). La capa de contratos es la **especificación y barrera de calidad para la RECONSTRUCCIÓN** de los 7 modelos sobre el EDW actualizado: primero se escribe el contrato, después se entrena el modelo que lo cumple — nunca al revés.

---

## 1. Nuevo contexto: pipeline de reconstrucción

```
Nuevo EDW (DDL actualizados en edw/, aún sin commit)
   ↓
Extracción ML actualizada        ← make_dataset.py DEBE reescribirse (ver §3)
   ↓
Construcción de datasets         ← contratos definen columnas/tipos/filtros esperados
   ↓
Features                          ← contratos definen el set de features y su semántica
   ↓
Entrenamiento de NUEVOS modelos   ← lógica de torneo reutilizable (ver §5)
   ↓
Validación mediante contratos ML  ← ★ BARRERA DE CALIDAD (validate_features/artifact/prediction)
   ↓
Exportación de artefactos         ← save_artifact extendido: pkl + meta.json completo
   ↓
Serving backend                   ← mismas columnas declaradas en el contrato
   ↓
Dashboard
```

Un modelo **no se publica** (no llega al volumen que monta el backend) si no pasa la validación de contrato. Eso invierte el flujo actual, donde el `.pkl` se publica y los errores de contrato se descubren (o no) como `0.0`/"Error" degradado en el dashboard.

---

## 2. Arquitectura ML actual encontrada (referencia histórica / diagnóstico)

Se documenta como **evidencia del estado legacy**, no como especificación a preservar.

### 2.1 Lado entrenamiento (`ml/`)

| Componente | Archivo(s) | Estado observado |
|---|---|---|
| Orquestador | `ml/main.py` | Entrena 7 modelos; ventana 3 años solo en ventas; calcula métricas pero no las persiste en el sidecar |
| Extracción EDW | `ml/src/data/make_dataset.py` | 7 `fetch_*` con SQL embebido contra el **esquema viejo** de `fact_ventas_detalle` (usa `es_devolucion`, `estado_factura`, `pct_margen > -9999`) → **roto contra el nuevo DDL** (§3) |
| Features | `ml/src/features/build_features.py` | `TimeSeriesLagsTransformer` sólido (lags/rollings/calendario/exógenas rezagadas) pero el `Pipeline` no se serializa con el modelo; columnas definidas por exclusión |
| Selección | `ml/src/training/model_selector.py` | Torneo RF/XGB/LGBM/CatBoost/HGB con CV temporal — **reutilizable** |
| Entrenadores | `ml/src/training/train_*.py` | `log1p` fuera del estimador; segmentación exporta `dict`; inconsistencias catalogadas en auditoría 11 |
| Exportación | `ml/src/utils/model_export.py` | `save_artifact` (joblib + `.meta.json`) — **reutilizable y extensible**; hoy solo lo usan 4/7 modelos |
| Predicción legacy | `ml/src/prediction/predict_model.py` | Código muerto (duplicado del loader del backend) |
| Artefactos | `ml/models/*.pkl` (12) | Mezcla de nombres viejos y nuevos; **ningún `.meta.json` existe en disco**; todos anteriores al nuevo EDW |
| Tests | — | No existe `ml/tests/` |

### 2.2 Lado serving (`backend/`)

| Componente | Archivo(s) | Estado observado |
|---|---|---|
| Carga | `backend/app/ml/model_loader.py` | Singleton por lifespan; no lee `.meta.json` (usa mtime) |
| Inferencia | `backend/app/ml/inference.py` | `X[model.feature_names_in_]` en ventas/demanda; churn/anomalías/segmentación pasan el DataFrame tal cual |
| Features serving | `backend/app/ml/preprocessing.py` | Copia manual de `build_features.py` (desincronización reconocida en su docstring) |
| Servicios | `prediction_service.py`, `goals_service.py` | `try/except` degradan todo fallo de contrato a 0.0/"Error"; metas arma 6 columnas a mano (el entrenamiento usa 7 — mismatch confirmado) |
| Repositorios | `prediction_repository.py`, `dataset_repository.py` | SQL contra el **esquema viejo** (`estado_factura != 'I'`, `es_devolucion`) → **también rotos contra el nuevo DDL** (§3) |
| Tests | `backend/tests/unit/test_inference.py` | Validan plomería con dummies, no contratos reales |

### 2.3 Contrato por modelo — estado legacy (resumen de auditoría 11 + esta fase)

| Modelo | Contrato entrenamiento↔serving | Causa dominante |
|---|---|---|
| Ventas | 🔴 roto | salida en `log1p` servida como USD (H-01) |
| Demanda | 🔴 roto | ídem + sin ventana 3 años (H-08) |
| Segmentación | 🔴 roto | artefacto `dict`, sin escalar en serving, semántica RFM distinta (H-02, H-14) |
| Churn | 🔴 roto | columnas distintas + etiqueta circular (H-03, H-05) |
| Anomalías | 🔴 roto | columnas distintas + score ficticio (H-04) |
| Recomendación | 🟡 con pérdidas | filtro solo `item_A`, sin lift (H-10) |
| Metas | 🔴 roto | 7 features en entrenamiento vs 6 en `goals_service.py:63-69` (falta `indice_estacional_relativo`; sin degradación con gracia) |

---

## 3. Impacto del nuevo EDW sobre los modelos ML

Fuente: `git diff` de `edw/02_dimensiones.sql`, `edw/03_hechos.sql`, `edw/04_indices.sql`, `edw/06_verificacion.sql` (cambios en working tree, motivados por las auditorías 07–10).

### 3.1 Cambios del EDW relevantes para ML

| # | Cambio en el EDW | Detalle |
|---|---|---|
| C-1 | **`fact_ventas_detalle` pierde `es_devolucion`, `estado_factura` y `tipo_documento`** | Migran a la junk dimension nueva **`dim_estado_documento`** (`estado_documento_sk` NOT NULL en la fact). Todo filtro de estado/devolución ahora requiere JOIN |
| C-2 | **`costo_unitario`, `costo_total`, `margen_bruto` ahora NULLables** | Antes se forzaba costo 0 (margen 100% artificial); ahora NULL real cuando el artículo no tiene `ultcos` (auditorías 08 F2 / 10) |
| C-3 | **Convención `pct_margen = 0` cuando `subtotal_neto = 0`** | El centinela de calidad `pct_margen = -9999` desaparece del diseño (auditoría 07 H8) |
| C-4 | **Centinelas `-1` sembrados en el DDL** para las 11 dimensiones (incluida la nueva) | Ya no dependen del loader; su presencia en toda dimensión es garantizada |
| C-5 | **`dim_geografia` eliminada**; **`fact_transferencias` nueva**; `fact_movimientos_inventario` gana `cliente_sk`/`vendedor_sk`; `num_factura` pasa a VARCHAR(20) | Cambios estructurales sin consumo ML directo hoy |

### 3.2 Qué datasets ML dependen de tablas modificadas

**Los 7 datasets** leen `fact_ventas_detalle` → todos afectados por C-1/C-2/C-3 en distinto grado:

| Consulta (entrenamiento) | Impacto | Severidad |
|---|---|---|
| `fetch_market_basket` (`WHERE NOT fvd.es_devolucion`) | **SQL inválido**: la columna ya no existe; requiere JOIN a `dim_estado_documento` | 🔴 rompe en ejecución |
| `fetch_goals_data` (`WHERE f.estado_factura != 'I'`) | **SQL inválido**: ídem | 🔴 rompe en ejecución |
| `fetch_transactions_for_anomalies` (`WHERE pct_margen > -9999`, features `costo_total`/`margen`) | Filtro **obsoleto** (C-3: el centinela ya no existe; ahora es inocuo pero engañoso); `costo_total` ahora trae **NULL reales** (C-2) — el `fillna(0.0)` de `main.py` reintroduciría exactamente el margen-100%-artificial que el EDW acaba de eliminar | 🟠 semántica cambiada |
| `fetch_daily_sales`, `fetch_sales_by_dimension`, `fetch_rfm_metrics` (+`fetch_churn_data`) | No rompen sintácticamente, pero **hoy no filtran estado/devolución** y con el nuevo esquema el filtro correcto es vía `estado_documento_sk` — la reconstrucción debe incorporarlo (homologa además H-15) | 🟠 deben actualizarse |

**Lado backend (mismo impacto):** `prediction_repository.py` (churn, anomalías, RFM, historial: todos filtran `estado_factura != 'I'`) y `dataset_repository.py` (ambas series) quedan **sintácticamente inválidos** contra el nuevo DDL. La reconstrucción de contratos debe declarar el filtro estándar una sola vez para ambos lados.

### 3.3 Qué features pueden cambiar

- **Anomalías:** el set actual (`subtotal_neto, cantidad, costo_total, margen`) debe rediseñarse: `costo_total`/`margen` ahora son NULLables (C-2) y la política de nulos pasa a ser una decisión de contrato (excluir filas sin costo vs. feature indicadora). `pct_margen=0` en cortesías (C-3) es un patrón nuevo que el detector verá.
- **Todos:** el filtro de población (`estado_factura`, `es_devolucion`) se vuelve un atributo del dataset vía `dim_estado_documento` — el contrato debe declararlo explícitamente (`population_filter`) para que entrenamiento y serving usen el mismo.
- **Ventas/Demanda:** las features de calendario/lags no cambian por el EDW; sí cambia el SQL base. `es_feriado` sigue sin poblarse en `dim_fecha` (deuda ETL, el workaround hardcodeado persiste).
- **Metas:** el SQL de `fetch_goals_data` cambia solo en el filtro; las features derivadas (estacionalidad, tendencia) se conservan.

### 3.4 Qué contratos deben redefinirse y qué modelos requieren reconstrucción completa

| Modelo | ¿Reconstrucción? | Razón |
|---|---|---|
| Ventas | ✅ Completa (reentrenar) | SQL base actualizado + target autocontenido (log1p dentro del artefacto) |
| Demanda | ✅ Completa | Ídem + ventana 3 años + decisión sobre identidad del SKU |
| Segmentación | ✅ Completa | Artefacto nuevo (Pipeline scaler+kmeans) + semántica RFM unificada + exclusión centinela `-1` |
| Churn | ✅ Completa **con rediseño metodológico** | Etiqueta temporal (corte T / horizonte T+90) — único caso donde cambia la definición del problema |
| Anomalías | ✅ Completa | Features rediseñadas por C-2/C-3 + score real (`decision_function`) |
| Recomendación | ✅ Completa | SQL inválido (C-1) + reglas direccionales con confidence/lift + clave `codart` |
| Metas | ✅ Completa | SQL inválido (C-1) + contrato de 7 features alineado con `goals_service` |

Conclusión: **los 7 contratos se definen desde cero** (a partir del diseño esperado y las reglas de negocio del EDW actualizado), y **los 7 modelos se reentrenan**. Ningún `.pkl` actual sobrevive como artefacto oficial.

### 3.5 Qué componentes pueden reutilizarse

| Componente | Veredicto |
|---|---|
| `model_selector.py` (torneo + CV temporal) | ✅ Reutilizable tal cual (con los fixes menores H-11 en su momento) |
| `build_features.py` (`TimeSeriesLagsTransformer`) | ✅ Reutilizable (corrigiendo `bfill` H-06 en la fase de reconstrucción); pasa a estar **declarado** por el contrato |
| `model_export.save_artifact` | ✅ Reutilizable, se **extiende** (metadata completa) — es el punto de enganche natural de los contratos |
| `SalesTimeSerieExtractor` (estructura clase/conexión) | 🟡 La clase sí; **todo su SQL se reescribe** contra el nuevo esquema (idealmente hacia vistas `ml.*`, H-22b) |
| `ModelLoader` / `inference.py` del backend | 🟡 Estructura sí; la selección de columnas pasará del atributo `feature_names_in_` al contrato (fase posterior) |
| `MultiModelPredictor` (`ml/src/prediction/`) | ❌ Descartar (código muerto con bugs duplicados) |
| `.pkl` actuales en `ml/models/` | ❌ Legacy: referencia histórica/diagnóstico únicamente |

---

## 4. Clasificación de artefactos

### 4.1 Legacy (los 12 `.pkl` actuales en `ml/models/`)

- Entrenados contra el **esquema viejo** del EDW, sin `.meta.json`, con las incompatibilidades de la auditoría 11.
- **Uso permitido:** referencia histórica, diagnóstico, comparación de métricas "antes/después".
- **Uso prohibido:** fuente para derivar contratos, base de features, artefacto publicado al backend tras la reconstrucción.
- El validador los reporta como `legacy: true` (metadata ausente ⇒ warning, no error), y los smoke tests los marcan `xfail` con referencia al hallazgo — nunca "pasan" el contrato por accidente.

### 4.2 Nuevos artefactos (post-contratos)

Requisitos obligatorios para publicarse:

1. Cumplir el **contrato de features** (columnas, tipos, orden, nulos, filtro de población).
2. **Metadata completa** en `.meta.json` (algoritmo, features, métricas reales, transformación de target, versiones de librerías, rango temporal y filas del dataset).
3. Pasar **validación automática** (`validate_features` + `validate_artifact` + `validate_prediction`).
4. Pasar el **smoke test** (cargar → construir fila según contrato → `predict()` → salida válida en tipo/escala/rango).
5. **Compatibilidad backend** verificada: las columnas del contrato == columnas que declara producir el repositorio de serving.

---

## 5. Diseño propuesto de la capa de contratos

### 5.1 Archivos a crear (Fase 1)

| Ruta | Contenido |
|---|---|
| `ml/src/contracts/model_contract.py` | `ModelContract`: nombre, versión, task (`regression/classification/clustering/recommendation/anomaly_detection`), features, target (+`transform`/`inverse_transform`), output (tipo/unidad/rango plausible), filtro de población, versiones, rango temporal |
| `ml/src/contracts/feature_schema.py` | `FeatureSpec`/`FeatureSchema`: nombre, dtype, obligatoriedad, orden, nulos; comparación con errores descriptivos |
| `ml/src/contracts/artifact_schema.py` | Esquema del `.meta.json` extendido (superset retrocompatible del actual) |
| `ml/src/contracts/contract_validator.py` | `validate_features()`, `validate_artifact()`, `validate_prediction()` + modo reporte (gate de publicación pre-`publish_models.py`) |
| `ml/contracts/models/*.json` (7) | Contratos declarativos **draft**: estructura completa; features definitivas se fijan al diseñar cada dataset nuevo en Fase 2/3, **no** copiando los pkl legacy |
| `ml/tests/test_model_contract.py` | Smoke test parametrizado por contrato (legacy ⇒ xfail documentado) |
| `docs/ml_contracts.md` | Propósito, cómo registrar un modelo, cómo validar, cómo evitar divergencia entrenamiento/serving, flujo de desarrollo |

Modificación mínima: `ml/src/utils/model_export.py` (extensión retrocompatible del sidecar). Nada más se toca en Fase 1.

### 5.2 Decisiones de diseño (actualizadas al enfoque de reconstrucción)

| ID | Decisión |
|---|---|
| **D-1** | Contratos declarativos en **JSON** (`ml/contracts/models/`), versionados en git, legibles por ambos lados sin acoplar paquetes. Claves en inglés (consistente con el meta actual), docs en español. *(Confirmado por el usuario.)* |
| **D-2 (reforzada)** | **El contrato es la especificación del modelo NUEVO; nunca se genera desde los artefactos.** Prohibido derivarlo de: `.pkl` existentes, `feature_names_in_`, o el comportamiento actual del serving. Flujo correcto: `contrato → entrenamiento → modelo → validación`; flujo prohibido: `modelo actual → contrato`. Los contratos se redactan desde el diseño esperado del pipeline reconstruido + reglas de negocio del EDW actualizado (auditoría 02 y §3 de este documento). |
| **D-3** | `dataclasses` stdlib + validación explícita; sin dependencias nuevas en `ml/requirements.txt`. |
| **D-4** | Los 7 JSON nacen con `"status": "draft"`; pasan a `"active"` cuando su modelo se reconstruye en Fase 3 y la dupla contrato+artefacto valida. Un contrato `draft` no bloquea nada; uno `active` es gate obligatorio de publicación. |
| **D-5** | Smoke test único parametrizado que recorre `ml/contracts/models/*.json`; artefactos legacy ⇒ `xfail` con referencia al hallazgo (H-01…H-05, metas). *(Confirmado por el usuario.)* |
| **D-6** | `validate_prediction` valida **escala y rango plausible** declarados en el contrato (`output.unit`, `output.range`): es lo que convierte el bug log1p (venta diaria de "12.3 USD") en un fallo de contrato explícito. |
| **D-7** | El validador corre como script de reporte (`python -m src.contracts.contract_validator`) antes de `publish_models.py` — la "barrera de calidad" del flujo de §1. |
| **D-8** | Tests en `ml/tests/` (convención del repo). *(Confirmado por el usuario.)* |
| **D-9** | El contrato incluye `population_filter` (estado del documento / devoluciones, ahora vía `dim_estado_documento`) y `data_range`: la primera unifica la población entrenamiento↔serving (cierra H-15 por diseño), la segunda queda lista para cruzar contra `edw.etl_control` (H-22) en una fase futura. |

### 5.3 Riesgos (actualizados)

| # | Riesgo | Mitigación |
|---|---|---|
| **R-0 (nuevo, principal)** | **Crear contratos basados en modelos legacy puede perpetuar los errores existentes** (codificaría como especificación los 6 contratos rotos de la auditoría 11). | Los contratos se definen a partir del **diseño esperado del nuevo pipeline y las reglas de negocio actuales** (EDW actualizado, auditoría 02, §3.3); los pkl legacy solo se usan como diagnóstico. Es la decisión D-2 y el criterio de revisión de cada JSON. |
| R-1 | Los pkl legacy reprueban los smoke tests y "rompen" la suite. | `xfail` documentado por hallazgo (confirmado); al reconstruirse cada modelo, su test pasa a estricto. |
| R-2 | No existe ningún `.meta.json` en disco; no se puede exigir metadata a legacy. | Metadata obligatoria solo para artefactos nuevos; legacy ⇒ warning `legacy: true`. |
| R-3 | `feature_names_in_` no es universal (CatBoost; artefactos no-estimador). | La fuente de verdad de features es el contrato JSON; el atributo del estimador es solo verificación cruzada cuando existe. |
| R-4 | Dos imágenes Docker (ml / backend); el validador debe correr en `ml/` sin importar código del backend. | `ml/src/contracts/` autocontenido; la compatibilidad con el backend se declara en el JSON, no importando repositorios. |
| R-5 | Extender `.meta.json` podría romper consumidores. | Solo se agregan claves (superset); hoy además nadie lee el meta (el loader usa mtime). |
| R-6 | El torneo multi-algoritmo cambia el estimador ganador por corrida. | El contrato declara las features del **dataset de entrada** (estables por diseño), no del estimador; `validate_artifact` verifica cada publicación. |
| R-7 | Smoke tests requieren xgboost/lightgbm/catboost instalados. | Skip con razón si falta la librería o el `.pkl`, igual que el `ModelLoader`. |
| **R-8 (nuevo)** | El nuevo DDL de `edw/` aún **no está commiteado ni aplicado** a una BD existente (los DDL solo corren en volumen nuevo). Los contratos podrían escribirse contra un esquema que luego cambie de nuevo. | Los contratos nacen `draft` (D-4) y se activan en Fase 3, cuando el EDW reconstruido esté cargado y verificado (`edw/06_verificacion.sql`); el `data_range` del meta ata cada artefacto al estado real de los datos. |

---

## 6. Estrategia posterior a los contratos ML

### Fase 1 — Infraestructura de contratos *(la única que se implementa al confirmar este documento)*

`ml/src/contracts/` (4 módulos) + 7 JSON draft + `save_artifact` extendido + `ml/tests/test_model_contract.py` + `docs/ml_contracts.md`. Sin tocar entrenamiento, backend, reglas de negocio ni `.pkl`.

### Fase 2 — Adaptación de extracción y datasets al nuevo EDW

- Reescribir el SQL de `make_dataset.py` contra el nuevo esquema (JOIN a `dim_estado_documento`, nulos reales de costo, filtro de población del contrato, exclusión de centinelas `-1`), idealmente materializado como vistas `ml.*` (`edw/09_vistas_ml.sql`, H-22b).
- Actualizar en espejo `dataset_repository.py` / `prediction_repository.py` del backend (hoy sintácticamente inválidos contra el nuevo DDL, §3.2).
- Promover a `active` la parte de dataset/población de cada contrato.

### Fase 3 — Reconstrucción modelo por modelo

Orden y ficha de reconstrucción (dataset origen sobre el EDW nuevo, features críticas, cambios por EDW, validaciones, dependencia backend):

| # | Modelo | Dataset origen (EDW nuevo) | Features críticas | Cambios esperados por EDW | Validaciones necesarias | Dependencia backend |
|---|--------|---------------------------|-------------------|---------------------------|------------------------|---------------------|
| 1 | **Ventas** | Serie diaria de `fact_ventas_detalle` + `dim_fecha`, filtrada vía `dim_estado_documento` | lags 1–90, rollings, calendario, exógenas rezagadas | Filtro de población explícito; mismo SQL base que `dataset_repository` | Contrato de features + salida en USD (rango plausible detecta log1p) + walk-forward coherente | `inference.predict_sales`, `prediction_service.get_sales_forecast_weekly`; decidir global vs por sucursal (H-14c) |
| 2 | **Demanda** | Serie producto-día (clave `codart`, no nombre) | lags por producto, ventana 3 años | Filtro de población; SCD2 por llave de negocio (H-21) | Ídem ventas + consistencia con serie por producto del serving | `predict_demand`, `get_demand_forecast` |
| 3 | **Segmentación RFM** | RFM por cliente, `cliente_sk <> -1`, semántica única (facturas o días — decidir y declarar) | recency/frequency/monetary | Exclusión centinela; filtro población | Artefacto = Pipeline con `.predict()`; mapeo estable cluster→segmento en meta (H-12) | `predict_segmentation`, `get_customer_segment` + `get_rfm_features` con la MISMA semántica |
| 4 | **Churn** | Dataset temporal nuevo: features a fecha de corte T, etiqueta = compra en (T, T+90] | tendencia de frecuencia, ticket, recencia a T | Rediseño metodológico (H-05) + filtro población | Contrato de features == `get_churn_features` (rediseñado); AUC sobre etiqueta no circular | `predict_churn`, `get_churn_risk` |
| 5 | **Anomalías** | Transacciones con política de nulos de costo declarada (C-2); sin filtro `-9999` (C-3, obsoleto) | descuento %, monto, flags de devolución vía junk dim, margen si hay costo | Features rediseñadas; `pct_margen=0` en cortesías es patrón nuevo | Score real (`decision_function`) con rango declarado; contraste con `fact_logs_auditoria` | `detect_anomalies`, `get_anomaly_status` + `get_transaction_features` alineado |
| 6 | **Recomendación** | Canastas por `num_factura` (VARCHAR(20)), excluyendo devoluciones vía junk dim, clave `codart` | reglas direccionales con support/confidence/lift | SQL reescrito (C-1) | Esquema del DataFrame de reglas como contrato (columnas + direccionalidad) | `get_recommendations` (filtro en ambas direcciones), response con `producto_cod` |
| 7 | **Metas** | `fetch_goals_data` reescrito (filtro vía junk dim) | 7 features incl. `indice_estacional_relativo`; sin `anio` crudo (H-13) | SQL inválido hoy (C-1) | Contrato de 7 features == `df_pred` de `goals_service` (hoy 6 — cerrar el gap) | `predict_goal_growth_ratio`, `goals_service._predict_goal_amount` |

Cada modelo reconstruido: contrato `draft → active`, artefacto nuevo con meta completa, smoke test `xfail → pass estricto`, y recién entonces `publish_models.py`.

### Fase 4 (posterior, fuera de este plan) — Integración de serving

El backend pasa a leer contratos/meta (selección de columnas, transformaciones, fecha real de entrenamiento, métricas reales del dashboard — cierra H-09) y se agrega el guard de frescura contra `edw.etl_control` (H-22).

---

## 7. Entregables de esta Fase 0 (cumplidos en este documento)

1. ✅ Arquitectura ML actual encontrada (§2).
2. ✅ Impacto de cambios del EDW (§3.1–3.3).
3. ✅ Componentes reutilizables (§3.5).
4. ✅ Componentes que deben reconstruirse (§3.4: los 7 modelos + extracción + repositorios del backend).
5. ✅ Diseño propuesto de contratos ML (§5).
6. ✅ Estrategia de reconstrucción (§6, ficha por modelo).
7. ✅ Orden recomendado de implementación (Fases 1→4; dentro de Fase 3: ventas → demanda → segmentación → churn → anomalías → recomendación → metas).

### Decisiones ya confirmadas por el usuario

- Tests legacy: **xfail documentado** con referencia al hallazgo.
- Ruta de tests: **`ml/tests/`**.
- Claves JSON: **inglés** (docs en español).

---

**⏸️ Fin de la Fase 0 (revisión 2). Sin código, sin contratos, sin cambios en modelos ni `.pkl`. Esperando confirmación para ejecutar la Fase 1 (infraestructura de contratos) tal como queda especificada en §5 y §6.**
