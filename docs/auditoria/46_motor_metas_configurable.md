# Auditoría 46 — Motor de Metas Comerciales (Fase 0 de `docs/features/plan_motor_metas_configurable.md`)

> **Fecha:** 2026-07-31. **Método:** `SELECT` contra `bi_postgres_edw` real + ejecución en modo lectura de `GoalMLService.suggest_goal`/`GoalRepository` dentro de `bi_backend` (sin escrituras; script descartado tras la corrida). Sin acceso a Producción (SAP) en esta auditoría — no era necesario, todo el insumo ya vive en el EDW.

## A-0.1 — Cumplimiento real de las metas ya configuradas

`public.metas_comerciales_operativas` tiene 18 filas: 9 para 2026-07 (mes ya cerrado a la fecha de la auditoría, 2026-07-31) y 9 para 2026-08 (mes que no ha empezado — `venta_real=$0` en las 9, dato esperado, no un hallazgo).

Cumplimiento real de las 9 filas de **julio** (único mes con dato comparable):

| Vendedor | Meta | Venta Neta real | Cumplimiento |
|---|---|---|---|
| VEN24 | $37.182,65 | $24.913,00 | **67,0%** |
| VEN15 | $16.885,18 | $12.842,63 | **76,1%** |
| VEN13 | $80.403,48 | $69.453,09 | **86,4%** |
| VEN02 | $62.039,69 | $54.298,43 | 87,5% |
| VEN16 | $12.176,90 | $11.650,13 | 95,7% |
| VEN03 | $32.584,39 | $31.862,12 | 97,8% |
| VEN21 | $32.040,90 | $33.553,67 | 104,7% |
| VEN01 | $67.557,89 | $74.307,99 | 110,0% |
| VEN17 | $5.652,92 | $7.035,26 | 124,5% |

**Mediana: 95,7%.** 33,3% (3/9) por debajo del umbral de pago del 90% (auditoría 45); 33,3% (3/9) sobre el 100%.

**Matiz importante para el usuario:** la mediana agregada de julio **no** es catastrófica — está cerca del rango sano de referencia (60–70% de la fuerza de ventas en o sobre cuota; aquí es 33%, algo bajo pero no roto). El problema no es "todas las metas están mal", es que **hay casos concretos y mecanismos concretos** que producen picos de sobre-ajuste — exactamente lo que confirma A-0.4. Se documenta para no sobre-vender el diagnóstico.

## A-0.2 — H-1 confirmado estructuralmente

`GoalMLService.suggest_goal(vendedor_origen, factor_estacional, factor_crecimiento)` **no recibe `anio`/`mes` en su firma**. El "mes objetivo" siempre se deriva como `último mes con datos + 1` (`IQRGoalCalculationEngine._calcular_base_siguiente_mes`). Confirmado en vivo: para los 3 vendedores probados, el último dato es 2026-07 y el motor calcula para 2026-08 — coincide con el período real porque hoy (2026-07-31) es el último día del mes, pero **no hay ningún mecanismo que ate el cálculo al período que Gerencia efectivamente pidió**: si se llamara `generate_proposals(2026, 10)` con el mismo histórico, el motor seguiría calculando para 2026-08 en silencio. Confirmado, severidad ALTA.

## A-0.3 — Viabilidad de estacionalidad multi-anual (revisa la hipótesis del plan)

20 vendedores con historia real en `fact_ventas_detalle`. Los 4 de mayor volumen (VEN01/02/03/13) y VEN15 tienen **9 años** de historia (2018–2026, 100–103 meses con venta). Con ventana de 24 meses, **81,1% de los pares (vendedor, mes-calendario) ya tienen ≥2 años de observaciones del mismo mes** — mejor de lo que el plan anticipaba (H-2 asumía "a lo sumo una observación"; la conclusión era válida para vendedores individuales cortos, no para la mayoría). Esto **valida** el diseño de índice estacional multi-anual por vendedor como caso general, con el índice de empresa como respaldo solo para la minoría de vendedores nuevos/cortos:

- **Historia larga (≥4 años, índice propio viable):** VEN01, VEN02, VEN03, VEN13, VEN15, VEN16, VEN17, VEN21.
- **Historia corta (2–3 años, índice propio poco confiable):** VEN22, VEN24.
- **1–3 meses o discontinuados (sin índice estacional posible):** VEN04, VEN07, VEN09, VEN10, VEN12, VEN14, VEN18, VEN19, VEN23 — varios con última venta hace 2-4 años (probablemente vendedores dados de baja, no "nuevos"); no deberían recibir una meta activa en absoluto.

## A-0.4 — Descomposición de la cadena (el hallazgo más directo del reclamo del usuario)

Recalculando `suggest_goal` **hoy** para los vendedores de peor cumplimiento en julio, con datos hasta el 30/31 de julio:

| Vendedor | método | atípicos IQR excluidos | atípicos ML | estacional | tendencia | factor tend. | CV | **meta recalculada hoy** | **meta persistida (ago-2026)** |
|---|---|---|---|---|---|---|---|---|---|
| VEN01 | IQR | 1 | 0 | $64.409,89 | $64.797,91 | 1,0007 | 0,076 | $64.648,70 | $74.508,70 |
| VEN02 | IQR | 4 | 0 | $42.189,69 | $57.438,22 | 1,0293 | 0,132 | $51.272,47 | $72.495,51 |
| VEN03 | IQR | 0 | 0 | $31.625,96 | $34.805,60 | 0,9387 | 0,126 | $31.181,23 | $43.292,22 |
| VEN13 | IQR | 0 | 0 | $72.991,46 | $86.655,30 | 0,9639 | 0,158 | $76.941,13 | **$121.359,95** |
| VEN15 | **IQR+ML** | 0 | **1** | $14.031,41 | $14.104,00 | 1,1486 | 0,129 | $16.158,06 | $20.326,42 |

**Hallazgo central: la meta persistida de agosto para VEN13 ($121.359,95) es un 58% más alta que lo que el mismo motor, con la misma configuración, calcula hoy ($76.941,13).** Esta discrepancia **no se puede explicar** porque `metas_comerciales_operativas` no guarda la traza del cálculo (confirma H-5): no hay forma de saber si se generó con un `factor_presion` distinto, con menos meses excluidos por IQR en ese momento, o con otra configuración de tipo de vendedor. Sea cual sea la causa, es la prueba concreta de dos cosas a la vez:

1. **H-3 (sin techo posterior)** es real: el rango teórico de multiplicadores posteriores al único guardarraíl es de hasta 1,79× — un salto observado de 1,58× (VEN13) cae dentro de ese rango sin que nada lo hubiera detenido.
2. **H-5 (sin trazabilidad)** impide diagnosticar exactamente esto — el caso que el propio usuario reporta ("valores demasiado elevados") es, en la práctica, indiagnosticable con el estado actual del sistema.

VEN15 además muestra el mecanismo de H-4 en acto: el único mes marcado como atípico por IsolationForest pesa 0,5 en el promedio, pero **no** se excluye de `componente_tendencia` con peso reducido correctamente atenuado — el `factor_tendencia_aplicado=1,1486` (el más alto de los 5 vendedores) sugiere que ese mes atípico sigue empujando la tendencia hacia arriba.

## A-0.5 — Estacionalidad y variabilidad reales del negocio

**Índice estacional agregado de la empresa** (9 años, `SUM(subtotal_neto)` por mes calendario, normalizado a media 1.0):

| Mes | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Índice | 1,040 | 0,913 | 0,970 | 0,929 | 1,034 | 1,019 | 1,074 | 1,007 | 0,989 | 1,013 | 0,931 | 1,081 |

La estacionalidad real del negocio es **moderada** (rango 0,913–1,081, ±10% máximo) — no hay un "mes bajo" dramático. Esto es importante para el diseño: la estacionalidad **no es la causa principal** de metas infladas; los responsables son H-3 (sin techo) y H-4 (picos filtrándose a la tendencia), confirmando que el diseño debe priorizar la banda de alcanzabilidad sobre el índice estacional.

**Coeficiente de variación por vendedor** (venta mensual bruta, histórico completo): los vendedores activos de mayor volumen son razonablemente estables (VEN01=0,277, VEN02=0,224, VEN03=0,175, VEN13=0,282, VEN21=0,220, VEN22=0,252, VEN24=0,258); varios vendedores marginales o discontinuados muestran CV extremo (VEN09=1,834, VEN19=1,650, VEN14=0,879, VEN17=0,999, VEN18=1,165, VEN04=1,204, VEN23=0,931) — consistente con A-0.3: son vendedores sin base estadística sólida para ninguna fórmula, y deberían caer en el peldaño más bajo de la escalera de degradación (o quedar excluidos de la generación automática).

## A-0.6 — Estado de Comisiones Variables (confirma H-8 en vivo)

`COMISION_MODO = plana` en este entorno; `public.comision_liquidaciones` tiene **0 filas**. Confirmado: hoy, en producción, la columna "Comisión (variable · piloto)" del panel "Comisiones devengadas" **nunca se renderiza** (`modoSombraActivo` siempre `false` en modo `plana`) — el gap de H-8 es 100% real y activo ahora mismo, no hipotético. Esto sube la prioridad de la Fase 5 del plan: es la única corrección de las siete fases que no depende de ninguna decisión sobre la fórmula de metas.

## Decisión (regla del plan §4)

A-0.1 no muestra una ruptura agregada catastrófica, pero A-0.4 confirma con un caso real y cuantificado (VEN13, +58%) que los mecanismos H-1/H-3/H-4/H-5 son reales y producen exactamente el síntoma reportado por el usuario en casos concretos, no en el promedio. Se procede con las Fases 1–7 del plan tal como están diseñadas: los guardarraíles (banda de alcanzabilidad final, tratamiento correcto de meses atípicos, trazabilidad persistida) atacan directamente los mecanismos confirmados, sin necesidad de rediseñar la fórmula desde cero.

Estacionalidad multi-anual **por vendedor** se confirma viable para la mayoría (A-0.3); índice de empresa como respaldo para el resto — diseño de la Fase 2 sin cambios respecto del plan.

## Aplicado (Fases 1-7 completas) y validación en vivo

Motor v2 implementado directamente sobre `goal_calculation_engine.py` (se evolucionó el mismo archivo en vez de mantener dos motores paralelos seleccionables — simplificación deliberada de esta sesión). Migración `0013_motor_metas_v2` aplicada contra `bi_postgres_edw` real (`trazabilidad_calculo` JSONB + `metas_config_parametros` sembrada). `bi_backend` reconstruido con arranque limpio (6/6 modelos ML).

**Bug real encontrado y corregido durante la validación en vivo** (no en unit tests): `CommissionService._MODO_BACKEND_A_LIQUIDACION` no tenía clave `"plana"` — al hacer que `get_commission_tracking` calculara la comisión variable SIEMPRE (H-8), la primera llamada real en modo `plana` (el modo de producción) lanzó `KeyError: 'plana'`. Antes este código nunca se ejecutaba en `plana` porque estaba gateado por `COMISION_MODO in ("sombra","variable")`. Corregido añadiendo `"plana": None` al mapa y un guard en `_persistir_snapshot` (`if modo_liquidacion is None: return`) — la comisión variable se calcula y se muestra, pero nunca se persiste como snapshot en modo `plana`. Confirmado en vivo: `GET /gerencia/goals/commissions?anio=2026&mes=7` devuelve `comision_variable`/`tramo_variable` reales para los 9 vendedores de julio-2026, y `public.comision_liquidaciones` permanece en 0 filas.

**Segundo bug real encontrado en vivo, preexistente (no introducido en esta sesión):** `GoalRepository.get_vendors_with_recent_sales` no excluía el registro centinela `codven='-1'` (regla 12, vendedor sin resolver) — al regenerar metas para 2026-08 se creó una fila real de meta comercial para "el vendedor -1" ($136,88). Corregido agregando `AND v.codven <> '-1'` a la consulta; el artefacto de prueba se eliminó de la base real tras confirmarlo, y la regeneración posterior ya no lo reproduce.

**Confirmación end-to-end del efecto de la corrección (H-1/H-3/H-5):** regenerando la meta de agosto-2026 para `VEN13` con el motor v2, el resultado es **$69.820,79** (105,8% de su venta neta real de julio, $69.453,09) — sustituye la meta v1 persistida anteriormente ($121.359,95, un 74,8% por encima de la venta real de julio). `GET /gerencia/goals/meta-sugerida?vendedor_origen=VEN13&anio=2026&mes=8` devuelve `es_trazabilidad_persistida=true` con la traza real (`banda_actuo=false`, la meta ya cayó dentro de la banda sin necesitar el guardarraíl).

Validado extremo a extremo: `pytest backend/tests/unit` (241 tests — 35 nuevos/reescritos en `test_goal_calculation_engine.py` cubriendo período objetivo explícito en cada mes calendario incluido diciembre→enero, índice estacional normalizado, banda de alcanzabilidad actuando como techo Y piso, cada peldaño de la escalera de degradación, un pico de un solo mes no domina la meta; 2 nuevos en `test_commission_service.py` para el bug de `_MODO_BACKEND_A_LIQUIDACION` y la guarda de rendimiento `call_count==1`; 240 passed, 1 falla preexistente ajena y dependiente de la fecha del sistema); `pytest backend/tests/integration -m integration` (126 passed, 3 skipped, 4 failed -- los 4 son artefactos ya documentados y ajenos: 2 por agotamiento del rate limiter de `/auth/login` en la corrida combinada -- pasan en aislamiento --, 1 por el vendedor 102 sin histórico suficiente en el EDW real a la fecha de esta corrida -- mismo hallazgo ya documentado en sesiones previas --, 1 en `test_prediccion_compras_mes_con_categoria` del módulo Bodega, no tocado en esta sesión); `tsc -b`/`oxlint`/`npm run build` de producción limpios. Probado en vivo con `curl` autenticado contra `bi_backend` real: `GET/PUT /gerencia/goals/meta-config/parametros` (validación de rango rechaza `banda_alcanzabilidad_max=5.0`), bitácora de cambios poblada, `/commission-simulation` sin cambios de comportamiento.
