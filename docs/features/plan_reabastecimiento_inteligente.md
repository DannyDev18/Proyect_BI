# Plan — Auditoría y Refactorización del Módulo de Reabastecimiento Inteligente

> **Estado:** PLAN. Ninguna fase ejecutada todavía.
> **Fecha de redacción:** 2026-08-04
> **Origen:** pedido explícito del usuario (prompt "Auditoría y Refactorización del Módulo de Reabastecimiento Inteligente" — rol Principal Product Designer / Staff UX Engineer / Supply Chain Consultant / ML Engineer / Solution Architect).
> **Objetivo declarado:** convertir el módulo de Bodega de un *dashboard de visualización* en un **Sistema de Apoyo a Decisiones (DSS) de reabastecimiento**.
> **Documento de auditoría a producir:** `docs/auditoria/50_reabastecimiento_inteligente.md` (no existe aún — la Fase 0 lo crea).

---

## 0. Cómo usar este documento

Este plan se escribió leyendo el código real del módulo, no de memoria. Las secciones §2 y §3 contienen **hallazgos preliminares ya confirmados por lectura de código** (con archivo y línea). No sustituyen la Fase 0: la auditoría formal debe además **cuantificarlos con `SELECT` reales contra `bi_postgres_edw`** antes de que se escriba una sola línea de código nuevo, siguiendo el flujo obligatorio de `CLAUDE.md` §"Flujo de trabajo esperado" (auditoría → propuesta → implementación → validación → documentación).

Regla que atraviesa todo el plan, heredada de sesiones previas de este proyecto y reafirmada aquí:

> **Ningún campo de ningún contrato nuevo puede ser simulado, inventado o rellenado con un placeholder.** Todo dato sale de una consulta real al EDW, de un modelo ya entrenado, o de una tabla de configuración que un humano llenó. Si un dato no existe (caso real: *lead time*, ver H-1), se declara faltante en la UI y se omite del contrato — **nunca se estima en silencio**.

---

## 1. Estado actual real del módulo (inventario, no opinión)

### 1.1 Superficie de código

| Capa | Archivo | Líneas | Rol |
|---|---|---|---|
| Router | [warehouse.py](backend/app/api/routes/warehouse.py) | 437 | 15 endpoints reales + 2 legados |
| Servicio | [warehouse_service.py](backend/app/services/warehouse_service.py) | 1662 | Toda la lógica de negocio |
| Repositorio | [warehouse_repository.py](backend/app/repositories/warehouse_repository.py) | 1025 | SQL sobre el EDW, RLS por `codalm` |
| Contratos | [warehouse.py](backend/app/schemas/warehouse.py) | 323 | Pydantic |
| Export | `warehouse_export.py` / `warehouse_pdf_export.py` | — | Excel / PDF |
| Página 1 | [DashboardBodega.tsx](frontend/src/pages/DashboardBodega.tsx) | 286 | KPIs + 5 gráficos |
| Página 2 | [BodegaAlmacenes.tsx](frontend/src/pages/BodegaAlmacenes.tsx) | 425 | Matriz, transferencias, plan de compra |
| Página 3 | [BodegaReportes.tsx](frontend/src/pages/BodegaReportes.tsx) | 268 | 5 reportes tipados + Excel/PDF |
| Filtros | [BodegaFilterBar.tsx](frontend/src/components/bodega/BodegaFilterBar.tsx) | 100 | 6 filtros globales |
| Tipos/hooks/servicios | `types/bodega.ts` (304), `hooks/bodega.ts` (132), `services/bodega.ts` (128) | 564 | Espejo del contrato |

### 1.2 Endpoints vigentes bajo `/analytics/bodega`

`/filtros`, `/kpis`, `/salidas-forecast`, `/prediccion-compras-mes`, `/rotacion-matriz`, `/top-productos`, `/salidas-categoria`, `/stock-reorden`, `/necesidad-compra`, `/inventario-matriz`, `/transferencias-sugeridas`, `/reportes/{tipo}`, `/reportes/{tipo}/excel`, `/reportes/{tipo}/pdf`, más los legados `/kpis-inventory` y `/demand-forecasting`.

### 1.3 Fórmulas de Supply Chain hoy implementadas

Todas viven en [warehouse_service.py:147-246](backend/app/services/warehouse_service.py#L147-L246):

```
salida_diaria      = salidas_periodo / 30            # ventana FIJA de 30 días
punto_reorden      = salida_diaria × (LEAD_TIME + STOCK_SEGURIDAD_DIAS)   # 7 + 5 = 12 días
dias_inventario    = stock / salida_diaria           # None si no hay salidas
estado             = Inmovilizado | Exceso | Crítico | Cerca | Seguro
cantidad_sugerida  = max(0, salida_diaria × horizonte − stock)
```

Parámetros en [config.py:109-166](backend/app/core/config.py#L109-L166) (`BODEGA_*`, 23 variables de entorno globales, ninguna configurable desde la UI ni por producto/proveedor/almacén).

---

## 2. Hallazgos preliminares confirmados por lectura de código

Severidad según el impacto sobre la **calidad de la decisión de compra**, no sobre la estética.

### 2.1 CRÍTICOS

**H-1 — El *lead time* no existe como dato: es una constante global de 7 días.**
`BODEGA_LEAD_TIME_DIAS=7` ([config.py:109](backend/app/core/config.py#L109)) se aplica idéntico a todo producto, proveedor y almacén. Peor: **el EDW no puede derivarlo hoy**. `edw.Fact_Compras` ([edw/03_hechos.sql:92-106](edw/03_hechos.sql#L92-L106)) tiene **una sola fecha** (`fecha_sk` = fecha de factura); no hay fecha de pedido ni de recepción, así que no existe el par de fechas que define un lead time. Consecuencia: el punto de reorden, el stock de seguridad y todo el riesgo de quiebre del módulo descansan sobre un número inventado. **Esto bloquea directamente el requisito "Lead Time por proveedor" y la columna "Lead Time" de la lista inteligente pedida por el usuario.** Ver §5 (decisión D-1) — es la decisión de negocio que hay que resolver antes de la Fase 1.

**H-2 — El motor de compra ignora el modelo ML.**
`_necesidad_compra_completo` ([warehouse_service.py:840-910](backend/app/services/warehouse_service.py#L840-L910)) — la función que produce *qué comprar y cuánto*, el corazón del módulo — calcula `cantidad = salida_diaria × horizonte − stock` usando un **promedio histórico plano de 30 días**. `demand_rf` no participa. El modelo solo se usa en `/salidas-forecast?producto_cod=...` (un gráfico) y `/prediccion-compras-mes` (otro gráfico). El módulo se presenta al usuario como *"Decisiones de compra basadas en histórico del EDW + predicción ML"* ([DashboardBodega.tsx:64](frontend/src/pages/DashboardBodega.tsx#L64)), lo cual **no es cierto para la recomendación de compra**.

**H-3 — No hay nivel de servicio ni variabilidad de demanda en ninguna fórmula.**
El stock de seguridad es `5 días × demanda media` fija. La fórmula estándar de la industria (`SS = z(nivel_servicio) × σ_demanda × √LT`) no está implementada en ninguna parte. Un artículo de demanda perfectamente estable y otro errático reciben el mismo colchón. El coeficiente de variación **sí se calcula**, pero enterrado y solo para transferencias (`_justificacion_transferencia`, [warehouse_service.py:1037](backend/app/services/warehouse_service.py#L1037), con `BODEGA_CV_ALTA/MEDIA`) — nunca llega al punto de reorden ni a la UI.

**H-4 — No existen las clasificaciones ABC ni XYZ.**
Ninguna búsqueda en backend o frontend devuelve estos conceptos. Sin ellos no hay priorización real: hoy todo el catálogo se trata con la misma política de inventario. El usuario los pide explícitamente como filtro y como gráfico.

**H-5 — La "aprobación" de transferencias es estado efímero de React.**
[BodegaAlmacenes.tsx:47-48](frontend/src/pages/BodegaAlmacenes.tsx#L47-L48): `useState<Record<string,'aprobada'|'rechazada'>>({})`. No se persiste, no se envía a ningún endpoint, se pierde al recargar la página. Es una **acción falsa**: el usuario cree estar decidiendo algo y no queda registro. Cualquier bloque de "Gestión Operativa" (aprobar / generar propuesta / exportar) debe partir de reconocer que hoy no hay ninguna persistencia de decisiones operativas en este módulo.

### 2.2 IMPORTANTES

**H-6 — La mitad de los KPIs que el backend calcula se tiran.**
`KpisBodegaResponse` ([schemas/warehouse.py:68-74](backend/app/schemas/warehouse.py#L68-L74)) devuelve 6 KPIs; `DashboardBodega.tsx` renderiza **3** (`total_articulos`, `stock_bajo`, `dias_inventario`). `rotacion`, `valor_inventario` y `tasa_stockout` se calculan en cada request —con su costo de consulta— y se descartan. `tasa_stockout` es, además, el único KPI cercano a un indicador de nivel de servicio real.

**H-7 — La banda de confianza no es un intervalo de predicción.**
[warehouse_service.py:455-472](backend/app/services/warehouse_service.py#L455-L472): la banda es `predicción ± MAE_global_del_modelo`, **constante para todos los SKU y para todo el horizonte**. Un pronóstico a 30 días tiene exactamente la misma banda que uno a 1 día. Está honestamente declarado en el código, pero es insuficiente para sostener una columna "Confianza del modelo" por artículo, que es lo que pide el usuario.

**H-8 — No hay exactitud del modelo medible en serving.**
Sólo existe el MAE global del sidecar `demand.meta.json`. No hay precisión por SKU ni histórica. **Existe la base para construirla**: `ml/scripts/backtest_demand_por_sku.py` (creado en la Fase 0 de `plan_mejora_pipeline_ml.md`) y la tabla `public.ml_model_runs`. Hoy nada de eso llega al usuario de bodega.

**H-9 — `salida_diaria` usa una ventana fija de 30 días que ignora el filtro de fechas.**
`_salida_diaria(salidas_periodo, dias=30)` se invoca con el default en `_enriquecer_producto` ([:213](backend/app/services/warehouse_service.py#L213)), que a su vez alimenta `/necesidad-compra`, `/stock-reorden`, `/inventario-matriz` y `/transferencias-sugeridas`. Si el usuario selecciona un rango de 90 días en la barra de filtros, la demanda diaria se sigue dividiendo entre 30. **Verificar en Fase 0 si `salidas_periodo` respeta o no el rango** — si lo respeta, la demanda diaria está inflada 3× en ese escenario; si no lo respeta, el filtro de fechas es decorativo para esos cuatro endpoints. Cualquiera de los dos casos es un defecto real.

**H-10 — Duplicación financiera con el Dashboard Ejecutivo.**
`valor_inventario`, `monto_ventas` en top-productos y en salidas-categoría, `KpiValorInventario.top_categorias`. El usuario fue explícito: el dinero solo aparece cuando sostiene una decisión de compra (presupuesto, costo de abastecimiento, capital inmovilizado), nunca como eje.

**H-11 — El horizonte de predicción no es del usuario.**
`dias_horizonte=30` es un query param que el frontend nunca expone; `BODEGA_HORIZONTE_COMPRA_DIAS=30` y `BODEGA_HORIZONTE_PLAN_DIAS=45` son env vars. El usuario pide el horizonte como filtro de primer nivel.

### 2.3 MENORES

**H-12** — El gráfico G1 (histórico+predicción de salidas) trae un `<Brush>` de zoom sobre una serie que ya es corta; complejidad sin decisión asociada.
**H-13** — El selector de producto del forecast solo ofrece el top-20 por salidas ([DashboardBodega.tsx:122](frontend/src/pages/DashboardBodega.tsx#L122)): justo los artículos que menos riesgo de quiebre desatendido tienen. No se puede pronosticar un artículo crítico que no esté en el top de ventas.
**H-14** — `sucursal` sigue en la firma de `_generar_reporte` siempre en `None` (deuda declarada tras el hallazgo Bodega-sucursal de la auditoría 42).
**H-15** — `edw.Fact_Transferencias` existe en el DDL ([edw/03_hechos.sql:271](edw/03_hechos.sql#L271)) pero las transferencias sugeridas se calculan solo desde el stock actual; **verificar en Fase 0 si la tabla tiene filas** — si las tiene, es la fuente para medir el lead time *interno* entre bodegas (que sí es derivable, a diferencia de H-1).

### 2.4 Oportunidades ya disponibles (no hay que construirlas desde cero)

- El coeficiente de variación por artículo ya se calcula → **XYZ es casi gratis**.
- `Fact_Ventas_Detalle` tiene costo y precio por línea → **ABC por valor de consumo es una sola consulta**.
- Existe paginación genérica (`Page[T]`), `DataTable` con `renderExpanded` (usado en Comisiones) y `Drawer` → **la lista inteligente con explicabilidad expandible no necesita componentes nuevos de base**.
- Existe un patrón probado de "tabla de configuración editable + bitácora" (`comision_config_auditoria`, `metas_config_modulos`) → **reutilizable tal cual para la política de inventario**.
- Existe un patrón probado de "motor puro + funciones testeables" (`commission_variable_engine.py`, `goal_pipeline_stages.py`) → **el motor de reabastecimiento debe seguirlo**.

---

## 3. Auditoría de KPIs — decisión propuesta

A confirmar/ajustar en Fase 0, pero esta es la propuesta de partida.

| KPI actual | Decisión | Justificación |
|---|---|---|
| Artículos en Inventario (SKUs activos / total / en cero) | **Fusionar** | Es censo, no decisión. Absorber "SKUs en cero con demanda" dentro de "Productos en quiebre". |
| Productos con Stock Bajo | **Mantener, redefinir** | Pasa a "Requieren compra hoy" (bajo ROP **estocástico**, no el determinista actual). |
| Días de Inventario (global) | **Mantener** | Es la cobertura promedio que el usuario pide, pero debe mostrar **mediana** además del promedio: un inmovilizado con 9.000 días distorsiona la media. |
| Rotación (calculado, no mostrado) | **Eliminar del centro de decisiones** | Métrica de eficiencia financiera, pertenece al Dashboard Ejecutivo. Se conserva dentro de ABC. |
| Valor de Inventario (calculado, no mostrado) | **Reemplazar** | Sale del centro de decisiones; vuelve solo como **"capital inmovilizado"** (stock sin salidas × costo), que sí es accionable. |
| Tasa de Stockout (calculado, no mostrado) | **Mantener y exponer** | Es el proxy más cercano a nivel de servicio real. Hoy se calcula y se tira (H-6). |
| — | **Nuevo** | **Productos en riesgo de quiebre antes del próximo abastecimiento** (cobertura < lead time). |
| — | **Nuevo** | **Productos en sobrestock / inmovilizados** + capital que representan. |
| — | **Nuevo** | **Exactitud del modelo** (WAPE del último backtest, con fecha de medición). |
| — | **Nuevo** | **Alertas activas** por severidad. |

---

## 4. Fase 0 — Auditoría obligatoria (no escribir código antes de terminarla)

**Entregable:** `docs/auditoria/50_reabastecimiento_inteligente.md`, con el formato de los reportes existentes (fecha, alcance, método, hallazgo con severidad, evidencia, acción). Estructura pedida por el usuario: *Problemas críticos / importantes / menores / oportunidades / recomendaciones priorizadas*.

**Método:** solo `SELECT` contra `bi_postgres_edw`; ejecución en modo lectura de los servicios reales dentro de `bi_backend` cuando haga falta ejercitar el motor. **Prohibido** cualquier escritura sobre SAP (restricción permanente del proyecto).

| ID | Pregunta a responder con datos | Criterio de cierre |
|---|---|---|
| A-0.1 | ¿`Fact_Compras` permite derivar algún lead time real? ¿Existe en SAP alguna tabla de órdenes de compra con fecha de pedido y de recepción (`pedidos`, `ordenescompra`, `encabezadocompras`)? | Sí/No con evidencia. Alimenta la decisión **D-1**. |
| A-0.2 | ¿`edw.Fact_Transferencias` tiene filas? ¿Permite medir el tiempo real entre salida de origen y entrada a destino? | Conteo real + rango de fechas. |
| A-0.3 | Distribución ABC real: ¿qué % de SKUs concentra el 80% del valor de consumo (12 meses)? | Curva de Pareto real, no supuesta. |
| A-0.4 | Distribución XYZ real: histograma del CV de demanda mensual por SKU. ¿Los umbrales `BODEGA_CV_ALTA=1.2 / CV_MEDIA=2.5` discriminan algo sobre datos reales? | Percentiles reales; recalibrar umbrales si no discriminan. |
| A-0.5 | ¿Cuántos SKU tienen historia suficiente para un ROP estocástico (≥6 meses con movimiento)? Cruzar con `ML_DEMANDA_MIN_MESES_VENTA=6`. | % del catálogo que **necesitará** política degradada. |
| A-0.6 | Confirmar H-9: ¿`salidas_periodo` respeta `fecha_desde/fecha_hasta`? Comparar la misma consulta a 30 y a 90 días. | Confirmado/refutado con dos respuestas reales. |
| A-0.7 | Impacto de sustituir el ROP determinista por el estocástico: recalcular ambos sobre todo el catálogo y comparar cuántos artículos cambian de estado. | Distribución del delta. **Si el cambio es masivo, es un cambio de política de negocio, no un refactor** — requiere aprobación explícita. |
| A-0.8 | Exactitud real de `demand_rf` por SKU: correr `ml/scripts/backtest_demand_por_sku.py`. ¿Es mejor que un promedio móvil ingenuo? | WAPE modelo vs. baseline. **Si el modelo no gana, H-2 se resuelve declarando el método estadístico, no forzando ML.** |
| A-0.9 | Medir la latencia real de `/necesidad-compra` e `/inventario-matriz` sobre el catálogo completo. | Línea base antes de agregar cálculos. |
| A-0.10 | Recorrido UX real de las 3 páginas con el rol `bodega`: cuántos clics separan "abrir el módulo" de "sé qué comprar". | Número concreto, para comparar contra el rediseño. |

---

## 5. Decisiones que requieren al usuario (bloquean el diseño, no la auditoría)

| ID | Decisión | Opciones | Recomendación |
|---|---|---|---|
| **D-1** | **Origen del lead time** (bloquea el ROP, la columna "Lead Time" y "Proveedor recomendado"). | (a) Tabla de configuración `public.reabastecimiento_lead_time` que gerencia llena por proveedor/categoría, con default global; (b) extender el ETL para extraer órdenes de compra de SAP y derivarlo (depende de A-0.1); (c) dejar el global de 7 días. | **(a) ahora + (b) después.** (a) es honesta, editable, auditable y no depende de que SAP tenga el dato; (b) es la solución definitiva pero es un proyecto de ETL propio. (c) queda descartada: es el H-1. |
| **D-2** | **Nivel de servicio objetivo** (define `z` del stock de seguridad). | 90% / 95% / 97.5%, global o por clase ABC. | **Por clase ABC**: A=97.5%, B=95%, C=90%. Configurable, sembrado con esos valores. |
| **D-3** | **"Enviar al ERP"** (bloque 5 del pedido). | SAP es **solo lectura** por restricción permanente del proyecto. | Reinterpretar como: **propuesta de compra persistida en `public.*` + export (Excel/PDF) + estado aprobada/rechazada con bitácora.** El write-back a SAP queda explícitamente fuera de alcance y documentado como tal. |
| **D-4** | **Alcance del reemplazo de las 3 páginas actuales.** | (a) Reemplazo total; (b) nueva página "Reabastecimiento" + retiro incremental de lo duplicado. | **(b).** El módulo tiene 3.400 líneas de backend en producción con RLS por almacén validada en vivo; un big-bang arriesga esa RLS. |
| **D-5** | **Presupuesto disponible** (filtro del simulador). | No existe ninguna fuente de presupuesto de compras en el EDW. | Entrada **manual** del usuario en el simulador (nunca leída de ningún lado ni inventada). |

---

## 6. Arquitectura funcional del módulo nuevo

### 6.1 Principio rector

Cada elemento de la UI debe poder completar esta frase: *"Estoy aquí porque el usuario necesita decidir **X**, y al terminar habrá hecho **Y**."* Si no puede, no entra.

### 6.2 Motor puro nuevo — `backend/app/services/replenishment_engine.py`

Funciones puras, sin I/O, 100% testeables (mismo patrón que `commission_variable_engine.py` / `goal_pipeline_stages.py`). Es el único lugar donde vive la matemática de Supply Chain.

```python
clasificar_abc(valor_consumo_por_sku, cortes=(0.80, 0.95)) -> Literal["A","B","C"]
clasificar_xyz(cv_demanda, umbrales) -> Literal["X","Y","Z"]
demanda_diaria(serie, ventana_dias) -> tuple[media, desviacion]   # corrige H-9
stock_seguridad(sigma_demanda, lead_time_dias, z) -> float        # z·σ·√LT  (H-3)
punto_reorden(demanda_media, lead_time_dias, stock_seguridad) -> float
cobertura_dias(stock, demanda_diaria) -> float | None
riesgo_quiebre(cobertura, lead_time, sigma) -> Literal["critico","alto","medio","bajo"]
cantidad_sugerida(stock, demanda_prevista, rop, horizonte, multiplo_compra) -> float
prioridad(abc, riesgo, cobertura, dias_a_quiebre) -> int          # score ordenable
explicar(...) -> DesgloseRecomendacion                            # trazabilidad completa
```

Contrato de degradación obligatorio: cada función devuelve, junto al número, el **método usado** (`estocastico` | `determinista` | `sin_historia`) y por qué. Un SKU con 2 meses de historia **no** recibe un `z·σ·√LT` fingido — recibe la política determinista y lo dice.

### 6.3 Persistencia nueva (migración Alembic `0016_reabastecimiento`)

| Tabla | Grano | Propósito |
|---|---|---|
| `public.reabastecimiento_politica` | `(clase_abc)` o global | `nivel_servicio`, `z`, `horizonte_default`, `dias_ventana_demanda`, cortes ABC/XYZ. Editable por gerencia, con bitácora en `comision_config_auditoria` (reutiliza el patrón existente). |
| `public.reabastecimiento_lead_time` | `(proveedor \| categoria \| producto)` + vigencia | **D-1(a)**. Resolución por especificidad: producto > categoría > proveedor > default global. |
| `public.propuesta_compra` | cabecera | **D-3**. Estado `borrador\|aprobada\|rechazada\|exportada`, usuario, fecha, filtros de origen, total. |
| `public.propuesta_compra_linea` | línea | Artículo, cantidad, costo, proveedor, **snapshot congelado de la justificación** (mismo criterio que `comision_liquidaciones`: la propuesta no se recalcula al mirarla). |
| `public.transferencia_decision` | sugerencia | Cierra **H-5**: la aprobación deja de ser `useState`. |

### 6.4 Endpoints nuevos — prefijo `/analytics/bodega/reabastecimiento`

| Endpoint | Devuelve | Bloque UX |
|---|---|---|
| `GET /resumen` | KPIs de decisión (§3) + conteo de alertas por severidad | 1. Centro de Decisiones |
| `GET /lista` | `Page[ItemReabastecimiento]` priorizada por criticidad | 2. Lista Inteligente |
| `GET /lista/{codart}/explicacion` | `DesgloseRecomendacion` completo | 3. Explicabilidad |
| `POST /simular` | Recalcula la lista bajo parámetros hipotéticos, **sin persistir** | 4. Simulación |
| `GET /alertas` | Alertas tipadas con acción sugerida y deep-link | Panel de alertas |
| `POST /propuestas` · `GET /propuestas` · `POST /propuestas/{id}/aprobar` · `GET /propuestas/{id}/excel` | Gestión operativa | 5. Gestión Operativa |
| `GET /exactitud-modelo` | WAPE por SKU/categoría del último backtest + fecha | KPI de exactitud |
| `PUT /politica` · `PUT /lead-times` | Configuración editable | Panel de configuración |

**Contrato central** — `ItemReabastecimiento` (la fila de la lista inteligente):

```
prioridad_score, prioridad_etiqueta, codart, nombre, categoria,
clase_abc, clase_xyz,
stock_actual, demanda_diaria_media, demanda_diaria_sigma,
demanda_prevista_horizonte, metodo_demanda,        # ml_demand_rf | estadistico | sin_historia
cobertura_dias, punto_reorden, stock_seguridad,
lead_time_dias, lead_time_origen,                  # producto|categoria|proveedor|default  ← nunca oculta que es default
cantidad_sugerida, costo_unitario, costo_total,
riesgo, dias_hasta_quiebre, fecha_estimada_quiebre,
proveedor_recomendado, confianza_modelo, confianza_origen,
estado, acciones_disponibles[]
```

Cada campo derivado de un modelo o de un default lleva **su procedencia al lado**. Es el mecanismo que impide que un lead time de 7 días inventado se lea como un dato del ERP.

### 6.5 Uso correcto del ML (cierra H-2, H-7, H-8)

1. `demanda_prevista_horizonte` pasa a alimentarse de `demand_rf` **cuando el SKU cumple el umbral de historia** y el backtest (A-0.8) demuestre que el modelo gana al baseline; en cualquier otro caso, método estadístico **declarado en el campo `metodo_demanda`**.
2. `confianza_modelo` deja de ser el MAE global: se deriva del **WAPE por SKU del backtest** (H-8), o se declara `null` con `confianza_origen="sin_backtest"`.
3. La banda de confianza del gráfico crece con el horizonte (`σ·√h`) en vez de ser constante (H-7).
4. El filtro "exactitud mínima del modelo" que pide el usuario **solo puede existir si (2) se implementa**. Si el backtest no llega a producir métricas por SKU, ese filtro se omite del diseño en vez de rellenarse con un número inventado.

---

## 7. Rediseño de la interfaz

### 7.1 Navegación propuesta (D-4: incremental)

```
Bodega
├── Reabastecimiento   ← NUEVA, página de aterrizaje por defecto del rol
│   ├── Centro de Decisiones (KPIs + alertas)
│   ├── Lista Inteligente (tabla priorizada + explicabilidad expandible)
│   ├── Simulador (panel lateral)
│   └── Propuestas de Compra (gestión operativa)
├── Status por Almacén ← se conserva; pierde el plan de compra (migra a Reabastecimiento)
├── Análisis           ← lo que sobreviva del dashboard actual, degradado a exploración
└── Reportes Gerencia  ← sin cambios (contrato tipado ya cerrado, Fase 5/6 previas)
```

### 7.2 Gráficos — mantener / eliminar / reemplazar

| Gráfico actual | Decisión | Motivo |
|---|---|---|
| G1 Histórico + Predicción de Salidas | **Mantener, reubicar** | Es el único que responde una pregunta de decisión ("¿alcanza el stock?"). Pasa a la vista de detalle de un artículo, con línea de ROP y de quiebre proyectado. Quitar el `<Brush>` (H-12) y permitir buscar **cualquier** artículo, no solo el top-20 (H-13). |
| G2 Matriz Rotación × Margen (scatter) | **Reemplazar** | Es análisis financiero, duplica el Dashboard Ejecutivo (H-10). Se reemplaza por la **matriz ABC/XYZ**, que sí define política de inventario. |
| G3 Top 20 Productos con Mayor Salida | **Eliminar** | Ordena por ventas, exactamente lo contrario de lo que pidió el usuario ("ordenar por criticidad, no por ventas"). Los más vendidos rara vez son los que están por quebrar. |
| G4 Distribución de Salidas por Categoría (pie) | **Eliminar** | Descriptivo puro. Ninguna acción se deriva de él. |
| G5 Stock vs Punto de Reorden | **Fusionar** | Se absorbe en la Lista Inteligente, que lo dice mejor y con acción. |
| G6 Predicción de Compras del Mes | **Mantener, reenfocar** | Útil para planificación de presupuesto. Pasa de "unidades por categoría" a "**necesidad de compra vs. presupuesto**". |
| — | **Nuevo** | Cobertura de inventario por categoría (barras con umbral de lead time). |
| — | **Nuevo** | Riesgo de ruptura por almacén (mapa de calor). |
| — | **Nuevo** | Demanda pronosticada vs. stock disponible (proyección de agotamiento). |
| — | **Nuevo** | Distribución ABC/XYZ (9 celdas, cada una con su política). |
| — | **Nuevo** | Exactitud histórica del modelo (solo si A-0.8 la produce). |
| — | **Nuevo, condicionado a D-1** | Lead Time por proveedor. **Si D-1 se resuelve como (a), este gráfico muestra la configuración vigente, no una medición** — y debe rotularse así. |

### 7.3 Filtros

**Se conservan:** Almacén, Categoría, Proveedor, Fechas, Tipo de movimiento.

**Se agregan** (cada uno debe tener un dato real detrás — los marcados ⚠ dependen de una decisión abierta):

| Filtro | Fuente | Estado |
|---|---|---|
| Clasificación ABC | Calculada (A-0.3) | ✅ |
| Clasificación XYZ | Calculada (A-0.4) | ✅ |
| Riesgo (crítico/alto/medio/bajo) | Motor | ✅ |
| Cobertura (rango de días) | Motor | ✅ |
| Estado del inventario | Ya existe (`estado`) | ✅ |
| Prioridad | Motor | ✅ |
| Horizonte de predicción | Query param ya existente, hoy no expuesto (H-11) | ✅ |
| Solo artículos con recomendación | Motor | ✅ |
| Solo artículos críticos | Ya existe (`solo_criticos`) | ✅ |
| Solo artículos con quiebre proyectado | Motor | ✅ |
| Lead Time | `reabastecimiento_lead_time` | ⚠ D-1 |
| Exactitud mínima del modelo | Backtest por SKU | ⚠ A-0.8 |

Implementación: reutilizar `ComboboxField` (catálogos en memoria) y `Autocomplete` (búsqueda contra backend), ambos ya existentes. Los filtros nuevos son de baja cardinalidad → `ComboboxField` o chips multi-selección.

### 7.4 Alertas inteligentes

Panel alimentado por `GET /reabastecimiento/alertas`, **integrado al sistema de Notificaciones existente** (`NotificationService._generar_bodega` ya reutiliza `WarehouseService.get_notificaciones` — se extiende, no se duplica).

| Severidad | Alerta | Regla | Acción enlazada |
|---|---|---|---|
| 🔴 | Se agotará antes del próximo abastecimiento | `cobertura_dias < lead_time` | → Lista filtrada + añadir a propuesta |
| 🟠 | Sobrestock sobre el límite | `cobertura > BODEGA_DIAS_EXCESO` con capital asociado | → Transferencias sugeridas |
| 🔵 | Cambio brusco vs. comportamiento histórico | Demanda del período fuera de `media ± 2σ` histórica | → Detalle del artículo |
| 🟢 | Disminución sostenida de demanda | Tendencia negativa ≥3 períodos consecutivos | → Revisar política / no comprar |

Toda alerta lleva **artículo, magnitud, plazo y un deep-link a la acción**. Una alerta sin acción enlazada no se emite.

---

## 8. Plan de implementación incremental

Ordenado por *impacto sobre la decisión ÷ riesgo de romper lo que ya funciona*. Cada fase es entregable y validable por separado.

| Fase | Contenido | Depende de | Riesgo |
|---|---|---|---|
| **F0** | Auditoría (§4) → `docs/auditoria/50_...md` + resolución de D-1..D-5 con el usuario | — | Nulo (solo lectura) |
| **F1** | `replenishment_engine.py` (motor puro) + suite de tests unitarios. **Sin tocar ningún endpoint ni la UI.** | F0 | Nulo |
| **F2** | Migración `0016` + repositorios de política/lead-time + endpoints de configuración + panel de configuración | F1, D-1, D-2 | Bajo |
| **F3** | `GET /reabastecimiento/lista` (+ ABC/XYZ, ROP estocástico, riesgo, prioridad). **Convive con `/necesidad-compra`, no lo reemplaza todavía.** | F2 | Medio — cambia la recomendación de compra (ver A-0.7) |
| **F4** | Frontend: página Reabastecimiento con Centro de Decisiones + Lista Inteligente + filtros nuevos | F3 | Bajo (página nueva) |
| **F5** | Explicabilidad (`/lista/{codart}/explicacion` + fila expandible con `renderExpanded`) | F3 | Bajo |
| **F6** | Corrección del uso del ML: H-2 (motor consume `demand_rf`), H-7 (banda por horizonte), H-8 (exactitud por SKU) | F3, A-0.8 | Medio |
| **F7** | Alertas inteligentes integradas a Notificaciones | F3 | Bajo |
| **F8** | Simulador (`POST /simular`) | F3 | Bajo (no persiste) |
| **F9** | Gestión operativa: propuestas de compra persistidas, agrupación por proveedor, export, aprobación; **cierre de H-5** (decisiones de transferencia persistidas) | F2, F3, D-3 | Medio (escribe en `public.*`) |
| **F10** | Limpieza: retirar G3/G4, migrar G2→ABC/XYZ, sacar KPIs financieros (H-10), exponer o retirar los KPIs muertos (H-6), decomisionar `/necesidad-compra` si `/lista` lo supera | F4-F9 | Medio (rompe contratos) |
| **F11** | Documentación: reglas RN-B12.. en `docs/auditoria/02_reglas_negocio_validadas.md` §16, actualización de `CLAUDE.md`, cierre de la auditoría 50 | Todas | Nulo |

**Corte mínimo de valor:** F0→F1→F2→F3→F4. Con eso el usuario ya tiene lista priorizada real, ABC/XYZ, ROP estocástico y lead time configurable — el salto grande de calidad de decisión. Todo lo demás es incremento sobre una base ya correcta.

---

## 9. Criterios de aceptación y validación

Por fase, y siguiendo el estándar de validación de este proyecto (no se declara terminado sin evidencia en vivo):

1. `pytest backend/tests/unit` verde, con **tests nuevos del motor puro** (cada fórmula de Supply Chain con su caso de degradación: sin historia, demanda cero, lead time faltante).
2. `pytest backend/tests/integration -k "bodega or warehouse or reabastecimiento"` sin regresiones, **incluido `test_bodega_rls.py`** — la RLS por almacén (RN-B10) es innegociable y toda consulta nueva debe pasar por `_filtros_snapshot`.
3. `tsc --noEmit`, `oxlint` y `npm run build` limpios.
4. `bi_backend` reconstruido, arranque limpio, migración `0016` aplicada contra `bi_postgres_edw` real.
5. **Prueba en vivo con datos reales**, documentada con cifras concretas en la auditoría 50: un artículo con su ROP antes/después, la lista priorizada, y el conteo de artículos que cambian de estado (A-0.7).
6. **Métrica UX:** clics desde "abrir el módulo" hasta "sé qué comprar y cuánto", comparados contra la línea base de A-0.10.
7. Verificación explícita de que **ningún campo del contrato nuevo está poblado con un valor inventado** — revisión campo por campo del `ItemReabastecimiento` contra su fuente.

---

## 10. Riesgos y salvaguardas

| Riesgo | Salvaguarda |
|---|---|
| El ROP estocástico cambia la política de compra de todo el catálogo de golpe | A-0.7 lo cuantifica **antes**; F3 convive con el motor viejo; la política es configurable y reversible sin desplegar código |
| Lead time configurado a mano queda desactualizado y nadie lo nota | Vigencia + bitácora; la UI muestra siempre `lead_time_origen` — un `default` visible es una invitación a corregirlo |
| Se rompe la RLS por almacén al agregar consultas | Todo SQL nuevo pasa por `WarehouseRepository._filtros_snapshot`; `test_bodega_rls.py` es criterio de aceptación de cada fase |
| El backtest muestra que `demand_rf` no gana al baseline | Está previsto: F6 declara `metodo_demanda="estadistico"`. **No se fuerza el ML para poder decir que hay ML** — mismo criterio con que se decomisionaron `goals_rf` y `sales_rf` |
| El módulo se vuelve lento al calcular ABC/XYZ/ROP por request | A-0.9 fija la línea base; ABC/XYZ se materializan por lote (no por request); reutilizar el patrón de cache ya existente (`_prediccion_cache`) |
| Alcance excesivo para una sesión | F0-F4 es el corte mínimo; cada fase posterior es independiente y se puede diferir explícitamente |

---

## 11. Fuera de alcance (declarado, no omitido)

- **Escritura hacia SAP.** Restricción permanente del proyecto (`CLAUDE.md` §Restricciones). "Enviar al ERP" se resuelve como propuesta persistida + export (D-3).
- **Extracción de órdenes de compra desde SAP** para lead time medido (D-1 opción b): es un proyecto de ETL propio, con su propio extractor, transformer, tabla de hechos y auditoría. Se documenta como trabajo futuro concreto.
- **Modelo ML nuevo.** El plan reutiliza `demand_rf`. Un ranker de priorización de compra podría explorarse después, pero el precedente de `cross_sell_ranker` (entrenado, medido, **no promovido**) recomienda no comprometerlo antes de tener el motor determinista funcionando y medido.
- **Optimización multi-echelon / EOQ con descuentos por volumen.** Sin datos de costos de pedido ni de almacenamiento en el EDW.
- **Notebooks y documentos de auditoría previos del módulo Bodega.** Se conservan como historia (mismo criterio aplicado en las decomisiones de `goals_rf` y `sales_rf`).
