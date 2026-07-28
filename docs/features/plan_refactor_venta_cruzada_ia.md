# Plan — Rediseño del módulo de Venta Cruzada como Motor Inteligente de Recomendación Comercial

**Fecha:** 2026-07-27
**Estado:** propuesta (ninguna fase implementada)
**Alcance:** `ml/main.py`, `ml/src/data/make_dataset.py`, `ml/contracts/models/cross_sell_ranker.json` (nuevo), `ml/models/registry.json`, `ml/retrain_all.py`, `backend/app/ml/{model_loader,inference}.py`, `backend/app/services/cross_sell_engine_service.py` (nuevo), `backend/app/schemas/cross_selling.py`, `backend/app/api/routes/sales.py`, `backend/app/repositories/{catalog,prediction}_repository.py`, `frontend/src/pages/VentasCrossSelling.tsx` + `components/crossSelling/*`
**Auditoría previa requerida:** `docs/auditoria/40_refactor_venta_cruzada.md` (Fase 0 de este plan, aún no escrita)
**Skills aplicadas:** `backend-ml-serving`, `ml-training-pipeline`, `frontend-design`

---

## 0. Resumen ejecutivo

El requerimiento pide convertir el módulo de Venta Cruzada en un asistente comercial que responda
"¿qué le vendo a ESTE cliente y por qué?" usando toda la infraestructura ML existente, y
**el ranking de las sugerencias debe producirlo el modelo de ML**, no una fórmula de factores
ajustados a mano (decisión del usuario, 2026-07-27).

Esa decisión es la que estructura el plan, porque hoy **no se cumple**: el artefacto
`recommendation.pkl` no es un modelo que puntúe, es una **tabla de reglas** (`item_A, item_B,
score, fuente`); `inference.get_basket_recommendations` solo la filtra y la ordena
([inference.py:107-116](../../backend/app/ml/inference.py#L107-L116)), y toda la personalización
real vive en factores heurísticos escritos a mano en `PredictionService`
(`factor_margen = 1 + 0.3 × margen_relativo`, tope por categoría, inyección de popularidad). El
modelo aporta los **candidatos**; el **orden** lo decide código heurístico.

Por eso el núcleo del plan (Fase 2) es un **modelo de ranking supervisado nuevo — el 7º del
proyecto** — que aprende el orden a partir de compras reales del EDW, con el score item-item como
una feature más junto al perfil del cliente (RFM, churn, segmento) y del producto (margen, clase,
rotación). El item-item se conserva como generador de candidatos: es el ganador documentado de una
competencia de 31 configuraciones y no se descarta.

Tres de los quince cambios pedidos siguen sin ser implementables tal como están redactados con los
datos de este proyecto, y uno más quedó resuelto por esta decisión. Están en §2 con su
reformulación; el resto del plan las asume.

Este documento **no implementa nada**: define el orden, los contratos y los criterios de
validación. La regla del `CLAUDE.md` aplica: la auditoría (Fase 0) va antes del primer cambio de
código.

---

## 1. Estado real del módulo hoy (verificado en código, 2026-07-27)

| Pieza | Archivo | Qué hace hoy |
|---|---|---|
| Página | `frontend/src/pages/VentasCrossSelling.tsx` (68 líneas) | Header + panel de top-combinaciones + autocompletar de cliente (**opcional**, solo excluye lo ya comprado) + asistente de canasta |
| Asistente | `components/crossSelling/SaleAssistant.tsx` | Canasta en `useState` local, autocompletar de producto, lista de `SuggestionCard` |
| Motor | `PredictionService.get_basket_recommendations` | item-item (`recommendation.pkl`) → filtro por fuente → factor de margen → diversificación por categoría (RN-CS3) → fallback por popularidad |
| Endpoints | `sales.py` | `POST /cross-selling/sugerencias`, `POST /eventos`, `GET /kpis`, `GET /top-combinaciones`, `GET /productos`, `GET /clientes` |
| Modelo | `ml/models/recommendation.pkl` (contrato v0.2.0) | Filtrado colaborativo item-item, similitud coseno, ventana 2 años, Precision@5=0.0769 |

**Correcciones de premisa del requerimiento** (para que el plan parta de hechos):

- **No existen "Combo #1 / #2 / #3"** en el código actual. La UI tiene un panel de *top
  combinaciones* (pares de productos co-ocurrentes, `catalog_repository.get_top_combinaciones`),
  sin numeración de combos. El CAMBIO 5 no es un renombrado: son **combos nuevos a construir**.
- **El buscador de cliente ya existe y ya es un autocomplete** (`components/ui/Autocomplete.tsx`,
  busca por nombre *y* por cédula/RUC vía `catalog_repository.search_clientes`). Lo que falta no es
  el componente sino el **payload**: hoy devuelve solo `{cliente_id, nombre}`. El CAMBIO 1 es
  enriquecer la respuesta, no reemplazar el widget.
- **Las recomendaciones ya son parcialmente personalizadas**: `get_basket_recommendations` excluye
  lo ya comprado por el cliente. Lo que no hacen es *cambiar el ranking* según el perfil del
  cliente. El CAMBIO 2 es un re-ranking, no un motor desde cero.
- **No hay ningún LLM en el proyecto.** `grep -riE "anthropic|openai|llm|claude|gemini"` sobre
  `backend/app`, `backend/requirements.txt` y `frontend/package.json` devuelve **0 resultados**.
  El "asistente IA" actual (`GoalsAISummaryPanel`) es un panel de reglas deterministas etiquetado
  como "IA". Esto condiciona los CAMBIOS 3 y 11 (ver §2.1).

---

## 2. Bloqueos reales y reformulaciones (leer antes de aprobar el plan)

### 2.1. "Explicabilidad de IA" y "copiloto conversacional" (CAMBIOS 3 y 11) — sin LLM en el stack

El CAMBIO 11 pide un asistente que responda preguntas abiertas ("¿qué debería vender?", "¿qué pasa
si agrego este producto?"). Eso requiere un LLM, que este proyecto no tiene, y agregarlo trae dos
consecuencias que son decisión de negocio, no técnica:

1. **Coste y dependencia externa nueva** en un proyecto que hoy corre 100% self-hosted en Docker.
2. **Riesgo de PII**: `public.cliente_lookup` es la única tabla con PII real y está aislada a
   propósito (regla 8). Un copiloto que responde sobre clientes concretos enviaría nombres/RUC a un
   tercero salvo que se anonimice el prompt.

**Dos opciones. Recomiendo la A** y el plan de fases la asume:

| | **Opción A — Explicabilidad determinista (recomendada)** | **Opción B — LLM real** |
|---|---|---|
| Qué | Narrativa generada por plantillas sobre las cifras reales de cada modelo. Un catálogo cerrado de preguntas frecuentes ("¿por qué esto?", "¿qué pasa si agrego X?") resuelto con los mismos endpoints | Provider LLM (Claude vía API) con las cifras del backend como contexto |
| Ventaja | Cero alucinación por construcción, cero coste, cero PII fuera; testeable con `pytest` | Preguntas abiertas de verdad |
| Costo | No responde nada fuera del catálogo de preguntas | API key, coste por request, anonimización obligatoria, tests no deterministas |
| Honestidad de etiqueta | Debe etiquetarse "Explicación del modelo", **no "IA generativa"** | "IA" es literal |

En ambos casos, **las cifras salen siempre del backend** — la capa de lenguaje nunca calcula.

**SHAP/LIME (mencionado en el CAMBIO 3):** aplicable solo parcialmente.

- `churn_rf` es un clasificador supervisado de árboles → **SHAP sí aplica** (`shap.TreeExplainer`,
  barato sobre 4 features: `recency`, `frequency`, `monetary_value`, `average_ticket`).
- `recommendation.pkl` **no es un modelo supervisado** — es una matriz de similitud coseno
  item-item. SHAP no tiene nada que explicar ahí. Su explicabilidad honesta es la
  **descomposición del score de ranking**, que ya es explícita en el código:
  `score_item_item × factor_margen`, más el ajuste de diversidad RN-CS3. Exponer esos tres
  sumandos es explicabilidad real; presentar un "SHAP" fabricado sobre él sería lo contrario.
- `shap` no está en `backend/requirements.txt` — es dependencia nueva (~50 MB con sus transitivas).

### 2.2. Qué etiqueta permite entrenar el ranking (habilita el CAMBIO 2) y cuál no existe (CAMBIO 4)

Para que el orden lo decida un modelo hace falta una **etiqueta**: qué sugerencia era buena. Hay
dos candidatas y la diferencia entre ellas decide el plan.

**(a) Telemetría de aceptación** — `public.recomendaciones_eventos` (`mostrada/aceptada/rechazada`,
RN-CS2). Etiqueta directa de lo que se quiere optimizar, pero con dos problemas: volumen
desconocido (se mide en A0-1) y **sesgo de exposición** — solo hay etiqueta para lo que el motor
actual ya mostró, así que un modelo entrenado ahí aprende a imitar al motor actual, no a superarlo.

**(b) Compra real posterior (recomendada, es la que usa el plan).** El EDW **sí tiene** la etiqueta
que importa: dado un cliente con su historial hasta la fecha `T`, ¿compró el producto `B` en la
ventana `(T, T+h]`? Sale de `fact_ventas_detalle`, es abundante (~539k líneas), no depende de
telemetría acumulada y no tiene sesgo de exposición. Es el planteamiento estándar de
*next-product-to-buy*, y el pipeline ya tiene el patrón de cortes temporales que necesita:
`fetch_churn_data` lo implementa para evitar la circularidad H-05 (features con datos `<= T`,
etiqueta en `(T, T+h]`).

Con (b) el ranking es un problema supervisado real, evaluable con el mismo backtest temporal que ya
se usó para elegir el item-item (Precision@K / Recall@K / Hit-Rate@5), y **SHAP aplica de verdad**
porque el ranker sí es un modelo de árboles — lo que resuelve la explicabilidad del CAMBIO 3 sin
inventar nada (§2.1).

La telemetría (a) no se descarta: se conserva como **métrica de negocio** (tasa de aceptación real,
ya expuesta por `GET /cross-selling/kpis`) para medir si el modelo nuevo mejora en producción, que
es su uso honesto dado el sesgo de exposición.

#### Lo que sigue sin ser entrenable: "probabilidad de cierre de la venta" (CAMBIOS 4, 12)

Pedido: predecir la probabilidad de cerrar la venta de una canasta.

**El EDW no tiene ventas perdidas.** `fact_ventas_detalle` contiene facturas emitidas (regla 1:
`estado='P'` procesada, `'A'` anulada). No hay cotizaciones rechazadas, oportunidades perdidas ni
carritos abandonados: el ERP no los registra y el módulo no es transaccional (el asistente arma una
canasta *simulada*, SAP factura). Sin ejemplos negativos no existe etiqueta y no se puede entrenar
ni evaluar un clasificador de cierre. Cualquier número mostrado ahí sería inventado.

Nótese que esto **no bloquea** el ranker de §2.2(b): "¿ordenó bien las sugerencias?" y "¿se cerró
la venta?" son preguntas distintas, y solo la segunda carece de datos. En la UI, el lugar de ese
KPI lo ocupa la **probabilidad de compra del producto sugerido**, que sí es la salida calibrada del
ranker, con su nombre real.

Mismo criterio para "probabilidad de recompra" y "probabilidad de fidelización" del CAMBIO 4:
`churn_rf` ya predice `probabilidad_abandono`. **Probabilidad de recompra ≈ 1 − p(abandono)** es la
misma cifra reexpresada; se muestra una vez, con su nombre real, no tres KPIs distintos que
sugieran tres modelos independientes.

### 2.3. Estacionalidad (CAMBIO 9) — el modelo item-item no tiene dimensión temporal

Pedido: selector Histórico / 90d / 30d / 7d que cambie las recomendaciones.

`recommendation.pkl` es una matriz de similitud **estática** entrenada sobre una ventana fija de 2
años (contrato v0.2.0, `data_range.ventana_anios: 2`). No acepta una ventana por request.

**El ranker de §2.2(b) resuelve esto sin artefactos por ventana y sin pesos a mano.** La recencia
entra como **features del modelo** —ventas del producto en los últimos 7 / 30 / 90 días
normalizadas por su media histórica, más mes y semana del año del corte `T`— y el modelo **aprende
cuánto pesa cada una** en vez de heredar un `W_RECENCIA` inventado. El selector de la UI
(`hist|90d|30d|7d`) pasa a ser un input de inferencia, no un artefacto distinto.

Esto es exactamente lo que se descarta al hacerlo con un factor multiplicativo fijo: si el negocio
es estacional, el peso correcto de "ventas de los últimos 7 días" no es constante entre categorías,
y un modelo de árboles lo captura por interacción; una constante en `config.py` no.

Las alternativas descartadas, para dejar constancia: entrenar 4 artefactos item-item (uno por
ventana) multiplica por 4 el gating/promoción/versionado y 7 días de datos no sostienen una matriz
de similitud; recalcular co-ocurrencia en SQL por request pone una query pesada en el camino
caliente del asistente.

**"Festividades" queda fuera:** `dim_fecha.es_feriado` nunca se pobló (hallazgo abierto de la
auditoría 05) y el pipeline de ML usa un workaround hardcodeado. Poblar esa columna es trabajo de
ETL, no de este módulo; si el negocio lo quiere, va como ítem separado.

### 2.4. CLV, márgenes y stock (CAMBIOS 1, 12) — cobertura parcial de datos

- **CLV no existe** en ningún lado del proyecto. Es calculable, pero hay que decidir cuál:
  **histórico** (`SUM(subtotal_neto)` del cliente, determinista, cero riesgo) o **predictivo**
  (BG/NBD + Gamma-Gamma, modelo nuevo). **Recomiendo el histórico** en la Fase 1, etiquetado
  "Valor histórico del cliente", que es exactamente lo que `Cartera360Repository` ya calcula como
  `valor_historico` — reutilizarlo, no duplicar la query.
- **Margen incompleto:** `dim_producto.costo_promedio` es NULL o 0 para parte del catálogo
  (H25-4, auditoría 25). El schema actual ya lo maneja bien (`margen_unitario: float | None`, no
  inventa un costo). **Los KPIs de margen del CAMBIO 12 deben propagar ese `None` hasta la UI**
  ("margen no disponible"), nunca degradarlo a 0 — un 0 se lee como "producto sin ganancia".
- **Stock:** `fact_inventario_snapshot` solo está poblada hacia adelante (<1% histórico pre-2026).
  Para "¿hay stock hoy?" sirve; para tendencias de stock, no. El filtro de stock del CAMBIO 14 se
  limita a disponibilidad actual.

---

## 3. Arquitectura objetivo

Arquitectura de dos etapas (**candidatos → ranking aprendido**), el patrón estándar de un motor de
recomendación en producción y el que hace que el orden lo decida ML:

```
ETAPA 1 — GENERAR CANDIDATOS (barato, alto recall)
  association (recommendation.pkl, item-item)  ──► ~50 codart candidatos
  ya validado: Precision@5=0.0769, cobertura 97.9%, ganador de 31 configuraciones

ETAPA 2 — RANKEAR (el modelo decide el orden)  ◄── ESTO ES LO NUEVO
  cross_sell_ranker.pkl  (7º modelo, clasificador de árboles, contrato propio)
    features del par (cliente, producto candidato):
      · score_item_item, misma_categoria_que_canasta      ← afinidad
      · recency, frequency, monetary_value, average_ticket ← RFM (mismas 4 de churn_rf)
      · p_abandono (churn_rf), segmento_rfm (segmentation) ← modelos existentes como features
      · margen_relativo, precio_relativo_categoria         ← economía del producto
      · ventas_7d / 30d / 90d normalizadas, mes, semana    ← estacionalidad (§2.3)
      · ya_compro_categoria, dias_desde_ultima_compra_cat  ← historial del cliente
    salida: p(compra del producto en (T, T+h])  → orden + KPI "probabilidad de compra"
    explicabilidad: SHAP TreeExplainer sobre estas features (real, §2.1)
                                │
FILTROS DE NEGOCIO (no ranking): stock, ya comprado, RLS de cartera
                                ▼
              CrossSellEngineService  →  /analytics/ventas/cross-selling/*
                                ▼
              VentasCrossSelling.tsx (Zustand + TanStack Query)
```

Consecuencia directa de la decisión del usuario: **`factor_margen`, `W_RECENCIA`,
`factor_segmento` y `factor_estrategia` dejan de existir como constantes.** El margen, la
recencia, el segmento y el riesgo de fuga pasan a ser **features** y el modelo aprende su peso
—incluidas las interacciones, p. ej. que el margen pese distinto en un cliente en riesgo que en un
cliente VIP, algo que un producto de constantes no puede representar.

Lo que **no** pasa a ser ML, a propósito: los filtros duros (stock, RLS, excluir lo ya comprado)
son reglas de negocio, no preferencias que se aprendan; y el tope de diversidad por categoría
(RN-CS3) se mantiene como post-proceso porque es una decisión comercial explícita —el vendedor
quiere ver opciones de otras categorías aunque el modelo prefiera cinco variantes de lo mismo—, no
un defecto del ranking.

**Decisiones de arquitectura:**

1. **Servicio nuevo, no engordar `PredictionService`.** Ya tiene 590 líneas y 6 casos de uso
   genéricos. El motor de venta cruzada compuesto va en `app/services/cross_sell_engine_service.py`
   y **consume** `PredictionService` por inyección — la misma frontera que respeta
   `Cartera360Service`. Los 6 endpoints actuales siguen apuntando a `PredictionService` sin
   cambios (retrocompatibilidad).
2. **Endpoints aditivos.** Ningún contrato existente cambia de forma. Los campos nuevos en
   respuestas existentes van como **opcionales** (`| None`), el mismo patrón con que Comisiones
   Variables extendió `/commissions`.
3. **Un endpoint por pregunta, no uno que devuelva todo.** El CAMBIO 1 pide refresco automático de
   todo el dashboard al elegir cliente: eso se resuelve con queries paralelas de TanStack Query
   sobre endpoints independientes (cada panel con su propio skeleton), no con un mega-endpoint que
   tarda lo que su parte más lenta.
4. **El camino caliente corre el ranker, no los 6 modelos.** Cada cambio de canasta ejecuta:
   lookup en la tabla de reglas (item-item) + **una** llamada vectorizada al ranker sobre ~50
   candidatos (una matriz de 50 filas, no 50 predicciones — el patrón de
   `get_churn_risk_batch`). Las features de cliente (RFM, churn, segmento) se resuelven **una vez**
   al seleccionar cliente y se reutilizan en cada recálculo: no dependen de la canasta. Presupuesto
   objetivo: < 300 ms p95, medido contra la línea base A0-6.
5. **El ranker entra al ciclo MLOps existente, no por fuera.** Clave `cross_sell_ranker` en
   `ml/models/registry.json` con su `metric_gate` (`precision_at_5`, `maximize`), entrenado por
   `ml/main.py::train_cross_sell_ranker` e incluido en `ml/retrain_all.py` — así el gating y la
   promoción automática de la Fase 3 del plan de pipeline ML lo cubren desde el día uno. No se
   repite el patrón del ganador de cross-selling publicado a mano por un script aparte, que ya
   causó un problema real documentado en `ml/main.py:244-256`.
6. **RLS obligatoria en todo endpoint nuevo con `cliente_id`.** La fuga de la auditoría 34 (H-V2,
   cualquier vendedor consultaba cualquier cliente) se cerró con
   `_verificar_pertenencia_cartera`. Cada endpoint nuevo de este plan que reciba `cliente_id`
   **debe** llamarlo, y cada uno debe tener un test que verifique el 403. Sin excepción.

---

## 4. Fases

### Fase 0 — Auditoría previa (`docs/auditoria/40_refactor_venta_cruzada.md`)

Obligatoria antes de tocar código (flujo del `CLAUDE.md`). Entregables, todos con evidencia SQL:

| # | Pregunta a responder | Query / método | Decide |
|---|---|---|---|
| A0-0 | **¿Alcanza el volumen para entrenar el ranker?** Pares `(cliente, producto)` positivos por corte `T`: clientes que compraron un producto nuevo en `(T, T+60d]`, sobre ~24 cortes mensuales | Cortes sobre `fact_ventas_detalle` con la definición de §Fase 2.2 | **Si la Fase 2 es viable.** Es el primer entregable: sin positivos suficientes, no hay ranker y el plan vuelve a factores heurísticos |
| A0-1 | ¿Cuántos eventos hay en `recomendaciones_eventos` y cuál es el balance aceptada/rechazada? | `SELECT evento, COUNT(*) FROM public.recomendaciones_eventos GROUP BY 1` | Si se abre la Fase 7 (§2.2) |
| A0-2 | ¿Qué % del catálogo vigente tiene `costo_promedio` no nulo y > 0? | `dim_producto WHERE es_vigente` | Cobertura real de los KPIs de margen |
| A0-3 | ¿Cuántos clientes tienen historial suficiente para RFM/churn? ¿Qué % de la cartera típica queda "sin historial"? | `fact_ventas_detalle` agrupada por `cliente_sk` | Cuánto pesa el estado vacío del CAMBIO 1 |
| A0-4 | ¿`fact_inventario_snapshot` tiene stock actual para los productos que el motor sugiere? | Cobertura de `codart` sugeridos vs. snapshot del último día | Si el filtro de stock es viable |
| A0-5 | ¿La afinidad local por sucursal (0/20 de intersección top-20, contrato v0.2.0 `notes`) invalida el modelo global para un vendedor concreto? | Precision@5 del artefacto actual segmentada por sucursal | Si hace falta un ajuste por sucursal (riesgo conocido, hoy sin cuantificar por vendedor) |
| A0-6 | Latencia actual de `POST /cross-selling/sugerencias` con canasta de 1..5 ítems | Medición contra el backend real | Línea base de rendimiento del CAMBIO 4 |

**A0-0 y A0-5 son los dos que pueden invalidar la Fase 2.** El primero decide si hay datos para
entrenar el ranker; el segundo, si la personalización tiene techo. El propio contrato documenta que
la afinidad entre productos es fuertemente local por sucursal y que el módulo sirve un modelo
global único. Si la degradación por sucursal es grande, ni el ranker lo arregla —la etapa de
candidatos seguiría siendo global— y habría que evaluar `sucursal` como feature del ranker o un
modelo por sucursal. Hay que saberlo antes de prometer personalización, no después del backtest.

---

### Fase 1 — Cliente 360 en el centro (CAMBIO 1)

**Backend**

1. `CatalogRepository.search_clientes` → enriquecer el payload: `ciudad`, `ultima_compra`,
   `frecuencia_12m`, `n_compras`. Una sola query con agregados por `cliente_sk`, **sin ML** (el
   autocompletar dispara con cada tecla; correr modelos ahí es inaceptable). `ClienteBusqueda` gana
   esos campos como **opcionales** para no romper al consumidor actual.
2. Endpoint nuevo `GET /analytics/ventas/cross-selling/clientes/{cliente_id}/perfil` →
   `PerfilClienteResponse`. Compone en una llamada lo que ya existe: `get_churn_risk` +
   `get_customer_segment` + agregados SQL nuevos (antigüedad, ticket promedio, frecuencia, valor
   histórico reutilizando el cálculo de `Cartera360Repository`, categoría/marca/productos
   favoritos). **Con `_verificar_pertenencia_cartera`.**
3. `probabilidad_recompra = 100 − probabilidad_abandono`, expuesta una sola vez y documentada en el
   schema como derivada de `churn_rf` (§2.2), no como modelo aparte.

**Frontend**

4. `VentasCrossSelling.tsx`: el cliente deja de ser opcional y pasa a ser el estado raíz de la
   página. Estado en **Zustand** (`store/crossSellStore.ts`) porque lo consumen paneles hermanos no
   anidados; la canasta vive en el mismo store (Fase 4).
5. Panel `ClientProfileCard` con skeleton por sección. Estado vacío cuando no hay cliente: no un
   spinner, sino la invitación a buscar uno (regla de copy del brief de diseño).

**Validación:** `pytest` de RLS (403 con cliente ajeno · 200 para gerencia) · latencia del
autocompletar bajo la línea base A0-6 · caso "cliente sin historial" renderiza el estado vacío, no
ceros.

---

### Fase 2 — `cross_sell_ranker`: el 7º modelo (CAMBIOS 2, 3, 7, 8, 9)

El corazón del plan y la fase más larga. Sigue **en orden** el flujo de la skill
`ml-training-pipeline` (contrato primero, D-2 — el contrato es el diseño, nunca se deriva del
`.pkl`).

**2.1 · Contrato primero.** `ml/contracts/models/cross_sell_ranker.json`, `status: "draft"` durante
todo el desarrollo, `active` solo al validar. Declara las features del diagrama de §3, el
`population_filter` (mismos filtros de negocio de siempre: `dim_estado_documento` con
`estado_documento_sk <> -1`, `NOT es_devolucion`, centinelas `cliente_sk/producto_sk <> -1`) y el
`plausible_range` de la salida `[0, 1]`.

**2.2 · Dataset con cortes temporales** — `make_dataset.py::fetch_cross_sell_ranking_data`. Es la
parte donde este pipeline ya se equivocó antes (circularidad H-05), así que el diseño es explícito:

- Varios cortes `T` (p. ej. mensuales sobre 2 años) para multiplicar ejemplos sin reusar el mismo
  snapshot. **Todas** las features se calculan con datos `<= T`; la etiqueta con `(T, T+h]`,
  `h = ML_RANKER_HORIZONTE_DIAS` (default 60, parametrizado como el resto).
- **Positivos:** pares `(cliente, producto)` que el cliente compró en `(T, T+h]` y no había
  comprado antes. **Negativos:** candidatos que el item-item habría propuesto en `T` y que el
  cliente **no** compró en la ventana. Muestreo de negativos controlado y declarado (ratio como
  env var) — negativos aleatorios del catálogo completo darían un modelo que solo aprende a
  distinguir "producto plausible" de "producto irrelevante", que es lo que el item-item ya hace.
- Combina dos hechos, así que aplica el patrón obligatorio de la skill: **agregar cada hecho por
  separado al grano común y unir los agregados** (CTEs), nunca JOIN directo entre facts —
  granularidades distintas producen fan-out. Verificar cardinalidad con `COUNT(*)` por CTE antes de
  dar el SQL por bueno.
- Riesgo a vigilar: el volumen de pares crece rápido. Acotar candidatos por corte y muestrear
  clientes de forma **determinista** (`ORDER BY cliente_sk DESC`, nunca `LIMIT` sin orden).

**2.3 · Entrenamiento** — `ml/main.py::train_cross_sell_ranker` reutilizando
`find_best_classification_model` (competencia RF/XGBoost/LightGBM/CatBoost ya existente, con
`hyperparameter_search=True`). **Split cronológico por corte `T`** (cortes viejos entrenan, cortes
recientes evalúan) — nunca aleatorio, aunque churn use estratificado: aquí los cortes comparten
clientes y un split aleatorio filtraría el futuro.

**2.4 · Backtest contra la línea base, con criterio de decisión previo.** La línea base es el
motor actual completo (item-item + factores heurísticos), medido con el mismo protocolo del
backtest de la auditoría 25: split temporal, Precision@5 / Recall@5 / Hit-Rate@5 / cobertura.

> **Regla de decisión, fijada antes de ver resultados:** si el ranker no supera
> `Precision@5 = 0.0769` (línea base) manteniendo cobertura ≥ 97.9%, **no se promueve** y el módulo
> se queda con el motor actual. Se documenta el resultado —positivo o negativo— en
> `ml/REPORTE_MEJORA_MODELOS.md`, igual que los 31 experimentos previos. Un modelo nuevo que
> empata no justifica el coste operativo de un artefacto más.

Esta regla es la que hace que "usar el modelo" sea una mejora verificada y no un acto de fe: el
gating de `promotion.py` la aplica automáticamente en cada reentrenamiento.

**2.5 · Serving** (skill `backend-ml-serving`): entrada `cross_sell_ranker` en `_MODEL_FILES`,
función `predict_cross_sell_ranking` en `inference.py` (patrón `_select_features` →
`_validate_features_or_raise` → `predict_proba` → validación de rango), y
`CrossSellEngineService` orquestando repo → features → inferencia → formateo, con el `try/except`
de degradación de siempre: **si el ranker falla, se cae al orden por score item-item**, que es el
comportamiento actual. Un modelo caído degrada la calidad del orden, no tumba el asistente.

**2.6 · Explicabilidad real (CAMBIO 3).** `shap.TreeExplainer` sobre el ranker devuelve la
contribución de cada feature a cada sugerencia. Eso es lo que alimenta el "¿por qué estoy viendo
esto?" y la barra de descomposición de la Fase 5 — ahora con contribuciones medidas, no con los
términos de una fórmula escrita a mano. SHAP corre sobre ~50 filas y 15 features: barato, pero se
cachea por `(cliente, canasta)` igual que el resto.

**Lo que el modelo absorbe (ya no son constantes):** margen (CAMBIO 2), estacionalidad y ventana
(CAMBIO 9), segmento (CAMBIO 7) y riesgo de fuga (CAMBIO 8) entran como features. En particular el
CAMBIO 8 deja de ser un `if p_abandono > 0.5: invertir prioridad de margen` para pasar a ser una
interacción aprendida entre `p_abandono` y las features de precio/margen — que es la forma correcta
de preguntarle a los datos si un cliente en riesgo compra distinto, en vez de asumirlo.

**Sigue sin ser ML, con motivo:**

- **CAMBIO 7 (nombres de segmento):** el mapa `cluster_id → nombre` sale del sidecar vía
  `inference.get_cluster_to_segment`, **nunca de un dict hardcodeado** (H-12, ya corregido una
  vez). El modelo tiene **K=4**; de los 7 perfiles del requerimiento, 4 vienen de RFM y "riesgo
  alto" de `churn_rf`, pero **"corporativo" y "flota" no existen como atributo en el EDW**. Se
  implementan los 5 derivables; los 2 restantes se documentan como no disponibles.
- **Etiquetas del CAMBIO 6** (Complementario / Reemplazo / Alta Rentabilidad…): son descripciones
  de un producto, no predicciones. Se derivan de reglas declaradas sobre datos reales
  (categoría distinta a la canasta, margen sobre el percentil configurado). Sin regla derivable ⇒
  sin etiqueta.
- **Descuentos (CAMBIO 8):** fuera de alcance. El sistema no tiene motor de precios ni autoridad
  para ofertar; sugerir un descuento que el ERP no aplicará es una promesa falsa al vendedor.

**Validación:** `contract_validator` limpio · dos clientes con perfiles distintos y la misma
canasta reciben rankings distintos (criterio de éxito nº1 del requerimiento, como test) · la suma
de contribuciones SHAP reconstruye el score mostrado (el desglose no puede mentir sobre el
ranking) · el backtest supera la línea base según la regla de 2.4 · `pytest` en `ml/` y en
`backend/` · p95 del endpoint bajo presupuesto (§3.4).

---

### Fase 3 — Canasta inteligente y simulación (CAMBIOS 4, 12)

1. `POST /cross-selling/simular` → `SimulacionVentaResponse`:
   `ticket_estimado` (suma real de precios de catálogo, no una predicción),
   `margen_estimado` (`None` donde falte costo — §2.4),
   `incremento_vs_ticket_promedio_cliente` (dato histórico real),
   `probabilidad_recompra` (de `churn_rf`),
   `probabilidad_compra_por_producto` (del ranker, Fase 2),
   `explicacion` (narrativa determinista sobre esas cifras, §2.1).
   **No incluye "probabilidad de cierre"** (§2.2).
2. Recálculo en vivo: la canasta en Zustand dispara una query con `useDebouncedValue` (**el hook ya
   existe**, `hooks/useDebouncedValue.ts`) y `keepPreviousData` para que los KPIs no parpadeen.
3. KPIs del CAMBIO 12: `support`/`confidence` **solo se muestran cuando la fuente los pobla** — el
   ganador item-item los deja NULL por construcción (`known_serving_mismatch` del contrato). Un
   panel que muestre "Lift: 0.00" para todas las sugerencias sería un bug de presentación, no un
   KPI. Se muestra el score de afinidad con su nombre real.

**Validación:** `Simular Venta` con canasta vacía → 400 · con productos sin costo → margen `None`
propagado hasta la UI · sin llamadas redundantes al backend por tecla (debounce verificado).

---

### Fase 4 — Combos inteligentes (CAMBIOS 5, 6)

Construcción nueva (no existían — §1). `GET /cross-selling/combos?cliente_id=&ventana=`: 3-5 combos
de 2-4 productos, cada uno generado por una **estrategia declarada** que le da su nombre comercial:

| Nombre comercial | Estrategia (real, no etiqueta) |
|---|---|
| Oferta Estrella | Mayor afinidad item-item con la canasta/historial |
| Mayor Rentabilidad | Maximiza margen agregado (solo con costo disponible) |
| Cliente Frecuente | Reincidencia histórica del propio cliente |
| Protección Total | Complementarios de categoría distinta (etiqueta "Preventivo") |
| Ideal para Flotas | **Condicionado a A0-3**: requiere identificar clientes de volumen. Si el EDW no lo soporta, no se emite |

Cada combo devuelve `confianza`, `incremento_esperado`, `margen_esperado`, `afinidad`,
`popularidad` y el `porque` del CAMBIO 6, todos derivados de los datos que ya calcula el motor.
**Un combo sin datos para su estrategia no se emite** — mejor 3 combos reales que 5 con dos
rellenos.

---

### Fase 5 — Rediseño de la interfaz (CAMBIOS 10, 13, 15)

**Punto de partida:** el proyecto **ya tiene un sistema de diseño oscuro coherente**
(`frontend/src/index.css`: `@theme` con `--font-display: Fraunces`, `IBM Plex Sans`, `JetBrains
Mono`, superficies `#0B0F19..#1A2235`, primario `#6D5DF6`, paleta de 8 colores de gráfico, curvas de
easing y duraciones declaradas). El requerimiento pide "dark theme, glassmorphism, cards modernas" —
**eso ya está resuelto y es consistente en los 4 dashboards**. Rediseñar esta página con un lenguaje
visual propio la desconectaría del resto del producto.

**Por tanto el trabajo de diseño no es una paleta nueva, es una jerarquía nueva.** Es lo que
realmente pide el CAMBIO 10 ("el mejor combo debe destacarse"): hoy todas las sugerencias son
`SuggestionCard` del mismo tamaño y peso, y la página no comunica qué mirar primero.

**El elemento distintivo propuesto** (uno solo, el resto se mantiene disciplinado): la **barra de
descomposición del score**. Cada sugerencia muestra su ranking como segmentos proporcionales
—afinidad · margen · recencia · segmento· estrategia— usando la paleta de gráficos existente. Es
literalmente la explicabilidad de la Fase 2 hecha objeto visual: el vendedor *ve* por qué un
producto quedó primero, y al pasar el cursor cada segmento nombra su factor con su cifra. Ninguna
otra página del producto tiene algo así, es específico de este módulo, y no es decorativo: si el
motor cambia el ranking, la barra cambia de forma.

- Jerarquía: la recomendación principal a doble ancho con la barra completa; las secundarias en una
  fila compacta con la barra reducida a una línea de 3 px.
- Motion: se reutilizan `--duration-*` y `--ease-out-soft` ya definidos; la única animación nueva es
  la transición de la barra al recalcularse la canasta — mueve información, no adorna. `prefers-reduced-motion` respetado.
- Visualizaciones (CAMBIO 13): **priorizar 3 de las 7 pedidas** — timeline del historial del
  cliente, radar del perfil RFM y evolución del ticket promedio, todas con datos que la Fase 1 ya
  trae. El heatmap de afinidad y el network graph de productos son atractivos pero exigen un
  endpoint de matriz N×N que no aporta a la decisión de "qué le vendo a este cliente"; quedan como
  backlog explícito, no se prometen. El "árbol de decisión simplificado" no aplica: el ganador es
  item-item, no un árbol (§2.1).
- Rendimiento (CAMBIO 15): TanStack Query y Zustand **ya son el estándar del proyecto** (no se
  introduce nada); se agrega `React.lazy` para los gráficos de Recharts, virtualización solo si
  A0-3 muestra listas largas de verdad, y optimistic UI en agregar/quitar de la canasta (es estado
  local, no hay request que revertir).

---

### Fase 6 — Explicabilidad avanzada y asistente (CAMBIOS 3, 11) · requiere decisión de §2.1

Con la **Opción A**: panel "¿Por qué esto?" por sugerencia, catálogo cerrado de preguntas
resueltas contra los endpoints de las fases 2-4, y SHAP real **solo para churn** (`shap` a
`backend/requirements.txt`, `TreeExplainer` sobre 4 features, resultado cacheado por cliente).
Etiquetado "Explicación del modelo".

Con la **Opción B**: además, proveedor LLM, anonimización obligatoria del prompt (nunca nombre/RUC),
y las cifras siempre inyectadas desde el backend como contexto — el LLM redacta, no calcula.

---

### Fase 7 — Realimentación con telemetría (condicionada a A0-1)

El ranker de la Fase 2 aprende de compras reales (§2.2b), no de la telemetría. Esta fase cierra el
lazo: una vez el módulo nuevo lleve tiempo en uso, `recomendaciones_eventos` tendrá etiquetas de
aceptación **generadas por el ranker**, no por el motor heurístico anterior.

Dos usos, en este orden:

1. **Medición (siempre, sin precondición):** comparar la tasa de aceptación antes/después del
   ranker sobre `GET /cross-selling/kpis`. Es la única evidencia de que la mejora del backtest se
   traduce en comportamiento real del vendedor.
2. **`aceptada` como feature o etiqueta auxiliar (condicionada):** solo con ≥ 2.000 eventos y ≥ 15%
   de clase minoritaria (medido en A0-1). Con el sesgo de exposición de §2.2(a) presente, entra
   como señal secundaria en el ranker existente, **no** como un 8º modelo — un modelo entrenado
   solo con lo que el motor ya mostró aprende a imitarse a sí mismo.

---

## 5. Contratos nuevos (resumen)

Todos aditivos, en `backend/app/schemas/cross_selling.py`; espejo en `frontend/src/types/crossSelling.ts`.

| Endpoint | Fase | Notas |
|---|---|---|
| `GET  /cross-selling/clientes/{id}/perfil` | 1 | RLS obligatoria |
| `POST /cross-selling/recomendaciones` | 2 | Reemplaza *funcionalmente* a `/sugerencias`, que **se conserva** intacto |
| `POST /cross-selling/simular` | 3 | RLS obligatoria |
| `GET  /cross-selling/combos` | 4 | RLS si trae `cliente_id` |
| `GET  /cross-selling/clientes?q=` | 1 | Existente, payload enriquecido con campos opcionales |

Campos nuevos en `SugerenciaProducto` (todos opcionales): `probabilidad_compra: float | None`
(salida del ranker), `explicacion: ExplicacionSugerencia | None` (contribuciones SHAP por feature),
`etiquetas: list[str]`, `stock_disponible: bool | None`.

**Artefacto ML nuevo:** `ml/models/cross_sell_ranker.pkl` + `.meta.json` +
`ml/contracts/models/cross_sell_ranker.json`; clave `cross_sell_ranker` en `registry.json`
(`metric_gate`: `precision_at_5`, `maximize`), en `_MODEL_FILES` del backend y en
`ml/retrain_all.py`. No requiere cambios de volumen Docker: los montajes son por directorio.

`config.py` — parámetros nuevos, ninguno hardcodeado: `CROSS_SELL_CANDIDATOS_N` (pool que entra al
ranker), `CROSS_SELL_UMBRAL_MARGEN_ALTO_PCT` (etiqueta, no ranking), `CROSS_SELL_COMBOS_N`,
`CROSS_SELL_MIN_EVENTOS_ACEPTACION`. Lado `ml/`: `ML_RANKER_HORIZONTE_DIAS`,
`ML_RANKER_RATIO_NEGATIVOS`, `ML_RANKER_CORTES_MESES`.
**Se retiran** `CROSS_SELL_PESO_MARGEN` y `CROSS_SELL_MIN_LIFT` del camino de ranking: el modelo
absorbe esa función. Se conservan mientras el ranker no esté promovido (fallback de §Fase 2.5).

---

## 6. Riesgos

| # | Riesgo | Mitigación |
|---|---|---|
| R-1 | **Afinidad local por sucursal** (contrato v0.2.0: 0/20 de intersección top-20 entre las 2 sucursales de mayor volumen) — la personalización tiene un techo estructural | Cuantificar en A0-5 **antes** de la Fase 2. Si es grave, es un plan aparte (modelo por sucursal), no un parche |
| R-2 | Precision@5 = 0.0769: ~1 de cada 13 sugerencias acierta | Es la métrica real del ganador de 31 candidatos, y la línea base que el ranker debe superar (regla de 2.4). La UI presenta sugerencias como opciones, no como certezas |
| R-3 | Etiquetar como "IA" lo que son reglas deterministas (deuda ya presente en `GoalsAISummaryPanel`) | Etiquetas honestas: "Explicación del modelo" · "Reglas de negocio" · "IA generativa" solo con Opción B |
| R-4 | Latencia: la canasta recalcula en cada cambio, ahora con un modelo en el camino | Debounce + features de cliente cacheadas + **una** inferencia vectorizada sobre ~50 candidatos (§3.4). Presupuesto p95 < 300 ms contra la línea base A0-6 |
| R-7 | **El ranker no supera la línea base** y el trabajo de la Fase 2 no se promueve | Es un resultado válido, no un fracaso: la regla de decisión de 2.4 está fijada de antemano y el gating la aplica solo. El módulo conserva el motor actual y las Fases 1, 3-6 siguen aportando valor por sí solas |
| R-8 | **Arranque en frío**: cliente nuevo o producto sin historial no tiene features de RFM/recencia | El ranker debe entrenarse con esos casos presentes (no filtrarlos del dataset) para que aprenda a puntuar con las features de producto solas. Test explícito del caso "cliente sin historial" |
| R-9 | Fuga temporal en el dataset de pares — el error más probable de la Fase 2, y ya ocurrió aquí (H-05) | Cortes `T` explícitos, features `<= T`, etiqueta en `(T, T+h]`, split cronológico por corte. Revisión dedicada en la auditoría 40 antes de entrenar. Una Precision@5 sospechosamente alta es señal de fuga, no de éxito |
| R-5 | Sobre-alcance: 15 cambios en una sola entrega | Fases 1-3 son el núcleo con valor propio; 4-7 son incrementales e independientes |
| R-6 | Regresión de la RLS de la auditoría 34 al agregar endpoints | Test de 403 obligatorio por endpoint nuevo con `cliente_id`, en la definición de terminado de cada fase |

---

## 7. Definición de terminado (por fase)

1. `pytest` verde en `backend/tests/` (unit + integration), con los tests nuevos de RLS.
2. `cd ml && python -m src.contracts.contract_validator` limpio — solo si la fase tocó `ml/`.
3. Probado contra el backend real reconstruido (`docker compose up --build backend`), no solo con
   mocks: `GET /health` → `modelos_ml_listos: true` y los endpoints nuevos ejercitados con
   `cliente_id` reales del EDW.
4. `docs/auditoria/40_refactor_venta_cruzada.md` actualizado con lo aplicado y la evidencia.
5. Reglas de negocio nuevas registradas en `docs/auditoria/02_reglas_negocio_validadas.md` §17
   (donde ya viven RN-CS1..CS3), numeradas RN-CS4 en adelante.
6. `CLAUDE.md` actualizado si cambió un contrato o se agregó un modelo.

Adicionales solo para la Fase 2 (modelo nuevo):

7. Métricas del backtest —supere o no la línea base— documentadas en
   `ml/REPORTE_MEJORA_MODELOS.md`, junto a los 31 experimentos previos de cross-selling.
8. `python retrain_all.py --model cross_sell_ranker` corre de punta a punta y deja traza en
   `public.ml_model_runs` (promoción o rechazo con su motivo).
9. `ml/tests/test_registry.py` sigue verde (falla si un `.pkl` en `ml/models/` no está en el
   registro) y el test de contrato del modelo nuevo existe.

---

## 8. Decisiones pendientes del usuario

1. **§2.1 — ¿Opción A (explicabilidad determinista) u Opción B (LLM real)?** Condiciona la Fase 6.
   Nota: con el ranker, la explicabilidad de las recomendaciones ya es SHAP real; la Opción B solo
   afecta al copiloto conversacional del CAMBIO 11.
2. **§2.2 — ¿Se acepta reemplazar "probabilidad de cierre de la venta" por "probabilidad de compra
   del producto sugerido"** (salida calibrada del ranker)? Sin esto, ese KPI no puede existir sin
   fabricar datos.
3. **§2.4 — ¿CLV histórico (recomendado) o predictivo (modelo nuevo)?**
4. **§4 Fase 4 — ¿Existe en el negocio una definición de "cliente de flota / corporativo"** que se
   pueda derivar del EDW? Si no, esos dos perfiles del CAMBIO 7 no se emiten.
5. **¿Se aprueba priorizar 3 de las 7 visualizaciones del CAMBIO 13**, dejando heatmap y network
   graph en backlog?
