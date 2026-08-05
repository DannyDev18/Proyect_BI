# Auditoría 45 — Sobrecumplimiento, umbral de pago al 90% y desglose de la comisión

> **Fecha:** 2026-07-31
> **Alcance:** Fase 0 (auditoría previa) y Fases 1-4 (implementación completa) del plan
> `docs/features/plan_comisiones_sobrecumplimiento_umbral_y_desglose.md`.
> **Método Fase 0:** solo `SELECT` contra el EDW real (`bi_postgres_edw`) y ejecución en modo lectura del motor de
> producción (`calcular_comision_variable_completa`) dentro del contenedor `bi_backend`. Sin escritura, sin
> artefactos dejados en `public.comision_liquidaciones` (verificado, ver A-0.4).
> **Estado:** aplicado en el entorno de desarrollo real (migración `0012_tramos_cumplimiento` corrida contra
> `bi_postgres_edw`, `bi_backend` reconstruido con arranque limpio). Ver §6 para el detalle de lo aplicado y la
> validación extremo a extremo.

## Resumen ejecutivo

El pedido del usuario ("hay valores demasiado elevados en algunos vendedores") **no** se explica por las hipótesis
H-1..H-4 que planteaba el plan (denominador de la tasa efectiva, contado de agencia, cobranza acumulada, proyección
optimista). La causa real, cuantificada abajo, es un componente que el plan no había señalado:

> **H-5 (nuevo, ALTO):** el bono "cliente nuevo/reactivado" (`$50` por cliente, `COMISION_BONO_CLIENTE_NUEVO`)
> cuenta como "nuevo" a cualquier cliente que compró en el mes y no tenía compras (de nadie) en los 6 meses
> previos. Para un vendedor de mostrador con alta rotación de compradores ocasionales, eso es la norma, no la
> excepción — no refleja ningún esfuerzo real de captación. En junio 2026, `VEN01` ("ALMACEN EL REY") facturó a
> 677 clientes distintos, de los cuales **512 calificaron como "nuevos"**, generando un bono de **$25.600** —
> **el 66% de todo lo pagado por este componente ese mes entre los 9 vendedores activos**, y muy por encima de su
> propia base comisionable de líneas ($255,50) y cobranza ($259,07) combinadas.

Además, sobre R-1/R-3 (impacto de dinero en tramos de cumplimiento): **el EDW de este entorno no tiene historial de
metas aprobadas** más allá del mes en curso — `public.metas_comerciales_operativas` solo tiene filas para 2026-07 y
2026-08 (`fact_metas_comerciales`, la tabla del esquema `edw`, está vacía desde el diseño original del módulo, regla
10 de `CLAUDE.md`). No es posible medir la distribución de 12 meses cerrados que pedía A-0.1/A-0.2 del plan. Se
documenta como limitación de datos, no se rellena con cifras inventadas — ver §2.

---

## 1. A-0.3 — Composición real de la comisión por vendedor (junio 2026)

Ejecutado con `calcular_comision_variable_completa` (el motor real, no una reconstrucción aparte) para los 9
vendedores con venta en 2026-06, mes totalmente cerrado con datos de cobranza reales.

| Vendedor | Venta neta | Líneas (margen/cat.) | Cobranza | Contado agencia | Devoluciones | **Bonos** | **Comisión final** | % cobranza+contado del total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| VEN01 | 60.874,05 | 255,50 | 259,07 | 0,00 | 54,06 | **25.600,00** | **25.545,94** | 50,3% |
| VEN02 | 62.168,43 | 60,35 | 975,38 | 0,00 | 295,98 | 450,00 | 154,02 | 94,2% |
| VEN03 | 33.941,09 | 128,68 | 216,76 | 0,00 | 36,94 | **7.850,00** | **7.813,06** | 62,7% |
| VEN13 | 97.863,53 | 220,37 | 973,95 | 0,00 | 388,72 | **7.500,00** | **7.111,28** | 81,5% |
| VEN15 | 16.967,24 | 34,97 | 147,07 | 0,00 | 79,01 | 3.650,00 | 3.570,99 | 80,8% |
| VEN16 | 11.402,10 | 22,05 | 98,67 | 0,00 | 5,43 | 1.900,00 | 1.894,57 | 81,7% |
| VEN17 | 8.672,02 | 21,95 | 26,33 | 0,00 | 9,10 | 2.300,00 | 2.290,90 | 54,5% |
| VEN21 | 41.957,52 | 24,69 | 789,53 | 0,00 | 219,61 | 50,00 | 0,00 | 97,0% |
| VEN24 | 36.747,07 | 40,07 | 470,08 | 0,00 | 264,34 | 0,00 | 0,00 | 92,1% |

**Lectura:** en 6 de 9 vendedores, `bonos` es **10 a 100 veces mayor** que la suma de `base_lineas_venta` +
`base_cobranza`. Ningún vendedor tiene `contado_agencia` > 0 este mes (nadie está configurado como
`jefe_agencia` con agencia asignada) — descarta H-2 como causa de este mes concreto, aunque el diseño del
componente sigue siendo el documentado.

### 1.1 Desglose del componente `bonos` (el hallazgo real)

| Vendedor | Bono venta cruzada | Clientes "nuevos/reactivados" (n) | Bono cliente nuevo (n × $50) | Clientes distintos del mes |
|---|---:|---:|---:|---:|
| VEN01 | 0,00 | **512** | **25.600,00** | 677 |
| VEN02 | 0,00 | 9 | 450,00 | 67 |
| VEN03 | 0,00 | 157 | 7.850,00 | 260 |
| VEN13 | 0,00 | 150 | 7.500,00 | 262 |
| VEN15 | 0,00 | 73 | 3.650,00 | 109 |
| VEN16 | 0,00 | 38 | 1.900,00 | 59 |
| VEN17 | 0,00 | 46 | 2.300,00 | 71 |
| VEN21 | 0,00 | 1 | 50,00 | 23 |
| VEN24 | 0,00 | 0 | 0,00 | 40 |

`bono_cross_sell` es $0,00 en los 9 vendedores (telemetría de venta cruzada casi vacía, consistente con lo ya
documentado en `docs/auditoria/40_refactor_venta_cruzada.md`, A0-1: solo 79 eventos históricos en todo el sistema).
El "bono de cobranza sana" (`comision_pre_bonos × 5%` cuando `dias_cobro_promedio < 30`) es la diferencia pequeña
entre `bonos` y `bono_cliente_nuevo` en la tabla — irrelevante frente al de cliente nuevo.

### 1.2 Causa raíz de H-5: `VEN01` no es un vendedor de cartera, es un mostrador

`edw.dim_vendedor.nombre_vendedor` para `VEN01` es **"ALMACEN EL REY"** — un código de venta de mostrador/tienda,
no una persona con cartera de clientes asignada (mismo patrón de "código de vendedor que en realidad es un punto de
venta" ya documentado para Bodega en `docs/auditoria/42_correcciones_integrales_sistema.md`, hallazgo Bodega-sucursal
del 2026-07-29 — aquí el defecto análogo aparece en Comisiones, no en RLS).

Verificado contra el histórico completo (no solo junio): `VEN01` ha vendido a **31.107 clientes distintos** en toda
la vida del EDW, de los cuales **17.037 (54,8%) compraron una sola vez** (un solo mes con actividad en todo su
historial). Comparar con `VEN21` (LUIS SANCHEZ, vendedor real de cartera): 86 clientes históricos totales, 9 de una
sola compra (10,5%). El bono de "cliente nuevo" mide, con precisión, la métrica que dice medir — pero esa métrica
**no significa lo mismo** para un mostrador de alta rotación que para un vendedor de cartera: cada comprador ocasional
de mostrador dispara el bono aunque no exista ningún esfuerzo de captación distinguible de una venta normal de
mostrador.

**No se propone una corrección en esta auditoría** (está fuera del alcance original del plan, que solo cubre
tramos de cumplimiento y desglose visual) — se deja como decisión explícita para el usuario en §4.

---

## 2. A-0.1 / A-0.2 — Limitación de datos: sin historial de metas aprobadas

`public.metas_comerciales_operativas` solo contiene:

| Año-mes | Estado | Filas |
|---|---|---|
| 2026-07 | APROBADA | 1 |
| 2026-07 | PROPUESTA | 8 |
| 2026-08 | PROPUESTA | 9 |

No existe ninguna meta persistida para los 12 meses previos (`edw.fact_metas_comerciales`, la tabla que en teoría
guardaría esto en el esquema dimensional, está vacía desde el diseño del módulo — regla de negocio 10 de
`CLAUDE.md`: "las metas operativas viven solo en `public.metas_comerciales_operativas`"). Esto **no es un defecto de
esta sesión**: es el estado real del entorno de desarrollo, sin generación retroactiva de metas para meses ya
cerrados.

**Proxy usado (único dato real disponible):** hoy es 2026-07-31 — el último día de julio — así que las metas de
julio (aunque en su mayoría `PROPUESTA`, no `APROBADA`) ya pueden compararse contra la venta neta real casi completa
del mes:

| Vendedor | Estado | Meta | Venta neta (jul-2026) | % cumplimiento |
|---|---|---:|---:|---:|
| VEN17 | PROPUESTA | 5.013,40 | 7.035,26 | **140,33%** |
| VEN01 | PROPUESTA | 64.348,42 | 74.307,99 | **115,48%** |
| VEN21 | APROBADA | 32.040,90 | 33.553,67 | **104,72%** |
| VEN16 | PROPUESTA | 12.381,03 | 11.650,13 | 94,10% |
| VEN02 | PROPUESTA | 58.098,83 | 54.298,43 | 93,46% |
| VEN03 | PROPUESTA | 37.388,73 | 31.862,12 | **85,22%** ← tramo CERCA hoy (0,7×); con R-3 pasaría a $0 |
| VEN24 | PROPUESTA | 33.536,46 | 24.913,00 | 74,29% (ya en LEJOS, sin cambio con R-3) |
| VEN15 | PROPUESTA | 17.554,63 | 12.842,63 | 73,16% (ya en LEJOS, sin cambio con R-3) |
| VEN13 | PROPUESTA | 104.810,86 | 69.453,09 | 66,27% (ya en LEJOS, sin cambio con R-3) |

**Con esta única muestra (9 vendedores, 1 mes, mayoría de metas sin aprobar todavía):**

- **R-3 (umbral 90%):** solo **1 de 9** vendedores (`VEN03`, 85,22%) quedaría afectado — pasaría de cobrar con
  multiplicador 0,7× a cobrar $0 en el componente `multiplicador_cumplimiento`. Los 3 restantes por debajo de 90%
  ya están en el tramo LEJOS (0,0×) y no cambian.
- **R-1 (escala de sobrecumplimiento):** **3 de 9** vendedores superan el 100% (`VEN17` 140%, `VEN01` 115%,
  `VEN21` 105%). Con la escala propuesta (1.20/1.35/1.50 en 100/110/125%), `VEN17` pasaría de 1,20× a **1,50×**
  (está sobre 125%) y `VEN01` de 1,20× a **1,35×** (está sobre 110%); `VEN21` se queda en 1,20× (no llega a 110%).

**Conclusión de A-0.1/A-0.2:** la muestra es demasiado pequeña (9 vendedores, 1 período, metas todavía no
aprobadas oficialmente) para una decisión de impacto financiero agregado. **No se recomienda aprobar el costo de
R-1/R-3 basándose en esta muestra** — la tabla se incluye solo como evidencia de que el mecanismo funciona como se
espera, no como proyección de costo. Cuando existan varios meses de metas `APROBADA` reales, este mismo query
(dejado documentado en el plan, §Fase 0) puede repetirse con una muestra significativa.

---

## 3. A-0.4 — Verificación de seguridad antes de tocar código

- `COMISION_MODO` no está seteado en el entorno del contenedor `bi_backend` → usa el default `"plana"`
  (`backend/app/core/config.py:186`). El esquema variable **no es el oficial hoy** en este entorno.
- `public.comision_liquidaciones`: **0 filas**. No hay snapshots `oficial` que la Fase 1 pudiera poner en riesgo de
  reescritura retroactiva, ni artefactos de pruebas anteriores que limpiar.
- Ninguna consulta de esta auditoría escribió en la base de datos (todas las conexiones usadas son de solo lectura
  a nivel de código — `calcular_comision_variable_completa` no llama a `db.add`/`db.commit`).

---

## 4. Decisiones que requieren al usuario antes de la Fase 1

1. **H-5 (bono cliente nuevo desbordado en vendedores de mostrador) — ¿se corrige en este mismo trabajo o se
   documenta y difiere?** No estaba en el alcance original del plan (que solo cubre tramos de cumplimiento +
   desglose visual), pero es la explicación real de "valores demasiado elevados" que motivó el pedido. Opciones:
   - **(a) Solo exponerlo** (lo que ya cubre la Fase 3 del plan: el desglose por componente hará visible que
     `bonos` es el 99% de la comisión de `VEN01`, sin cambiar el cálculo). Gerencia decide manualmente si es
     correcto.
   - **(b) Tope al bono de cliente nuevo** (ej. `COMISION_BONO_CLIENTE_NUEVO_TOPE_MES`, un máximo en $ o en número
     de clientes por vendedor/mes) — cambio de una línea en `commission_bonus.py`, pero es una decisión de negocio
     (¿cuál es el tope razonable?).
   - **(c) Excluir vendedores de mostrador del bono** — requiere primero definir qué distingue a un "vendedor de
     mostrador" de uno de cartera en los datos (no hay una columna explícita hoy; `nombre_vendedor` como
     "ALMACEN X" es una heurística, no una regla declarada).
   - Recomendación de esta auditoría: **(a) ahora** (ya está en el plan, Fase 3, sin trabajo adicional) y dejar
     (b)/(c) como una auditoría/plan separado si gerencia confirma que el patrón se repite en otros meses.
2. **R-1/R-3 con muestra insuficiente (§2):** ¿se aplica igual la semilla propuesta (tramo `[0,90)→0.0`,
   escala 1.20/1.35/1.50) asumiendo que es una mejora estructural razonable aunque no se pueda medir su costo
   agregado con 12 meses reales? El diseño ya mitiga el riesgo (vigencia por fecha, no retroactivo sobre snapshots
   oficiales — no hay ninguno hoy). Recomendación: **proceder** — el mecanismo es correcto por diseño y el costo
   real se podrá medir en vivo mes a mes una vez activo, sin esperar a tener historial que este entorno no tiene.

---

## 5. Reglas de negocio derivadas de esta auditoría (para consolidar en la Fase 4)

- **RN-CM15 (nueva):** el multiplicador de cumplimiento de la Comisión Variable se resuelve desde una tabla
  configurable con vigencia (`public.comision_tramos_cumplimiento`), no desde constantes de módulo. El esquema
  plano legacy (`calcular_comision`) no se modifica.
- **RN-CM16 (nueva):** por debajo del 90% de cumplimiento de meta, el componente `multiplicador_cumplimiento` del
  esquema variable es 0,0 (sin comisión de venta/cobranza/contado); los bonos configurados (venta cruzada, cliente
  nuevo, cobranza sana) se siguen sumando después de ese paso, salvo que gerencia reordene la fórmula.
- **H-5 (hallazgo, no regla):** el bono de cliente nuevo/reactivado no distingue vendedores de cartera de
  códigos de venta de mostrador con alta rotación de compradores ocasionales — pendiente de decisión de negocio,
  ver §4.

---

## 6. Aplicado (Fases 1-4) y validación extremo a extremo

Decisiones del usuario tras revisar §4: **(1)** no tocar el bono de cliente nuevo (H-5 queda solo documentado y
expuesto en el desglose, sin corrección de código); **(2)** proceder con la semilla propuesta de tramos de
cumplimiento pese a la muestra insuficiente de §2, dado que el mecanismo es correcto por diseño y no hay
snapshots oficiales que arriesgar.

### 6.1 Cambios aplicados

- **Backend — motor puro:** `commission_engine.py` gana `TramoCumplimiento` (dataclass) y
  `resolver_tramo_cumplimiento` (función pura, sin BD) — reemplaza los 4 tramos fijos como fuente del
  multiplicador. `ETIQUETAS_COMPONENTES_FORMULA` (fuente única de etiquetas legibles, usada por el editor de
  fórmula y el desglose del simulador).
- **Backend — persistencia:** migración `0012_tramos_cumplimiento` (renombrada desde el nombre original del plan,
  `0012_comision_tramos_cumplimiento` — **33 caracteres excedía el límite de 32 de `alembic_version.version_num`**,
  hallazgo real durante la aplicación, no anticipado; ver §6.3). Tabla `public.comision_tramos_cumplimiento`
  (modelo `ComisionTramoCumplimiento`), semilla de 5 tramos (`[0,90)→0.0`, `[90,100)→1.0`, `[100,110)→1.2`,
  `[110,125)→1.35`, `[125,∞)→1.5`, todas con `bono_fijo=0.00`). `CommissionConfigRepository` gana
  `get_tramos_cumplimiento_vigentes`/`get_tramos_cumplimiento_as_tramos`/`replace_tramos_cumplimiento` (resolución
  por perfil específico con fallback a genérico, mismo patrón que `comision_matriz_categorias`).
- **Backend — orquestación:** `commission_variable_engine.calcular_comision_variable_completa` resuelve el
  multiplicador desde los tramos (`tramos_cumplimiento` pre-resuelto opcional, mismo patrón de optimización que
  `matriz`/`rangos_credito` — el simulador los resuelve una vez por período, no por vendedor); `bono_fijo` del
  tramo se integra al componente `bonos` existente. `ResultadoComisionVariable` gana `pct_cumplimiento`/`tramo`.
  `CommissionSimulationService` (los 3 métodos) pasa `tramos_cumplimiento` pre-resuelto y expone el desglose
  (`ComponenteComisionDetalle`, `_detalle_desde_traza`) en `ProyeccionVendedor`; en la proyección (promedio 3/6
  meses), los pasos `sumar`/`restar` se promedian y los `multiplicar` se mantienen constantes (verificado
  analíticamente y con test: son constantes entre los meses históricos simulados por diseño del método).
- **Backend — API:** `GET/PUT /gerencia/goals/commission-config/tramos-cumplimiento` (mismo patrón de
  `tramos-cobranza`, con validación de cobertura `[0,∞)` sin huecos/solapes en `CommissionConfigService`).
  `ProyeccionVendedorResponse` gana `pct_cumplimiento`/`nivel`/`multiplicador_cumplimiento`/`comisiona`/
  `componentes: list[ComponenteComisionResponse]`.
- **Frontend:** pestaña nueva "Tramos de cumplimiento" en `CommissionConfigPanel.tsx` (editor de tramos, mismo
  patrón que Cobranza). `DataTable.tsx` gana `renderExpanded` opcional (fila expandible), usado por
  `CommissionSimulationPanel.tsx` para mostrar la tubería completa paso a paso (`DesgloseComision`), columnas
  nuevas `% cumplimiento`/`Tramo`, y corrección de presentación de H-1 (headerTitle explícito sobre qué incluye
  el numerador de "% comisión / margen de venta", más un indicador visual cuando cobranza+contado superan el 50%
  de la base).
- **Corrección colateral real, no anticipada:** `app/database/base.py` (la lista de modelos que Alembic usa para
  `Base.metadata`, insumo de `--autogenerate` y del test de guardia `test_alembic_schema_sync.py`) no importaba
  `ComisionTramoCobranza`/`ComisionFormula`/`ComisionFormulaComponente` desde antes de esta sesión (brecha
  preexistente de la auditoría 44, nunca cerrada) — corregido junto con el registro de `ComisionTramoCumplimiento`,
  ya que de lo contrario mi propio modelo nuevo tendría el mismo defecto.

### 6.2 Reglas de negocio nuevas

RN-CM15 y RN-CM16 consolidadas en `docs/auditoria/02_reglas_negocio_validadas.md` §18.

### 6.3 Incidente real durante la aplicación de la migración (documentado, no solo "funcionó a la primera")

Al aplicar `0012` contra el entorno real, el contenedor `bi_backend` entró en un ciclo de reinicio silencioso
(exit code 1 sin traceback en los logs, porque `entrypoint.sh` siempre ejecuta `apply_migrations.py` ANTES de
cualquier comando, incluso overrides de diagnóstico vía `docker run --entrypoint`). Aislado con
`docker run --entrypoint python` (bypass real del entrypoint) más `except BaseException` explícito, se
identificaron y corrigieron DOS defectos reales encadenados, ninguno relacionado con lógica de negocio:

1. **`etiqueta VARCHAR(30)` insuficiente:** la semilla incluye `"Sin comisión (< 90% de la meta)"` (31 caracteres,
   con tilde) — columna ampliada a `VARCHAR(50)` en el modelo, la migración y el schema Pydantic (headroom para
   etiquetas personalizadas de gerencia).
2. **Revision ID de 33 caracteres:** `alembic_version.version_num` es `VARCHAR(32)` por defecto (Alembic estándar)
   — `'0012_comision_tramos_cumplimiento'` (33) lo excedía por 1 carácter, fallando silenciosamente en el
   `UPDATE` final de la transacción de migración (el `CREATE TABLE`/`INSERT` de la semilla sí se completaban,
   pero el commit completo de la migración fallaba, dejando la tabla creada pero `alembic_version` sin avanzar —
   de ahí el reintento infinito en cada arranque). Migración renombrada a `0012_tramos_cumplimiento` (25
   caracteres).

Verificado con `SELECT` reales tras la corrección: `public.comision_tramos_cumplimiento` con 5 filas correctas
(tildes verificadas con `psql`, un mojibake visual observado en un pipe de terminal de Windows era solo de
presentación, no de los datos almacenados); `alembic_version = '0012_tramos_cumplimiento'`; `bi_backend` con
arranque limpio y `health=healthy` tras el fix, sin más reinicios.

### 6.4 Validación extremo a extremo

- `pytest backend/tests/unit` (224 tests: 223 passed, 1 failed — la misma falla preexistente y ajena ya
  documentada en `CLAUDE.md`, `test_classify_vendor_risk_marca_en_riesgo_y_alta_probabilidad`, dependiente de la
  fecha del sistema). Tests nuevos: `resolver_tramo_cumplimiento` (umbral 90%, escala de sobrecumplimiento, tramo
  de último recurso), `calcular_comision_variable_completa` con multiplicador 0 (comisión final $0 pese a bases
  positivas) y con escala >100%, guardas de rendimiento (`get_tramos_cumplimiento_as_tramos.call_count == 1` por
  período en `simular()` y una sola vez en `proyectar_comision_variable()`), y el promedio del desglose en la
  proyección reproduce `comision_variable_proyectada`.
- `pytest backend/tests/integration -m integration -k "commission or metas_actualizacion"` (13 tests: 12 passed,
  1 failed — mismo fallo preexistente ya documentado, vendedor `102` sin suficiente histórico en el EDW real a la
  fecha de esta corrida).
- `tsc --noEmit` / `oxlint` / `npm run build` de producción limpios (advertencias preexistentes ajenas a esta
  sesión, sin relación con los archivos tocados).
- **Prueba en vivo contra `bi_backend` real** (migración aplicada, `COMISION_MODO` en su default `plana` durante
  toda la prueba, `public.comision_liquidaciones` en 0 filas antes y después — sin riesgo de tocar dinero real ni
  dejar artefactos):
  - `GET /gerencia/goals/commission-config/tramos-cumplimiento` devuelve los 5 tramos sembrados.
  - `POST /gerencia/goals/commission-simulation {"anio":2026,"mes":6}` (mes sin meta configurada en este entorno):
    todos los vendedores en `pct_cumplimiento=0.0`/`comisiona=false` (correcto: sin meta persistida, `monto_meta=0`
    → cumplimiento 0 por diseño existente, no un bug de esta auditoría) — el desglose muestra los 7 componentes
    reales con montos coherentes (ej. `VEN01`: `base_lineas_venta=583.09`, `base_cobranza=259.07`,
    `factor_tipo_vendedor=0.7`, `multiplicador_cumplimiento=0.0`, `devoluciones=123.37`, `bonos=25600.00` →
    `comision_final=25476.63`, reproduciendo exactamente el hallazgo H-5 de forma transparente).
  - `POST /gerencia/goals/commission-simulation {"anio":2026,"mes":7}` (mes con metas reales, `PROPUESTA`/
    `APROBADA`): confirma R-3 en vivo — `VEN13` (82,06%) y `VEN24` (73,70%) quedan en `"Sin comisión (< 90% de la
    meta)"`/`multiplicador=0.0`/`comisiona=false`; confirma R-1 en vivo — `VEN17` (118,23%) y `VEN21` (115,19%)
    reciben `"Sobrecumplimiento alto"`/`multiplicador=1.35` (no el 1.2× plano anterior); `VEN03` (92,89%) y `VEN16`
    (90,89%) en `"Meta"`/`1.0×`; `VEN01` (104,49%) en `"Sobrecumplimiento"`/`1.2×` — la escala completa de 5
    tramos se ejercitó con datos reales del EDW.
  - `PUT /gerencia/goals/commission-config/tramos-cumplimiento` con un hueco `[0,50)+[60,∞)` rechazado con `400`;
    con la semilla completa aceptado con `200`, quedó registrado en `GET .../auditoria` (bitácora poblada
    correctamente); tramos restaurados a los valores/etiquetas originales al terminar la prueba.

