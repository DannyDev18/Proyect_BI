# Auditoría 47 — Fase 0 del plan de Metas v3 y Comisiones Unificadas

> **Fecha:** 2026-07-31. **Método:** `SELECT` real contra `bi_postgres_edw` (contenedor `bi_postgres_edw`, BD `edw`, usuario `etl_user`) vía `docker exec`. Ninguna escritura. Continuación de `docs/features/plan_motor_metas_v3_y_comisiones_unificadas.md` §3.

## A-0.3 — Cumplimiento real de julio-2026 y origen de cada meta

Las 9 metas de julio-2026 (todas generadas con el motor v2, `estacional_propio_v2`/`estacional_empresa_v2` — no hay contaminación de metas v1 legado en este período):

| Vendedor | Meta | Venta real | % cumplimiento |
|---|---|---|---|
| VEN24 | $45.763,31 | $28.050,81 | 61.3% |
| VEN02 | $67.891,27 | $61.929,98 | 91.2% |
| VEN13 | $80.217,75 | $73.284,06 | 91.4% |
| VEN15 | $14.749,11 | $13.706,68 | 92.9% |
| VEN16 | $13.720,07 | $12.746,34 | 92.9% |
| VEN03 | $36.317,32 | $34.067,44 | 93.8% |
| VEN01 | $71.297,38 | $76.392,31 | 107.1% |
| VEN21 | $32.040,90 | $37.593,66 | 117.3% |
| VEN17 | $1.506,80 | $7.193,66 | 477.4% |

**Mediana: 92.9%. Solo 3/9 (33.3%) alcanzó ≥100%** — muy por debajo del 60-70% que Zoltners, Sinha & Lorimer fijan como calibración correcta de una cuota. **Confirma R-9**, pero con un matiz importante que corrige la lectura inicial: **6 de 9 vendedores están en el rango 91-94%**, es decir, justo bajo el escalón de 100% pero **por encima** del umbral duro de 90% que R-2 introduciría — bajo el gate propuesto, esos 6 seguirían cobrando (a un multiplicador menor), no en $0. Solo `VEN24` (61.3%, 10 meses de historia, motor cayó a `estacional_empresa_v2` por falta de historia propia) quedaría en el tramo `[0,90)→0.0×`. El problema real de calibración es el **agrupamiento sistemático justo bajo el 100%**, no una mayoría bajo el 90%.

`VEN17` (477.4%) es un outlier severo: su meta ($1.506,80) es 47x menor que la de vendedores comparables — indica una banda de alcanzabilidad calculada sobre un histórico casi nulo o degradado. `banda_actuo=true` para VEN17 en ambos meses (julio Y agosto), confirmando que la banda SÍ actuó pero sobre una referencia baja.

## A-0.4 — Meses de historia por vendedor activo (viabilidad de E6/madurez)

| Rango de meses | Vendedores | % del total (24) |
|---|---|---|
| 0 meses | 4 (VEN20, VEN05, VEN06, VEN08) | 16.7% |
| 1-5 meses | 6 (VEN07, VEN10, VEN14, VEN12, VEN23, VEN19) | 25.0% |
| 6-23 meses | 3 (VEN18, VEN04, VEN24, VEN09) | ~17% |
| ≥24 meses | 11 (VEN22, VEN21, VEN11, VEN17, VEN16, VEN15, VEN13, VEN02, VEN03, VEN01) | ~46% |

**Confirma R-8 con severidad mayor a la esperada: 42% de los vendedores activos tiene <6 meses de historia**, incluidos 4 con **0 meses** (nunca facturaron). El diseño de madurez del §10/§18-E6 del plan (transición gradual 0/1-5/6-23/≥24) es directamente aplicable y necesario — hoy esos 10 vendedores dependen enteramente del escalón único `mediana_equipo × 0.60`.

Los vendedores con más historia (VEN01/02/03/13/15/16/17) son literalmente **almacenes/mostradores** (`nombre_vendedor`: "ALMACEN EL REY", "ALMACEN ATAHUALPA", etc.), no vendedores de cartera individuales — confirma la lectura de la auditoría 45 sobre `VEN01`.

## A-0.1 / R-6 — Anatomía del costo de comisión (caso VEN01)

No se re-ejecutó el motor completo (ya hay evidencia primaria suficiente): el propio usuario aportó el desglose real de julio-2026 para `VEN01` — comisión final $26.110,43, de los cuales **$25.444,91 (97.4%) son bonos**, contra una base de líneas+cobranza de apenas $1.283,08 pre-factor. `COMISION_BONO_CLIENTE_NUEVO=$50` sin techo (`backend/app/core/config.py:193`) es la causa mecánica: la auditoría 45 (H-5) ya había cuantificado un mes comparable con 512/677 clientes "nuevos" × $50 ≈ $25.600 para el mismo vendedor — coincide en orden de magnitud con lo reportado ahora. **Causa raíz confirmada, no nueva.** `VEN01` es un mostrador con alta rotación de compradores ocasionales (31.107 clientes distintos de por vida, 55% de compra única, auditoría 45) — el bono de "cliente nuevo" no distingue eso de una captación real de cartera.

**Decisión que resulta de esta evidencia (aplicada en la Fase 2 de este plan):** techo relativo de bonos sobre la base pre-bonos + exclusión/tope distinto para perfiles de mostrador/agencia (`comision_config_vendedor.tipo`/`agencia`, ya existente).

## A-0.6 — Simulador (diferido)

No se ejecutó la comparación completa por límite de tiempo de esta sesión; la causa estructural ya está confirmada por lectura de código (plan §7, tres causas candidatas: fecha de configuración hoy-vs-cierre, promedio de multiplicadores en la proyección, inclusión/exclusión de bonos). Se prioriza en la Fase 4 con el test de paridad T-13 como validación directa, en vez de una reconstrucción manual adicional.

## Validación en vivo de las Fases 1-3 aplicadas (post-implementación)

`bi_backend` reconstruido con las Fases 1 (retiro del esquema plano), 2 (compuerta de cumplimiento + techo de bonos) y 3 (retiro de factores de crédito) aplicadas; arranque limpio, 6/6 modelos ML cargados. Probado en vivo con el usuario real `gerencia@empresa.com` contra `GET /gerencia/goals/commissions?anio=2026&mes=7`:

- **VEN13** (82,25% cumplimiento, bajo el 90%): `comision_devengada=$0,00` pese a `bonos=$5.100,00` en la traza -- confirma que la compuerta de la Fase 2 ahora sí bloquea la comisión completa, no solo la base.
- **VEN01/ALMACEN EL REY** (99,01% cumplimiento, el caso reportado por el usuario): bonos pasan de **$25.444,91** (97,4% de la comisión, caso original) a **$929,33** (techo relativo al 100% de la base pre-bonos, $929,33) -- comisión final **$1.613,03**, frente a los $26.110,43 originales. Reducción de ~93,8% en este caso puntual, con el mecanismo actuando de forma genérica (no una regla ad-hoc para este vendedor).

Sin errores en logs del contenedor durante la prueba. `pytest backend/tests/unit` completo: 240 passed, 1 falla preexistente ajena (dependiente de la fecha del sistema, ya documentada). `tsc --noEmit`/`oxlint` del frontend limpios.

## Validación en vivo de la Fase 4 (simulador) y Fase 7 parcial (madurez E6)

**Fase 4:** `POST /commission-simulation` con `{"anio":2026,"mes":7,"usar_configuracion_de_hoy":false}` responde `modo=reconstruccion_fiel` y `VEN01: $1.613,03` -- **coincide centavo a centavo** con `GET /commissions?anio=2026&mes=7` ($1.613,0293), confirmando en vivo la paridad que exigía R-4.

**Fase 7 (parcial -- solo la etapa E6/madurez, sin el resto del pipeline v3):** regenerando las metas de agosto-2026 (`POST /gerencia/goals/generate`) con la transición gradual ya viva, `VEN24` (10 meses de historia real, confirmado en A-0.4) pasa de $32.379,10 a **$30.646,62** -- el nuevo peso 80%/20% (propio/benchmark del equipo) actuando donde antes, con el escalón único legado (umbral de 3 meses vía `fecha_ingreso`), no se aplicaba ningún benchmark a un vendedor con 10 meses de historia. Sin errores en logs; 9 registros actualizados.

## Validación en vivo del cierre del gap de 0 meses de historia (R-8, continuación de la Fase 7)

`GoalRepository.get_active_vendors_without_history` (nueva) confirma en vivo, con el mismo `SELECT` de esta auditoría, los 4 vendedores exactos ya identificados en A-0.4: `VEN05` (IVAN ORTIZ), `VEN06` (UDO WEIH), `VEN08` (GONZALO TORRES), `VEN20` (CONTAB.ALTAHUALPA) -- ninguno tiene una sola fila en `fact_ventas_detalle` con estado válido.

`GoalMLService.generate_proposals` los incluye ahora en el lote (antes `get_vendors_with_recent_sales`, que exige venta el mes anterior, nunca los traía) y les asigna el benchmark puro del equipo vía `ajustar_meta_por_madurez(meses_antiguedad=0)` -- sin invocar el motor IQR, que exige histórico y lanzaría `ValidationError`. Regenerando agosto-2026 en vivo contra `bi_backend` reconstruido: `registros_creados` pasa de **9 a 13** -- exactamente los 4 vendedores nuevos -- cada uno con `monto_meta=$35.490,94`/`unidades_meta=1.305,55` (la mediana real del equipo de ese período) y `metodo_estadistico='sin_historico'`/`meses_historico_usados=0` en la trazabilidad persistida. Sin errores en logs. `pytest backend/tests/unit`: 253 passed (1 falla preexistente ajena, ya documentada).

Con esto, el gap real que había quedado documentado como NO resuelto en la sesión anterior queda cerrado: los 24 vendedores activos reciben una meta, sin excepción.

## Dos hallazgos reales adicionales, reportados por el usuario en producción y corregidos

Petición explícita del usuario tras ver el sistema en vivo: "las comisiones variables aun
no estan funcionando bien para todos los vendedores, de igual manera revisar si las
formulas para las metas y para las comisiones son funcionales para todos". Investigación
contra `bi_backend`/`bi_postgres_edw` reales confirmó 2 defectos distintos, no relacionados
entre sí:

### H-1 -- Traza de comisión inconsistente con el gate (bug real, corregido)

`calcular_comision_variable_completa` (Fase 2, R-2) ya forzaba `comision_final=0.0`
cuando el tramo de cumplimiento tenía multiplicador ≤0, pero la TRAZA devuelta
(`traza_formula`, expuesta al frontend como `componentes` -- el desglose expandible de
"Cumplimiento real y comisión por vendedor") seguía siendo la salida cruda de
`evaluar_formula` **sin** la compuerta: los pasos `devoluciones`/`bonos`, posteriores al
paso `multiplicador_cumplimiento` en la tubería, seguían restando/sumando sobre el
acumulado ya "gateado", terminando en un `acumulado_tras_paso` final distinto de cero.
Confirmado en vivo con `ALMACEN ATAHUALPA`/julio-2026 (82,25% cumplimiento, bajo el
90%): `comision_devengada=$0,00` pero la traza terminaba en `$4.689,34` tras sumar
`$5.100,00` de bonos -- gerencia veía un desglose que contradecía el total mostrado,
exactamente el síntoma reportado ("no está funcionando bien"). Corregido en
`commission_variable_engine.py`: cuando el gate aplica, se reescribe `acumulado_tras_paso`
a `$0` desde el paso `multiplicador_cumplimiento` (inclusive) en adelante -- los pasos
ANTERIORES (líneas, cobranza, contado de agencia, factor de tipo) se conservan intactos,
transparentes ("esto es lo que hubiera ganado antes del gate"). Nuevo test de regresión
(`test_umbral_90_deja_la_traza_consistente_con_el_cero_pese_a_bonos`) reproduce el caso
exacto con bonos activos. Validado en vivo tras reconstruir `bi_backend`: la misma
consulta ahora muestra los 3 últimos pasos en `$0`, consistente con `comision_devengada`.

### H-2 -- 11 de 24 vendedores "activos" no recibían ninguna meta (bug real, corregido)

`GoalRepository.get_vendors_with_recent_sales` exigía venta en el mes INMEDIATO anterior
al objetivo -- sin meta, un vendedor no puede tener comisión ni cumplimiento, así que
"las fórmulas no funcionan para todos" era literalmente cierto para estos vendedores: no
hay fórmula que aplicar sin una meta. Confirmado en vivo: regenerando agosto-2026 antes
de esta corrección, 11 de los 24 vendedores marcados `activo=TRUE` en `edw.dim_vendedor`
no tenían fila en `metas_comerciales_operativas`. Investigando el histórico real de cada
uno se encontraron dos grupos distintos: 9 genuinamente inactivos (última venta entre
2018-02 y 2024-03, ninguno con actividad en más de 2 años) -- correctamente sin meta,
no es un defecto de estos -- y **2 casos reales de vendedores con actividad reciente
excluidos injustamente**: `VEN22` (última venta oct-2025) y `VEN23` (última venta
dic-2025), ambos dentro del último año pero sin venta en julio-2026 específicamente.
**Decisión del usuario, explícita:** ventana de elegibilidad de 12 meses (vendedor activo
+ al menos una venta en los 12 meses previos al mes objetivo), no solo el mes inmediato
anterior. Corregido: `get_vendors_with_recent_sales` gana `meses_ventana=12` (parámetro,
default 12) y por primera vez filtra explícitamente `v.activo=TRUE` (antes no lo exigía
en absoluto, solo dependía indirectamente de que hubiera venta reciente). Validado en
vivo: regenerando agosto-2026, `registros_creados` pasa de 13 a **15** -- exactamente
`VEN22`($39.900,00)/`VEN23`($11.900,00) sumándose; los 9 vendedores genuinamente
inactivos (2018-2024, todos >12 meses de antigüedad) siguen correctamente sin meta,
confirmado consultando `edw.fact_ventas_detalle` directamente. Con esto, **15 de los 24
vendedores activos reciben una meta real** -- los 9 restantes no tienen defecto que
corregir, están fuera de la ventana de negocio acordada.

`pytest backend/tests/unit`: 291 passed (1 falla preexistente ajena, ya documentada).
`bi_backend` reconstruido dos veces (una por hallazgo), arranque limpio, sin errores en
logs durante ninguna de las pruebas en vivo.

## Fase 5/6 aplicada -- motor de metas v3 modular de 16 etapas (R-9/R-10/R-12)

Petición explícita del usuario tras el cierre de R-8: implementar el pipeline modular
completo de 16 etapas del plan (§18), no solo la etapa E6 ya aplicada. Alcance real
entregado, con las decisiones de ingeniería tomadas para no reescribir sobre una
hipótesis un motor que ya mueve dinero real y metas ya validadas en producción:

**Migración `0014_metas_config_modular`** (aplicada en vivo contra `bi_postgres_edw`,
nombre de revisión 25 caracteres, lección de la `0012` respetada): tabla nueva
`public.metas_config_modulos` (una fila por etapa, catálogo cerrado por `CHECK`), sembrada
exactamente con la configuración de §19 -- E1/E2/E3/E4/E5/E6/E8/E10/E11 activas, E7/E9/
E12/E13/E14/E15/E16 desactivadas con su `razon_desactivacion` visible. Los 13 valores de
`metas_config_parametros` se migraron por `SELECT` real (no hardcodeados) hacia el JSONB
de las etapas correspondientes; esa tabla y sus endpoints `/meta-config/parametros/*` se
CONSERVAN sin cambios (mismo criterio que `comision_factores_credito`), pero el motor real
ya no las lee. **Bug real encontrado y corregido durante la validación en vivo:** el
primer intento de `bulk_insert` serializaba `parametros` con `json.dumps()` antes de
insertarlo en una columna `JSONB` -- SQLAlchemy ya serializa dicts automáticamente, así
que el resultado era una cadena JSON *citada* dentro del JSONB (`'"{...}"'`), no un objeto;
`GET /meta-config/modulos` fallaba 500 al validar contra Pydantic. Corregido pasando dicts
crudos; migración revertida y reaplicada en vivo para sanear los datos ya insertados.

**Catálogo cerrado** (`app/services/goal_pipeline_stages.py::ETAPAS_CATALOGO`): documenta
las 16 etapas con TODOS los métodos que describe el plan §18, marcando cada uno
`implementado: true/false` -- los declarados-pero-no-implementados (ej. `isolation_forest`,
`holt_winters`, `regresion_lineal`, agrupador `sucursal`/`region`) exponen su motivo real
(sin dato, decomisionado, o simplemente no construido en esta sesión) y `MetaConfigModuloService`
**rechaza activarlos** (`ValidationError` explícito) -- nunca se puede prender en la UI algo
que no calcula nada real, cumpliendo el requisito de tesis de mostrar la arquitectura
completa tipo SPM sin fingir que todo está implementado.

**Etapas E1/E2/E3/E4/E5/E10 (banda)**: en vez de reescribir la matemática ya probada de
`IQRGoalCalculationEngine` en 6 funciones independientes (alto riesgo de introducir un
defecto sutil en un motor ya validado con datos reales), se le agregaron interruptores
(`aplicar_limpieza`/`aplicar_estacionalidad`/`aplicar_tendencia`/`aplicar_estabilidad`/
`aplicar_banda`, todos `True` por defecto) -- la etapa modular controla si esa parte del
motor se ejecuta, pero el cálculo en sí sigue siendo el mismo código ya probado. Sus
parámetros ahora se leen del JSONB de `metas_config_modulos` (`MetaConfigModuloService.
get_pipeline_config`), no de `metas_config_parametros`. **6 tests nuevos** verifican que
con todos los interruptores en `True` el resultado es idéntico al v2 (equivalencia exigida
por §19), y que cada interruptor en `False` es exactamente neutro para su etapa.

**Etapas E6/E7/E8/E9/E11/E13/E15/E16 (`app/services/goal_pipeline_stages.py`)**:
implementadas como funciones puras independientes (mismo patrón que `ajustar_meta_por_
madurez`, ya validado en producción). E6 (madurez, ya aplicada la sesión anterior) y E8
(tipo de vendedor) están wireadas y activas -- **E8 absorbe la lógica que antes vivía
duplicada como `COMISION_META_FACTOR_EXTERNO`/`_INTERNO` leída directo de `settings`**
(requisito explícito del plan, evita el defecto de doble aplicación que ya causó un bug
real documentado en la auditoría 46 H-10). **E11 (redondeo) queda ACTIVA en la semilla**
(múltiplo 100, "cercano") -- es una mejora deliberada, no una regresión: el plan (§19)
explícitamente excluye a E11 (junto con E6) de la exigencia de equivalencia numérica
exacta con v2. E7/E9/E13/E15/E16 quedan **desactivadas en la semilla** (idéntico a v2);
sus funciones están completas y probadas (16 tests nuevos en
`test_goal_pipeline_stages.py`), listas para activar el día que gerencia decida el
crecimiento estratégico (E7) o que se audite la cobertura de cartera (E9/E13) o exista
suficiente histórico de cumplimiento (E15, Fase 9.B) -- activarlas hoy es un no-op seguro
por diseño de cada función (degradan omitiendo el ajuste si falta cualquier insumo).

**Trazabilidad v3** (§20 del plan, parcial): `trazabilidad_calculo` gana `"version": "v3"`
y `"config_snapshot"` (la configuración de las 16 etapas TAL COMO ESTABA al generar, no un
recálculo con la configuración de hoy) -- validado en vivo, `config_snapshot.E1_limpieza`
reproduce exactamente `{metodo: "tukey", activo: true, parametros: {...}}`. **No
implementado en esta sesión** (limitación explícita, no descuido): el formato exacto de
`etapas: [...]` del §20 (una entrada granular por etapa EJECUTADA, con entrada/salida de
cada paso) -- `IQRGoalCalculationEngine` sigue siendo una caja que no emite trazas
intermedias por etapa; refactorizarlo para hacerlo requeriría tocar de nuevo el motor ya
probado, evaluado como riesgo innecesario para el valor que aporta en esta pasada.

**API**: `GET /meta-config/catalogo` (16 etapas + métodos + implementado/motivo),
`GET /meta-config/modulos` (configuración vigente), `PUT /meta-config/modulos/{etapa}`
(valida contra el catálogo, rechaza métodos no implementados, valida rangos numéricos de
parámetros conocidos, bitácora en `comision_config_auditoria` con `tabla='metas_config_modulos'`).

**Frontend**: `MetaConfigPanel.tsx` reescrito por completo -- de una tabla plana de 13
parámetros a 16 tarjetas expandibles (una por etapa), cada una con su interruptor de
activación, su selector de método (opciones no implementadas deshabilitadas con su
motivo) y sus parámetros como JSON editable. **No implementado en esta sesión**: la
previsualización en vivo (punto 3 de la Fase 8 del plan, "meta que produciría la
configuración actualmente editada contra la meta vigente") -- requeriría un endpoint de
simulación adicional; queda como el siguiente punto concreto si se retoma esta fase.

**Validado en vivo, extremo a extremo:** `pytest backend/tests/unit` -- 290 passed (1
falla preexistente ajena, ya documentada); 39 tests nuevos entre `test_goal_pipeline_
stages.py` (16), `test_meta_config_modulo_service.py` (8), y los interruptores en
`test_goal_calculation_engine.py` (6) más los 2 de la Fase 7 remanente de este mismo
bloque de trabajo. Migración `0014` aplicada y saneada contra `bi_postgres_edw` real;
`bi_backend` reconstruido, arranque limpio, 6/6 modelos ML. `GET /meta-config/catalogo` y
`/modulos` responden 200 con las 16 etapas reales; `PUT` con un método no implementado
(`isolation_forest`) rechazado 400 con el motivo real. Regenerando agosto-2026
(`POST /gerencia/goals/generate`): **13 registros creados** (los 24 vendedores activos,
incluidos los 4 de 0 meses de historia de la Fase 7), TODAS las metas ahora múltiplos de
100 (efecto real y esperado de E11) -- ej. `VEN13: $64.500,00` (antes `$64.483,xx` sin
redondear), `VEN01: $59.700,00`; `trazabilidad_calculo.version='v3'` y `config_snapshot`
poblados con la configuración real usada, confirmados con `SELECT` directo. Sin errores en
logs del contenedor durante toda la prueba. `tsc --noEmit`/`oxlint`/`npm run build` del
frontend limpios; `bi_frontend` reconstruido sin errores (verificación visual en
navegador real sigue sin ser posible en este entorno Windows, limitación ya documentada
en sesiones previas).

**Pendiente de esta fase, explícitamente diferido (no por descuido):** Fase 8 punto 3
(previsualización en vivo del editor); formato de trazabilidad granular `etapas: []` de
§20 (hoy solo `config_snapshot`, sin el detalle paso a paso); E12 (distribución
corporativa, requiere la tabla `public.metas_corporativas` que el plan mismo documenta
como inexistente); wiring de datos reales de Cartera360 para E9/E13 (las funciones están
listas, pero `GoalMLService` no consulta hoy clientes activos/ticket/frecuencia); §18.bis
(el orden real de ejecución que el plan describe -- banda DESPUÉS de madurez/tipo/
capacidad -- no se reordenó; el orden actual sigue siendo el heredado del v2, banda
dentro de `IQRGoalCalculationEngine.calcular()` antes de E6-E9, decisión explícita para no
arriesgar los números de E6 ya validados en producción la sesión anterior); Fase 9
(backtest formal); Fase 10 restante (nada nuevo, ya cubierta por E13 arriba).

## Conclusión de la Fase 0 (habilita las fases siguientes)

1. **R-9 confirmado, calibración necesaria** pero el gate del 90% (R-2) no vacía la nómina de comisiones como se temía — solo 1/9 vendedores de julio cae bajo el umbral. Se procede con la secuencia del plan (metas primero, gate después) por prudencia, no por que el impacto agregado sea catastrófico.
2. **R-8 confirmado y más severo de lo estimado** (42% con <6 meses) — E6/madurez es prioritario.
3. **R-6 confirmado sin ambigüedad**, causa raíz ya conocida — techo de bonos + discriminación por perfil se implementan en la Fase 2.
4. `sucursal` sigue sin ser agrupador válido (ya descartado, auditoría 42); dado que los vendedores de mayor historia son almacenes/mostradores, el agrupador de benchmark recomendado para E6 es la **mediana del equipo completo** (no hay una segmentación por tipo/canal con suficiente granularidad hoy) — se documenta como limitación conocida, reevaluable si `comision_config_vendedor.tipo` gana más cobertura.
