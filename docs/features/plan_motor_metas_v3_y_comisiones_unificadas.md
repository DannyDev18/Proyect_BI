# Plan — Motor de Metas v3 (modular, tipo SPM) y unificación del esquema de Comisiones Variables

> **Estado:** propuesto (ninguna fase aplicada).
> **Fecha:** 2026-07-31
> **Módulo:** Metas y Comisiones (panel de Gerencia + panel del vendedor).
> **Reemplaza y absorbe:** `docs/features/plan_backtest_y_factores_opcionales_metas.md` (sus Fases A-F se conservan íntegras aquí como Fases 9 y 10; ese archivo queda marcado como superado por este).
> **Continúa:** `docs/features/plan_motor_metas_configurable.md` (motor v2, auditoría 46) y `docs/features/plan_comisiones_sobrecumplimiento_umbral_y_desglose.md` (tramos de cumplimiento, auditoría 45).

---

## 0. Qué pidió el usuario (enunciado literal, desagregado en requisitos)

| # | Requisito | Ámbito |
|---|---|---|
| **R-1** | La comisión ya no debe ser plana; debe salir del motor de comisiones variables. El esquema plano deja de formar parte del sistema. | Comisiones |
| **R-2** | La comisión solo entra en uso cuando se alcanza la meta; si no se alcanza, no comisiona. | Comisiones |
| **R-3** | "Cumplimiento real y comisión por vendedor" debe mostrar la comisión variable ya construida, no la plana. | Comisiones / UI |
| **R-4** | La simulación de comisiones está mal: valores demasiado grandes que no concuerdan con las comisiones reales. | Simulador |
| **R-5** | Los tramos de cumplimiento no están dentro de las reglas de las comisiones. | Comisiones |
| **R-6** | Investigar a profundidad por qué ciertos vendedores tienen comisiones desproporcionadas (caso `VEN01`, julio-2026: $26.110,43 de los cuales $25.444,91 son bonos) mientras otros quedan muy bajos. La empresa está perdiendo dinero. | Comisiones |
| **R-7** | Quitar los factores de crédito de la fórmula y del panel: no aportan nada a las comisiones. | Comisiones |
| **R-8** | Hay almacenes/vendedores sin datos históricos; sus metas deben calcularse de otra forma. | Metas |
| **R-9** | Implementar una fórmula de metas válida y probada en otras empresas: en julio casi ningún vendedor alcanzó la meta, por lo que casi nadie comisionaría. | Metas |
| **R-10** | La pestaña "Fórmula de metas" no se está tomando en cuenta al 100% y no funciona correctamente. | Metas / UI |
| **R-11** | La bitácora de cambios debe vivir en una pestaña propia ("Bitácora de cambios"), registrar cambios de **metas y de comisiones**, y ser de **solo lectura**. | UI |
| **R-12** | Refactorizar el motor de metas hacia un **motor modular de generación de metas** (18 etapas parametrizables, estilo SAP SPM / Oracle Sales Planning / Anaplan / Xactly), no una fórmula única. | Metas |
| **R-13** | (Heredado del plan anterior) Backtest formal de 12 meses cerrados. | Metas |
| **R-14** | (Heredado del plan anterior) Los 4 factores opcionales de la Fase 6 del plan v2. | Metas |

**Observación de coherencia entre R-2 y R-9:** son requisitos en tensión directa. R-2 endurece el pago (sin meta no hay comisión) y R-9 constata que casi nadie alcanza la meta hoy. Aplicar R-2 sobre las metas actuales dejaría a la mayoría del equipo en $0 de comisión — un resultado que la empresa no puede sostener operativamente. **Este plan resuelve la tensión ordenando las fases: R-9/R-12 (metas alcanzables) se calibran ANTES de que R-2 (umbral duro) entre en vigor**, y la calibración se valida con el criterio de la literatura de compensación comercial: *una cuota bien puesta debe ser alcanzada por el 60-70% de la fuerza de ventas* (Zoltners, Sinha & Lorimer, *The Complete Guide to Sales Force Incentive Compensation*); por debajo del 50% de alcance, el problema es la cuota, no el vendedor. Ese porcentaje es el criterio de aceptación cuantitativo de todo el bloque de metas de este plan.

---

## 1. Estado actual verificado en el código (no supuesto)

Lectura directa de `backend/app/services/` y `frontend/src/components/goals/` a fecha de este plan:

1. **El esquema plano sigue siendo el oficial.** `CommissionService.get_commission_tracking` calcula `calcular_comision(...)` (esquema plano) para **todos** los vendedores y lo expone como `comision_devengada`; la comisión variable viaja como campo **opcional** paralelo (`comision_variable`). En el frontend, `CommissionTracker.tsx:75` renderiza `comision_devengada` como columna principal y `comision_variable` como columna secundaria condicionada a `hayDatosVariables`. → R-1/R-3 confirmados: el panel muestra la plana como cifra principal.
2. **`COMISION_MODO` sigue en `plana`** en este entorno, lo que además hace que `get_my_commission` (panel del vendedor) **no** calcule la variable en absoluto (`commission_service.py:194`), a diferencia de `get_commission_tracking`, que sí la calcula siempre desde la auditoría 46. Son dos comportamientos distintos para el mismo concepto en dos pantallas distintas.
3. **Los bonos escapan al gate de cumplimiento.** En `commission_variable_engine.calcular_comision_variable_completa`, el paso `multiplicador_cumplimiento` se aplica como paso `multiplicar` de la tubería, y `bonos` es un paso `sumar` **posterior**. Consecuencia estructural: un vendedor con 0.0× de multiplicador (bajo el 90%, "Sin comisión") **igual cobra el 100% de sus bonos**. La regla RN-CM16 ("no comisiona bajo el 90%") es hoy falsa en la práctica para el componente de bonos. → causa directa de R-2 y componente central de R-6.
4. **El bono de cliente nuevo no tiene techo ni discrimina el tipo de código de venta.** `commission_bonus.calcular_bonos_periodo` calcula `clientes_nuevos × COMISION_BONO_CLIENTE_NUEVO` sin límite superior ni relación con la base comisionable del vendedor. La auditoría 45 (H-5) ya lo había cuantificado: `VEN01` ("ALMACEN EL REY", un mostrador con 31.107 clientes distintos históricos y 55% de compra única) generó $25.600 de este bono en un mes con una base comisionable propia de $514,57. En su momento la decisión explícita fue **no tocarlo**; el caso que ahora reporta el usuario ($25.444,91 de $26.110,43 = **97,4% de la comisión son bonos**) es exactamente ese hallazgo materializado. → R-6 tiene causa raíz ya identificada y documentada, no requiere descubrimiento nuevo, requiere **decisión y corrección**.
5. **Los factores de crédito están cableados en 3 lugares:** `calcular_base_lineas_venta(lineas, matriz, rangos_credito, config)` en el motor, `get_factores_credito_as_rangos` pre-resuelto en `CommissionService`/`CommissionSimulationService`, y la pestaña `'credito'` de `CommissionConfigPanel.tsx:92` + endpoints `GET/PUT /commission-config/credito`. La auditoría 30 (H4) ya documentó que **solo hay datos reales para plazos de 0 y 30 días** en el EDW — es decir, el factor es casi constante y efectivamente no discrimina nada. → R-7 está respaldado por evidencia previa.
6. **La bitácora existe pero está escondida y solo cubre comisiones.** Es la pestaña `'auditoria'` **dentro** de `CommissionConfigPanel` (`AuditoriaTab`, línea 932), alimentada por `public.comision_config_auditoria`. La migración `0013` ya amplió su `CHECK` para admitir `metas_config_parametros`, así que la tabla **ya puede** registrar cambios de metas — falta que la UI la exponga como pestaña propia de primer nivel. → R-11 es en su mayor parte trabajo de UI + verificación de que `MetaConfigService` efectivamente escriba en esa tabla.
7. **La configuración de metas no puede expresar un motor modular.** `public.metas_config_parametros` (migración `0013`) tiene `valor NUMERIC(10,4)` con `CHECK (valor > 0)` y 13 filas escalares. Un motor modular necesita: **selectores de método** (`'mediana'`, `'tukey'`, `'holt_winters'` — texto, no número), **banderas de activación** (`false`/`0` — prohibido por el `CHECK`), y **parámetros anidados por módulo**. → R-12 **exige una migración de esquema nueva**, no solo filas nuevas. Este es el hallazgo más importante para el dimensionamiento del trabajo.
8. **La escalera para vendedores sin histórico existe pero es tosca.** `GoalMLService._ajustar_meta_por_tipo` usa `mediana_equipo × COMISION_VENDEDOR_NUEVO_FACTOR` para el vendedor nuevo — un único escalón, sin transición gradual ni benchmark segmentado (sucursal/zona/canal). El motor v2 etiqueta ese caso como `equipo_prorrateado_v2`. → R-8 se resuelve con la Etapa 6 (madurez) del motor modular, no con un parche aparte.
9. **La banda de alcanzabilidad ya existe** (`_aplicar_banda`, 0.85–1.20 × mediana desestacionalizada reciente) y ya se aplica sobre la meta final. Que julio haya tenido cumplimiento generalizado bajo no se explica sola por ausencia de guardarraíl → **R-9 requiere Fase 0 (auditoría con `SELECT`) antes de tocar el motor**, para saber si el problema es la banda, el nivel base, la presión comercial, o metas generadas con el motor v1 antes de que la banda existiera.

---

## 2. Principio rector del plan

> **No se reescribe un motor de dinero real sobre una hipótesis.** Toda fase que cambie una cifra que se paga (comisión) o que se compromete (meta) va precedida de una auditoría con `SELECT` sobre datos reales, documentada en `docs/auditoria/`. Toda corrección de comportamiento se entrega detrás de configuración con default = comportamiento actual, salvo que el usuario haya pedido explícitamente el cambio de default (R-1, R-2, R-7 sí lo piden).

---

## 3. Fase 0 — Auditoría previa obligatoria (solo `SELECT` + ejecución en modo lectura)

**Entregable:** `docs/auditoria/47_metas_v3_y_comisiones_unificadas.md`.
**Ninguna fase posterior arranca sin esta.**

### A-0.1 — Anatomía real del costo de comisión (R-6)
Para los últimos 6-12 meses con datos, y para **cada** vendedor, descomponer la comisión variable en sus 7 componentes (ya disponibles en `traza_formula`) y reportar:
- Peso porcentual de `bonos` sobre la comisión final, por vendedor.
- Dentro de bonos: separación entre cross-sell, cliente nuevo/reactivado y cobranza sana.
- Ratio `bono_cliente_nuevo / base_comisionable_propia` por vendedor (el indicador que delató a `VEN01`).
- Conteo de clientes "nuevos" por vendedor y % de ellos con **una sola compra de por vida** (distingue cartera real de mostrador con rotación).
- **Criterio de decisión:** cuántos vendedores tienen `bonos > 50%` de su comisión final. Si es un caso aislado (mostradores), la corrección es discriminar por tipo de código de venta; si es sistémico, la corrección es un techo relativo sobre bonos.

### A-0.2 — Cuánto cambia el costo total al aplicar R-1 y R-2 (impacto en dinero)
Recalcular, para los mismos meses, el costo agregado bajo tres escenarios:
1. Esquema plano actual (lo que hoy muestra el panel como oficial).
2. Esquema variable **tal como está** (bonos fuera del gate).
3. Esquema variable **con R-2 aplicado correctamente** (bonos dentro del gate + tramo `[0,90) → 0.0×`).
Reportar el delta absoluto y por vendedor. **Este número es el argumento que gerencia necesita antes de aprobar el cambio de esquema oficial**, y es también la validación cruzada de R-4 (si el simulador da valores muy distintos de esta reconstrucción, el defecto del simulador queda cuantificado, no supuesto).

### A-0.3 — Por qué julio tuvo cumplimiento generalizado bajo (R-9)
- Distribución real de cumplimiento de julio-2026: mediana, percentiles, y **% de vendedores que alcanzó ≥100%** (comparar contra el 60-70% de la literatura).
- Para cada vendedor de julio: ¿su meta fue generada con motor v1 o v2? (`metodo` en `metas_comerciales_operativas`). Si son metas v1, el diagnóstico correcto es "metas legado sin banda", no "el motor v2 está mal calibrado".
- ¿Actuó la banda de alcanzabilidad (`banda_actuo` en `trazabilidad_calculo`)? ¿Como techo o como piso?
- Descomposición del gap: cuánto del exceso viene del nivel base, cuánto del índice estacional, cuánto de la presión comercial (`factor_estacional`), cuánto del factor de tipo de vendedor.

### A-0.4 — Viabilidad de datos del motor modular (R-12)
Antes de diseñar 18 etapas configurables, confirmar con `SELECT` **qué etapas tienen datos reales** en este EDW:
| Etapa | Dato requerido | Verificar |
|---|---|---|
| 6 (madurez) | Meses de historia por vendedor | Distribución real; cuántos < 6, 6-23, ≥24 meses |
| 6 (benchmark) | Agrupador para el benchmark | ¿`sucursal` sirve? **Hallazgo previo: NO** (auditoría 42: un vendedor transacciona en 4-7 de 7 sucursales). Evaluar alternativas reales: canal, tipo de vendedor, tramo de tamaño de cartera |
| 9 (capacidad instalada) | Clientes activos × ticket promedio × frecuencia | Ya calculable vía `Cartera360Repository` — confirmar cobertura |
| 12 (distribución corporativa) | Meta de empresa top-down | **No existe hoy** ningún objetivo corporativo capturado en el sistema — requiere tabla/entrada nueva |
| 13 (factor cartera) | Clientes activos por vendedor y mes | Ya disponible |
| 14 (factor potencial) | Mercado disponible vs. capturado | **No derivable del EDW** — no hay dato de mercado total |
| 15 (factor cumplimiento histórico) | Cumplimiento pasado del vendedor | Solo julio/agosto-2026 aprobadas → **hoy no calculable de forma significativa** |
| 3 (estacionalidad regional) | Región/zona | `dim_geografia` está **vacía** (0 filas, hallazgo abierto de auditoría 05) |

**Regla de esta auditoría:** cada etapa que no tenga dato real se implementa como **módulo declarado pero desactivado, con la razón documentada en su propia descripción**, nunca como un factor que devuelva un número inventado. La arquitectura modular es exactamente lo que permite declararlas sin fingirlas.

### A-0.5 — Almacenes/vendedores sin histórico (R-8)
Enumerar los códigos de vendedor activos con 0 meses de venta en la ventana, y los que tienen histórico pero pertenecen a almacenes de apertura reciente. Cuantificar cuántos son y desde cuándo existen — determina si el caso justifica benchmark segmentado o basta el prorrateo por mediana del equipo ya existente.

### A-0.6 — Divergencia real del simulador (R-4)
Ejecutar `CommissionSimulationService.reconstruir_mes_especifico` sobre julio-2026 y comparar **vendedor por vendedor** contra `CommissionService.get_commission_tracking` del mismo período. Cuantificar la divergencia y aislar su origen entre las causas candidatas ya visibles en el código: (a) el simulador resuelve la configuración vigente **hoy** y el cálculo real la vigente **al cierre del período** (diferencia por diseño, documentada); (b) la proyección promedia pasos `sumar`/`restar` pero mantiene constantes los `multiplicar`; (c) inclusión/exclusión de bonos y devoluciones (`incluir_bonos`/`incluir_devoluciones`). **No se toca el simulador hasta saber cuál de las tres explica la magnitud reportada.**

---

## 4. Fase 1 — Retiro del esquema plano (R-1, R-3)

**Precondición:** A-0.2 aprobada por gerencia (el cambio mueve dinero real).

1. `COMISION_MODO` pasa de tres estados a dos: `sombra` (calcula y muestra, no persiste como oficial) y `variable` (oficial). Se retira `plana` del catálogo y con él la rama de `_MODO_BACKEND_A_LIQUIDACION` que la representa.
2. `commission_engine.calcular_comision` (esquema plano) y sus constantes `UMBRAL_*`/`COMISION_MULT_*` dejan de alimentar `VendorCommissionRow.comision_devengada`. **No se borran de golpe:** siguen siendo el fallback documentado `TRAMOS_CUMPLIMIENTO_FALLBACK` y el motor de referencia de los tests históricos. Se marcan como legado en el docstring y se retiran de toda ruta de servicio.
3. `VendorCommissionRow` se reestructura: `comision_devengada` pasa a ser **la comisión variable** (un solo concepto, un solo número); `pct_cumplimiento`/`nivel`/`tasa_aplicada_pct` pasan a resolverse desde los **tramos configurables** (los de la auditoría 45), no desde los 4 fijos del esquema plano. Se eliminan los campos duplicados `comision_variable`/`nivel_variable`/`pct_cumplimiento_variable`/`tramo_variable` — dejan de tener sentido cuando hay una sola verdad.
4. `get_my_commission` (panel del vendedor) se alinea con `get_commission_tracking`: calcula la comisión variable **siempre**, sin condicionar a `COMISION_MODO`. Hoy son dos comportamientos distintos para el mismo concepto (§1.2).
5. **Frontend:** `CommissionTracker.tsx` deja de tener dos columnas de comisión; muestra una sola, con el desglose de 7 componentes accesible (mismo patrón `renderExpanded` ya construido en `CommissionSimulationPanel`). La leyenda "piloto en sombra" y `modo_comision` se retiran o se reetiquetan según el modo real.
6. **Migración de datos:** ninguna. `comision_liquidaciones` conserva sus snapshots; el `CHECK` de `modo` (`'sombra'|'oficial'`) ya es independiente de `COMISION_MODO`.

**Riesgo declarado:** este cambio hace que el número que gerencia ve como "comisión" cambie de valor de un día para otro. Debe ir acompañado del reporte de A-0.2 y comunicado, no desplegado en silencio.

---

## 5. Fase 2 — El gate de meta se aplica a la comisión completa (R-2, R-5)

**Este es el corazón de R-2 y la corrección de mayor impacto económico del plan.**

1. **Los bonos entran en el gate.** Hoy `bonos` es un paso `sumar` posterior al `multiplicar` del cumplimiento (§1.3). Se introduce en `evaluar_formula` la noción de **compuerta de cumplimiento** aplicada sobre el **resultado final** de la tubería, no como un paso intermedio: `comision_final = tubería_completa × multiplicador_tramo`. Bajo el 90%, `multiplicador = 0.0` y la comisión final es $0 **incluidos los bonos**, que es literalmente lo que pide el usuario.
   - Se conserva el paso `multiplicar` en la tubería configurable por compatibilidad de la fórmula ya sembrada, pero se **prohíbe** que `bonos` quede fuera de su alcance mediante una validación de estructura en `CommissionConfigService` (no se puede guardar una fórmula donde `bonos` tenga orden posterior al multiplicador sin que exista compuerta final).
2. **Techo relativo de bonos (R-6).** Nuevo parámetro configurable `bono_tope_pct_sobre_base` (p. ej. los bonos no pueden exceder el X% de la comisión pre-bonos). Default **según el resultado de A-0.1**, no elegido a priori. Esto acota estructuralmente el caso `VEN01` sin necesidad de una regla ad-hoc por vendedor.
3. **Bono de cliente nuevo discriminado por tipo de código de venta (R-6).** El bono deja de aplicarse indiscriminadamente: los códigos de mostrador/agencia (identificables por `comision_config_vendedor.tipo`/`agencia`, ya existente) quedan excluidos o con un bono propio, porque un comprador ocasional de mostrador **no es** una captación de cartera. La clasificación concreta sale de A-0.1 (% de clientes con compra única por vendedor), no de una suposición.
4. **Los tramos de cumplimiento pasan a ser la única fuente de nivel/tasa (R-5).** Se retiran los 4 tramos fijos legacy de toda ruta de servicio (quedan solo como fallback defensivo documentado). La tabla "Cumplimiento real y comisión por vendedor" muestra el tramo real configurado, su multiplicador y su bono fijo.
5. **Secuencia obligatoria:** esta fase **no se activa en producción antes de la Fase 5** (metas alcanzables). Aplicar el umbral duro sobre las metas actuales dejaría a la mayoría del equipo en $0 (§0, tensión R-2/R-9). El código se entrega e integra; el switch de activación es de gerencia, con el backtest de la Fase 9 como evidencia.

---

## 6. Fase 3 — Retiro de los factores de crédito (R-7)

Respaldado por la auditoría 30 (H4): solo existen datos reales para plazos de 0 y 30 días, así que el factor es casi constante y no discrimina.

1. **Motor:** `calcular_base_lineas_venta` deja de recibir `rangos_credito`; se retira `dias_plazo` de la ponderación (el campo se conserva en `LineaComisionable` como dato informativo del desglose, no como factor).
2. **Fórmula:** el componente no existe como paso propio (siempre fue un modificador interno de `base_lineas_venta`), así que no hay cambio en `COMPONENTES_FORMULA`.
3. **Configuración:** `public.comision_factores_credito` **no se borra** (contiene el histórico de una configuración que sí estuvo vigente y del que dependen snapshots ya congelados); se marca como obsoleta, se retiran los endpoints `GET/PUT /commission-config/credito` y su pestaña del panel. Nueva migración solo para registrar la baja lógica.
4. **Snapshots congelados:** intactos. Un snapshot `oficial` ya calculado con factores de crédito sigue devolviéndose tal cual (inmutabilidad, RN-CM6) — nunca se recalcula retroactivamente.
5. **Pre-resolución:** se retira `rangos_credito` del `config_periodo` de `CommissionService` y del simulador (una consulta menos por período).

---

## 7. Fase 4 — Corrección del simulador (R-4)

**Depende de A-0.6** — el diseño concreto se fija con la causa ya aislada. Correcciones previstas según las tres causas candidatas:

1. **Reconstrucción de un mes cerrado** debe usar la configuración vigente **al cierre de ese período**, igual que el cálculo real. Hoy usa la de hoy "por diseño"; ese diseño es correcto para un "¿qué pasaría si aplicara la config de hoy al pasado?" pero **no** para "reconstruir el mes X", que es como lo lee el usuario. Se separan explícitamente en dos modos con etiqueta visible en la UI, en vez de una sola vista ambigua.
2. **Proyección hacia adelante:** revisar que promediar `sumar`/`restar` y mantener constantes los `multiplicar` siga siendo válido con la compuerta final de la Fase 2 (la compuerta cambia el orden de magnitud del resultado; un multiplicador constante sobre un promedio no es lo mismo que el promedio de los productos cuando el multiplicador puede ser 0.0 en algunos meses).
3. **Bonos y devoluciones:** la exclusión en la proyección (`incluir_bonos=False`) es defendible, pero **debe mostrarse en la UI** — si la tabla dice "comisión proyectada" y omite hasta el 97% del valor real (caso `VEN01`), la cifra es engañosa aunque el código sea correcto.
4. **Test de paridad obligatorio:** un test nuevo que, para un mes cerrado y la misma configuración, exija que simulador y cálculo real coincidan dentro de una tolerancia de centavos. Ese test es la garantía permanente contra R-4.

---

## 8. Fase 5 — Motor de Metas v3: pipeline modular (R-9, R-12)

### 8.1 Decisión de arquitectura

El motor v2 es **una fórmula fija** con parámetros. El v3 es **un pipeline de etapas intercambiables**. Se implementa como una evolución de `goal_calculation_engine.py` hacia un paquete `app/services/metas/`:

```
app/services/metas/
  pipeline.py            # orquestador: ejecuta las etapas activas en orden, acumula trazabilidad
  contexto.py            # ContextoMeta: histórico, vendedor, período objetivo, benchmark, config
  etapas/
    limpieza.py          # E1: ninguna | tukey | zscore | isolation_forest
    nivel_base.py        # E2: mediana | promedio | ponderado | mixto | forecast_ml
    estacionalidad.py    # E3: propio | sucursal | region | empresa (con cascada de prioridad)
    tendencia.py         # E4: regresion_lineal | promedio_movil | suavizado_exp | holt_winters | ninguna
    estabilidad.py       # E5: peso por coeficiente de variación
    madurez.py           # E6: mezcla propio/benchmark según meses de historia
    estrategia.py        # E7: objetivo de crecimiento de la empresa
    tipo_vendedor.py     # E8: factor por tipo/seniority
    capacidad.py         # E9: clientes × ticket × frecuencia (tope duro)
    banda.py             # E10: clamp de alcanzabilidad
    redondeo.py          # E11
    distribucion.py      # E12: reparto top-down de la meta corporativa por peso
    cartera.py           # E13
    potencial.py         # E14  (declarada, sin datos → desactivada)
    cumplimiento.py      # E15  (declarada, activable cuando haya ≥6 meses de metas aprobadas)
    volatilidad.py       # E16: penalización por CV alto
  registro.py            # catálogo cerrado etapa → métodos disponibles (validación)
```

**Reglas de diseño no negociables:**
- **Catálogo cerrado**, igual que `COMPONENTES_FORMULA` en comisiones: la configuración elige entre métodos **registrados**, nunca ejecuta expresiones arbitrarias. Este módulo determina compromisos de dinero; una superficie de evaluación dinámica es inaceptable.
- **Cada etapa es una función pura** `(ContextoMeta, params) -> (ContextoMeta, TrazaEtapa)`. Sin acceso a BD dentro de las etapas — el contexto llega ya resuelto por el repositorio, igual que hoy.
- **Toda etapa desactivada es neutra por construcción** (factor 1.0 / paso a través), y su omisión queda registrada en la traza. Nunca "no aparece": aparece como `activa: false` con su razón.
- **Compatibilidad:** con la configuración semilla (E1=tukey, E2=mixto, E3=propio→empresa, E4=promedio_movil, E5 activo, E10 activo con 0.85-1.20, resto desactivado), el pipeline debe reproducir el motor v2 **dentro de tolerancia numérica**. Ese es un test obligatorio: el v3 no puede cambiar ninguna meta hasta que gerencia cambie configuración.

### 8.2 Fórmula integradora

```
meta_preliminar = nivel_base
                × indice_estacional(mes_objetivo)
                × factor_tendencia_atenuado_por_estabilidad
                × objetivo_estrategico_empresa
                × factor_tipo_vendedor
                × factor_cartera        (si activo)
                × factor_potencial      (si activo)
                × factor_cumplimiento   (si activo)

meta_final = redondear( clamp( min(meta_preliminar, capacidad_instalada), piso, techo ) )
```
donde `piso`/`techo` = banda de alcanzabilidad × referencia (mediana desestacionalizada reciente × índice estacional), y el orden de restricciones es: **capacidad → banda → mínimo/máximo absolutos → redondeo** (nunca redondear antes de acotar).

### 8.3 Fundamentación bibliográfica (requisito de tesis, R-9)

| Etapa | Fundamento |
|---|---|
| E1 limpieza (Tukey) | Tukey, *Exploratory Data Analysis* — regla IQR estándar |
| E2-E4 nivel/estacionalidad/tendencia | Hyndman & Athanasopoulos, *Forecasting: Principles and Practice* — descomposición clásica nivel × estacionalidad × tendencia; ratio-to-moving-average |
| E4 Holt-Winters | Winters (1960), suavizado exponencial con estacionalidad |
| E6 madurez / benchmark | Zoltners, Sinha & Lorimer, *The Complete Guide to Sales Force Incentive Compensation* — cuotas para representantes nuevos vía benchmark del grupo comparable |
| E7/E12 objetivo corporativo y reparto | Reconciliación **bottom-up ↔ top-down**, práctica estándar de sales planning (SAP SPM, Oracle Sales Planning, Anaplan) |
| E9 capacidad instalada | Capacity-based quota setting — la cuota no puede exceder la capacidad de la cartera |
| E10 banda de alcanzabilidad | Zoltners et al. — **objetivo de calibración: 60-70% de la fuerza de ventas debe alcanzar la cuota**; <50% indica cuota mal puesta |
| E16 volatilidad | Penalización de crecimiento en series de alta varianza — práctica de forecasting robusto |

Esta tabla se traslada íntegra a `docs/auditoria/02_reglas_negocio_validadas.md` como reglas RN-MT7..RN-MT2x y al capítulo metodológico de la tesis.

### 8.4 Criterio de aceptación de R-9

Tras calibrar con el backtest (Fase 9), la configuración elegida debe producir, sobre los meses reales disponibles, una distribución de cumplimiento con **mediana en 95-105%** y **entre 60% y 70% de vendedores en ≥100%**. Si la semilla actual no lo logra, se ajustan los parámetros (banda, objetivo estratégico, presión comercial) **con la evidencia del backtest**, no por tanteo.

---

## 9. Fase 6 — Configuración modular (habilitador de la Fase 5)

**Migración nueva `0014_metas_config_modular`** — `metas_config_parametros` tal como está **no puede** expresar el motor modular (§1.7: `NUMERIC` + `CHECK valor > 0` impide métodos por nombre y banderas apagadas).

Diseño propuesto:
- `public.metas_config_modulos` — una fila por etapa: `etapa` (catálogo cerrado), `metodo` (texto, validado contra el registro de la etapa), `activo` (bool), `orden`, `parametros` (JSONB), `actualizado_por`, `actualizado_en`.
- `metas_config_parametros` se **conserva** y se migra: sus 13 filas actuales pasan a poblar el `parametros` JSONB de la etapa correspondiente. No se pierde configuración ni se rompe una meta ya generada (cada meta guarda su propia `trazabilidad_calculo` completa desde la migración `0013`).
- **Validación en servicio, no solo en BD:** `MetaConfigService` valida que el método exista en el registro de esa etapa y que los parámetros estén en rango (nunca una `banda_max=5.0` que anule el guardarraíl — misma regla ya vigente).
- **Sin vigencia histórica**, igual que hoy y por la misma razón deliberada: cada meta persiste su trazabilidad completa, así que un cambio de configuración solo afecta metas futuras.
- **Bitácora:** cada cambio se registra en `comision_config_auditoria` con `tabla='metas_config_modulos'` (el `CHECK` se amplía en esta migración; el precedente ya existe desde `0013`).

---

## 10. Fase 7 — Vendedores y almacenes sin histórico (R-8)

Es la **Etapa 6 (madurez)** del pipeline, no un parche aparte:

| Meses de historia | Nivel base |
|---|---|
| 0 | `benchmark` puro |
| 1-5 | `w × propio + (1-w) × benchmark`, con `w = meses/6` (transición gradual, no escalón) |
| 6-23 | `0.80 × propio + 0.20 × benchmark` |
| ≥24 | `propio` (pipeline completo) |

- **Benchmark = mediana del grupo comparable**, nunca el promedio (un vendedor grande lo distorsiona — misma lección ya aplicada en `generate_proposals`).
- **El agrupador del benchmark es configurable y su elección la decide A-0.4.** Advertencia crítica ya documentada: **`sucursal` NO sirve** como agrupador (auditoría 42: un vendedor típico transacciona en 4-7 de 7 sucursales). Candidatos reales: tipo de vendedor, tramo de tamaño de cartera, canal. Si ninguno resulta discriminante en A-0.4, el benchmark es la mediana del equipo completo — que es lo que ya hace hoy, ahora con transición gradual y etiquetado explícito en la traza.
- **Almacén sin histórico:** un almacén nuevo se comporta como un vendedor nuevo; la meta cae al benchmark del grupo. Si además el vendedor es nuevo, el método se etiqueta `benchmark_puro_v3` y la UI lo declara explícitamente ("meta de referencia del equipo, no del histórico propio"), en vez de presentar un número sin advertencia.

---

## 11. Fase 8 — Frontend (R-3, R-10, R-11)

1. **`CommissionTracker` ("Cumplimiento real y comisión por vendedor")** — una sola columna de comisión (la variable), con % de cumplimiento y tramo real configurado, y desglose de 7 componentes expandible (R-3).
2. **Pestaña "Bitácora de cambios" de primer nivel** (R-11) — se saca `AuditoriaTab` de dentro de `CommissionConfigPanel` y se promueve a pestaña propia de `DashboardMetas.tsx`, junto a Propuestas / Fórmula de metas / Configuración / Simulación. Muestra los cambios de **ambos** dominios (comisiones y metas) desde `comision_config_auditoria`, con filtro por tabla/usuario/fecha. **Estrictamente de solo lectura**: sin acciones, sin edición, sin borrado — la tabla ya es append-only en la BD, la UI debe reflejarlo.
3. **Pestaña "Fórmula de metas"** (R-10) — se reescribe sobre el modelo modular: una tarjeta por etapa, con su selector de método, su switch de activación, sus parámetros, y **la razón visible cuando una etapa está desactivada por falta de datos** (E14 potencial, E15 cumplimiento histórico, E3-regional por `dim_geografia` vacía). Requisito explícito del usuario ("no se está tomando en cuenta al 100%"): incluir una **previsualización** que muestre, para un vendedor y período elegidos, la meta que produciría la configuración **actualmente editada** contra la meta vigente — para que el gerente vea el efecto antes de guardar.
4. **Trazabilidad "cómo se calculó"** — se extiende al formato de pipeline: una fila por etapa ejecutada, con valor de entrada, método aplicado, valor de salida, y las etapas omitidas listadas con su razón. Sigue devolviendo la traza **persistida** (`es_trazabilidad_persistida=true`), nunca un recálculo con la configuración de hoy (RN-MT5, ya vigente).
5. **Retiro de la pestaña "Factores de crédito"** (R-7).

---

## 12. Fase 9 — Backtest formal (R-13, absorbe el plan anterior)

### 9.A — Backtest motor-a-motor (ejecutable de inmediato)
Sin bloqueo: re-ejecuta v1 (vía `git show`), v2 (actual) y v3 (nuevo) sobre el mismo histórico real de `fact_ventas_detalle`, walk-forward, cada mes como período objetivo con solo el histórico previo como insumo.

**Entregable:** `backend/scripts/backtest_motor_metas.py` (herramienta de auditoría, no código de producción) que reporta por motor:
- Distribución de cumplimiento vs. Venta Neta real: mediana, percentiles 10/25/75/90, **% de vendedores ≥100%** (el criterio de los 60-70%), % bajo 90%, % sobre 125%.
- **Costo total agregado de comisión** que cada nivel de meta habría generado, reutilizando `calcular_comision_variable_completa` con la meta recalculada y el gate de la Fase 2 activo.
- Casos de mayor divergencia entre motores, vendedor por vendedor.

**Este backtest es el instrumento de calibración de la Fase 5** — la configuración semilla del v3 se elige aquí con evidencia, no antes.

> **Ejecutado 2026-08-04** (`docs/auditoria/48_backtest_motor_metas.md`): v2 mediana 99,5%/48,8% ≥100%/costo $109.022,44 vs. v3 mediana 93,2%/37,2% ≥100%/costo $99.230,67 sobre 129 observaciones vendedor-mes (12 meses × 10-11 vendedores elegibles). Resultado agregado dominado por un solo caso (`VEN23`, histórico casi vacío) donde v3 corrige una meta v2 sin sentido de negocio ($26,80-$294,40) a un rango realista ($8.600-$22.600) -- confirma que E6 corrige un defecto real, pero el tamaño de muestra (10-11 vendedores/mes) es insuficiente para recalibrar la semilla con este resultado como única evidencia. No se tocó ningún parámetro de la Fase 6 a partir de esta corrida.

### 9.B — Backtest contra metas realmente aprobadas (espera activa)
Cuando existan ≥6-12 meses con `estado='APROBADA'` (acumulación natural del uso), se corre el mismo script con `--contra-metas-aprobadas`: meta v3 recalculada vs. meta realmente aprobada vs. venta real. **No se generan metas aprobadas artificialmente para acelerarlo** — sería fabricar la evidencia que este motor existe para no fabricar. Disparador: revisar `SELECT COUNT(DISTINCT (anio,mes)) FROM public.metas_comerciales_operativas WHERE estado='APROBADA'` cada vez que se retome el módulo.

---

## 13. Fase 10 — Factores opcionales heredados (R-14)

Absorbidos del plan anterior, ahora **como etapas del pipeline** en vez de parches sueltos:

| Factor | Etapa | Decisión |
|---|---|---|
| **Días hábiles del mes** | — | **Cerrado sin implementar.** `dim_fecha.es_feriado` nunca se puebla (auditoría 05); sin feriados reales queda "días que no son fin de semana", que **duplica** lo que el índice estacional propio ya captura (un diciembre con navidad siempre tuvo navidad en los años del índice). Se documenta la evaluación. Reabrir solo si una auditoría futura demuestra con `SELECT` que el índice estacional es insuficiente en meses con feriados móviles. |
| **Cartera activa** | E13 | Viable hoy (`Cartera360Repository`). Default desactivado. Auditoría previa: cuantificar vendedores con cambio de cartera >20% mes a mes y si coincide con saltos de venta ya explicados por otro mecanismo (no doble-contar). Advertencia a documentar: un cambio de cartera puede ser una reasignación administrativa, no desempeño. |
| **Meses no representativos** (vacaciones/ausencia) | E1 (limpieza) | Viable. Nuevo método de limpieza `umbral_absoluto`: excluir meses con venta `< umbral × mediana` (p. ej. 0.15). Es el espejo del lado bajo de lo que la banda ya corrige del lado alto. **Riesgo a documentar:** puede ocultar una caída real y sostenida si se calibra mal — activar solo tras revisar en la previsualización los casos concretos que dispara. |
| **Tope de variación intermensual** | E10 (restricciones) | Viable, el guardarraíl más directo. `tope_variacion_intermensual_pct` (p. ej. ±15% respecto de la meta **aprobada** del mes anterior del mismo vendedor), default desactivado, aplicado como **segundo clamp** después de la banda. Efecto real limitado hasta que existan dos metas aprobadas consecutivas (mismo crecimiento de datos que 9.B). |

---

## 14. Orden de ejecución y dependencias

| Fase | Contenido | Depende de | Bloqueo |
|---|---|---|---|
| **0** | Auditoría A-0.1..A-0.6 → `47_...md` | — | Ninguno. **Bloquea todo lo demás.** |
| **6** | Configuración modular (migración `0014`) | A-0.4 | — |
| **5** | Motor de metas v3 (pipeline) | Fase 6 | — |
| **7** | Madurez/benchmark (E6) | Fase 5, A-0.4/A-0.5 | Agrupador del benchmark por confirmar |
| **9.A** | Backtest motor-a-motor + **calibración de la semilla v3** | Fase 5 | — |
| **3** | Retiro de factores de crédito | A-0.1 | — |
| **1** | Retiro del esquema plano | A-0.2 aprobada por gerencia | Decisión de negocio |
| **2** | Gate de meta sobre la comisión completa + techo de bonos | Fases 1 y **9.A** (metas ya calibradas) | **Activación en producción: decisión de gerencia** |
| **4** | Corrección del simulador | A-0.6, Fase 2 | — |
| **8** | Frontend (tracker, bitácora, fórmula modular) | Fases 1-6 | — |
| **10** | Factores opcionales (E13, E1-umbral, E10-tope) | Fase 5, 9.A | Cartera: auditoría propia |
| **9.B** | Backtest contra metas aprobadas | 9.A | **Espera pasiva:** ≥6 meses de metas `APROBADA` |

**Secuencia crítica a respetar:** `0 → 6 → 5 → 9.A → 2`. Activar el gate duro (R-2) antes de calibrar las metas (R-9) dejaría a casi todo el equipo sin comisión, que es precisamente el problema que el usuario reporta.

---

## 15. Validación exigida

- **Tests unitarios del pipeline v3:** una etapa, un archivo de tests. Obligatorio un test de **equivalencia v2↔v3** con la configuración semilla (el v3 no cambia ninguna meta hasta que gerencia cambie configuración) y un test por etapa que verifique que, desactivada, es exactamente neutra.
- **Test de paridad simulador ↔ cálculo real** sobre un mes cerrado con la misma configuración (garantía permanente contra R-4).
- **Test del gate:** un vendedor bajo el 90% con bonos altos debe dar **comisión final $0**, bonos incluidos (garantía permanente contra el defecto de §1.3).
- **Test del techo de bonos:** reproducir el caso `VEN01` con datos sintéticos y verificar que el techo lo acota.
- `pytest backend/tests/unit` completo sin regresiones antes de cerrar cualquier fase (la falla preexistente dependiente de la fecha del sistema ya documentada no cuenta).
- `pytest backend/tests/integration -k "meta or goal or commission"`.
- `tsc --noEmit` / `oxlint` / `npm run build` limpios.
- Migraciones `0014` aplicadas contra `bi_postgres_edw` real y validadas con `bi_backend` reconstruido, siguiendo la lección de la migración `0012`: **nombre de revisión ≤32 caracteres** (`alembic_version.version_num VARCHAR(32)`) y longitudes de `VARCHAR` verificadas contra los textos reales que se van a insertar.
- **Ninguna fase escribe sobre `metas_comerciales_operativas` ni activa un cambio de esquema de comisión en producción sin que gerencia haya revisado el impacto** en la previsualización (metas) y en el reporte de A-0.2 (comisiones).

---

## 16. Riesgos

| Riesgo | Mitigación |
|---|---|
| El gate duro deja al equipo sin comisión | Secuencia obligatoria `9.A → 2`; criterio 60-70% de alcance antes de activar |
| El techo de bonos recorta ingresos legítimos de un vendedor real (no un mostrador) | El techo es relativo a la base propia, y el default sale de A-0.1 sobre datos reales, no de una elección a priori |
| 18 etapas configurables = superficie de configuración inmanejable | Catálogo cerrado + validación de rangos en servicio + semilla que reproduce el v2 + etapas sin datos declaradas desactivadas con razón visible |
| Un cambio de configuración altera metas ya comprometidas | Sin vigencia histórica **por diseño**: cada meta guarda su `trazabilidad_calculo` completa; un cambio solo afecta metas futuras |
| Snapshots `oficial` de comisión afectados por el retiro de factores de crédito | Inmutabilidad ya vigente (RN-CM6): un snapshot congelado nunca se recalcula |
| Retirar `COMISION_MODO=plana` elimina la vía de rollback | El rollback pasa a ser `variable → sombra` (calcula y muestra, no persiste como oficial); se documenta explícitamente |

---

## 17. Decisiones que requieren al usuario

1. **Techo de bonos (R-6):** ¿acotar bonos como % de la comisión pre-bonos, excluir del bono de cliente nuevo a los códigos de mostrador/agencia, o ambas? (Recomendación: **ambas** — son defectos distintos: uno de magnitud, otro de aplicabilidad.) El valor concreto se fija con A-0.1.
2. **Retiro del esquema plano (R-1):** ¿se retira `COMISION_MODO=plana` del catálogo, o se conserva como vía de rollback de emergencia? (Recomendación: retirar; el rollback pasa a ser `sombra`.)
3. **Agrupador del benchmark (R-8):** a confirmar con A-0.4. `sucursal` está descartado por evidencia previa.
4. **Objetivo estratégico de crecimiento (E7) y meta corporativa (E12):** hoy **no existen** en el sistema. ¿Gerencia define un % de crecimiento anual que el motor deba repartir, o E7/E12 quedan declaradas y desactivadas en esta iteración?
5. **Días hábiles (Fase 10):** ¿confirma cerrarlo sin implementar por el bloqueo real de datos (`es_feriado` sin poblar)?
6. **Prioridad entre las etapas opcionales:** este plan recomienda tope de variación intermensual → cartera activa → meses no representativos.

---

## 18. Especificación detallada de las etapas del pipeline v3

Cada etapa se especifica con: **métodos disponibles** (catálogo cerrado), **parámetros**, **entrada/salida** y **degradación** (qué hace cuando le faltan datos). Ninguna etapa puede fallar con excepción por falta de datos: degrada, etiqueta y sigue — el pipeline siempre produce una meta o declara explícitamente que no puede producirla.

### E1 — Limpieza de datos (outliers)
**Entrada:** serie mensual cruda del vendedor. **Salida:** serie con índices excluidos + conteo.

| Método | Parámetros | Comportamiento |
|---|---|---|
| `ninguna` | — | Paso a través. Útil para diagnosticar y para el backtest comparativo. |
| `tukey` *(semilla)* | `k` (1.5 / 2.0 / 3.0), `ventana_referencia` | `[Q1 − k·IQR, Q3 + k·IQR]` sobre los últimos `ventana_referencia` meses. Es exactamente lo que hace hoy `_indices_sin_outliers`. |
| `zscore` | `z_max` (3.0) | Excluye `|z| > z_max`. Más agresivo que Tukey en series casi normales, más laxo en colas gruesas. |
| `isolation_forest` | `contamination`, `n_estimators`, `random_state` | **Solo si hay ≥24 meses**; con menos, degrada a `tukey` y lo registra en la traza. Reutiliza el patrón de `estimar_contamination_iqr` ya usado en `ml/`. |
| `umbral_absoluto` | `fraccion_mediana` (0.15) | Meses no representativos (Fase 10): excluye `venta < fraccion × mediana`. **Combinable** con `tukey` (se aplican en cascada, `tukey` primero). |

**Degradación:** con menos de `meses_minimos_para_iqr` (4) puntos no hay resolución de cuartiles → no se excluye nada, se etiqueta `limpieza_omitida_por_historia_corta`.
**Regla invariante:** la limpieza nunca puede dejar la serie vacía; si el filtro elimina todo, se revierte a la serie completa (comportamiento ya vigente en el v2, se conserva).

### E2 — Nivel base
**Entrada:** serie limpia **desestacionalizada** (E3 se calcula antes conceptualmente; ver §18.bis sobre el orden real). **Salida:** un escalar `nivel_base`.

| Método | Parámetros | Fórmula |
|---|---|---|
| `mediana` | — | `mediana(serie)`. El más robusto, el más conservador. |
| `promedio` | — | `media(serie)`. Sensible a colas; incluido para el backtest comparativo. |
| `ponderado` | `meses_recientes` (6), `peso_recientes` (0.40) | `peso · media(últimos N) + (1−peso) · media(anteriores)`. |
| `mixto` *(semilla)* | `alpha` (0.70) | `α · mediana + (1−α) · promedio`. **Recomendado**: robustez de la mediana con algo de sensibilidad del promedio. |
| `forecast_ml` | `modelo` | Reservado. **Desactivado**: `goals_rf` fue decomisionado (auditoría 20) y no se reintroduce un modelo ML aquí sin una competencia formal documentada. Se declara para no cerrar la puerta arquitectónicamente. |

**Ponderación ML preexistente:** el peso `PESO_MES_ATIPICO_ML = 0.5` para meses marcados por el detector de anomalías se conserva y se aplica **dentro** de E2, como hoy (regla de negocio ya validada: "reducir su influencia, no eliminar").

### E3 — Estacionalidad
**Salida:** `indice_estacional(mes_objetivo)` + `fuente`.

**Cascada de prioridad configurable** (`prioridad: ["propio", "sucursal", "region", "empresa"]`), evaluada mes a mes, no todo-o-nada:

| Fuente | Condición para usarse | Estado |
|---|---|---|
| `propio` *(semilla, prioridad 1)* | ≥ `min_anios_estacional` (2) observaciones del mismo mes calendario en la ventana | **Activo** — ratio-to-moving-average normalizado, ya implementado |
| `sucursal` | — | **Desactivado por evidencia**: `sucursal` no es una unidad de agrupación válida para vendedores (auditoría 42) |
| `region` | `dim_geografia` poblada | **Desactivado por datos**: 0 filas (auditoría 05) |
| `empresa` *(semilla, prioridad 2)* | Índice agregado de toda la empresa para ese mes | **Activo** — ya implementado, rango real medido 0,913–1,081 (auditoría 46) |
| `neutro` | Último recurso | Índice = 1.0, etiquetado explícitamente |

**Normalización obligatoria:** el conjunto de índices calculados se escala para que su promedio sea 1.0 — evita que una señal parcial (pocos meses con índice propio) sesgue el nivel general. Ya implementado, se conserva.

### E4 — Tendencia
**Entrada:** serie desestacionalizada (últimos `ventana` meses). **Salida:** `factor_tendencia` acotado.

| Método | Parámetros | Fórmula |
|---|---|---|
| `ninguna` | — | `1.0` |
| `promedio_movil` *(semilla)* | `ventana` (4) | Mediana de las variaciones intermensuales relativas — robusta a un mes raro dentro del propio segmento. Es lo que hace hoy `_factor_tendencia_bruto`. |
| `regresion_lineal` | `ventana` | Pendiente OLS proyectada un período; `factor = ŷ(t+1) / nivel_base`. |
| `suavizado_exponencial` | `alpha` | Holt simple (nivel + tendencia). |
| `holt_winters` | `alpha`, `beta`, `gamma`, `periodos` (12) | **Requiere ≥24 meses**; con menos degrada a `promedio_movil` y lo registra. Nota: absorbe estacionalidad, por lo que si se activa, **E3 debe desactivarse** para no aplicar el ajuste estacional dos veces — el registro de etapas valida esta incompatibilidad y la rechaza al guardar. |

**Clamp obligatorio:** `factor = clamp(factor, factor_tendencia_min, factor_tendencia_max)` (0.85–1.20 en la semilla), **siempre**, sea cual sea el método.

### E5 — Peso de estabilidad
`CV = σ/μ` sobre la serie desestacionalizada limpia.
`peso = max(peso_min, 1 − CV/CV_alto)` cuando `CV > CV_alto`, si no `1.0`.
`factor_tendencia_final = 1 + (factor_tendencia − 1) · peso`.
Un vendedor errático no recibe el mismo empuje de crecimiento que uno estable con la misma tendencia nominal. Ya implementado (`_peso_estabilidad`), se conserva como etapa propia y desactivable.

### E6 — Madurez del vendedor
Ver §10 (Fase 7) para la tabla de mezcla. Parámetros: `umbral_nuevo_meses` (6), `umbral_maduro_meses` (24), `peso_benchmark_intermedio` (0.20), `agrupador_benchmark` (`equipo` | `tipo_vendedor` | `tramo_cartera` | `canal`), `estadistico_benchmark` (`mediana` *(semilla)* | `promedio`).
**Salida:** `nivel_base` mezclado + etiqueta de método (`propio_v3` / `mezcla_madurez_v3` / `benchmark_puro_v3`).

### E7 — Objetivo estratégico de la empresa
`factor = 1 + crecimiento_pct/100`. Parámetro único: `crecimiento_pct`.
**Desactivado en la semilla** hasta que gerencia defina el objetivo (§17.4). Es la vía correcta y explícita para lo que hoy se hace de forma implícita con el slider de "Presión Comercial" — **ambos no deben aplicarse simultáneamente sin advertencia**: el registro marca la combinación como "doble crecimiento" y la UI la señala.

### E8 — Factor por tipo de vendedor
Tabla configurable `tipo → factor` (junior 0.95, senior 1.05, KAM 1.10, …), respaldada por `public.comision_config_vendedor.tipo` que ya existe.
**Compatibilidad obligatoria:** hoy `GoalMLService._ajustar_meta_por_tipo` aplica `COMISION_META_FACTOR_EXTERNO` / `COMISION_META_FACTOR_INTERNO`. Esta etapa **absorbe** esa lógica; no puede quedar aplicándose en dos sitios (defecto que ya causó el bug del slider de presión, H-10 de la auditoría 46). Migrar y **borrar** el cálculo duplicado del servicio es parte de la Fase 5, no opcional.

### E9 — Capacidad instalada
`capacidad = clientes_activos × ticket_promedio × frecuencia_compra_mensual`, con los tres insumos ya disponibles vía `Cartera360Repository`.
Se aplica como **tope duro**: `meta = min(meta, capacidad × holgura)`, con `holgura` (p. ej. 1.10) configurable para no clavar la meta exactamente en la capacidad observada.
**Degradación:** sin cartera medible (vendedor nuevo, mostrador) la etapa se omite y lo registra — nunca devuelve capacidad 0, que anularía la meta.

### E10 — Restricciones finales (orden estricto)
1. `min(meta, capacidad)` (E9, si activa)
2. **Banda de alcanzabilidad**: `clamp(meta, banda_min·ref, banda_max·ref)` con `ref = mediana desestacionalizada de los últimos N meses × índice estacional del mes objetivo`
3. **Tope de variación intermensual** (Fase 10, desactivado): `clamp(meta, meta_aprobada_anterior · (1±tope))`
4. **Piso/techo absolutos** (opcionales, en moneda)
5. **Redondeo** (E11) — siempre el último

**Invariante:** redondear antes de acotar produce metas fuera de banda. El pipeline valida el orden en tiempo de arranque, no confía en la configuración.

### E11 — Redondeo
`multiplo` ∈ {1, 100, 500, 1000, 10000}. Semilla: `100`. Modo: `arriba` | `abajo` | `cercano` *(semilla)*.

### E12 — Distribución corporativa (top-down)
`peso_vendedor = ventas_vendedor / ventas_totales`; `meta = base + (meta_empresa × peso)`.
**Desactivado**: requiere una meta corporativa que hoy no existe en el sistema (§17.4). Si gerencia la define, la tabla nueva `public.metas_corporativas (anio, mes, monto_objetivo, creado_por)` es el insumo, y esta etapa **reconcilia** bottom-up (suma de metas individuales) con top-down (objetivo de empresa) — el punto donde este motor se vuelve comparable con Anaplan/Oracle Sales Planning.

### E13 — Factor cartera
`factor = clientes_activos_mes / promedio_clientes_activos_ventana`, acotado a `[min, max]` (p. ej. 0.85–1.15) para que una reasignación administrativa no dispare la meta. Desactivado por defecto (§13).

### E14 — Factor potencial
`mercado_capturado / mercado_disponible`. **Declarado y desactivado permanentemente en este proyecto**: el EDW no tiene ninguna fuente de mercado total y ninguna es derivable de un ERP transaccional propio. Se documenta como el ejemplo canónico de "etapa que la arquitectura soporta pero los datos no habilitan".

### E15 — Factor de cumplimiento histórico
`factor = 1 + (cumplimiento_promedio − 1) × peso`, acotado.
**Desactivado por datos hoy** (solo julio/agosto-2026 aprobadas). Se activa junto con la Fase 9.B, cuando haya ≥6 meses de cumplimiento real medible. Es la etapa que premia al vendedor que sistemáticamente supera su cuota con una cuota mayor — y por eso mismo requiere el guardarraíl de la banda para no convertirse en un castigo al alto desempeño.

### E16 — Penalización por volatilidad
Si `CV > umbral` (p. ej. 0.40), reduce el componente de crecimiento (E4/E7) por un factor configurable. Se solapa parcialmente con E5; el registro advierte si ambas están activas para evitar doble penalización.

### §18.bis — Orden real de ejecución (importante)
El orden conceptual del requerimiento (limpieza → nivel → estacionalidad → tendencia) **no** es el orden de ejecución correcto: la estacionalidad debe calcularse **antes** de limpiar y nivelar, porque tanto la detección de outliers como el nivel base y la tendencia deben operar sobre la serie **desestacionalizada** (de lo contrario un diciembre alto se marca como outlier siendo estacionalidad normal — defecto H-4 ya corregido en el v2). Orden real:

```
E3 (calcular índices) → desestacionalizar → E1 (limpieza) → E2 (nivel base)
→ E4 (tendencia) → E5 (estabilidad) → E6 (madurez) → reestacionalizar (× índice del mes objetivo)
→ E7 (estrategia) → E8 (tipo) → E13/E14/E15 (factores) → E16 (volatilidad)
→ E9 (capacidad) → E10 (banda + topes) → E11 (redondeo)
```
Este orden se codifica en `pipeline.py` como **estructura fija**; lo configurable es el método y la activación de cada etapa, **no** su posición. Permitir reordenar libremente las etapas sería una superficie de error sin ningún beneficio de negocio.

---

## 19. Configuración semilla recomendada (Fase 6)

| Etapa | Método | Activa | Parámetros |
|---|---|---|---|
| E1 limpieza | `tukey` | ✅ | `k=1.5`, `ventana_referencia=12` |
| E2 nivel base | `mixto` | ✅ | `alpha=0.70` |
| E3 estacionalidad | cascada | ✅ | `prioridad=[propio, empresa]`, `min_anios=2` |
| E4 tendencia | `promedio_movil` | ✅ | `ventana=4`, `min=0.85`, `max=1.20` |
| E5 estabilidad | — | ✅ | `cv_alto=0.5`, `peso_min=0.3` |
| E6 madurez | mezcla | ✅ | `6/24 meses`, `benchmark=mediana`, agrupador **por definir en A-0.4** |
| E7 estrategia | — | ❌ | `crecimiento_pct` pendiente de gerencia |
| E8 tipo vendedor | tabla | ✅ | migrado desde `COMISION_META_FACTOR_*` |
| E9 capacidad | — | ❌ | activar tras medir cobertura en A-0.4 |
| E10 banda | — | ✅ | `0.85–1.20`, `meses_referencia=6` |
| E11 redondeo | `cercano` | ✅ | `multiplo=100` |
| E12 distribución | — | ❌ | sin meta corporativa |
| E13 cartera | — | ❌ | Fase 10 |
| E14 potencial | — | ❌ | **sin datos, permanente** |
| E15 cumplimiento | — | ❌ | activable con Fase 9.B |
| E16 volatilidad | — | ❌ | solapa con E5 |

**Esta semilla debe reproducir el motor v2 dentro de tolerancia numérica** (salvo E11-redondeo y E6-madurez, que son mejoras deliberadas). Cualquier desviación mayor es un bug del pipeline, no una mejora — se trata como tal en la validación.

---

## 20. Contrato de trazabilidad del pipeline

`metas_comerciales_operativas.trazabilidad_calculo` (JSONB, ya existe desde la migración `0013`) pasa del formato plano del v2 a un formato de pipeline. **Compatibilidad obligatoria:** el lector debe reconocer ambos formatos por la clave `version` y renderizar las metas legado sin romperse.

```jsonc
{
  "version": "v3",
  "vendedor_origen": "VEN13",
  "anio_objetivo": 2026, "mes_objetivo": 8,
  "generado_en": "2026-08-01T09:00:00Z",
  "config_snapshot": { /* etapa → {metodo, activo, parametros} tal como estaba al generar */ },
  "historico_usado": [ { "anio": 2023, "mes": 8, "ventas": 0.0, "unidades": 0.0 } ],
  "etapas": [
    {
      "etapa": "E3_estacionalidad", "metodo": "cascada", "activa": true,
      "entrada": null, "salida": 1.0814,
      "detalle": { "fuente": "propio", "anios_observados": 3 },
      "nota": null
    },
    {
      "etapa": "E1_limpieza", "metodo": "tukey", "activa": true,
      "entrada": 36, "salida": 34,
      "detalle": { "excluidos": [ {"anio": 2025, "mes": 12, "ventas": 0.0} ], "q1": 0.0, "q3": 0.0 }
    },
    {
      "etapa": "E9_capacidad", "metodo": null, "activa": false,
      "entrada": null, "salida": null,
      "nota": "Desactivada: sin cartera activa medible para este vendedor."
    }
  ],
  "meta_pre_restricciones": 0.0,
  "restricciones_aplicadas": [
    { "tipo": "banda_alcanzabilidad", "actuo": true, "lado": "techo", "referencia": 0.0, "limite": 0.0 }
  ],
  "meta_final": 0.0,
  "metodo": "estacional_propio_v3"
}
```

**Requisitos del contrato:**
- `config_snapshot` es lo que hace la traza autosuficiente: la meta se puede explicar años después aunque la configuración haya cambiado diez veces. Es la corrección definitiva de H-5 (auditoría 46).
- Las etapas **desactivadas aparecen igual**, con `activa: false` y su `nota`. El requisito del usuario ("que se muestren los valores REALES con los que se calculó") incluye saber qué **no** se aplicó y por qué.
- `GET /gerencia/goals/meta-sugerida` sigue devolviendo la traza **persistida** cuando la meta ya existe (`es_trazabilidad_persistida=true`) y solo cae a cálculo en vivo, etiquetado, para metas legado o períodos sin generar. Regla ya vigente (RN-MT5), se conserva sin cambios.

---

## 21. Cambios de contrato API

| Endpoint | Cambio | Requisito |
|---|---|---|
| `GET /gerencia/goals/commissions` | `comision_devengada` pasa a ser la comisión **variable**; se retiran `comision_variable`/`nivel_variable`/`pct_cumplimiento_variable`/`tramo_variable` (duplicados); se agrega `componentes` (desglose de 7 pasos) | R-1, R-3 |
| `GET /analytics/ventas/goals/mi-comision` | Calcula siempre la variable; `modo_comision` pierde el valor `plana` | R-1 |
| `GET/PUT /gerencia/goals/commission-config/credito` | **Se retiran** | R-7 |
| `GET/PUT /gerencia/goals/meta-config/parametros` | **Se reemplazan** por `GET/PUT /gerencia/goals/meta-config/modulos` (etapa, método, activo, parámetros) | R-12 |
| `POST /gerencia/goals/meta-config/previsualizar` | **Nuevo**: recibe una configuración candidata + vendedor + período, devuelve la meta que produciría y su traza, **sin persistir nada** | R-10 |
| `GET /gerencia/goals/meta-config/catalogo` | **Nuevo**: catálogo cerrado de etapas y métodos disponibles, con su estado (`disponible` / `sin_datos` + razón) — el frontend no debe llevar esa lista cableada | R-10, R-12 |
| `GET /gerencia/goals/bitacora` | **Nuevo** (o ampliación del existente de auditoría de comisiones): bitácora unificada metas + comisiones, paginada, **solo lectura** | R-11 |
| `POST /gerencia/goals/commission-simulation` | Gana `modo` (`reconstruccion_fiel` \| `config_actual`) y expone explícitamente qué se incluyó/excluyó | R-4 |

**Regla de compatibilidad:** todo cambio de contrato se acompaña de la actualización del tipo TypeScript espejo en `frontend/src/types/` en el mismo commit. La auditoría A-0.4 del plan de correcciones integrales ya encontró un caso real de tipo desalineado que dejó 3 de 4 KPI cards leyendo `undefined` durante meses — no se repite.

---

## 22. Consultas de la Fase 0 (esqueleto)

> Todas son `SELECT`. Los nombres de columna se verifican contra el DDL real antes de ejecutar; los esqueletos indican intención, no sintaxis final. El motor de comisiones se ejerce en **modo lectura** dentro de `bi_backend` (mismo arnés ya usado en las auditorías 44/45/46), nunca escribiendo snapshots.

**A-0.1 — clientes "nuevos" que son compradores ocasionales de mostrador**
```sql
-- % de clientes de cada vendedor con UNA sola compra de por vida:
-- separa cartera real de mostrador con alta rotación (el patrón de VEN01).
SELECT v.codven,
       COUNT(*) FILTER (WHERE c.compras_vida = 1)::numeric / NULLIF(COUNT(*), 0) AS pct_compra_unica,
       COUNT(*) AS clientes_distintos
FROM (
  SELECT vendedor_sk, cliente_sk, COUNT(DISTINCT num_documento) AS compras_vida
  FROM edw.fact_ventas_detalle GROUP BY 1, 2
) c
JOIN edw.dim_vendedor v ON v.vendedor_sk = c.vendedor_sk
GROUP BY v.codven ORDER BY pct_compra_unica DESC;
```

**A-0.2 — costo agregado por escenario**: ejercicio del motor en modo lectura, no SQL puro. Se ejecuta `calcular_comision_variable_completa` por vendedor/mes con y sin la compuerta de la Fase 2, y se totaliza. **Ninguna corrida escribe en `comision_liquidaciones`** (verificar `COUNT(*)` antes y después, como en la auditoría 45).

**A-0.3 — distribución de cumplimiento de julio y origen de cada meta**
```sql
SELECT m.id_vendedor_origen, m.monto_meta, m.metodo, m.estado,
       (m.trazabilidad_calculo->>'banda_actuo') AS banda_actuo
FROM public.metas_comerciales_operativas m
WHERE m.anio = 2026 AND m.mes = 7 AND m.estado = 'APROBADA';
```
cruzado con la venta neta real del mismo período por vendedor.

**A-0.4 — meses de historia por vendedor (madurez)**
```sql
SELECT v.codven, COUNT(DISTINCT (f.anio, f.mes)) AS meses_con_venta,
       MIN(f.fecha_completa) AS primera_venta
FROM edw.fact_ventas_detalle fv
JOIN edw.dim_fecha f ON f.fecha_sk = fv.fecha_sk
JOIN edw.dim_vendedor v ON v.vendedor_sk = fv.vendedor_sk
GROUP BY v.codven ORDER BY meses_con_venta;
```

**A-0.5 — vendedores/almacenes activos sin histórico**: mismo esqueleto con `HAVING COUNT(...) = 0` sobre el catálogo de vendedores vigentes, más el cruce con la fecha de primer movimiento del almacén en `edw.fact_movimientos_inventario`.

---

## 23. Matriz de tests

| # | Test | Fase | Garantiza |
|---|---|---|---|
| T-1 | Equivalencia v2 ↔ v3 con la semilla, sobre ≥20 series sintéticas y ≥5 reales | 5 | El v3 no cambia ninguna meta hasta que gerencia cambie configuración |
| T-2 | Cada etapa desactivada es **exactamente** neutra | 5 | Ninguna etapa "apagada" mueve el resultado |
| T-3 | Orden de restricciones: redondeo después de acotar | 5 | Ninguna meta fuera de banda |
| T-4 | `holt_winters` + `E3 activa` es rechazado al guardar | 6 | Sin doble ajuste estacional |
| T-5 | Método inexistente en el catálogo es rechazado (400) | 6 | Catálogo cerrado, sin ejecución arbitraria |
| T-6 | `banda_max` fuera de rango es rechazado | 6 | El guardarraíl no se puede anular desde la UI |
| T-7 | Vendedor con 0 meses → `benchmark_puro_v3`, meta > 0, traza explícita | 7 | R-8 |
| T-8 | Vendedor con 3 meses → mezcla `w=0.5`, no escalón | 7 | R-8 |
| T-9 | Cumplimiento 89.9% con bonos altos → **comisión final $0** | 2 | R-2, el defecto de §1.3 |
| T-10 | Cumplimiento 90.0% → paga (frontera inclusiva) | 2 | Sin off-by-one en dinero |
| T-11 | Caso `VEN01` sintético: bonos acotados por el techo | 2 | R-6 |
| T-12 | Bono de cliente nuevo no aplica a perfil mostrador/agencia | 2 | R-6 |
| T-13 | Paridad simulador ↔ cálculo real, mismo mes y config, tolerancia de centavos | 4 | R-4 |
| T-14 | Proyección con multiplicador 0.0 en algún mes no promedia mal | 4 | R-4 |
| T-15 | Comisión sin factores de crédito = comisión con factor neutro | 3 | R-7 sin cambio de valor inesperado |
| T-16 | Snapshot `oficial` previo se devuelve intacto tras el retiro de crédito | 3 | RN-CM6 |
| T-17 | Traza v2 legado se renderiza sin romper el lector v3 | 8 | Compatibilidad |
| T-18 | Bitácora registra un cambio de configuración de **metas** | 8 | R-11 |
| T-19 | Endpoint de bitácora no expone ningún verbo de escritura | 8 | R-11 (solo lectura) |
| T-20 | Previsualización no persiste nada (conteo de filas antes/después) | 8 | R-10 |

---

## 24. Reglas de negocio a documentar

En `docs/auditoria/02_reglas_negocio_validadas.md`:

**§24 (Metas), nuevas RN-MT7..RN-MT16:**
- RN-MT7 — La meta se calcula con un pipeline de etapas de catálogo cerrado; el orden de ejecución es fijo, lo configurable es método y activación.
- RN-MT8 — La estacionalidad se resuelve **antes** de limpiar y nivelar; nivel, outliers y tendencia operan sobre la serie desestacionalizada.
- RN-MT9 — Toda etapa sin datos se declara desactivada con su razón; nunca devuelve un valor inventado.
- RN-MT10 — El benchmark de vendedores nuevos es la **mediana** del grupo comparable; `sucursal` está descartada como agrupador (auditoría 42).
- RN-MT11 — Transición gradual de madurez (0 / 1-5 / 6-23 / ≥24 meses), sin escalones.
- RN-MT12 — Orden de restricciones: capacidad → banda → topes absolutos → redondeo.
- RN-MT13 — Criterio de calibración: 60-70% de la fuerza de ventas debe alcanzar la meta (Zoltners et al.).
- RN-MT14 — El factor de tipo de vendedor se aplica en **un solo** lugar (E8); queda prohibido duplicarlo en el servicio.
- RN-MT15 — La traza persiste el `config_snapshot` completo; una meta se explica sin depender de la configuración actual.
- RN-MT16 — La previsualización nunca persiste.

**§18 (Comisiones), nuevas RN-CM17..RN-CM21:**
- RN-CM17 — La comisión del sistema es **única y variable**; el esquema plano queda retirado de toda ruta de servicio.
- RN-CM18 — La compuerta de cumplimiento se aplica a la comisión **completa, bonos incluidos**: bajo el umbral, la comisión final es $0. (Corrige el alcance real de RN-CM16.)
- RN-CM19 — Los bonos están acotados por un techo relativo a la base comisionable propia del vendedor.
- RN-CM20 — El bono de cliente nuevo/reactivado no aplica a códigos de mostrador/agencia (no son captación de cartera).
- RN-CM21 — El factor de plazo de crédito queda retirado del cálculo (sin poder discriminante real, auditoría 30 H4); su tabla se conserva por integridad histórica.

---

## 25. Definición de "hecho" por fase

Una fase se cierra únicamente cuando cumple **todas**:
1. Su auditoría correspondiente está escrita con cifras reales (no hipótesis) en `docs/auditoria/`.
2. Sus tests de la §23 están verdes, y `pytest backend/tests/unit` completo no tiene regresiones.
3. `tsc --noEmit` / `oxlint` / `npm run build` limpios si tocó frontend.
4. Si tocó migraciones: aplicada contra la BD real, `bi_backend` reconstruido y **arrancando limpio** (verificado en logs, no asumido).
5. Probada **en vivo** contra el backend real con datos reales, con el resultado transcrito en la auditoría.
6. Si tocó dinero: verificado que `public.comision_liquidaciones` no ganó filas espurias durante la prueba (conteo antes/después) y que ningún snapshot `oficial` previo cambió.
7. Las reglas de negocio nuevas están en `docs/auditoria/02_reglas_negocio_validadas.md`.
8. `CLAUDE.md` actualizado con lo aplicado, lo pendiente y lo **explícitamente descartado con su razón**.

---

## 26. Qué NO hace este plan (alcance declarado)

- **No reintroduce ML en el cálculo de metas.** `goals_rf` fue decomisionado con auditoría propia (20); E2-`forecast_ml` queda declarado y desactivado. Reactivarlo exigiría una competencia formal de modelos documentada, fuera de este alcance.
- **No implementa E14 (potencial de mercado).** No hay fuente de dato y no la habrá desde un ERP transaccional propio.
- **No genera metas aprobadas artificialmente** para desbloquear la Fase 9.B.
- **No toca el ETL ni el EDW.** Todo el trabajo es de `backend/` + `frontend/` + migraciones de `public.*`. Si A-0.4 revelara que una etapa necesita un dato que el EDW no extrae, se documenta como hallazgo y se declara la etapa sin datos — no se abre un frente de ETL dentro de este plan.
- **No decide activar el esquema variable como oficial.** Entrega el código, el impacto medido y el rollback; la activación es de gerencia.

