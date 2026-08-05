# Plan — Motor de Metas Comerciales configurable, estacional y con fundamentación de negocio

> **Estado:** propuesto (ninguna fase aplicada).
> **Fecha:** 2026-07-31
> **Módulo:** Metas y Comisiones (panel de Gerencia) — `backend/app/services/goal_calculation_engine.py`, `goal_ml_service.py`, `goal_repository.py`, `frontend/src/components/goals/*`.
> **Auditoría asociada (a crear en la Fase 0):** `docs/auditoria/46_motor_metas_configurable.md`.
> **Antecedentes:** `docs/auditoria/16_venta_neta_y_propuesta_meta_siguiente_mes.md`, `19_grano_vendedor_metas_y_meta_futura_razonable.md`, `20_decomision_goals_rf.md`, `35_actualizacion_modulo_metas.md`, `45_sobrecumplimiento_umbral_y_desglose.md`.

---

## 1. Qué pidió el usuario

1. Revisar **exactamente** la fórmula de la meta: qué valores toma, bajo qué criterios.
2. Hacer la fórmula **editable y manejable por el gerente** (como ya lo es la fórmula de comisiones tras la auditoría 44/45).
3. Usar **meses anteriores del mismo año** + **el mismo mes de años anteriores**; y cuando no haya suficiente información, **cambiar la forma de fijar la meta**.
4. Las metas actuales son **demasiado elevadas**: hay valores que un vendedor no alcanza en un mes bajo ni en un mes normal.
5. Adoptar una **fórmula usada en otras empresas**, con fundamentación documentada (requisito de tesis).
6. **Meses atípicos** (un mes excepcionalmente bueno) no deben elevar la meta de los meses siguientes.
7. Considerar **otros factores** para un buen sistema de metas, ahora que el de comisiones ya está casi cerrado.
8. **"Ver cómo se calculó"** debe mostrar los **valores reales** con los que se calculó la meta del vendedor elegido.
9. En **"Comisiones devengadas" → "Cumplimiento real y comisión por vendedor"** debe entrar también la **comisión variable**.

---

## 2. La fórmula actual, exactamente como está hoy

Fuente única: `IQRGoalCalculationEngine.calcular` ([goal_calculation_engine.py](backend/app/services/goal_calculation_engine.py)), invocada desde `GoalMLService.suggest_goal` → `generate_proposals`.

### 2.1 Insumo

`GoalRepository.get_vendor_monthly_history(vendedor, meses=24)` — serie mensual de **Venta Neta** (`SUM(fact_ventas_detalle.subtotal_neto)` − `SUM(fact_devoluciones.total_linea_devolucion)`), grano vendedor (todas sus sucursales), **últimos 24 meses**.

### 2.2 Cadena de cálculo (en orden real de ejecución)

| # | Paso | Código | Parámetro |
|---|---|---|---|
| 1 | Recortar a los últimos 24 meses | `_tomar_ultimos_meses` | `MESES_VENTANA_MAX = 24` |
| 2 | Marcar outliers por Tukey. Los cuartiles se calculan **solo sobre los últimos 12 meses**, pero el filtro se aplica a los 24. Con <4 puntos no filtra nada. | `_indices_sin_outliers` | `IQR_MULTIPLICADOR = 1.5`, `VENTANA_RECIENTE_OUTLIERS = 12` |
| 3 | Meses marcados por IsolationForest (`anomaly.pkl`) **no se excluyen**: pesan 0.5 | `calcular` | `PESO_MES_ATIPICO_ML = 0.5` |
| 4 | `componente_estacional` = promedio ponderado de los meses cuyo `mes` == mes objetivo dentro de la ventana | `_calcular_base_siguiente_mes` | — |
| 5 | `componente_tendencia` = promedio ponderado de los **últimos 4 meses** | idem | `RECENT_TREND_MONTHS = 4` |
| 6 | `base = (estacional + tendencia) / 2`; si no hay estacional, `base = tendencia` | idem | peso fijo 50/50 |
| 7 | `factor_tendencia_bruto` = mediana de las razones intermensuales de esos 4 meses, acotada | `_factor_tendencia_bruto` | `[0.85, 1.20]` |
| 8 | Atenuación por variabilidad: `factor = 1 + (bruto − 1) × peso_estabilidad`, donde `peso_estabilidad` cae de 1.0 a 0.3 cuando el CV supera 0.5 | `_peso_estabilidad` | `CV_ALTO = 0.5`, `PESO_ESTABILIDAD_MIN = 0.3` |
| 9 | Techo/piso de sanidad: `base × factor_tendencia` acotado a `[0.7, 1.3] × componente_tendencia` | `_limitar_contra_tendencia` | `LIMITE_VS_TENDENCIA_MIN/MAX` |
| 10 | `meta = base_sana × factor_estacional × factor_crecimiento` — **sin ningún tope posterior** | `calcular` | `factor_crecimiento` = slider "Presión Comercial" 0–25% |
| 11 | Ajuste por tipo de vendedor: `× 1.10` (externo) o `× 0.95` (interno); vendedor nuevo (<3 meses) → `0.60 × promedio del equipo` | `GoalMLService._ajustar_meta_por_tipo` | `COMISION_META_FACTOR_*`, `COMISION_VENDEDOR_NUEVO_*` |
| 12 | `unidades_meta` = **unidades del mes anterior × factor_presion** — sin IQR, sin estacionalidad, sin tendencia | `generate_proposals` | — |

**Los 13 parámetros de negocio de la tabla son constantes de módulo en Python.** El gerente solo controla un slider de 0–25%.

---

## 3. Hallazgos preliminares (verificados en código; se cuantifican en la Fase 0)

| ID | Sev. | Hallazgo |
|---|---|---|
| **H-1** | **ALTO** | **La meta no se calcula para el período que se pide.** `generate_proposals(anio, mes)` llama a `suggest_goal(vendedor)` sin pasar el período; `_calcular_base_siguiente_mes` deriva `mes_objetivo = último mes con datos + 1`. Generar metas de septiembre con datos hasta julio produce la estacionalidad de **agosto**. El drawer "cómo se calculó" tiene el mismo desfase. Es la causa raíz más probable de "metas que no corresponden al mes". |
| **H-2** | **ALTO** | **La ventana de 24 meses hace imposible lo que pide el usuario.** Con 24 meses hay a lo sumo **una** observación del mismo mes de un año anterior (frecuentemente cero, si el vendedor tiene <24 meses de historia). No existe "el mismo mes de años anteriores" en plural; un índice estacional sobre 1 punto no es un índice, es un dato suelto. |
| **H-3** | **ALTO** | **Ningún tope sobre la meta final.** Los pasos 10 y 11 se aplican **después** del único guardarraíl (`_limitar_contra_tendencia`). Cota superior real: `1.3 (sanidad) × 1.25 (presión) × 1.10 (externo) = 1.79 ×` la tendencia reciente. Un vendedor cuyos últimos 4 meses promedian $10.000 puede recibir una meta de $17.875 sin que ninguna validación lo impida. Explica directamente "valores que no van a alcanzar". |
| **H-4** | **ALTO** | **El filtro de meses atípicos no protege la tendencia.** El paso 5 promedia los últimos 4 meses **crudos**; si el mes bueno es reciente y no cayó fuera de las bandas de Tukey (probable con IQR ancho o CV alto), entra completo en `componente_tendencia`, que además es el ancla del techo del paso 9 — el pico se autolegitima. Peor: `factor_tendencia_bruto` usa la razón contra ese mismo mes, así que un pico puede empujar tendencia **y** factor a la vez. Es exactamente el escenario que el usuario describe. |
| **H-5** | **MEDIO** | **Sin trazabilidad persistida.** `metas_comerciales_operativas` guarda solo `monto_meta`. El drawer "cómo se calculó" **recalcula hoy** con los datos y la configuración de hoy: los números mostrados no son los que produjeron la meta guardada (mismo defecto de clase que el ya corregido en liquidaciones oficiales, auditoría 35 H2). Incumple el requisito 8 del usuario. |
| **H-6** | **MEDIO** | **No hay degradación explícita por falta de datos.** Hay tres fallbacks implícitos y silenciosos (sin cuartiles con <4 meses; sin estacional → tendencia pura; vendedor nuevo → 60% del promedio del equipo) que no se distinguen entre sí, no se etiquetan en `metodo`, y no se muestran al gerente. Un vendedor con 2 meses de historia recibe una meta presentada igual que uno con 24. |
| **H-7** | **MEDIO** | **`unidades_meta` es indefendible.** `unidades del mes anterior × presión`: sin limpieza de outliers, sin estacionalidad, sin tendencia. Si el mes anterior fue atípico, la meta de unidades hereda el pico entero. |
| **H-8** | **MEDIO** | **Comisión variable ausente de "Comisiones devengadas".** `CommissionService.get_commission_tracking` solo puebla `comision_variable` si `COMISION_MODO in ("sombra","variable")`; en `plana` la columna ni se renderiza. Además `nivel`/`tasa` de esa tabla salen de `calcular_comision` (esquema plano legacy, 4 tramos fijos) e **ignoran los tramos de cumplimiento configurables** de la auditoría 45 — dos verdades distintas sobre el mismo vendedor en el mismo panel. |
| **H-9** | **BAJO** | **Factores mezclados de dominio.** El ajuste de meta por tipo de vendedor vive en `COMISION_META_FACTOR_*` (namespace de comisiones) y se resuelve vía `CommissionConfigRepository`: acopla la política de metas a la de comisiones sin razón de negocio. |
| **H-10** | **BAJO** | **El slider de presión miente en la UI.** `GoalsConsole.tsx:162` recalcula el monto en el frontend como `(monto / 1.1) × (1 + pressure/100)`, asumiendo que la meta mostrada ya trae un 10% incorporado — un supuesto que no se cumple si el vendedor es interno (×0.95) o nuevo (×0.60). |

---

## 4. Fase 0 — Auditoría obligatoria (antes de tocar código)

Solo `SELECT` contra el EDW y ejecución en modo lectura del motor real dentro de `bi_backend`. Sin escrituras. Producto: `docs/auditoria/46_motor_metas_configurable.md`.

**A-0.1 — Cuantificar la brecha real (el núcleo del reclamo del usuario).** Para cada vendedor activo, con los períodos ya aprobados de `metas_comerciales_operativas`: `monto_meta` vs. Venta Neta realmente lograda. Reportar la **distribución de cumplimiento**: mediana, % de vendedores bajo el 90% (el nuevo umbral de pago de la auditoría 45), % sobre 100%. *Criterio de referencia de la industria: un esquema sano ubica al 60–70% de la fuerza de ventas en o sobre su cuota. Si la mediana está muy por debajo, el reclamo queda cuantificado, no supuesto.*

**A-0.2 — Confirmar H-1 en vivo.** Ejecutar `suggest_goal` para 3 vendedores reales e imprimir `mes_objetivo` interno vs. el mes del período que Gerencia generó. Confirmar o descartar el desfase.

**A-0.3 — Viabilidad de la estacionalidad multi-anual (H-2).** Contar, por vendedor, cuántos años tiene de historia mensual continua en `fact_ventas_detalle` y cuántas observaciones del mismo mes calendario existirían con ventanas de 24 / 36 / 48 meses. Decide si el índice estacional se calcula **por vendedor**, o —para vendedores cortos— con un **índice de la empresa/categoría** como respaldo (pooling). Sin este dato, la Fase 2 se diseñaría a ciegas.

**A-0.4 — Descomponer las metas más altas (H-3/H-4).** Para los 5 vendedores con peor cumplimiento en A-0.1, imprimir la cadena completa: histórico usado, meses excluidos por IQR, meses marcados por IsolationForest, componente estacional, componente tendencia, factor de tendencia, base tras el techo, y cada multiplicador posterior. Objetivo: **atribuir numéricamente** cuánto del exceso viene del pico atípico, cuánto del `factor_presion`, cuánto del `×1.10` de vendedor externo.

**A-0.5 — Estabilidad y estacionalidad reales del negocio.** Índice estacional agregado por mes calendario (¿existe realmente un "mes bajo"?) y CV por vendedor. Determina si vale la pena un índice estacional por vendedor o si el ruido individual exige el índice agregado.

**A-0.6 — Impacto de H-8.** Verificar `COMISION_MODO` vigente y contar filas en `comision_liquidaciones`; medir el costo por consulta de calcular la comisión variable para todos los vendedores del período (el simulador ya resuelve la configuración una vez por período — mismo patrón a reusar).

> **Regla de decisión:** si A-0.1 y A-0.4 no confirman que las metas son sistemáticamente inalcanzables, se presenta el hallazgo al usuario antes de cambiar la fórmula. No se reescribe un motor de metas sobre una hipótesis.

---

## 5. Diseño propuesto

### 5.1 Fundamentación (requisito 5, y respaldo de tesis)

El método propuesto es el estándar de **quota setting bottom-up basado en histórico**, tal como lo describen Zoltners, Sinha & Lorimer (*The Complete Guide to Sales Force Incentive Compensation*) para fuerzas de venta con territorios estables y datos históricos por vendedor, combinado con la **descomposición clásica de series de tiempo** (nivel × índice estacional × tendencia; Hyndman & Athanasopoulos, *Forecasting: Principles and Practice*) para el componente predictivo, y con los tres guardarraíles que la práctica empresarial exige y que hoy faltan:

1. **Base robusta, no promedio simple.** Mediana / media recortada sobre el histórico deseasonalizado — robusta a un mes extraordinario por construcción, no por un filtro que puede fallar (corrige H-4).
2. **Índice estacional ratio-to-moving-average** calculado sobre varios años y **normalizado** (los 12 índices promedian 1.0) — es la formalización exacta de "el mismo mes de años anteriores" que pidió el usuario, y evita el doble conteo actual (hoy la estacionalidad entra sumada al nivel, no como un factor).
3. **Banda de alcanzabilidad explícita** sobre la meta **final**, no sobre un valor intermedio (corrige H-3).

Esto se documentará como regla de negocio nueva (RN-MT*) en `docs/auditoria/02_reglas_negocio_validadas.md`, con las referencias bibliográficas completas para la tesis.

### 5.2 Fórmula propuesta

```
meta = clamp(
          nivel_base × indice_estacional(mes_objetivo) × factor_tendencia × factor_presion × factor_tipo,
          piso  = k_min × referencia_alcanzable,
          techo = k_max × referencia_alcanzable
       )
```

donde:

- **`nivel_base`** = media recortada (o mediana, configurable) de la serie **deseasonalizada** de los últimos `N` meses (`N` configurable, propuesta 36), tras excluir outliers por Tukey **y** descontar el peso de los meses marcados por IsolationForest. *Deseasonalizar antes de promediar es lo que impide que un diciembre fuerte contamine el nivel de un febrero.*
- **`indice_estacional(m)`** = ratio-to-moving-average del mes `m` promediado sobre **todos los años disponibles**, normalizado a media 1.0. Se calcula **por vendedor** si tiene ≥ `min_anios_estacional` años (propuesta 2); si no, cae al índice de la empresa (decisión respaldada por A-0.3/A-0.5).
- **`factor_tendencia`** = pendiente relativa reciente, acotada y atenuada por CV — se conserva el mecanismo actual, que es correcto, pero calculado sobre la serie **deseasonalizada** (hoy se calcula sobre la serie cruda, mezclando estacionalidad con tendencia).
- **`factor_presion`**, **`factor_tipo`** — políticas de gerencia, sin cambios conceptuales.
- **`referencia_alcanzable`** = mediana deseasonalizada de los últimos `M` meses (propuesta 6) × índice estacional del mes objetivo. Es "lo que este vendedor realmente vende en un mes como este". `k_min`/`k_max` configurables (propuesta 0.85 / 1.20).

**El mes objetivo es el del período solicitado**, no el siguiente al último dato (corrige H-1).

### 5.3 Escalera de degradación por falta de datos (requisito 3)

Explícita, etiquetada en `metodo`, **visible en la UI**:

| Datos disponibles | Método | Etiqueta |
|---|---|---|
| ≥ 2 años con el mismo mes | Fórmula completa, índice estacional propio | `estacional_propio_v2` |
| ≥ 12 meses, sin años previos suficientes | Fórmula completa con **índice estacional de la empresa** | `estacional_empresa_v2` |
| 4–11 meses | Sin índice estacional: mediana reciente × tendencia acotada | `tendencia_robusta_v2` |
| 1–3 meses (vendedor nuevo) | `factor_nuevo` × **mediana del equipo** (no el promedio: hoy usa el promedio, que un vendedor grande distorsiona) | `equipo_prorrateado_v2` |
| 0 meses | **No se propone meta**; se marca para captura manual, en vez de emitir un número sin respaldo | `sin_historico` |

### 5.4 Otros factores a incorporar (requisito 7)

Se proponen **como parámetros configurables desactivados por defecto**, para que gerencia los active con evidencia, no por defecto:

- **Días hábiles del mes objetivo** (`dim_fecha` ya los tiene): un febrero de 20 días hábiles no debe tener la misma meta que un marzo de 23. Factor = `hábiles(mes) / promedio_hábiles`.
- **Cartera activa del vendedor**: cambios grandes en el número de clientes asignados (`Cartera360`) justifican mover la base; hoy se ignora por completo.
- **Ausencias / meses parciales**: un mes con ventas casi nulas por vacaciones o baja entra hoy como un mes malo real y **baja** la meta futura, el espejo exacto del problema del pico. Se propone un umbral de "mes no representativo" (`< x%` de la mediana) que se excluye igual que un outlier alto.
- **Tope de variación intermensual de la meta**: la meta de un vendedor no puede saltar más de `y%` respecto de su meta aprobada del mes anterior sin justificación explícita — el guardarraíl que más rápido corta el reclamo del usuario.

### 5.5 Configuración editable por el gerente (requisito 2)

Se reutiliza **exactamente** el patrón ya probado en Comisiones (auditoría 44/45): tabla de configuración con vigencia + repositorio + servicio con validación + bitácora + pestaña en el panel. **No** se introduce evaluación de expresiones arbitrarias — el gerente edita **parámetros** de una fórmula fija y auditada, no una fórmula libre; misma decisión de seguridad ya tomada para el motor de comisiones.

- Migración `0013_metas_config` → `public.metas_config_parametros` (clave, valor, vigencia, `actualizado_por`), sembrada con los valores actuales para que **la primera versión reproduzca el comportamiento vigente**, y `public.metas_indice_estacional` (opcional, override manual de gerencia sobre un mes concreto).
- Endpoints `GET/PUT /gerencia/goals/meta-config/*`, con validación de rangos (nada de `k_max = 5.0`) y registro en `comision_config_auditoria` (o su equivalente renombrado).
- Pestaña **"Fórmula de metas"** en el panel de Metas, con **previsualización**: al mover un parámetro, muestra el impacto sobre los vendedores del período **antes** de guardar — el equivalente del simulador de comisiones, y el argumento que gerencia necesita para decidir.

### 5.6 Trazabilidad real (requisito 8)

Columna `trazabilidad_calculo JSONB` en `metas_comerciales_operativas`, poblada en `generate_proposals` con la traza completa (histórico usado, meses excluidos y por qué, índice estacional aplicado, cada factor, la banda de alcanzabilidad y si actuó). El drawer **lee el JSON persistido** en vez de recalcular; solo cae al cálculo en vivo (etiquetado como tal) para metas anteriores a esta migración. Se muestran los **valores reales** — importes, no solo nombres de factor — paso a paso, mismo formato de desglose expandible que ya se aplicó al simulador de comisiones en la auditoría 45.

### 5.7 Comisión variable en "Comisiones devengadas" (requisito 9)

- `get_commission_tracking` calcula **siempre** la comisión variable (independiente de `COMISION_MODO`), resolviendo la configuración **una vez por período** — mismo patrón de pre-resolución ya aplicado en `CommissionSimulationService`, para no disparar N consultas por vendedor.
- `COMISION_MODO` deja de decidir *si se muestra* y pasa a decidir solo *cuál es la oficial*: en `plana` la variable se rotula "referencia", en `variable` es la que paga. **No se escriben snapshots** desde esta vista en modo `plana` (la inmutabilidad de la auditoría 35 H2 se respeta intacta).
- La tabla gana `% cumplimiento`, `Tramo` (los tramos configurables de la auditoría 45, no los 4 fijos del esquema legacy) y **fila expandible con el desglose de 7 componentes**, reutilizando el `renderExpanded` que `DataTable` ya tiene.

---

## 6. Fases de implementación

| Fase | Contenido | Depende de |
|---|---|---|
| **0** | Auditoría A-0.1..A-0.6 → `docs/auditoria/46_motor_metas_configurable.md`. **Punto de decisión con el usuario** sobre la semilla de parámetros. | — |
| **1** | **Correcciones de defecto puro, sin cambio de fórmula:** H-1 (período objetivo real), H-10 (slider), H-5 parcial (persistir trazabilidad del motor actual). Cada una es un bug independiente y entregable por separado. | 0 |
| **2** | Motor v2: deseasonalización, índice estacional multi-anual, base robusta, banda de alcanzabilidad, escalera de degradación (§5.2/§5.3). Función pura y testeable, misma interfaz `GoalCalculationStrategy` — el motor v1 se conserva seleccionable por parámetro para comparación. | 1 |
| **3** | Persistencia y CRUD de configuración: migración `0013`, repositorio, servicio con validación, bitácora, endpoints (§5.5). Semilla = comportamiento vigente. | 2 |
| **4** | Frontend: pestaña "Fórmula de metas" con previsualización; drawer "cómo se calculó" leyendo la traza persistida (§5.6). | 3 |
| **5** | Comisión variable + tramos + desglose en "Comisiones devengadas" (§5.7). **Independiente de las fases 1–4** — puede adelantarse si el usuario lo prioriza. | 0 |
| **6** | `unidades_meta` con el mismo tratamiento que el monto (H-7); factores opcionales de §5.4. | 2 |
| **7** | Documentación: RN-MT* en `02_reglas_negocio_validadas.md`, actualización de `CLAUDE.md` y `docs/manual_metas_y_comisiones.md`, referencias bibliográficas para la tesis. | 2–6 |

---

## 7. Validación exigida

- **Backtest obligatorio antes de aplicar la Fase 2 a datos reales:** recalcular con el motor v2 las metas de los últimos 12 meses cerrados y comparar la **distribución de cumplimiento** resultante contra la real (A-0.1). Criterio de aceptación explícito: la mediana de cumplimiento debe acercarse al rango 90–105% **sin** que la meta agregada de la empresa caiga por debajo de un umbral que gerencia acepte. Bajar todas las metas es trivial y equivocado; el objetivo es que sean *alcanzables y exigentes*, y eso se mide, no se afirma.
- Tests unitarios nuevos: índice estacional normalizado (suma 12), mes objetivo correcto en cada mes calendario incluido diciembre→enero, un pico de un solo mes **no** mueve la meta más de X%, cada peldaño de la escalera de degradación, la banda de alcanzabilidad actúa en ambos sentidos, guardas de rendimiento `call_count == 1` en el tracking de comisiones.
- `pytest backend/tests/unit` + `backend/tests/integration -k "meta or goal or commission"`; `tsc --noEmit` / `oxlint` / `npm run build`.
- Prueba en vivo contra `bi_backend` con datos reales, verificando que `metas_comerciales_operativas` **no** se altere hasta que el usuario apruebe la semilla (las fases 0–2 no escriben metas).

---

## 8. Riesgos

| Riesgo | Mitigación |
|---|---|
| Este módulo alimenta el cálculo de **dinero real** (la meta es el denominador del % de cumplimiento, que a su vez fija el multiplicador de comisión de la auditoría 45). | Fases 0–2 son de solo lectura; la semilla de parámetros reproduce el comportamiento actual; el cambio de motor requiere aprobación explícita del usuario tras ver el backtest. |
| Este entorno **no tiene historial de metas aprobadas de meses anteriores** (`metas_comerciales_operativas` solo tiene 2026-07/08, ya constatado en la auditoría 45). | A-0.1 puede quedar sin base comparativa. En ese caso el backtest de la Fase 7 se hace contra **metas recalculadas** con el motor v1 sobre meses históricos reales de venta — comparación motor-a-motor, no motor-contra-meta-aprobada, y se declara la limitación explícitamente. |
| Bajar metas reduce mecánicamente el gasto en comisiones y sube el cumplimiento aparente. | El backtest reporta **ambos** efectos: distribución de cumplimiento **y** costo total de comisión resultante. La decisión final es de gerencia, con las dos cifras a la vista. |
| Metas ya `APROBADA` no deben moverse retroactivamente. | El motor v2 solo aplica a propuestas nuevas; `generate_proposals` ya respeta `estado == 'PROPUESTA'`. Se agrega test de regresión. |

---

## 9. Decisiones que requieren al usuario

1. **Semilla de parámetros** (§5.2): ventana de 36 meses, banda de alcanzabilidad 0.85–1.20, mediana vs. media recortada.
2. **Estacionalidad por vendedor vs. de empresa** cuando el vendedor tiene poca historia (§5.3) — se resuelve con la evidencia de A-0.3/A-0.5.
3. **Cuáles de los factores opcionales de §5.4** activar (días hábiles, cartera, meses no representativos, tope de variación).
4. **Prioridad de la Fase 5** (comisión variable en el panel): es independiente y puede ir primero.
