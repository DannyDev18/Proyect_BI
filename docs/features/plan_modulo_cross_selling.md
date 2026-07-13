# Plan de Ejecución: Módulo de Venta Cruzada (Cross-Selling)

> **Fecha:** 2026-07-13
> **Fuente de requerimientos:** `docs/features/modulo_cross_selling_requerimientos.md`
> **Generado con:** skill `module-requirements-analyzer` + skills `ml-training-pipeline` y `backend-ml-serving`
> **Estado:** PLAN — pendiente de aprobación antes de implementar (flujo CLAUDE.md: auditoría → cambios)

---

## 1. Análisis de Requerimientos

### 1.1 Objetivo del módulo

Asistir al vendedor con sugerencias de productos complementarios en el momento de la venta:
dado el/los producto(s) que el cliente está comprando (y opcionalmente el cliente), sugerir
Top 3–5 productos adicionales con nombre, precio, razón ("clientes que compraron X también
compraron Y") y un clic para agregarlos, midiendo la tasa de aceptación como KPI.

### 1.2 Punto de partida — LO QUE YA EXISTE (no rehacer)

El requerimiento pide construir el módulo "desde cero", pero el proyecto **ya tiene la base
entrenada y servida**. El plan reutiliza y extiende:

| Capa | Componente existente | Estado |
|---|---|---|
| ML | `ml/src/training/train_recommendation_engine.py` — reglas de asociación **direccionales** (A→B y B→A) con support/confidence/lift por co-ocurrencia sobre canastas (`num_factura`), llave `codart`. Equivale funcionalmente a Apriori/mlxtend (decisión documentada en el contrato). | ✅ Operativo (490 reglas, 17.009 facturas, min_support=0.005) |
| ML | `ml/src/data/make_dataset.py::fetch_market_basket` — dataset desde el EDW con filtros de negocio correctos (dim_estado_documento, sin devoluciones, sin centinela `-1`). | ✅ Operativo |
| Contrato | `ml/contracts/models/recommendation.json` v0.1.0, `status: active`. | ✅ Activo |
| Backend | `model_loader.py` clave `association` → `recommendation.pkl`; `inference.get_recommendations`; `prediction_service.get_product_recommendations(cliente_id)`. | ✅ Operativo |
| API | `GET /api/v1/analytics/ventas/recommendations?cliente_id=` (RBAC `vendedor_checker`) y `GET /analytics/ventas/goals/recomendaciones`. | ✅ Operativo |
| Frontend | Tarjeta "Recomendaciones de Venta Cruzada" en `DashboardVentas.tsx` (por cliente). | ✅ Operativo |

### 1.3 Brechas reales (lo que el plan SÍ construye)

1. **Recomendación por producto/canasta** (punto de venta): hoy solo existe por historial de
   cliente. Falta `codart(s) → sugerencias` — el caso de uso central del requerimiento.
2. **Enriquecimiento de la sugerencia**: hoy se devuelve solo `producto_cod` + `score` (lift).
   Falta nombre, precio, categoría, margen estimado y texto de razón.
3. **Heurísticas de negocio**: filtrar productos ya en la canasta / ya comprados, priorizar
   margen, límite Top-N configurable.
4. **Re-análisis del modelo ML (alta prioridad)**: el modelo v0.1.0 se trata como línea base a
   superar, no como solución final. Se re-evalúan variables (min_support, umbrales de
   lift/confidence, ventana, definición de canasta, granularidad del ítem) y compiten
   estrategias alternativas — Apriori/FP-Growth con mlxtend, filtrado colaborativo item-item
   con scikit-learn, e híbrido con fallback por categoría — con selección por backtest
   (detalle completo en §2.3).
5. **Evaluación offline del modelo**: hoy no hay métricas. Falta backtest temporal con
   Precision@K / Recall@K / Hit-Rate + estimación de impacto en ticket promedio.
6. **Telemetría / KPI de conversión**: registrar sugerencias mostradas vs aceptadas
   (tabla nueva en `public.*`) y exponer la tasa de conversión.
7. **UI de asistente de venta**: componente donde el vendedor arma una canasta simulada y ve
   sugerencias con botón "Agregar". **Aclaración de alcance:** el POS real es el ERP SAP (esta
   plataforma es BI, no factura); el punto de integración es un *Asistente de Venta Cruzada*
   dentro del dashboard de Ventas, no un carrito transaccional.
8. **Documentación**: guía de reentrenamiento, guía del vendedor, diagrama del módulo.

### 1.4 Usuarios / roles afectados (RBAC)

- **`ventas`** (principal): asistente de venta cruzada, sugerencias, registro de aceptación.
- **`gerencia`**: KPI de conversión y reporte de rendimiento del módulo.
- **`administrador`**: reentrenamiento (`/admin/modelos/retrain`, solo dev) y salud del modelo.
- `bodega`: sin cambios.

### 1.5 Correcciones al plan original del usuario (obligatorias por CLAUDE.md)

| Pedía el requerimiento | Se hará en su lugar | Regla |
|---|---|---|
| Extraer de `renglonesfacturas`/`encabezadofacturas` (SAP) | Entrenar SOLO desde el EDW (`fact_ventas_detalle`); SAP únicamente `SELECT` de validación | EDW fuente oficial; SAP solo lectura |
| Endpoint `POST /recomendar_productos` en `main.py` | Endpoints bajo `/api/v1/analytics/ventas/...`, capas routes→services→repositories, RBAC | Convenciones backend |
| `recommendation_engine.py` suelto que carga el `.pkl` al iniciar | Reutilizar `ModelLoader` singleton (lifespan) + `inference.py` | Skill backend-ml-serving |
| `pickle.dump` manual | `save_artifact` (joblib + sidecar `.meta.json`) + contrato JSON + `contract_validator` | Regla D-2 contrato-primero |
| Instalar `surprise` | No se usa `surprise` (dependencia pesada, sin mantenimiento activo); el colaborativo item-item se implementa con scikit-learn ya presente. `mlxtend` SÍ entra como candidato, solo en `ml/requirements.txt` (entrenamiento) | Acople de versiones H-20 |
| Guardar dataset como CSV | Dataset efímero en memoria (patrón `fetch_*` existente); nada de CSVs versionados | Patrón `make_dataset.py` |

---

## 2. Descomposición Técnica

### 2.1 Capa de Datos (EDW)

**Sin tablas nuevas en `edw.*`** — `fact_ventas_detalle` + `dim_producto` cubren el entrenamiento.

Tabla nueva en `public.*` (app, no DW — como `metas_comerciales_operativas`):

- **`public.recomendaciones_eventos`** — telemetría del módulo:
  `id BIGSERIAL, fecha timestamptz, usuario_id, cliente_sk NULL, producto_origen_cod,
  producto_sugerido_cod, score_lift NUMERIC, motivo TEXT, evento ('mostrada'|'aceptada'|'rechazada'),
  fecha_carga`. Índices por `(fecha)`, `(evento)`.
- DDL agregado a `edw/07_public_app_tables.sql` (para volúmenes nuevos) + modelo SQLAlchemy en
  el backend (`Base.metadata.create_all` la crea en BD existente, patrón actual).
- **Validaciones previas contra el EDW** (solo SELECT):
  - Volumen: nº facturas con 2+ productos, nº `codart` únicos con ventas en la ventana.
  - Cobertura de reglas actuales: % de `codart` vendidos el último trimestre que aparecen como
    `item_A` (dimensiona la necesidad del fallback).
  - Margen: verificar que `dim_producto` vigente tenga costo (`ultcos`) y precio utilizables;
    si el margen por unidad no es derivable de forma confiable, la heurística de margen usa
    `subtotal_neto − costo_total` histórico por producto y se documenta la fórmula.

### 2.2 Pipeline ETL

**Sin extractores ni transformers nuevos** — el dato ya llega al EDW. Nota: el riesgo abierto
"`etl/loaders/` borrado del working tree" NO bloquea este módulo (no requiere recargas), pero
si se necesita refrescar el EDW antes de entrenar, primero restaurar los loaders (`git restore`).

### 2.3 Modelos de ML (`ml/`) — RE-ANÁLISIS COMPLETO — con skill `ml-training-pipeline`

**Decisión de alcance (2026-07-13, pedida por el usuario):** el módulo es de alta prioridad y
el modelo actual NO se da por bueno. Se re-analiza el problema de recomendación desde los
datos, se re-evalúan todas las variables/hiperparámetros de la estrategia, y **se reemplaza el
modelo v0.1.0 si un candidato lo supera en el backtest**. Lo único intocable son las reglas
metodológicas del pipeline (contrato-primero, filtros de negocio, split temporal, sin fuga).

Contrato-primero (D-2): **`recommendation.json` a v0.2.0 en `draft` ANTES de tocar el
entrenamiento**; `active` solo tras validar el candidato ganador.

**2.3.a EDA nuevo del problema (notebook `ml/notebooks/eda_cross_selling.ipynb`)**
- Distribución de tamaño de canasta (¿cuántas facturas tienen 2, 3, 5+ productos?).
- Concentración de ventas por producto/categoría (curva de Pareto) — determina si las reglas a
  nivel `codart` son viables o si conviene un nivel mixto `codart` + `codgrupo`.
- Estabilidad temporal de las co-ocurrencias (¿los pares frecuentes de 2024 siguen siéndolo en
  2026?) — determina la ventana de entrenamiento.
- Cobertura actual: % de canastas del último trimestre que recibirían ≥1 sugerencia con las
  490 reglas v0.1.0 (línea base a superar).
- Diferencias por sucursal y por segmento RFM (¿la afinidad es global o local?).

**2.3.b Variables/parámetros a re-evaluar (grid experimental, todo parametrizado `ML_*`)**

| Variable | Valor actual (v0.1.0) | Espacio a explorar |
|---|---|---|
| `min_support` | 0.005 | 0.001–0.01 (más reglas vs ruido) |
| Umbral de `lift` | ninguno (solo orden) | lift mínimo 1.5–3 para admitir una regla |
| Umbral de `confidence` | ninguno | 0.05–0.3 |
| Ventana temporal | muestra `ML_MUESTRA_MARKET_BASKET` (sin ventana explícita) | 1, 2, 3 años, todo el histórico |
| Definición de canasta | `num_factura` | factura vs cliente-día (compras del mismo cliente el mismo día) |
| Granularidad del ítem | `codart` | `codart`, `codgrupo`, y jerárquico (regla codart si existe, si no codgrupo) |
| Tamaño de itemset | pares (2) | pares + tríos frecuentes (evaluar costo/beneficio) |
| Ponderación | frecuencia simple | ponderar canastas recientes (decay temporal) |

**2.3.c Estrategias candidatas a competir (misma evaluación para todas)**
1. **Co-ocurrencia direccional actual re-tuneada** (línea base mejorada con el grid de arriba).
2. **Apriori/FP-Growth con `mlxtend`** (itemsets de 2–3, métricas estándar): se agregaría
   `mlxtend` SOLO a `ml/requirements.txt` (entrenamiento; el artefacto sigue siendo un
   DataFrame de reglas, el backend no necesita la librería — no rompe el acople de runtime).
3. **Filtrado colaborativo item-item** (similitud coseno sobre matriz cliente×producto binaria,
   implementable con scikit-learn ya presente — sin `surprise`): captura afinidades que las
   reglas de canasta pierden (compras en facturas separadas del mismo cliente).
4. **Híbrido** (si 1/2 y 3 aportan señal distinta): reglas de canasta como fuente primaria +
   item-item como segunda fuente + popularidad por categoría como fallback final, con score
   combinado y `motivo` diferenciado por fuente ("comprados juntos" vs "clientes similares"
   vs "popular en la categoría").

**2.3.d Selección por backtest (obligatoria, decide el ganador)**
- Split temporal: canastas hasta T entrenan; canastas de (T, T+h] evalúan. Nunca split aleatorio.
- Métricas de decisión: **Precision@K y Recall@K (K=3,5)**, **Hit-Rate@5** (≥1 acierto por
  canasta), **cobertura** (% de canastas con sugerencia) y **estimación de impacto en ticket**
  (valor medio de los aciertos). Ganador = mejor Precision@5 con cobertura ≥ la línea base;
  empates se rompen por simplicidad (menos piezas móviles).
- Todos los experimentos (ganadores y perdedores) quedan en `ml/REPORTE_MEJORA_MODELOS.md`
  con sus métricas — un cambio que no supere la línea base NO se publica.

**2.3.e Artefacto y contrato del ganador**
- `save_artifact` con `metrics={precision_at_5, recall_at_5, hit_rate_5, cobertura, ...}`,
  `data_range` y `library_versions` reales; el contrato v0.2.0 documenta la estrategia final,
  sus features (si el híbrido agrega columnas: `fuente`, `score_combinado`), el
  `population_filter` y los umbrales elegidos con su justificación.
- Si gana el híbrido/colaborativo y requiere librería nueva en runtime del backend, se
  actualizan `ml/requirements.txt` **y** `backend/requirements.txt` en el mismo cambio (H-20);
  el diseño prioriza artefactos-DataFrame precomputados para evitarlo.
- Validar con `python -m src.contracts.contract_validator` + `pytest ml/tests/` y publicar con
  `publish_models.py`.

Frecuencia de reentrenamiento: mensual (manual vía `POST /admin/modelos/retrain` en dev;
la calendarización queda en Fase 6 de la hoja de ruta, no se inventa un scheduler nuevo aquí).

### 2.4 Backend (FastAPI) — con skill `backend-ml-serving`

Sin modelo nuevo en `_MODEL_FILES` (se reutiliza la clave `association`).

**Inferencia** (`app/ml/inference.py`):
- Extender/agregar función pura `get_recommendations_for_basket(loader, items: list[str], top_n)`
  que filtra reglas por `item_A ∈ canasta`, excluye `item_B ∈ canasta`, agrega por `item_B`
  (max lift), ordena por lift.

**Repositorio** (`app/repositories/prediction_repository.py` o `catalog_repository.py`):
- `get_products_info(codarts) → nombre, precio, categoría, costo` desde `dim_producto` vigente
  (`es_vigente`, excluyendo centinela `-1`).
- `get_client_purchased_codarts(cliente_id)` (ya existe historial; reutilizar).

**Servicio** (`app/services/prediction_service.py`, mismo dominio):
- `get_basket_recommendations(items, cliente_id=None, top_n=settings.CROSS_SELL_TOP_N)`:
  reglas → heurísticas (excluir canasta y ya-comprados del cliente; reordenar por
  `lift × factor_margen` con pesos configurables) → fallback por categoría si no hay reglas →
  enriquecer con catálogo → armar `motivo` ("Los clientes que llevan X suelen llevar Y").
  Patrón obligatorio: `try/except` + `logger.error` + degradación a lista vacía.
- `log_recommendation_event(...)` y `get_conversion_kpis(...)` (telemetría) — repositorio propio
  sobre `public.recomendaciones_eventos`.

**Schemas** (`app/schemas/analytics.py` o módulo nuevo `cross_selling.py`): request/response
Pydantic (`SugerenciaProducto`: codart, nombre, precio, score, motivo, categoria).

**Endpoints** (`app/api/routes/sales.py`, prefijo `/analytics/ventas`, RBAC `vendedor_checker`):
- `POST /cross-selling/sugerencias` — body `{items: [codart], cliente_id?: str, top_n?: int}`.
- `POST /cross-selling/eventos` — registra mostrada/aceptada/rechazada.
- `GET /cross-selling/kpis?desde=&hasta=` — tasa de conversión, sugerencias mostradas/aceptadas
  (también visible para `gerencia` vía checker correspondiente).

**Config** (`app/core/config.py`): `CROSS_SELL_TOP_N`, `CROSS_SELL_MIN_LIFT`,
`CROSS_SELL_PESO_MARGEN` — env vars, sin hardcodes.

### 2.5 Frontend (React + Vite)

- **Tipos** `src/types/crossSelling.ts` + **servicio** `src/services/crossSelling.ts` (Axios,
  contratos espejo de los schemas).
- **Hooks** `src/hooks/crossSelling.ts` (TanStack Query; claves en `src/constants/queryKeys.ts`).
- **Componentes** `src/components/crossSelling/`:
  - `SaleAssistant.tsx` — asistente de venta: buscador de producto (autocomplete por
    código/nombre), canasta simulada, panel de sugerencias.
  - `SuggestionCard.tsx` — nombre, precio, motivo, score, botón **"Agregar"** (mueve la
    sugerencia a la canasta y dispara evento `aceptada`; al renderizarse dispara `mostrada`).
  - `CrossSellKpiPanel.tsx` — tasa de conversión (para Ventas y reutilizable en Gerencia).
- **Integración**: nueva sección/pestaña en `DashboardVentas.tsx` (la tarjeta por-cliente
  existente se conserva y se enlaza con el asistente). Permisos en
  `src/constants/permissions.ts` si se agrega ruta nueva.

---

## 3. Orden de Ejecución (Fases)

### Fase 1 — Auditoría y validación de datos (Día 1) — *entregable Fase 0+1 del requerimiento*
- Crear `docs/auditoria/25_modulo_cross_selling.md` ANTES de tocar código: alcance, mapeo
  origen→EDW (renglonesfacturas→fact_ventas_detalle, articulos→dim_producto, etc.), diagrama
  del flujo y punto de integración, decisiones de estrategia (asociación + fallback; se
  descarta colaborativo con justificación), hallazgos.
- Ejecutar los SELECT de validación (§2.1): volúmenes, cobertura de reglas, disponibilidad de
  margen. Solo SELECT contra EDW; SAP solo si hay que reconciliar volúmenes.
- Definir formato de sugerencia (Top-N, campos, texto de motivo) y registrar la regla de
  negocio nueva en `docs/auditoria/02_reglas_negocio_validadas.md`.

### Fase 2 — Re-análisis y EDA del modelo (Días 2-3) — *entregable Fase 2 del requerimiento*
- Notebook `ml/notebooks/eda_cross_selling.ipynb` (§2.3.a): canastas, Pareto, estabilidad
  temporal, cobertura de la línea base, afinidad por sucursal/segmento.
- Con el EDA, fijar el grid experimental (§2.3.b) y confirmar qué estrategias candidatas
  (§2.3.c) tienen sentido con los datos reales; registrar decisiones en la auditoría 25.
- `recommendation.json` → v0.2.0 `draft` con el diseño del dataset y las features candidatas
  (contrato-primero, ANTES de entrenar).

### Fase 3 — Entrenamiento, competencia y selección (Días 4-6) — *entregable Fase 3 del requerimiento*
- Implementar el arnés de backtest temporal con Precision@K / Recall@K / Hit-Rate / cobertura
  en `ml/src/training/` (reutilizable para reentrenamientos futuros).
- Correr el grid sobre la co-ocurrencia re-tuneada, Apriori/FP-Growth (mlxtend), item-item
  (scikit-learn) e híbrido; ajustar `fetch_market_basket` (ventana/canasta parametrizadas `ML_*`).
- Seleccionar ganador por las reglas de §2.3.d; documentar TODOS los experimentos en
  `ml/REPORTE_MEJORA_MODELOS.md`; generar fallback por categoría.
- `save_artifact` con métricas; `contract_validator` limpio; `pytest ml/tests/`; contrato a
  `active`; `publish_models.py`.

### Fase 4 — Backend (Días 7-9) — *entregable Fase 4 del requerimiento*
- Tabla `public.recomendaciones_eventos` (DDL en `edw/07` + modelo SQLAlchemy).
- Repositorio catálogo/telemetría → servicio (`get_basket_recommendations`, heurísticas,
  eventos, KPIs) → schemas → endpoints en `sales.py` → dependencias en `dependencies.py`.
- Config `CROSS_SELL_*`. Tests unitarios (inference con loader fake, servicio con repos fake)
  e integración (endpoints). Verificar `GET /health` → `modelos_ml_listos: true`.

### Fase 5 — Frontend (Días 10-12) — *entregable Fase 5 del requerimiento*
- Tipos → servicio → hooks → componentes (`SaleAssistant`, `SuggestionCard`, `CrossSellKpiPanel`).
- Integración en `DashboardVentas.tsx`; eventos mostrada/aceptada conectados; si el ganador es
  el híbrido, la UI muestra el `motivo` diferenciado por fuente.
- `oxlint` + build; prueba end-to-end manual con usuario rol `ventas`.

### Fase 6 — Monitoreo y cierre (Día 13) — *entregable Fase 6 del requerimiento*
- KPI de conversión visible (Ventas/Gerencia).
- Documentación: instrucciones de reentrenamiento (README en `ml/` o auditoría 25), guía breve
  del vendedor, diagrama de arquitectura del módulo (en auditoría 25).
- Actualizar `CLAUDE.md` (endpoints nuevos, tabla `public.*` nueva) y cerrar auditoría 25 con
  lo aplicado y las métricas finales.

---

## 4. Dependencias y Secuencia

```
Fase 1 (auditoría + SELECTs)
   └─► Fase 2 (EDA + grid experimental + contrato v0.2.0 draft)
          └─► Fase 3 (competencia de estrategias → backtest → ganador → contrato active → publish)
                 └─► Fase 4 (backend: repos → servicio → endpoints → tests)  ◄─ requiere .pkl publicado
                        └─► Fase 5 (frontend: tipos → hooks → UI)            ◄─ requiere contratos API estables
                               └─► Fase 6 (KPIs + docs + CLAUDE.md)
```

Bloqueos conocidos: ninguno duro. El ETL roto (loaders borrados) solo afecta si se quiere
refrescar el EDW antes de entrenar.

## 5. Checklist de Auditoría (CLAUDE.md)

- [ ] Producción SAP: **cero escrituras**; validación solo `SELECT`.
- [ ] Entrenamiento SOLO desde EDW; filtros obligatorios (`dim_estado_documento <> -1`,
      `NOT es_devolucion`, `producto_sk <> -1`, llave `codart` no nombre).
- [ ] Contrato v0.2.0 escrito ANTES de entrenar (D-2); `active` solo tras validar.
- [ ] Sin hardcodes: `CROSS_SELL_*` y `ML_*` por env vars.
- [ ] Backend en capas; excepciones de dominio, no `HTTPException` en servicios.
- [ ] `ModelLoader` singleton inyectado; `loader.get_features()`, nunca `feature_names_in_`.
- [ ] Degradación con gracia (modelo caído ⇒ widget vacío, no 500).
- [ ] RBAC en todos los endpoints (`vendedor_checker` / gerencia para KPIs).
- [ ] PII: respuestas usan catálogo de productos (sin PII); nombres de cliente solo vía el
      mecanismo existente (`cliente_lookup`), nunca desde `edw.dim_cliente`.
- [ ] Tabla nueva en `public.*` (no en `edw.*`), con `fecha_carga`, DDL en `edw/07` + modelo ORM.
- [ ] Reglas de negocio nuevas documentadas en `02_reglas_negocio_validadas.md`.
- [ ] Sin secretos en el repo.

## 6. Riesgos Identificados y Mitigaciones

| Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|
| Baja cobertura de reglas (490 reglas vs catálogo completo) → muchas canastas sin sugerencia | Alta | Medio | Fallback por categoría/popularidad (Fase 2); medir cobertura en Fase 1 antes de fijar min_support |
| Margen no derivable de forma confiable (`ultcos` desactualizado/nulo) | Media | Medio | Validación en Fase 1; si falla, heurística de margen se pospone y se ordena solo por lift (documentado) |
| Precision@K baja en backtest (reglas ≠ comportamiento futuro) | Media | Alto | Competencia de 4 estrategias (§2.3.c) con grid de variables; no publicar regresiones (regla del pipeline) |
| Ningún candidato supera con claridad la línea base v0.1.0 | Media | Medio | El backtest es la puerta de decisión: se publica el mejor disponible y se documenta el techo alcanzado con evidencia (valor de tesis igual: comparación metodológica) |
| mlxtend/matriz cliente×producto no escalan con el volumen (~539k líneas) | Baja | Medio | EDA de Fase 2 dimensiona antes de entrenar; muestreo determinista `ML_*` y granularidad `codgrupo` como plan B |
| Costo del grid experimental alarga la Fase 3 | Media | Bajo | Grid acotado a las variables de §2.3.b; experimentos adicionales solo si el EDA los justifica |
| Doble instancia de lógica de recomendación (por cliente vs por canasta) divergiendo | Media | Medio | Ambos casos de uso comparten `inference.py` y el mismo artefacto; heurísticas solo en el servicio |
| Telemetría infla la BD app | Baja | Bajo | Índices + granularidad por evento; purga futura documentada |
| DDL de `public.recomendaciones_eventos` no aplicado en BD existente | Media | Medio | `Base.metadata.create_all` del backend la crea (patrón vigente); verificar en arranque |

## 7. Hitos y Entregas

| Hito | Día | Validación |
|---|---|---|
| Auditoría 25 + validaciones de datos | 1 | Documento en `docs/auditoria/` con SELECTs y decisiones |
| EDA + grid experimental + contrato v0.2.0 `draft` | 3 | Notebook con hallazgos; decisiones registradas en auditoría 25 |
| Modelo ganador seleccionado y publicado | 6 | Backtest supera línea base v0.1.0; `contract_validator` limpio; `GET /health` OK; experimentos en `REPORTE_MEJORA_MODELOS.md` |
| API cross-selling operativa | 9 | `pytest` unit+integration verdes; Swagger `/docs` |
| UI asistente de venta | 12 | Flujo e2e manual rol `ventas`; oxlint/build OK |
| KPIs + documentación + CLAUDE.md | 13 | Tasa de conversión visible; auditoría 25 cerrada |

## 8. Documentación Requerida

- [ ] `docs/auditoria/25_modulo_cross_selling.md` (antes de codificar; cerrar al final).
- [ ] `docs/auditoria/02_reglas_negocio_validadas.md` — reglas nuevas (formato de sugerencia,
      heurísticas, telemetría).
- [ ] `ml/REPORTE_MEJORA_MODELOS.md` — backtest Precision@K/Recall@K.
- [ ] `CLAUDE.md` — endpoints nuevos, tabla `public.recomendaciones_eventos`, estado del módulo.
- [ ] Guía del vendedor (breve, en `docs/features/` o dentro de la auditoría 25).

## 9. Consideraciones de Calidad de Datos

- Reutilizar los filtros ya validados del contrato (`population_filter`).
- Verificar que el fallback nunca sugiera el centinela `-1` ni productos no vigentes (SCD2:
  `es_vigente = TRUE`).
- `edw/06_verificacion.sql` no requiere cambios (no hay tablas `edw.*` nuevas); la tabla de
  telemetría se verifica desde el backend (tests de integración).

## 10. Notas y Observaciones

- **Alcance honesto para la tesis:** la "aceptación" de una sugerencia es un registro en la
  plataforma BI, no una línea de factura en SAP (el ERP no se toca). La tasa de conversión mide
  la utilidad percibida por el vendedor; el cruce contra ventas reales del EDW puede añadirse
  después como métrica de impacto.
- El requerimiento de "re-entrenamiento automático semanal" se resuelve con el mecanismo
  existente (`POST /admin/modelos/retrain`, solo dev) + la calendarización ya planificada en la
  Fase 6 de `docs/hoja_de_ruta_ejecucion.md`; no se introduce un scheduler nuevo en este módulo.
- El filtrado colaborativo item-item SÍ entra en la competencia de esta fase (§2.3.c); lo que
  queda como trabajo futuro son la factorización de matrices (SVD con `surprise`) y las pruebas
  A/B en vivo, con la justificación registrada en la auditoría 25.
- **Prioridad del módulo: ALTA.** El criterio de "hecho" no es que el endpoint responda, sino
  que el modelo publicado tenga métricas offline documentadas que superen (o acoten con
  evidencia) la línea base, cobertura medida, y KPI de conversión operando en producción.
