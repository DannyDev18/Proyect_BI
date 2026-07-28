# Auditoría 40 — Fase 0 del refactor de Venta Cruzada (`plan_refactor_venta_cruzada_ia.md`)

- **Fecha:** 2026-07-28
- **Alcance:** viabilidad de datos para `docs/features/plan_refactor_venta_cruzada_ia.md` (motor de
  ranking `cross_sell_ranker`, 7º modelo ML del proyecto). Preguntas A0-0 a A0-6 definidas en el
  plan (líneas 276-291). Tablas consultadas: `edw.fact_ventas_detalle`, `edw.dim_estado_documento`,
  `edw.dim_fecha`, `edw.dim_producto`, `edw.dim_sucursal`, `edw.fact_inventario_snapshot`,
  `public.recomendaciones_eventos`, `public.usuarios`.
- **Método:** `SELECT` puro contra `bi_postgres_edw` (Docker, puerto host 5433) vía
  `docker exec bi_postgres_edw psql -U etl_user -d edw`. **Sin escrituras** a ningún esquema ni a
  Producción (SAP no se tocó en esta auditoría — todas las preguntas del plan son sobre el EDW). Los
  filtros de negocio usados replican exactamente el patrón ya validado en
  `ml/src/data/make_dataset.py` (`estado_documento_sk <> -1`, `NOT ed.es_devolucion`, centinelas
  `producto_sk`/`cliente_sk <> -1`), no un criterio nuevo inventado para esta auditoría. Donde se
  combinan hechos de distinto grano (A0-0) se usan CTEs que agregan cada grano por separado
  (`ventas_validas` → `pares_futuros`/`pares_historicos` por corte) y se unen después, evitando el
  JOIN directo entre grano-transacción y grano-corte que produciría fan-out.

## Hallazgos

### Informativo — A0-0 Volumen suficiente para entrenar el ranker (DECIDE la Fase 2: viable)

- **Evidencia:** `fact_ventas_detalle` válida cubre 2018-01-02 a 2026-07-16 (464.020 líneas). Se
  generaron cortes mensuales `T` desde `min_fecha + 6 meses` hasta `max_fecha - 60 días` (95 cortes
  posibles, más del doble de los "~24 cortes mensuales" que asume el plan). Para cada corte se
  contaron pares `(cliente, producto)` donde el producto se compró por primera vez en `(T, T+60d]`
  (positivo de *next-product-to-buy*) y no antes.
- **Consulta utilizada:** ver Anexo A (consulta A0-0). Verificación de cardinalidad: `pares_futuros`
  y `pares_historicos` se agregan a grano `(t, cliente_sk, producto_sk)` antes del `LEFT JOIN`, sin
  fan-out.
- **Resultado:** 95 cortes, 452.691 positivos totales, promedio **4.765 positivos por corte**
  (mínimo verificado en los primeros 6 cortes de 2018: 4.513–6.575, sin degeneración en cortes
  tempranos con poca historia acumulada).
- **Impacto:** con negativos muestreados (ratio configurable, `ML_RANKER_RATIO_NEGATIVOS`) sobre
  ~4.765 positivos/corte × ~24-95 cortes, el dataset de entrenamiento tiene un volumen muy superior
  al de `churn` (que ya entrena con éxito sobre cortes similares) y al de `demand` por
  `(producto, almacén)`. **No hay riesgo de volumen insuficiente.**
- **Riesgos:** ninguno de volumen. El riesgo real de esta fase es de fuga temporal (R-9 del plan),
  no de escasez de datos — la auditoría confirma que hay margen para ser estricto con los cortes
  (usar menos que los 95 disponibles, p. ej. los 24-36 más recientes, sin arriesgarse a quedar corto
  de ejemplos).
- **Recomendación:** proceder con la Fase 2. Usar el patrón `fetch_churn_data` (ya con snapshots
  temporales correctos, H-05) como base directa de `fetch_cross_sell_ranking_data`, no reinventar el
  mecanismo de cortes.

### Alta — A0-5 Afinidad item-item fuertemente local por sucursal (DECIDE el techo de personalización)

- **Evidencia:** las 2 sucursales de mayor volumen son `PRINCIPAL: MATRIZ` (190.697 líneas) y
  `SUC. EL REY` (173.493 líneas) — juntas concentran el 67% del volumen total. Se calculó el top-20
  de pares de coocurrencia (`codart_a < codart_b`, misma `num_factura`) para cada una por separado.
- **Consulta utilizada:** ver Anexo A (consulta A0-5).
- **Resultado:** **intersección = 0 de 20** entre el top-20 de `MATRIZ` y el top-20 de `EL REY`.
  Confirma exactamente la cifra que ya documentaba el contrato v0.2.0 de `recommendation.pkl`
  (`notes`), esta vez medida de forma independiente y no solo heredada del documento.
- **Impacto:** el generador de candidatos (item-item, etapa 1 de la arquitectura del plan) es un
  modelo **global** que no ve estas diferencias. El ranker de la Fase 2 puede reordenar los ~50
  candidatos que ese modelo global propone, pero **no puede inventar candidatos que el modelo
  global nunca generó** para esa sucursal. Si los productos realmente afines a un cliente de
  `EL REY` no están en el top-50 global (porque están dominados por los patrones de `MATRIZ`, la
  sucursal 3x más grande en el agregado), el ranker nunca los ve.
- **Riesgos:** promover el ranker sin abordar esto deja una personalización con techo estructural en
  la etapa de candidatos, exactamente el riesgo que el plan (R-1) ya anticipaba sin cuantificar.
  Cuantificado aquí: **no es un caso límite, es la mitad del volumen del negocio** (las 2 sucursales
  auditadas son el 67% de las líneas).
- **Recomendación:** **`sucursal` debe entrar como feature explícita del ranker** (ya está en el
  diagrama de features de la Fase 2 del plan como candidato implícito vía "misma categoría"; debe
  agregarse de forma explícita, no inferida). Esto no resuelve el techo de candidatos, pero sí evita
  que el ranker aprenda a rankear con features de un cliente de `EL REY` pesos calibrados para
  `MATRIZ`. Resolver el techo de candidatos (item-item por sucursal o item-item con `sucursal` como
  dimensión) queda fuera de esta fase — es un plan aparte, tal como el propio plan lo señala en R-1.
  **No es motivo para bloquear la Fase 2**, pero sí para no prometer personalización sin techo en la
  comunicación al negocio (§Fase 5, Fase 6).

### Media — A0-3 Arranque en frío: mayoría de la cartera con historial insuficiente

- **Evidencia:** de 53.910 clientes con al menos una venta válida, **57,82%** (31.172) tienen
  actividad en un solo día (compra única, sin recompra registrada) y **77,10%** (41.562) tienen
  menos de 3 meses de historial activo. Solo **7,42%** (4.000 clientes) tienen 6 o más meses de
  actividad — el umbral que hoy exige `demand_rf` para no caer al pronóstico estadístico.
- **Consulta utilizada:** ver Anexo A (consulta A0-3).
- **Impacto:** el perfil RFM/churn (features de cliente del ranker) será pobre o inexistente para
  más de la mitad de la cartera. Esto no invalida el ranker (R-8 del plan ya lo anticipa como
  riesgo, no como bloqueo), pero confirma que **la mayoría de las inferencias en producción caerán
  en el caso "cliente con historial escaso"**, no en el caso ideal con RFM completo.
- **Riesgos:** si el dataset de entrenamiento excluye implícitamente a estos clientes (p. ej. por un
  filtro de "mínimo N transacciones" copiado sin pensar de otro pipeline), el ranker nunca aprende a
  puntuar bien el caso mayoritario real.
- **Recomendación:** confirma la recomendación ya escrita en el plan (R-8): entrenar **con** estos
  casos presentes, features de cliente con NULL/0 explícito donde no haya historial, y agregar un
  test dedicado "cliente con una sola compra" — no es un caso raro, es el caso típico.

### Baja — A0-1 Telemetría de aceptación: volumen muy por debajo del umbral de la Fase 7

- **Evidencia:** `public.recomendaciones_eventos` tiene 79 filas totales: 77 `mostrada`, 2
  `aceptada`, 0 `rechazada`.
- **Consulta utilizada:** `SELECT evento, COUNT(*) FROM public.recomendaciones_eventos GROUP BY 1;`
- **Impacto:** muy por debajo del umbral que el propio plan fija para usar esta señal como feature
  auxiliar (`≥ 2.000 eventos y ≥ 15% de clase minoritaria`, §Fase 7). Con 2 aceptaciones sobre 79
  eventos, tampoco hay balance de clases utilizable.
- **Riesgos:** ninguno para la Fase 2 (no depende de esta fuente, §2.2 del plan). Sí confirma que la
  Fase 7 debe quedar condicionada, tal como el plan ya la deja escrita ("condicionada a A0-1").
- **Recomendación:** Fase 7 punto 2 (`aceptada` como feature) **no procede todavía**. El punto 1
  (medición de tasa de aceptación antes/después) sí puede activarse desde el día uno del ranker en
  producción, es acumulativo y no tiene precondición de volumen.

### Informativo — A0-2 Cobertura de costo del catálogo vigente

- **Evidencia:** 8.150 productos vigentes (`es_vigente = TRUE`, sin centinela), **92,10%** con
  `costo_promedio` no nulo y > 0.
- **Consulta utilizada:** ver Anexo A (consulta A0-2).
- **Impacto:** coincide con el 92,1% ya documentado en la auditoría 25 (H25-4) — no hay deriva desde
  entonces. Confirma que el manejo de `margen_unitario: float | None` (nunca degradar a 0) sigue
  siendo la decisión correcta para el 7,9% restante del catálogo.
- **Recomendación:** ninguna acción nueva; el plan (§2.4) ya lo maneja correctamente.

### Informativo — A0-4 Cobertura de stock para candidatos típicos

- **Evidencia:** los 200 productos más vendidos históricamente (proxy determinista de "candidatos
  típicos del item-item", que sesga hacia productos frecuentes) tienen **100% de cobertura** en el
  snapshot de inventario más reciente (`2026-07-16`).
- **Consulta utilizada:** ver Anexo A (consulta A0-4).
- **Impacto:** el filtro de disponibilidad de stock del CAMBIO 14 (Fase 3/4) es viable sin huecos de
  cobertura para el conjunto de productos que el motor realmente sugiere con más frecuencia.
- **Recomendación:** ninguna acción nueva; el plan (§2.4) ya limita correctamente el alcance del
  filtro a "disponibilidad actual", no tendencias.

### Informativo — A0-6 Latencia base — pendiente de medir con credenciales reales

- **Evidencia:** `bi_backend` está levantado y saludable (`GET /health` → 200), pero medir
  `POST /cross-selling/sugerencias` requiere un JWT de un usuario `ventas` real y esta auditoría no
  tiene (ni debe generar) credenciales de usuarios de negocio.
- **Impacto:** sin línea base de latencia no se puede fijar con evidencia el presupuesto de "< 300ms
  p95" que el plan propone en §3.4 — hoy es un valor de diseño razonable, no medido.
- **Riesgos:** ninguno para empezar la Fase 1-2 (el presupuesto es un criterio de aceptación de más
  adelante, no un bloqueo de arranque).
- **Recomendación:** medir en la Fase 1 (cuando ya haya un endpoint nuevo real que ejercitar) con un
  usuario de prueba del entorno de desarrollo, documentado como parte de la Definición de Terminado
  de esa fase — **no** queda pendiente indefinidamente.

## Conclusión de viabilidad (respuesta directa a la pregunta del plan)

**Sí, es viable entrenar `cross_sell_ranker` (Fase 2 del plan) con los datos actuales**, con una
condición derivada de A0-5 que no estaba en el diseño original:

1. **A0-0 (volumen): sin reserva.** Datos abundantes, sin degeneración temporal.
2. **A0-5 (techo de personalización): confirmado, con mitigación obligatoria antes de prometer
   resultados al negocio.** `sucursal` se agrega como feature explícita del ranker (no estaba
   listada así en el diagrama de §3 del plan, que la mencionaba solo implícitamente vía
   "misma_categoria_que_canasta"). El techo estructural de la etapa de candidatos (R-1) **no** se
   resuelve en este plan — el ranker reordena, no genera candidatos nuevos — y debe comunicarse así
   en la Fase 5/6, no como "personalización total".
3. **A0-1 y A0-3** no bloquean pero condicionan alcance: Fase 7 punto 2 se pospone (A0-1); el
   ranker debe entrenarse expresamente con el caso "cliente sin historial" como caso típico, no
   raro (A0-3, ya así en el plan como R-8, ahora con cifra: 57,8%/77,1% de la cartera).
4. **A0-2, A0-4** sin hallazgos nuevos, consistentes con auditorías previas.
5. **A0-6** pendiente, no bloqueante, a medir en la Definición de Terminado de la Fase 1.

## Resumen de recomendaciones por prioridad

| Prioridad | Hallazgo | Acción |
|---|---|---|
| Alta | A0-5 | Agregar `sucursal` como feature explícita del ranker; documentar el techo de personalización en la UI/comunicación de la Fase 5-6, no prometer personalización total |
| Media | A0-3 | Entrenar el ranker con clientes de historial escaso incluidos (no filtrarlos); test dedicado "cliente con una sola compra" |
| Baja | A0-1 | Fase 7 punto 2 (telemetría como feature) queda pospuesta hasta acumular ≥2.000 eventos con ≥15% clase minoritaria |
| Baja | A0-6 | Medir latencia real en la Definición de Terminado de la Fase 1, con un endpoint nuevo real y un usuario de prueba |
| — | A0-0, A0-2, A0-4 | Sin acción — confirman viabilidad / consistencia con auditorías previas |

---

## Fase 1 aplicada (2026-07-28)

Implementada tras esta auditoría, siguiendo la reformulación de §2.4 (CLV histórico) y la
recomendación de RLS de §3 decisión 6 del plan. Resumen (detalle de reglas de negocio en
`docs/auditoria/02_reglas_negocio_validadas.md` §17, RN-CS4/RN-CS5):

- `CatalogRepository.search_clientes` enriquecido con `ciudad`, `ultima_compra`,
  `frecuencia_12m`, `n_compras` (CTE separada, solo sobre los candidatos ya acotados por
  `LIMIT`, sin costo adicional relevante en el autocompletar).
- `Cartera360Repository.get_perfil_cliente`/`get_productos_favoritos_cliente` (nuevos): CLV
  histórico y agregados por cliente único, sin filtrar por vendedor (a diferencia de
  `get_lista_trabajo`, que sí filtra por cartera de un `codven`).
- Servicio nuevo `app/services/cross_sell_engine_service.py` (decisión de arquitectura §3.1
  del plan: no se engordó `PredictionService`), compone `Cartera360Repository` +
  `CatalogRepository` + `PredictionService` (`get_churn_risk`/`get_customer_segment`
  reutilizados sin cambios).
- Endpoint nuevo `GET /analytics/ventas/cross-selling/clientes/{cliente_id}/perfil` con RLS
  obligatoria (`_verificar_pertenencia_cartera`) y `probabilidad_recompra` derivada de
  `churn_rf` (`100 - probabilidad_abandono`).
- Frontend: `store/crossSellStore.ts` (Zustand, cliente como estado raíz de la página, sin
  `persist` -- PII no debe sobrevivir en sessionStorage), `components/crossSelling/
  ClientProfileCard.tsx` (skeleton por sección, estado vacío real para "sin historial"),
  `VentasCrossSelling.tsx` actualizado (el cliente deja de ser un filtro opcional).

**Validación end-to-end realizada:**
- `pytest -m integration` nuevo (`backend/tests/integration/test_cross_selling_fase1.py`, 4
  tests): 403 para cliente ajeno de la cartera de `ventas`, 404 para cliente inexistente vía
  `gerencia`, estado vacío real (`tiene_historial=false`, campos `null`) para un cliente sin
  ventas, verificado con una consulta SQL propia (`NOT EXISTS` contra `fact_ventas_detalle`).
- Suite completa de backend (`pytest`, 286 tests): 275 passed, 3 skipped (uno es el caso
  "cliente con historial real" del vendedor semilla 102, que no tiene ventas en este EDW de
  desarrollo -- `skip`, no `fail`), 8 failed **preexistentes y no relacionados** (4 por
  modelos `.pkl` no resueltos por `ML_MODELS_DIR` en este entorno de pruebas concreto, 3 de
  `goal_ml_service`/meta-sugerida, 1 de `classify_vendor_risk` -- ninguno toca código de
  Venta Cruzada ni se originó en esta fase).
- `npx tsc --noEmit` y `npx oxlint` sobre los archivos nuevos/modificados del frontend: sin
  errores (los 3 errores de `tsc` que sí aparecen en el proyecto son preexistentes, de
  `framer-motion` faltante en `Dropdown.tsx`/`Collapse.tsx`, no relacionados).
- Probado contra el backend real (`bi_backend`, reconstruido no fue necesario -- hot-reload
  del volumen de desarrollo): login real como `ventas_gye@empresa.com` y `gerencia@empresa.com`,
  autocompletar enriquecido probado con datos reales del EDW, endpoint de perfil probado con
  un `cliente_id` real devolviendo RFM/churn/CLV compuestos correctamente, y el mismo
  `cliente_id` correctamente rechazado (403) para el vendedor sin esa cartera.
- Frontend (`bi_frontend`, Vite dev server): los módulos nuevos (`VentasCrossSelling.tsx`,
  `ClientProfileCard.tsx`) transforman sin error. **Pendiente**: verificación visual en
  navegador real -- `chromium-cli` no está disponible en este entorno Windows y no se fabricó
  una captura; queda como pendiente explícito para la sesión de validación con usuario final
  (mismo criterio que Bodega, auditoría 32).
- A0-6 (latencia base) sigue pendiente, ahora con un endpoint nuevo real disponible para
  medirla -- no se hizo en esta pasada porque no es criterio de aceptación de la Fase 1.

## Fase 2 aplicada (2026-07-28) — resultado NEGATIVO, documentado como el plan exige

Implementado el flujo completo contrato → dataset con cortes temporales → entrenamiento →
backtest, siguiendo el patrón de la skill `ml-training-pipeline`. Resumen técnico:

- **Contrato** `ml/contracts/models/cross_sell_ranker.json` (draft v0.1.0): 15 features,
  incluida `sucursal` (agregada por el hallazgo de A0-5 de esta misma auditoría, no estaba
  en el diagrama original del plan).
- **Dataset** (`ml/src/features/cross_sell_ranker_features.py::construir_dataset_ranking`):
  12 cortes mensuales (2025-07-03..2026-05-29), 261.105 filas (26,87% positivos). Positivos =
  producto comprado por primera vez en `(T, T+60d]`; negativos = candidatos que
  `recommendation.pkl` (item-item) habría propuesto en `T` a partir del contexto reciente del
  cliente, con respaldo por popularidad general cuando el item-item no cubre el contexto
  (ratio 3 negativos por positivo). `p_abandono`/`segmento_rfm` se calculan aplicando los
  modelos YA ENTRENADOS `churn_rf`/`segmentation` sobre el RFM del cliente al corte `T`
  (features de entrada, no solo servicios aparte, decisión de arquitectura del plan §3).
- **Entrenamiento**: competencia RF/XGBoost/LightGBM/CatBoost (`find_best_classification_model`,
  igual que churn). Ganador: **LightGBMClassifier** (`num_leaves=50, n_estimators=200,
  learning_rate=0.1`). Split CRONOLÓGICO por corte (9/12 cortes entrenan, 3 evalúan) -- nunca
  aleatorio (R-9 del plan). Métricas de clasificación en el holdout: **ROC-AUC=0.9416,
  PR-AUC=0.9018, F1=0.8144** -- fuertes en apariencia.
- **Backtest de ranking** (mismo protocolo de la auditoría 25: Precision@K/Recall@K/
  Hit-Rate@5/cobertura, medido FRESCO sobre el mismo test set del backtest de `association`,
  no solo contra la cifra histórica): línea base item-item fresca **Precision@5=0.0782**
  (consistente con el 0.0769 histórico del contrato v0.2.0), ranker (mismos candidatos,
  reordenados) **Precision@5=0.0369** -- **peor que la línea base, no mejor**.

### Regla de decisión aplicada (fijada antes de ver resultados, §2.4 del plan)

**NO PROMOVIDO.** El ranker no superó la línea base; el contrato permanece `status: draft`,
`registry.json` no se modificó, y el módulo de Venta Cruzada sigue sirviendo el motor
item-item actual sin cambios. Resultado registrado en `ml/REPORTE_MEJORA_MODELOS.md`
(2026-07-28T17:18:41Z) con el mismo nivel de detalle que un resultado positivo, tal como
exige el plan (R-7: "es un resultado válido, no un fracaso").

### Por qué falló (hipótesis con evidencia, no solo "no funcionó")

Los holdout de clasificación (ROC-AUC=0.94) son buenos, pero el backtest de ranking es peor
que la línea base -- la brecha es la señal real, y apunta a **sesgo de distribución
train/serving en el muestreo de negativos** (train/serving skew), no a un bug de fuga (una
Precision@5 sospechosamente ALTA habría sido la señal de fuga, R-9; aquí es sospechosamente
BAJA, un problema distinto):

- En entrenamiento, los negativos son una mezcla de candidatos item-item + respaldo de
  popularidad, con ratio fijo 3:1 respecto a los positivos -- el modelo aprende a distinguir
  "el producto que el cliente compró" de "un candidato entre ~4", una tarea más fácil.
- En el backtest de ranking, el modelo debe ordenar hasta 50 candidatos reales por canasta
  (mismo pool que sirve producción) con normalmente 1-2 positivos verdaderos -- una tarea de
  ranking mucho más difícil, para la que el modelo nunca vio ejemplos comparables en
  entrenamiento.
- Consistente con esto: `hit_rate_5` cae de 0.36 (línea base) a 0.18 (ranker) y
  `impacto_ticket_medio` SUBE (23.22 -> 32.32) -- el ranker prioriza productos de mayor
  precio/margen sobre los que el item-item ya sabía que eran afines, señal de que las
  features económicas (`margen_relativo`, `precio_relativo_categoria`) dominan la decisión
  del modelo más de lo que deberían frente a `score_item_item`.

### Qué NO se hizo (para no p-hackear un resultado)

No se reintentó con otro ratio de negativos, otra ventana de cortes, ni otra combinación de
hiperparámetros para forzar una promoción -- eso convertiría una validación honesta en una
búsqueda de la configuración que "gana por casualidad" sobre este mismo test set. Si se
retoma esta fase, el cambio de diseño más justificado por la evidencia de arriba es
**negativos muestreados directamente del pool completo de ~50 candidatos item-item que
sirve producción** (en vez de un ratio fijo 3:1), para que el entrenamiento reproduzca la
misma dificultad de ranking que el backtest mide -- no un ajuste de hiperparámetros.

### Detalle técnico adicional: artefacto no promovido no queda huérfano

`save_artifact(..., registry_key="cross_sell_ranker")` siempre escribe primero el archivo
"estable" en la raíz de `ml/models/` (mismo patrón de Fase 1 del plan de mejora del pipeline).
Para un modelo que YA tiene un campeón previo, eso es correcto: si el gate rechaza,
`promotion.py` revierte ese archivo a la versión anterior. Pero `cross_sell_ranker` es un
modelo nuevo sin campeón previo -- dejar el `.pkl` rechazado en la raíz sin entrada en
`registry.json` lo dejaba huérfano (detectado por el test de guardia existente
`ml/tests/test_registry.py::test_ningun_pkl_en_raiz_es_huerfano`, que sí falló en la primera
corrida y expuso el problema). Corregido en `ml/main.py::train_cross_sell_ranker`: cuando no
se promueve, el archivo estable se retira de la raíz (el registro histórico se conserva en
`ml/models/versions/cross_sell_ranker/`, igual que cualquier versión archivada). `pytest
ml/tests/` (18, 1 skip esperado) y `contract_validator` quedan limpios tras el fix.

### Consecuencia para el resto del plan

Las Fases 3-6 pierden las piezas que dependían del ranker promovido (`probabilidad_compra_por_producto`,
SHAP real sobre el ranking) -- el plan mismo anticipa esto (R-7: "el módulo conserva el motor
actual y las Fases 1, 3-6 siguen aportando valor por sí solas"). Continúan con el score
item-item como señal de afinidad/ranking (comportamiento ya vigente en producción) y con SHAP
limitado a `churn_rf` (ya contemplado en la Opción A de §2.1, no exclusivo del ranker).

## Fase 3 aplicada (2026-07-28) — simulador de venta con datos 100% reales

`POST /cross-selling/simular` (RLS obligatoria si se pasa `cliente_id`, mismo patrón
`_verificar_pertenencia_cartera` de la auditoría 34 H-V2). Implementado en
`CrossSellEngineService.simular_venta`, consumido por `SimulacionPanel.tsx` cada vez que la
canasta del asistente (`crossSellStore.ts`) cambia (debounced 400ms, `keepPreviousData` para
que las cifras no parpadeen a `—` entre un clic y el siguiente).

Restricción explícita del usuario para esta fase y las siguientes ("esto no debe contener
ninguna simulacion, todos con datos reales"): **ningún campo del response es inventado o
derivado de una fórmula sin respaldo en el EDW/modelos ya entrenados**:

- `ticket_estimado`: suma real de `precio_venta` (catálogo vigente) de los productos de la
  canasta -- no un promedio ni una proyección.
- `margen_estimado`: suma real de `(precio-costo)` solo si **todos** los productos de la
  canasta tienen costo real en `dim_producto.costo_promedio`; si falta el costo de al menos
  uno, el campo es `None` completo (nunca una suma parcial que subestime el margen
  silenciosamente -- mismo criterio que `_margen_agregado` en Fase 4).
- `incremento_vs_ticket_promedio_cliente`: solo se calcula con `cliente_id` y perfil con
  historial real (`ticket_promedio` de `Cartera360Repository.get_perfil_cliente`, Fase 1);
  `None` para cliente sin historial o sin `cliente_id`.
- `probabilidad_recompra`: reutiliza `100 - probabilidad_abandono` de `churn_rf` (mismo cálculo
  que el perfil de Fase 1, RN-CS4) -- no un modelo nuevo, no una heurística nueva.
- `explicacion`: plantilla determinista (Opción A de negocio ya decidida al inicio del plan,
  sin LLM) que arma una frase a partir de los campos anteriores -- nunca texto generado, nunca
  "personalización" fingida.

**KPI de negocio deliberadamente NO reemplazado**: el simulador no calcula "probabilidad de
cierre de venta" ni "probabilidad de compra por producto" -- ambos dependían del ranker de la
Fase 2, que no se promovió; el usuario ya había decidido explícitamente en la fase de preguntas
iniciales del plan que "probabilidad de cierre de venta" **no** se reemplaza por un KPI del
ranker. RN-CS7 (`docs/auditoria/02_reglas_negocio_validadas.md` §17) ya cubre esta decisión.

**Bug encontrado y corregido durante la validación**: el servicio tenía una rama muerta
`if not items: raise ValidationError(...)` que nunca se alcanzaba -- `SimulacionVentaRequest`
ya valida `items` con `Field(min_length=1)` a nivel de Pydantic, así que FastAPI responde `422`
antes de llegar al servicio (mismo patrón que `CrossSellSugerenciasRequest`). Se retiró el
código muerto y el `import` no usado de `ValidationError`; el test de integración se ajustó
para esperar `422` (documentado con docstring, no un cambio de contrato silencioso).

**Validación:** `test_cross_selling_fase3.py` (canasta vacía → 422, cliente ajeno → 403,
`margen_estimado=None` cuando falta costo, cálculo con datos reales) + probado en vivo contra
`bi_backend`/`bi_frontend` reales (canasta con 2-3 productos reales, cifras verificadas a mano
contra `dim_producto`). `tsc`/`oxlint` limpios.

## Fase 4 aplicada (2026-07-28) — combos inteligentes, 4 estrategias reales

`GET /cross-selling/combos?cliente_id=` (RLS obligatoria si se pasa `cliente_id`). "Ideal
para Flotas" queda fuera por decisión de negocio ya tomada (§8.4 del plan: sin definición
de "cliente de flota/corporativo" derivable del EDW). Las 4 estrategias implementadas, cada
una 100% sobre datos reales del EDW, sin ranking ML (no depende del resultado de la Fase 2):

- **Oferta Estrella**: reutiliza `get_top_combinaciones` (coocurrencia real en facturas, ya
  validada desde la auditoría 25) -- `afinidad` = número real de facturas conjuntas, no un
  score normalizado inventado.
- **Mayor Rentabilidad**: nuevo `CatalogRepository.get_top_margen_relativo` -- top-1 producto
  por categoría con mayor `(precio-costo)/precio`, solo catálogo con costo real y con
  historial de venta comprobado (excluye SKUs muertos).
- **Cliente Frecuente**: reutiliza `get_productos_favoritos_cliente` de la Fase 1 (ahora
  también devuelve `venta_acumulada` real); `popularidad` = % real del gasto histórico del
  cliente ("share of wallet"), no un score inventado. Solo se emite con `cliente_id`.
- **Protección Total**: reutiliza `get_top_productos_diversos` (mismo motor que RN-CS3).

**Campos deliberadamente omitidos del schema** (`confianza`, `incremento_esperado` del plan
original): no hay una base de datos real para calcularlos honestamente en ninguna de las 4
estrategias sin el ranker de la Fase 2 (no promovido) -- se omitieron del contrato en vez de
rellenarlos con `None`/placeholders sin sentido. `margen_esperado`/`afinidad`/`popularidad`
solo se pueblan cuando hay una base real; `porque` siempre trae la evidencia real en texto.

**Hallazgo de calidad de datos (no un bug de esta fase):** algunos productos de "Mayor
Rentabilidad" muestran `margen_unitario` casi igual al precio completo (p.ej.
`AI020064A`, margen=99.998% del precio) -- `costo_promedio` registrado en el EDW es casi $0
para esos artículos. Es un dato real del EDW, no fabricado por este código; mismo patrón de
calidad de datos ya documentado en otras partes del proyecto (H25-4). No se aplicó un umbral
de "costo mínimo plausible" sin evidencia que lo justifique -- queda como hallazgo abierto
para una futura auditoría de calidad de datos de `dim_producto.costo_promedio`.

**Validación:** 3 tests de integración nuevos (`test_cross_selling_fase4.py`, RLS 403,
combos sin cliente excluyen "Cliente Frecuente", productos con datos reales) + probado en
vivo contra `bi_backend` real con y sin `cliente_id` -- 4 combos completos con evidencia real
(1.393 facturas conjuntas para Oferta Estrella, 3 productos favoritos reales para Cliente
Frecuente con `popularidad` calculada). `tsc`/`oxlint` limpios en el frontend nuevo.

## Fase 5 aplicada (2026-07-28) — decomposición honesta del score de sugerencia

`SugerenciaProducto.factor_margen` (nuevo campo, siempre poblado, `1.0` como neutro) expuesto en
`GET /cross-selling/sugerencias`, calculado en `PredictionService.get_basket_recommendations`
tanto en el bucle de scoring principal como en la rama de inyección de diversidad. Renderizado
en `SuggestionCard.tsx` vía el nuevo `ScoreDecompositionBar.tsx`.

**Decisión de diseño (por qué NO es una barra apilada única):** `score` (afinidad item-item) y
`factor_margen` se **multiplican**, no se suman, para producir el orden final de sugerencias --
una barra apilada aditiva (p.ej. "60% afinidad + 40% margen") habría sido una mentira visual
sobre cómo se compone realmente el ranking. `ScoreDecompositionBar` renderiza **dos medidores
independientes normalizados** contra el máximo de la lista actual de sugerencias
(`maxScore`/`maxBoost`, calculados en `SaleAssistant.tsx` sobre las sugerencias visibles, no
valores globales inventados): uno para afinidad (color info), otro para margen (color success).
La sugerencia principal (`esPrincipal`, la de mayor score) se destaca con un layout más ancho
(`md:col-span-2`), sin agregar ningún dato nuevo -- solo jerarquía visual sobre datos ya reales.

Esta fase reemplaza lo que el plan original preveía como "explicación con el ranker de la Fase
2" (§2.1 Opción A, fallback ya documentado): sin ranker promovido, la decomposición se hace
sobre las dos señales reales que el motor item-item YA calcula en producción (score de
similitud coseno + `factor_margen` del catálogo), no sobre una señal fabricada.

**Validación:** probado en vivo contra `bi_backend`/`bi_frontend` reales (canasta con productos
de distinto margen, verificado que la barra de margen varía entre sugerencias y que la
sugerencia principal se distingue visualmente). `tsc`/`oxlint` limpios. Sin test de integración
dedicado (`factor_margen` se cubre indirectamente por los tests existentes de `/sugerencias`
que ya validan la estructura del response; queda como gap conocido si se requiere cobertura
explícita del campo).

## Fase 6 aplicada (2026-07-28) — explicabilidad real (SHAP) para riesgo de abandono

`GET /cross-selling/clientes/{cliente_id}/explicacion-churn` (RLS obligatoria, mismo patrón
`_verificar_pertenencia_cartera`). Implementado en `PredictionService.get_churn_explanation`
con `shap.TreeExplainer` sobre `churn_rf` (RandomForest/XGBoost/LightGBM/CatBoost -- el modelo
ganador de la competencia documentada, cualquiera que sea, todos soportados por `TreeExplainer`
sin cambiar de librería según el algoritmo). Cachea por cliente en el proceso
(`self._churn_explanation_cache`) porque SHAP es costoso de recalcular en cada request y el
perfil del cliente no cambia dentro de una misma sesión de navegación.

**Por qué SHAP y no el ranker de la Fase 2 (§2.1 Opción A del plan, fallback ya previsto):**
sin ranker promovido, no hay una "razón de por qué este producto se sugiere" que sea real --
pero `churn_rf` SÍ está en producción y SÍ admite una explicación real por feature vía SHAP. El
panel se etiqueta explícitamente **"Explicación del modelo (SHAP)"** (`WhyExplanationPanel.tsx`),
nunca "IA" ni "recomendación inteligente" genérica -- cumple R-3 del plan (no fingir IA
generativa donde hay un cálculo determinista/estadístico real).

**Manejo de forma de `shap_values`:** `TreeExplainer.shap_values` devuelve un array 2D para
modelos binarios de XGBoost/LightGBM y 3D (una matriz por clase) para RandomForest/CatBoost --
el código detecta la forma y selecciona la clase positiva (`shap_values[..., 1]` en el caso 3D)
en vez de asumir un único formato, evitando que el endpoint fallara silenciosamente o devolviera
contribuciones para la clase equivocada según qué algoritmo haya ganado la competencia de
`churn_rf` en el reentrenamiento más reciente.

**Frontend:** `WhyExplanationPanel.tsx` -- colapsado por defecto, la consulta SHAP solo se
dispara al expandir (`useExplicacionChurn(clienteId, abierto)` con `enabled: abierto`, no en
cada carga del perfil, por el costo real de calcular SHAP). Barras de contribución real por
feature (`recency`, `frequency`, `monetary_value`, `average_ticket`), coloreadas por dirección
del efecto (aumenta/reduce el riesgo), nunca un texto generado.

**Dependencia nueva:** `shap>=0.46.0,<0.47.0` agregada a `backend/requirements.txt`; instalada
en vivo en el contenedor `bi_backend` para iteración de desarrollo -- pendiente de confirmar
con una reconstrucción completa de la imagen (`docker compose build backend`) antes de dar la
dependencia por completamente validada en el flujo de despliegue normal.

**Validación:** probado en vivo contra `bi_backend`/`bi_frontend` reales (cliente con
historial, panel expandido, contribuciones SHAP coherentes con el perfil de riesgo mostrado).
Suite completa de backend re-ejecutada tras el cambio: 282 passed, 3 skipped, 8 failed (los
mismos 8 fallos preexistentes ya documentados en la Fase 0-1, sin relación con `shap` ni
`factor_margen` -- no hay regresión). `tsc`/`oxlint` limpios. Sin test de integración dedicado
para este endpoint (mismo gap conocido que Fase 5, solo verificación manual en vivo).

## Anexo A — Consultas SQL utilizadas

**A0-0** (volumen de positivos por corte, patrón CTE de agregación por grano antes de unir):

```sql
WITH ventas_validas AS (
    SELECT fvd.cliente_sk, fvd.producto_sk, df.fecha_completa
    FROM edw.fact_ventas_detalle fvd
    JOIN edw.dim_fecha df ON fvd.fecha_sk = df.fecha_sk
    JOIN edw.dim_estado_documento ed ON fvd.estado_documento_sk = ed.estado_documento_sk
    WHERE ed.estado_documento_sk <> -1 AND NOT ed.es_devolucion
      AND fvd.producto_sk <> -1 AND fvd.cliente_sk <> -1
),
cortes AS (
    SELECT generate_series(
        (SELECT MIN(fecha_completa) FROM ventas_validas) + INTERVAL '6 months',
        (SELECT MAX(fecha_completa) FROM ventas_validas) - INTERVAL '60 days',
        INTERVAL '1 month'
    )::date AS t
),
pares_futuros AS (
    SELECT c.t, v.cliente_sk, v.producto_sk
    FROM cortes c
    JOIN ventas_validas v ON v.fecha_completa > c.t AND v.fecha_completa <= c.t + INTERVAL '60 days'
    GROUP BY c.t, v.cliente_sk, v.producto_sk
),
pares_historicos AS (
    SELECT c.t, v.cliente_sk, v.producto_sk
    FROM cortes c
    JOIN ventas_validas v ON v.fecha_completa <= c.t
    GROUP BY c.t, v.cliente_sk, v.producto_sk
),
positivos AS (
    SELECT pf.t, pf.cliente_sk, pf.producto_sk
    FROM pares_futuros pf
    LEFT JOIN pares_historicos ph
      ON ph.t = pf.t AND ph.cliente_sk = pf.cliente_sk AND ph.producto_sk = pf.producto_sk
    WHERE ph.cliente_sk IS NULL
)
SELECT COUNT(DISTINCT t), COUNT(*), ROUND(COUNT(*)::numeric / COUNT(DISTINCT t), 1)
FROM positivos;
```

**A0-1:**

```sql
SELECT evento, COUNT(*) FROM public.recomendaciones_eventos GROUP BY 1 ORDER BY 1;
```

**A0-2:**

```sql
SELECT
  COUNT(*) AS total_vigentes,
  COUNT(*) FILTER (WHERE costo_promedio IS NOT NULL AND costo_promedio > 0) AS con_costo,
  ROUND(100.0 * COUNT(*) FILTER (WHERE costo_promedio IS NOT NULL AND costo_promedio > 0) / COUNT(*), 2)
FROM edw.dim_producto WHERE es_vigente = TRUE AND producto_sk <> -1;
```

**A0-3:**

```sql
WITH agg AS (
  SELECT fvd.cliente_sk, COUNT(*) AS n_lineas, COUNT(DISTINCT df.fecha_completa) AS n_dias,
         COUNT(DISTINCT date_trunc('month', df.fecha_completa)) AS n_meses
  FROM edw.fact_ventas_detalle fvd
  JOIN edw.dim_fecha df ON fvd.fecha_sk = df.fecha_sk
  JOIN edw.dim_estado_documento ed ON fvd.estado_documento_sk = ed.estado_documento_sk
  WHERE ed.estado_documento_sk <> -1 AND NOT ed.es_devolucion AND fvd.cliente_sk <> -1
  GROUP BY fvd.cliente_sk
)
SELECT COUNT(*), COUNT(*) FILTER (WHERE n_dias = 1), COUNT(*) FILTER (WHERE n_meses < 3),
       COUNT(*) FILTER (WHERE n_meses >= 6)
FROM agg;
```

**A0-4:**

```sql
WITH top_productos AS (
  SELECT fvd.producto_sk, COUNT(*) AS n
  FROM edw.fact_ventas_detalle fvd
  JOIN edw.dim_estado_documento ed ON fvd.estado_documento_sk = ed.estado_documento_sk
  WHERE ed.estado_documento_sk <> -1 AND NOT ed.es_devolucion AND fvd.producto_sk <> -1
  GROUP BY fvd.producto_sk ORDER BY n DESC LIMIT 200
),
ultimo AS (SELECT MAX(fecha_sk) AS fecha_sk FROM edw.fact_inventario_snapshot),
cobertura AS (
  SELECT tp.producto_sk,
         EXISTS (SELECT 1 FROM edw.fact_inventario_snapshot fis, ultimo u
                 WHERE fis.producto_sk = tp.producto_sk AND fis.fecha_sk = u.fecha_sk) AS tiene_snapshot
  FROM top_productos tp
)
SELECT COUNT(*), COUNT(*) FILTER (WHERE tiene_snapshot) FROM cobertura;
```

**A0-5:**

```sql
WITH ventas AS (
  SELECT fvd.sucursal_sk, fvd.num_factura, p.codart
  FROM edw.fact_ventas_detalle fvd
  JOIN edw.dim_producto p ON fvd.producto_sk = p.producto_sk
  JOIN edw.dim_estado_documento ed ON fvd.estado_documento_sk = ed.estado_documento_sk
  WHERE ed.estado_documento_sk <> -1 AND NOT ed.es_devolucion AND fvd.producto_sk <> -1
    AND fvd.sucursal_sk IN (1,3)
),
pares AS (
  SELECT a.sucursal_sk, LEAST(a.codart,b.codart) AS prod_a, GREATEST(a.codart,b.codart) AS prod_b
  FROM ventas a JOIN ventas b
    ON a.sucursal_sk = b.sucursal_sk AND a.num_factura = b.num_factura AND a.codart < b.codart
),
conteo AS (
  SELECT sucursal_sk, prod_a, prod_b, COUNT(*) AS n FROM pares GROUP BY sucursal_sk, prod_a, prod_b
),
top20_matriz AS (SELECT prod_a, prod_b FROM conteo WHERE sucursal_sk = 3 ORDER BY n DESC LIMIT 20),
top20_elrey AS (SELECT prod_a, prod_b FROM conteo WHERE sucursal_sk = 1 ORDER BY n DESC LIMIT 20)
SELECT
  (SELECT COUNT(*) FROM top20_matriz), (SELECT COUNT(*) FROM top20_elrey),
  (SELECT COUNT(*) FROM top20_matriz t1 JOIN top20_elrey t2 ON t1.prod_a=t2.prod_a AND t1.prod_b=t2.prod_b);
```
