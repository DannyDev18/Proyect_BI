# Manual del Módulo Metas y Comisiones

> **Fecha:** 2026-07-14
> **Alcance:** módulo completo tal como está implementado hoy en el repositorio — metas automáticas (estadística IQR) + esquema de comisión plano (vigente) + sistema de **Comisiones Variables** por margen/categoría/crédito/tipo de vendedor (piloto en sombra, opcional).
> **Referencias de origen:** `docs/modulo_metas.md` (especificación original), `docs/features/plan_integracion_comisiones_variables.md` (plan de integración), `docs/auditoria/30_comisiones_variables.md` (auditoría de datos), `docs/auditoria/02_reglas_negocio_validadas.md` §15/§18 (reglas RN-CM1..CM4).

---

## Parte 1 — Manual de Usuario

### 1.1 ¿Qué hace este módulo?

Cada mes, la plataforma:

1. **Genera una meta de venta por vendedor** de forma automática, basada en su historial de los últimos 24 meses (sin inventar números: usa estadística — mediana, recorte de picos, tendencia reciente).
2. **Calcula la comisión devengada** de cada vendedor según cuánto vendió respecto a su meta.
3. Opcionalmente (si gerencia lo activa), calcula en paralelo una **comisión alternativa** que paga según el margen real que dejó cada producto vendido, no solo el monto total — sin afectar el pago real hasta que gerencia decida activarla oficialmente.

Hay dos roles con vistas distintas:

- **Vendedor:** ve su propia meta, su progreso, y su comisión — página `Mi Meta y Comisión` (menú Ventas → Metas).
- **Gerencia / Administrador:** ve y aprueba las metas de todos los vendedores, la liquidación de comisiones del mes, y (nuevo) la configuración y simulación del esquema de Comisiones Variables — página `Metas y Comisiones` (menú Gerencia).

### 1.2 Panel del vendedor

Ruta: `/ventas/metas` → componente "Mi Meta y Comisión".

| Sección | Qué muestra |
|---|---|
| **Meta Asignada / Ventas Actuales / Cumplimiento / Restante** | Tarjetas con la meta del mes en curso, lo vendido hasta hoy (Venta Neta = ventas − devoluciones), y cuánto falta. |
| **Progreso hacia la meta** | Medidor circular con el % de cumplimiento y una alerta si estás en la última semana del mes por debajo del 70%. |
| **Pronóstico de cierre del mes** | Proyección de cuánto venderás al cierre del mes (modelo de ventas `sales_rf`) y la probabilidad de alcanzar la meta. |
| **Meta sugerida (próximo período)** | Adelanto de lo que sería tu meta el mes que viene, con el detalle de cuántos meses de histórico se usaron y cuántos se excluyeron por atípicos. |
| **Comisión** | Tu comisión devengada del mes en curso, el tramo alcanzado (Excelente/Meta/Cerca/Lejos), la tasa aplicada y el bono de sobrecumplimiento si aplica. |
| **"Con el sistema nuevo habrías ganado"** | *Solo aparece si gerencia activó el piloto en sombra.* Compara tu comisión actual contra lo que ganarías con el nuevo esquema por margen — es informativo, **no afecta tu pago** mientras esté en modo sombra. |
| **Productos recomendados para cerrar tu meta** | Sugerencias de productos que sueles vender bien, para ayudarte a llegar a la meta. |
| **Facturas post-meta** | Una vez superado el 100%, lista las facturas que emitiste después de cruzar la meta. |

### 1.3 Panel de gerencia

Ruta: `/gerencia/metas` (o el menú "Metas y Comisiones"). Tiene **3 pestañas**:

#### Pestaña "Operación" (la que ya existía)

- **Consola de Metas:** elige el período, ajusta el "Factor de Presión Comercial" (un slider que empuja las metas al alza o a la baja, ej. +10%) y presiona **"Generar Plan con Inteligencia ML"**. Esto crea o actualiza una propuesta de meta para cada vendedor. Desde la tabla puedes editar el monto y el % de comisión de cada propuesta, y **Aprobar** o **Rechazar**.
- **Comisiones devengadas:** tabla con la Venta Neta real, meta, % de cumplimiento, tramo y comisión de cada vendedor en el período elegido. Si el piloto en sombra está activo, aparece una columna adicional "Comisión (variable · piloto)" con el monto que pagaría el esquema nuevo.
- **Vendedores en riesgo / Alta probabilidad / Recomendaciones por categoría:** paneles de IA que resaltan quién va mal encaminado, quién va a superar la meta, y qué categorías conviene empujar.

#### 1.3.1 Consola de Metas — detalle absoluto de cada input

Componente: `frontend/src/components/goals/GoalsConsole.tsx`. Esta sección describe **cada campo que puede tocarse** en la pantalla, qué significa, qué formato acepta, qué validación tiene en el backend y qué efecto real produce en el sistema.

**No existe filtro de sucursal ni de vendedor individual en esta pantalla.** La tabla siempre lista a todos los vendedores del período elegido, porque la meta se calcula a grano vendedor, no vendedor×sucursal (regla de negocio 10 — un vendedor puede transaccionar en varias sucursales, ver `docs/auditoria/19_grano_vendedor_metas_y_meta_futura_razonable.md`).

---

**1. Select "Año / Mes de Planificación"**

- **Qué es:** el período (año, mes) sobre el que se va a generar, revisar o editar metas.
- **Campo técnico:** `period.anio`, `period.mes` (estado local del componente).
- **De dónde salen las opciones:** `GET /gerencia/goals/periods` — solo devuelve períodos donde existen datos (no un rango arbitrario infinito).
- **Efecto:** cambia qué se consulta en `useGoalsTracking(anio, mes)` — es decir, toda la tabla de abajo (metas, comisiones, estados) se recarga para el período elegido. No dispara ningún cálculo por sí solo, solo cambia el "de qué mes estoy hablando".
- **Nota práctica:** normalmente se usa para planificar el **mes siguiente** al actual (generar la meta de agosto durante julio), pero técnicamente permite navegar a cualquier período con datos, incluyendo meses ya cerrados (para revisión histórica).

---

**2. Slider "Factor de Presión Comercial (+X%)"**

- **Qué es:** un ajuste manual y discrecional de gerencia sobre el resultado que ya calculó el motor estadístico (IQR) — permite "empujar" todas las metas propuestas al alza (nunca a la baja: el rango es 0–25%, no admite negativos).
- **Campo técnico:** `pressure` (estado del slider, entero) → se traduce a `factor = 1 + pressure/100` → se envía como el query param `pressure_factor` (tipo `float`) a `POST /gerencia/goals/generate`.
- **Rango en la UI:** `<input type="range" min="0" max="25">` — de 0% a 25%, en pasos de 1.
- **Validación en el servidor:** **no tiene límite explícito en el backend** (`goals.py:75`) — el límite de 0–25 es solo una restricción visual del slider en el frontend. Si se llamara al endpoint directamente con un valor fuera de ese rango, el backend lo aceptaría igual.
- **Efecto real:** al presionar "Generar", cada meta calculada por el motor IQR (ver Parte 2, fórmula) se multiplica por este factor **antes** de guardarse como propuesta. Ej.: si el motor calculó $10,000 para un vendedor y el slider está en +10%, la propuesta sale en $11,000.
- **Efecto visual adicional:** mientras una propuesta esté en estado `PROPUESTA` (no aprobada ni rechazada todavía), mover el slider recalcula en vivo el monto mostrado en pantalla, para que gerencia vea el impacto antes de confiar el cambio al servidor.
- **Cuándo usarlo:** típicamente en campañas, fin de año fiscal, o cuando gerencia tiene información cualitativa (ej. una promoción agresiva) que el histórico de ventas todavía no refleja y que el motor estadístico no puede anticipar por sí solo.

---

**3. Botón "Generar Plan con Inteligencia ML"**

- **Qué es:** dispara el cálculo real de propuestas de meta para **todos** los vendedores con actividad reciente en el período elegido.
- **Acción técnica:** `generateGoals(anio, mes, factor)` → `POST /gerencia/goals/generate?pressure_factor=...`.
- **Qué pasa del lado del servidor** (ver Parte 2, §2.3 de la fórmula IQR y §1.3.1 más abajo de este documento): por cada vendedor, se corre el motor IQR sobre 24 meses de histórico, se aplica el ajuste por tipo de vendedor (externo/interno/nuevo), y **por último** se aplica este `pressure_factor`. El resultado se guarda (o actualiza si ya existía) en `public.metas_comerciales_operativas` con estado `PROPUESTA`.
- **Idempotencia:** volver a presionar "Generar" para el mismo período **recalcula y sobrescribe** las propuestas que sigan en estado `PROPUESTA` — no crea duplicados. Las que ya fueron `APROBADA` o `RECHAZADA` no se ven afectadas por una nueva generación (se preservan las decisiones ya tomadas).
- **Efecto secundario:** al terminar, se dispara una notificación interna a gerencia (ver módulo de Notificaciones) avisando que las metas del período quedaron generadas.

---

**4. Input de texto "Meta Propuesta ($)" (por fila de la tabla)**

- **Qué es:** permite a gerencia sobrescribir manualmente el monto de meta calculado por el sistema para un vendedor específico, antes de aprobarlo.
- **Campo técnico:** `proposals[i].monto_meta`.
- **Formato de entrada:** texto libre formateado como moneda en pantalla; se limpia con una expresión regular (`[^0-9.-]+`) y se convierte con `parseFloat` antes de enviarse — es decir, puedes escribir `$12,500.00` y el sistema lo interpreta como `12500.00`.
- **Persistencia:** el cambio es **solo local** (en memoria del navegador) hasta que se presiona "Aprobar" o "Rechazar" en esa fila — en ese momento se envía como `monto_meta` dentro del payload `PUT /gerencia/goals/{goal_id}/review`.
- **Validación del backend:** `GoalReviewPayload.monto_meta` — tipo `float`, `ge=0.0` (no admite montos negativos; sí admite $0, por ejemplo para anular efectivamente una meta sin borrarla).
- **Cuándo se usa:** cuando gerencia tiene contexto puntual sobre un vendedor (ej. licencia médica programada, cambio reciente de cartera) que el motor estadístico no puede conocer, y el "Factor de Presión Comercial" (que es global, afecta a todos) no es la herramienta correcta para un caso individual.

---

**5. Input numérico "Comisión (%)" (por fila de la tabla)**

- **Qué es:** el porcentaje base de comisión que se le asignará a ese vendedor sobre el cumplimiento de su meta (esquema plano, regla de negocio 10 — no confundir con las tasas del esquema variable por margen, que se configuran en la pestaña "Comisiones Variables · Config").
- **Campo técnico:** `proposals[i].comision_base_pct`.
- **Formato:** `<input type="number">` sin `min`/`max` fijados en el HTML del componente.
- **Validación del backend:** `GoalReviewPayload.comision_base_pct` — `ge=0.0, le=100.0` (el servidor sí rechaza valores fuera de 0–100% aunque el input del navegador no lo impida visualmente).
- **Persistencia:** igual que el monto de meta, viaja en el mismo `PUT /gerencia/goals/{goal_id}/review` al aprobar o rechazar.
- **Efecto:** esta tasa es la que después usa `commission_engine.calcular_comision` (esquema plano) para liquidar la comisión real del vendedor una vez que se conoce su Venta Neta del mes.

---

**6. Botones "Aprobar" / "Rechazar" (por fila)**

- **Qué son:** la decisión final de gerencia sobre cada propuesta de meta individual.
- **Campo técnico:** ambos llaman a `PUT /gerencia/goals/{goal_id}/review`, cambiando el campo `estado` a `APROBADA` o `RECHAZADA` respectivamente. El backend valida `estado` contra el patrón `^(APROBADA|RECHAZADA)$` — ningún otro valor es aceptado desde este endpoint.
- **Efecto de "Aprobar":** la meta queda oficial para ese vendedor y ese período — es la que se usará para calcular su % de cumplimiento y su comisión real durante el mes.
- **Efecto de "Rechazar":** la meta queda descartada; el vendedor no tiene una meta oficial vigente para ese período hasta que se genere/apruebe una nueva propuesta.
- **Nota:** aprobar o rechazar envía en el mismo request lo que esté escrito en ese momento en los inputs de monto y comisión (puntos 4 y 5) — es decir, "Aprobar" no solo cambia el estado, también persiste cualquier edición manual pendiente en esa fila.

---

**7. Botón "Info" junto al nombre del vendedor → Drawer "Cómo se calculó la meta sugerida"**

- **Qué es:** una ventana de detalle, **solo lectura** (ningún campo aquí es editable), que explica de forma transparente el cálculo estadístico detrás de la cifra propuesta para ese vendedor.
- **Campo técnico:** dispara `GET /gerencia/goals/meta-sugerida?vendedor_origen=...`.
- **Campos que muestra, uno por uno:**

  | Campo | Qué significa |
  |---|---|
  | `meta_sugerida_estadistica` | El monto que el motor IQR calculó **antes** de aplicar el ajuste por tipo de vendedor y el Factor de Presión Comercial — es decir, la cifra "pura" del histórico. |
  | `metodo_estadistico` | Nombre del método usado (identifica el motor IQR, para trazabilidad si en el futuro convive con otro método). |
  | `meses_historico_usados` | Cuántos meses de venta real del vendedor entraron al cálculo (hasta 24, mínimo 12 para que el sistema considere el histórico suficiente). |
  | `valores_atipicos_excluidos` | Cuántos meses fueron recortados por el filtro IQR (Tukey, banda `[Q1-1.5·IQR, Q3+1.5·IQR]`) por ser meses anormalmente altos o bajos frente al resto. |
  | `meses_atipicos_ml_detectados` | Cuántos meses fueron marcados como estadísticamente raros por el detector de anomalías (`IsolationForest`) — a diferencia del punto anterior, estos **no se excluyen**, solo pesan menos (50%) en el promedio. |
  | `componente_estacional` | El promedio de lo que este vendedor vendió en el **mismo mes calendario** de años anteriores (ej. si se está calculando julio, el promedio de julios pasados). `null` si no hay suficiente historial para calcularlo. |
  | `componente_tendencia` | El promedio ponderado de los últimos 4 meses reales de venta — captura hacia dónde va el vendedor **ahora**, no su patrón estacional. |
  | `factor_tendencia_aplicado` | El multiplicador de crecimiento/caída aplicado (acotado siempre entre 0.85 y 1.20) — mayor a 1.0 significa que la tendencia reciente es de crecimiento, menor a 1.0 que está cayendo. |
  | `coeficiente_variacion` | Qué tan volátil/errático es el histórico de venta del vendedor (desviación estándar ÷ promedio). Un valor alto explica por qué el `factor_tendencia_aplicado` puede estar cerca de 1.0 aunque la tendencia cruda sea más pronunciada (el sistema se vuelve conservador cuando el vendedor es errático). |

- **Por qué importa este drawer:** es la herramienta de transparencia para que un vendedor o gerencia entienda **por qué** salió ese número y no otro — evita que la meta se perciba como una "caja negra". Nota: lo que muestra es la meta *antes* del ajuste por tipo de vendedor (externo/interno/nuevo) y *antes* del Factor de Presión Comercial del slider — esos dos ajustes se aplican después, solo al presionar "Generar".

#### Pestaña "Comisiones Variables · Config" (nueva)

Aquí gerencia configura el esquema de comisión por margen **sin necesidad de programar**. Tiene 3 sub-pestañas:

1. **Matriz de categorías:** define, por código de categoría de producto (ej. `BAT`, `REP`, o `*` como comodín), qué grupo le corresponde (A/B/C/S/X), qué tasa de comisión aplica, si se calcula sobre el **margen** o sobre el **valor** de venta, y un factor estratégico temporal (ej. 1.3x para empujar liquidación de inventario). Cada regla que guardas queda con fecha de vigencia — no se pierde el historial.
2. **Factores de crédito:** tabla editable de cuánto se reduce la comisión según el plazo de pago otorgado al cliente (ej. contado = factor 1.0, 30 días = factor 0.85). Puedes agregar o quitar tramos y guardar todo de una vez.
3. **Tipo de vendedor:** marca cada vendedor como **externo** (factor 1.0, el de referencia) o **interno** (factor 0.70 por defecto, editable) — refleja que un vendedor externo tiene mayor costo de soporte para la empresa. Un vendedor sin configurar se trata automáticamente como externo, nunca se le penaliza por omisión.

> ⚠️ Nota de datos reales (ver auditoría 30): el catálogo de productos no tiene nombres de categoría cargados desde SAP, así que las categorías se identifican por **código** (ej. `BAT` = baterías), no por nombre. Y el ajuste por plazo de crédito hoy solo tiene información real para **contado** y **30 días** — los demás tramos (45/60/90 días) están disponibles para configurar pero sin historial de ventas real que los respalde todavía.

#### 1.3.2 Comisiones Variables · Config — detalle absoluto de cada input

Componente: `frontend/src/components/goals/CommissionConfigPanel.tsx`. Todo lo que se guarda aquí alimenta al motor puro `commission_engine.calcular_comision_variable` (ver Parte 2, §2.3, la fórmula completa) — **nada de esto paga dinero real mientras `COMISION_MODO=plana`** (el modo por defecto); solo entra en vigor real en `sombra` (se calcula pero no se paga) o `variable` (pasa a ser lo oficial).

**Sub-pestaña "Matriz de categorías"** — define cuánto se comisiona por tipo de producto. Payload: `MatrizCategoriaPayload`.

| Input | Campo técnico | Tipo / rango | Qué significa | Validación backend |
|---|---|---|---|---|
| Autocomplete "Clase (código)" | `clase` | string, 1–5 caracteres, se normaliza a mayúsculas; admite `*` como comodín | El código de clase de producto tal como existe en `dim_producto.clase` (ej. `BAT` = baterías). El comodín `*` crea una regla "para todo lo que no tenga una regla más específica" — es el fallback universal. | `min_length=1, max_length=5` |
| Input "Subclase (opcional)" | `subclase` | string, ≤5 caracteres; se deshabilita al editar una regla existente | Refina la clase a un nivel más específico (ej. clase `BAT`, subclase `BAT-AUTO`). Dejarlo vacío hace que la regla aplique a toda la clase sin distinguir subclase. | `max_length=5` |
| Select "Grupo" | `grupo` | enum: `A` \| `B` \| `C` \| `S` \| `X` | La categoría comercial a la que se asigna esta clase/subclase — determina cómo se trata la línea en el motor (`S`=servicio, tasa sobre valor; `X`=línea excluida/cortesía, tasa 0%; `A/B/C` son categorías normales de margen, cada una con su propia tasa). | Pattern regex del enum |
| Input número "Tasa (%)" | `tasa_pct` | `step=0.1`, `min=0`, `max=100` | El porcentaje de comisión que se paga sobre la base elegida (margen o valor) para esta clase/subclase. Ej.: `tasa_pct=8` sobre una línea con `margen_bruto=$1,000` en base `margen` da `$80` de comisión antes de los demás factores. | `ge=0, le=100` |
| Select "Base" | `base` | `margen` \| `valor` | Sobre qué monto de la línea se aplica la tasa: `margen` = utilidad bruta real (precio de venta − costo), `valor` = el monto total de venta de la línea, sin descontar costo. Los servicios (grupo `S`) casi siempre usan `valor` porque no tienen costo de inventario que produzca un margen calculable. | — |
| Input número "Factor estratégico" | `factor_estrategico` | `step=0.05`, `min=0.5`, `max=1.5` | Un multiplicador temporal que gerencia puede subir (ej. `1.3`) para incentivar más la venta de una categoría específica (ej. liquidar inventario de temporada), o bajar (ej. `0.8`) para desincentivarla sin tocar la tasa base. Se multiplica directo en la fórmula del motor. | `ge=0.5, le=1.5` |
| Botón "Guardar regla" / "Guardar cambios" | — | acción → `POST commission-config/matriz` | Crea o actualiza la regla. **Nunca sobrescribe una fila vigente en el sitio:** cierra la vigencia de la regla anterior (`vigente_hasta`) e inserta una nueva con `vigente_desde=hoy` — así el historial de qué tasa aplicaba en qué fecha queda íntegro para auditoría y para que la simulación retroactiva use la tasa correcta de cada período pasado. | — |
| Botón "Editar" (por fila) | — | acción, UI | Carga los valores de una regla existente en el formulario para modificarla (bloquea `subclase` para no partir accidentalmente el histórico de una regla activa). | — |

**Orden de resolución de reglas** (importante para entender qué gana): el motor busca primero `(clase, subclase)` exacto → si no hay, `(clase, NULL)` → si no hay, el comodín `('*', NULL)`. Una regla más específica siempre gana sobre una genérica.

---

**Sub-pestaña "Factores de crédito"** — cuánto se penaliza la comisión según el plazo de pago otorgado al cliente. Es una tabla editable en bloque (todos los tramos se guardan juntos). Payload: `FactorCreditoPayload[]`.

| Input | Campo técnico | Tipo / rango | Qué significa | Validación backend |
|---|---|---|---|---|
| Input número "Desde (días)" | `dias_desde` | int, `min=0` | El inicio del tramo de plazo de crédito (ej. `0` para contado, `31` para el tramo que empieza después de 30 días). | `ge=0` |
| Input número "Hasta (días)" | `dias_hasta` | int, nullable, `min=0` | El fin del tramo. Dejarlo vacío significa "sin tope" — el último tramo abierto (ej. 90+ días) normalmente se deja así. | `ge=0` (si se informa) |
| Input número "Factor" | `factor` | `step=0.01`, `min=0`, `max=2.0` | El multiplicador que reduce (o aumenta) la comisión de esa línea según el plazo de crédito. Ej. contado = `1.0` (sin penalización), 30 días = `0.85` (15% menos de comisión) — refleja que vender a crédito le cuesta más financieramente a la empresa que vender de contado. Tope ampliado a `2.0` (antes `1.5`) para permitir premiar, no solo penalizar. | `ge=0, le=2.0` |
| Botón "Agregar tramo" | — | acción, UI | Añade una fila vacía a la tabla para definir un nuevo rango de días. | — |
| Botón "Quitar" (por fila) | — | acción, UI | Elimina un tramo de la tabla **en memoria** — no se persiste hasta "Guardar matriz de crédito". | — |
| Botón "Guardar matriz de crédito" | — | acción → `PUT commission-config/credito` | Envía el arreglo completo de tramos y **reemplaza toda la configuración de crédito de una sola vez** (a diferencia de la matriz de categorías, aquí no se guarda tramo por tramo — es un PUT de todo el conjunto). | — |

> ⚠️ Cobertura real de datos: solo hay tráfico histórico real para los tramos de **0 días** (contado) y **30 días**. Los tramos de 45/60/90 días se pueden configurar pero no tienen historial de ventas que los respalde en el EDW actual (auditoría 30, H4).

> **`pct_al_facturar` eliminado (migración `0010_eliminar_pct_al_facturar`):** este campo reservado ("% al facturar") nunca llegó a usarse por el motor real -- la necesidad que intentaba cubrir (repartir la comisión entre el momento de facturar y el momento de cobrar) ya la resuelve, con datos reales, la Comisión sobre Cobros (auditoría 44, §18 RN-CM14). Se retiró de la tabla/API/base de datos en vez de mantenerlo como placeholder muerto.

---

**Sub-pestaña "Tipo de vendedor"** — clasifica a cada vendedor como externo o interno, con su propio factor de comisión. Payload: `ConfigVendedorPayload`.

| Input | Campo técnico | Tipo / rango | Qué significa | Validación backend |
|---|---|---|---|---|
| Autocomplete "Código de vendedor" | `vendedorOrigen` / `id_vendedor_origen` | obligatorio, string (código SAP del vendedor) | Identifica a qué vendedor aplica esta configuración. | Requerido |
| Select "Tipo" | `tipo` | `externo` \| `interno` | **Externo:** vendedor de campo/comisionista tradicional — factor de referencia `1.0`. **Interno:** vendedor de mostrador/oficina, típicamente con salario base más alto y menor costo variable esperado — factor sugerido `0.70`. Al cambiar este select, la UI **autosugiere** el factor típico (1.0 o 0.70) en el campo siguiente, pero sigue siendo editable. | Enum |
| Input número "Factor de comisión" | `factor_tipo` | `step=0.05`, `min=0`, `max=1.5` | El multiplicador final que se aplica sobre TODA la comisión variable calculada del vendedor (después de sumar todas sus líneas), reflejando su costo de estructura para la empresa. Es editable manualmente incluso después de la autosugerencia — por ejemplo, un vendedor interno con desempeño excepcional podría configurarse con `0.85` en vez del `0.70` por defecto. | `ge=0, le=1.5` |
| Columna "Fecha de ingreso" (`fecha_ingreso`) | `fecha_ingreso` | fecha, **no editable en esta UI** | Solo se muestra en la tabla, no tiene input propio en el formulario — se usa internamente para la regla de "vendedor nuevo" (ver Parte 2, §2.4: `COMISION_VENDEDOR_NUEVO_MESES`/`_FACTOR`, que afecta el cálculo de **metas**, no de comisión variable). Al guardar tipo/factor desde este formulario, el valor existente de `fecha_ingreso` se reenvía tal cual, sin poder cambiarlo aquí. | — |
| Botón "Guardar vendedor" | — | acción → `PUT commission-config/vendedores/{vendedor_origen}` | Crea o actualiza la fila de configuración de ese vendedor específico. | — |

> Vendedor sin fila configurada aquí: el sistema lo trata automáticamente como **externo** con factor `1.0` (`COMISION_FACTOR_EXTERNO_DEFAULT`) — nunca se le penaliza por omisión, es un default neutral, no punitivo.

---

**Sub-pestaña "Bitácora de cambios"** — solo lectura, sin inputs. Muestra el historial de auditoría de todo lo configurado en las tres sub-pestañas anteriores: quién cambió qué, cuándo, y el detalle del cambio (tabla `public.comision_config_auditoria`, append-only — nunca se edita ni se borra un registro de esta bitácora).

#### 1.3.3 Comisiones Variables · Simulación (Proyección) — detalle absoluto de cada input

> **Rediseño 2026-07-27:** este panel dejó de ser una comparación retroactiva "esquema plano vs. variable" de meses ya cerrados. Ahora es una **proyección hacia adelante**, exclusivamente del esquema variable: toma los últimos 3 o 6 meses YA CERRADOS de cada vendedor como base histórica y estima cuánto pagaría la matriz **configurada hoy** el próximo mes calendario. La comparación retroactiva contra el esquema plano sigue existiendo, pero solo internamente — la usa la alerta de divergencia del piloto en sombra (`NotificationService._generar_divergencia_comisiones`), no este panel.

Componente: `frontend/src/components/goals/CommissionSimulationPanel.tsx`. Este panel **no escribe nada en la configuración** — es de solo consulta, corre el motor sobre datos históricos reales del EDW para estimar el próximo mes, sin comprometerse a nada.

| Input | Campo técnico | Tipo / rango | Qué significa | Efecto |
|---|---|---|---|---|
| Selector "Meses de historial" | `meses_historico` | opciones fijas: `3` / `6` (el backend rechaza cualquier otro valor con 400) | Cuántos meses YA CERRADOS (excluye el mes en curso, incompleto) se usan como base de la proyección — el mismo tipo de ventana de tendencia que usa el motor IQR de metas, no un rango arbitrario. | Determina cuántos meses hacia atrás consulta `CommissionSimulationService.proyectar_comision_variable`. |
| Botón "Proyectar" | — | acción → `POST /gerencia/goals/commission-simulation` con `{"meses_historico": 3\|6}` | Para cada vendedor con ventas en la ventana, calcula la comisión variable de cada uno de esos meses históricos con la matriz/crédito/tipo de vendedor **vigentes HOY** (no los vigentes en cada mes histórico — a propósito: la pregunta que responde es "si mantengo la config actual, ¿cuánto pagaría con el patrón de venta reciente de cada vendedor?"), y promedia esos meses para proyectar el mes siguiente al actual. | No persiste nada — es un cálculo transitorio, se recalcula cada vez que se presiona el botón. |

**Supuestos explícitos de la proyección** (para que gerencia no la lea como una promesa exacta):
- **Cumplimiento neutro:** cada mes histórico se calcula con `venta_real == monto_meta`, es decir, tramo **Meta** (multiplicador 1.0×, ni bono de Excelente ni castigo de Cerca/Lejos) — porque la meta real del período proyectado todavía no existe (la genera la Consola de Metas, un motor distinto). La proyección aísla la fórmula de margen/categoría/crédito/tipo de vendedor, no intenta adivinar si el vendedor cumplirá una meta futura.
- **Sin bonos ni devoluciones estimadas:** son eventos puntuales del mes ya cerrado (venta cruzada aceptada, cliente nuevo, cobranza sana, devoluciones reales), no un patrón proyectable con la misma base estadística que la venta — se omiten del cálculo proyectado a propósito, en vez de inventar un promedio poco confiable.

**Qué muestra la tabla de resultado** (solo lectura, sin inputs):

| Columna | Campo técnico | Qué significa |
|---|---|---|
| Código vendedor | `vendedor_origen` | El código SAP del vendedor (`codven`). |
| Vendedor | `nombre_vendedor` | Nombre real, resuelto en lote desde el catálogo (`CatalogRepository.get_vendedores_info`) — nunca una consulta por fila. |
| Período proyectado | `periodo_proyectado` | El mes calendario siguiente al actual, formato `YYYY-MM` (ej. si hoy es julio 2026, `2026-08`). Igual para todas las filas de una misma corrida. |
| Venta neta promedio | `venta_neta_promedio` | Promedio mensual de Venta Neta del vendedor en la ventana histórica elegida — la base de comparación, no entra directo en la fórmula de comisión (que trabaja a nivel de línea). |
| Margen bruto promedio | `margen_bruto_promedio` | Promedio mensual del margen bruto real de las líneas de venta del vendedor en la ventana — la base "margen" que usa la mayoría de las reglas de la matriz (§1.3.2). **Excluye las líneas de clases marcadas como grupo `X`** (ej. `Z-999` "chatarra", ver `docs/features/matriz_categorias_comision_variable.md` §4): esas líneas ya no aportan nada a la comisión, y su costo suele venir mal registrado en el ERP (márgenes negativos absurdos que antes distorsionaban esta columna y podían volver negativo el denominador de "% comisión/margen"). |
| Comisión variable proyectada | `comision_variable_proyectada` | El resultado: promedio de la comisión variable que esos mismos meses históricos habrían generado con la matriz de HOY. Es la estimación de lo que pagaría el próximo mes si el patrón de venta se mantiene. |
| % comisión / margen | `tasa_efectiva_pct` | `comisión proyectada ÷ margen bruto promedio × 100` — la tasa **efectiva** real (mezcla de todas las categorías que vende ese vendedor), distinta de cualquier tasa nominal individual de la matriz. |

El resumen (tarjetas KPI arriba de la tabla) agrega estos mismos valores a nivel de todos los vendedores: comisión variable total proyectada, margen bruto promedio total, % comisión/margen global y cantidad de vendedores proyectados.

**Por qué existe este panel:** le permite a gerencia ver, con datos reales del EDW y la configuración ya cargada en 1.3.2, cuánto costaría el esquema variable el próximo mes — sin tener que esperar a que ese mes cierre para saberlo, y sin mezclar esa proyección con el esquema plano (que es una decisión de negocio distinta, ya cubierta por la alerta de divergencia del piloto en sombra).

### 1.4 ¿Cómo se activa el esquema nuevo de verdad?

El sistema tiene 3 modos, controlados por una sola variable de configuración (`COMISION_MODO`), que solo puede cambiar un desarrollador/administrador de infraestructura:

| Modo | Qué pasa |
|---|---|
| **`plana`** (el de siempre, activo por defecto) | Solo se calcula y paga el esquema plano de tasa por tramos. Nada nuevo es visible. |
| **`sombra`** | Se calculan **ambos** esquemas. El pago real sigue siendo el plano, pero tanto vendedores como gerencia ven la comparación ("lo que habrías ganado con el nuevo sistema"). Es el modo recomendado para el piloto de 2–3 meses. |
| **`variable`** | El esquema por margen pasa a ser el oficial. El plano se sigue calculando solo como referencia. |

**Volver atrás es instantáneo:** cambiar `COMISION_MODO` de vuelta a `plana` restaura el comportamiento anterior sin perder nada — cada mes calculado en modo sombra queda guardado como un registro histórico ("liquidación congelada"), así que nunca se pierde el rastro de lo que se calculó.

---

## Parte 2 — Manual del Desarrollador

### 2.1 Arquitectura general

```
Frontend (React)                Backend (FastAPI)                         PostgreSQL (edw + public)
─────────────────                ──────────────────                        ──────────────────────
DashboardMetas.tsx        →      goals.py (router)             →           edw.fact_ventas_detalle
 ├─ GoalsConsole                  ├─ GoalsService                          edw.fact_devoluciones
 ├─ CommissionTracker             ├─ CommissionService                     edw.dim_producto
 ├─ CommissionConfigPanel         ├─ CommissionSimulationService           edw.dim_formapago
 └─ CommissionSimulationPanel     ├─ CommissionConfigService                public.metas_comerciales_operativas
                                  ├─ GoalMLService                          public.comision_matriz_categorias
VendorGoalDashboard.tsx   →      sales.py (router, /goals/mi-comision)     public.comision_factores_credito
                                  └─ commission_engine.py (motor puro)      public.comision_config_vendedor
                                                                             public.comision_liquidaciones
```

El módulo tiene **dos capas de comisión que conviven**:

1. **Esquema plano** (preexistente): `commission_engine.calcular_comision` — tasa sobre Venta Neta total por tramos de cumplimiento (EXCELENTE/META/CERCA/LEJOS). No se tocó.
2. **Esquema variable** (nuevo): `commission_engine.calcular_comision_variable` — función pura adicional, calcula la comisión línea por línea según margen/categoría/crédito/tipo de vendedor.

Ambas conviven porque `settings.COMISION_MODO` decide cuál(es) se ejecuta(n) en cada request.

### 2.2 Archivos clave

| Capa | Archivo | Responsabilidad |
|---|---|---|
| Motor de cálculo (puro, sin BD) | `backend/app/services/commission_engine.py` | `calcular_comision` (plano) y `calcular_comision_variable` (nuevo). Testeado con `backend/tests/unit/test_commission_engine.py` (32 tests, incluye los ejemplos numéricos de la propuesta original como golden tests). |
| Repositorio de datos | `backend/app/repositories/goal_repository.py` | Consultas SQL sobre `edw.*` — venta neta, líneas de venta a grano de línea (`get_commission_lines`), perfil de margen por categoría, líneas sin costo, bonos (cliente nuevo, venta cruzada aceptada), devoluciones. |
| Repositorio de configuración | `backend/app/repositories/commission_config_repository.py` | CRUD de las tablas `public.comision_*` (matriz, crédito, tipo de vendedor) y snapshots de liquidación. Todo con vigencias — nunca se sobreescribe una fila vigente, se cierra y se inserta una nueva. |
| Servicio de liquidación | `backend/app/services/commission_service.py` | `get_commission_tracking` (panel gerencial) y `get_my_commission` (panel vendedor). Según `COMISION_MODO`, calcula uno o ambos esquemas y persiste snapshots. |
| Simulación / proyección | `backend/app/services/commission_simulation_service.py` | Solo lectura del EDW — dos métodos: `simular()` (retroactivo, plano vs. variable, uso interno de la alerta de divergencia del piloto en sombra) y `proyectar_comision_variable()` (hacia adelante, solo variable, el que consume el panel "Simulación" — §1.3.3). Ninguno persiste nada. |
| Configuración expuesta a gerencia | `backend/app/services/commission_config_service.py` | Envuelve `CommissionConfigRepository` para los endpoints CRUD y los reportes de solo lectura (perfil de categorías, líneas sin costo). |
| Ajuste de metas por tipo de vendedor | `backend/app/services/goal_ml_service.py` (`generate_proposals`, `_ajustar_meta_por_tipo`) | Si hay configuración de tipo de vendedor, multiplica la meta base por `COMISION_META_FACTOR_EXTERNO`/`_INTERNO`, o aplica la regla de vendedor nuevo (60% del promedio del equipo durante los primeros meses). |
| Modelos SQLAlchemy | `backend/app/models/commission_config.py` | `ComisionMatrizCategoria`, `ComisionFactorCredito`, `ComisionConfigVendedor`, `ComisionLiquidacion`. Registrados en `backend/app/database/base.py` para que `Base.metadata.create_all` los cree. |
| DDL espejo | `edw/07_public_app_tables.sql` (sección 5) | Mismo esquema para cuando se levanta un volumen Docker nuevo desde cero (no depende de que el backend arranque primero). |
| Endpoints | `backend/app/api/routes/goals.py` (gerencia) y `backend/app/api/routes/sales.py` (vendedor, `/goals/mi-comision`) | Ver tabla de endpoints abajo. |
| Inyección de dependencias | `backend/app/api/dependencies.py` | Fábricas `get_commission_config_repository`, `get_commission_service`, `get_commission_simulation_service`, `get_commission_config_service`, y sus `...Dep` para los routers. |
| Configuración | `backend/app/core/config.py` (bloque "Comisiones Variables") | Todos los umbrales/tasas por defecto, sin hardcodes — ver tabla completa abajo. |
| Frontend — tipos | `frontend/src/types/commissionConfig.ts`, campos añadidos en `types/goals.ts` y `types/ventas.ts` | Espejo TS de los schemas Pydantic. |
| Frontend — servicio | `frontend/src/services/commissionConfig.ts` | Llamadas axios a los endpoints nuevos. |
| Frontend — hooks | `frontend/src/hooks/commissionConfig.ts` | React Query: queries + mutations para cada recurso de configuración. |
| Frontend — UI | `frontend/src/components/goals/CommissionConfigPanel.tsx`, `CommissionSimulationPanel.tsx` | Paneles de gerencia (pestañas "Config" y "Simulación" en `DashboardMetas.tsx`). |
| Frontend — comparador vendedor | `frontend/src/components/goals/VendorGoalDashboard.tsx` (tarjeta "Con el sistema nuevo habrías ganado") | Aparece solo si `comision_variable != null` en la respuesta de `mi-comision`. |

### 2.3 La fórmula del motor variable

```
Comisión mes = [ Σ por cada línea de venta:
                   base_comisionable × tasa_categoría × factor_estratégico × factor_crédito ]
               × factor_tipo_vendedor
               × multiplicador_cumplimiento(meta)      ← reutiliza calcular_nivel() del motor plano
               − devoluciones_estimadas
               + bonos (venta cruzada aceptada, cliente nuevo/reactivado, cobranza sana)
               , con piso $0 (nunca negativa)
```

Reglas de clasificación de línea (`_calcular_linea` en `commission_engine.py`):

1. Descuento de la línea > `COMISION_TOPE_DESCUENTO_PCT` y no aprobado → comisión $0, marcada `pendiente_aprobacion`.
2. `|subtotal_neto| < COMISION_UMBRAL_SUBTOTAL_X` (cortesías/redondeos) → grupo **X**, tasa 0%.
3. `es_servicio = true` → grupo **S**, tasa sobre el **valor** de venta (no hay costo de inventario que dé margen).
4. `margen_bruto IS NULL` (línea sin costo en SAP) → tasa mínima (`COMISION_TASA_MINIMA_SIN_COSTO_PCT`) sobre el valor.
5. Resto → se busca la regla más específica en la matriz configurada: `(clase, subclase)` exacto > `(clase, NULL)` > comodín `('*', NULL)`.

El multiplicador de cumplimiento reutiliza los mismos 4 tramos del motor plano (`NivelCumplimiento`), pero con multiplicadores propios y configurables: `COMISION_MULT_EXCELENTE` (default 1.2), 1.0 para META, `COMISION_MULT_CERCA` (default 0.7), `COMISION_PISO_LEJOS` (default 0.0).

### 2.4 Configuración (`backend/app/core/config.py`)

| Variable | Default | Qué controla |
|---|---|---|
| `COMISION_MODO` | `plana` | `plana` \| `sombra` \| `variable` — **el mecanismo de rollback**. |
| `COMISION_TOPE_DESCUENTO_PCT` | `30.0` | Umbral de descuento que bloquea comisión sin aprobación. |
| `COMISION_TASA_MINIMA_SIN_COSTO_PCT` | `5.0` | Tasa aplicada a líneas sin costo registrado (sobre valor). |
| `COMISION_UMBRAL_SUBTOTAL_X` | `1.0` | Bajo este monto, la línea se excluye (grupo X). |
| `COMISION_BONO_CLIENTE_NUEVO` | `50.0` | Monto fijo por cliente nuevo/reactivado. |
| `COMISION_BONO_CROSS_SELL_PCT` | `5.0` | % adicional sobre ventas originadas en sugerencias aceptadas del asistente. |
| `COMISION_BONO_COBRANZA_PCT` / `COMISION_BONO_COBRANZA_DIAS` | `5.0` / `30` | % de bono si el promedio de días de cobro del vendedor es menor al umbral. |
| `COMISION_MESES_CLIENTE_REACTIVADO` | `6` | Ventana de inactividad para contar a un cliente como "nuevo/reactivado". |
| `COMISION_MULT_EXCELENTE` / `COMISION_MULT_CERCA` / `COMISION_PISO_LEJOS` | `1.2` / `0.7` / `0.0` | Multiplicadores del esquema variable por tramo de cumplimiento. |
| `COMISION_FACTOR_EXTERNO_DEFAULT` / `COMISION_FACTOR_INTERNO_DEFAULT` | `1.0` / `0.70` | Factor de comisión por tipo de vendedor cuando no hay fila explícita en `comision_config_vendedor`. |
| `COMISION_META_FACTOR_EXTERNO` / `COMISION_META_FACTOR_INTERNO` | `1.10` / `0.95` | Ajuste de la meta generada según el tipo de vendedor. |
| `COMISION_VENDEDOR_NUEVO_MESES` / `COMISION_VENDEDOR_NUEVO_FACTOR` | `3` / `0.60` | Ventana y factor de la regla de "vendedor nuevo" (meta = % del promedio del equipo). |

### 2.5 Endpoints

Todos bajo `/api/v1`, con `PermissionChecker` de gerencia/administrador salvo donde se indica.

| Endpoint | Método | Rol | Descripción |
|---|---|---|---|
| `/gerencia/goals/tracking` | GET | gerencia | Metas configuradas del período (sin venta real). |
| `/gerencia/goals/periods` | GET | gerencia | Períodos con datos disponibles. |
| `/gerencia/goals/generate` | POST | gerencia | Genera/actualiza propuestas de meta (motor IQR + ajuste por tipo de vendedor). |
| `/gerencia/goals/ai-summary` | GET | gerencia | Vendedores en riesgo/alta probabilidad + recomendaciones por categoría. |
| `/gerencia/goals/commissions` | GET | gerencia | Cumplimiento real + comisión devengada por vendedor; incluye `comision_variable`/`nivel_variable` cuando `COMISION_MODO != plana`. |
| `/gerencia/goals/{goal_id}/review` | PUT | gerencia | Aprobar/rechazar una meta propuesta. |
| `/gerencia/goals/commission-config/matriz` | GET, POST | gerencia | Leer / crear-actualizar reglas de categoría (con vigencia). |
| `/gerencia/goals/commission-config/credito` | GET, PUT | gerencia | Leer / reemplazar la matriz completa de factores de crédito. |
| `/gerencia/goals/commission-config/vendedores` | GET | gerencia | Listar configuración de tipo de vendedor. |
| `/gerencia/goals/commission-config/vendedores/{vendedor_origen}` | PUT | gerencia | Crear/actualizar tipo y factor de un vendedor. |
| `/gerencia/goals/commission-simulation` | POST | gerencia | Proyección de comisión variable del próximo mes, con base en 3 o 6 meses de historial (§1.3.3) — solo esquema variable, sin comparar contra el plano. |
| `/gerencia/goals/commission-analysis/categorias` | GET | gerencia | Perfil de margen agregado por categoría (Fase 1 del plan). |
| `/gerencia/goals/lineas-sin-costo` | GET | gerencia | Reporte de líneas sin costo registrado (salvaguarda 2). |
| `/analytics/ventas/goals/mi-comision` | GET | ventas | Comisión del vendedor autenticado en el mes en curso; incluye `comision_variable`/`desglose_variable` cuando corresponde. |
| `/analytics/ventas/goals/facturas-post-meta` | GET | ventas | Facturas emitidas tras alcanzar el 100% de la meta. |
| `/analytics/ventas/goals/meta-sugerida`, `/goals/forecast-cierre`, `/goals/recomendaciones` | GET | ventas | Meta sugerida, pronóstico de cierre y recomendaciones comerciales (sin cambios). |

### 2.6 Tablas nuevas (`public.*`)

```sql
comision_matriz_categorias   (id, clase, subclase, grupo, tasa_pct, base, factor_estrategico, vigente_desde, vigente_hasta, creado_por)
comision_factores_credito    (id, dias_desde, dias_hasta, factor, pct_al_facturar, vigente_desde, vigente_hasta)
comision_config_vendedor     (id, id_vendedor_origen UNIQUE, tipo, factor_tipo, fecha_ingreso, activo)
comision_liquidaciones       (id, anio, mes, id_vendedor_origen, esquema, modo, comision_total, detalle_json, fecha_calculo,
                               UNIQUE(anio, mes, id_vendedor_origen, esquema, modo))
```

Se crean automáticamente al arrancar el backend (`Base.metadata.create_all`, ver `backend/app/database/base.py`) y también existen como DDL explícito en `edw/07_public_app_tables.sql` para volúmenes Docker nuevos. Ninguna toca el esquema `edw` (regla del proyecto: el DW es solo lectura/append desde el ETL).

`comision_liquidaciones` es el registro de auditoría/transparencia: cada vez que se consulta un período **ya cerrado** (no el mes en curso) en modo sombra o variable, se congela un snapshot con el desglose completo línea por línea en `detalle_json`. El mes en curso nunca se persiste porque cambia con cada consulta.

### 2.7 Cómo extender el módulo

- **Agregar un bono nuevo:** añadir el cálculo en `CommissionService._calcular_bonos` (o crear un método propio si necesita datos nuevos del repositorio), sumar al total que ya se pasa a `calcular_comision_variable(bonos_total=...)`. No tocar el motor puro para lógica que depende de BD.
- **Agregar una salvaguarda nueva:** si depende solo de los datos de la línea (ej. otro tipo de descuento), añadir la regla dentro de `_calcular_linea` en `commission_engine.py` y su test correspondiente en `test_commission_engine.py`. Si depende de datos externos (ej. historial de churn del vendedor), resolverla en el servicio antes de llamar al motor.
- **Cambiar los umbrales de tramos o tasas por defecto:** son env vars (`COMISION_*` en `config.py`) — no requiere despliegue de código, solo reiniciar el backend con la nueva variable.
- **Activar el piloto en producción:** cambiar `COMISION_MODO=sombra` en `.env` (o el mecanismo de configuración del entorno) y reiniciar el contenedor backend (`docker compose up -d backend` para que tome el `.env` nuevo — un `docker restart` simple **no** relee `env_file`).

### 2.8 Testing

```bash
cd backend
python -m pytest tests/unit/test_commission_engine.py -v   # motor puro, 32 tests
python -m pytest tests/unit -v                              # suite completa
```

Los tests del motor variable cubren: clasificación por grupo (A/B/C/S/X), factor de crédito, línea sin costo, descuento excesivo (con y sin aprobación), umbral de exclusión, factor por tipo de vendedor, piso configurable del tramo LEJOS, devoluciones, bonos, y el golden test del ejemplo numérico de `docs/features/propuesta_sistema_comisiones_variables.md` §5.

Para probar contra datos reales del EDW (requiere Docker corriendo):

```bash
docker compose up -d backend
# Login y prueba de endpoints, ver docs/auditoria/30_comisiones_variables.md para ejemplos de consultas SQL de validación
```

### 2.9 Limitaciones conocidas (no son bugs, son brechas de datos documentadas)

| Brecha | Detalle | Dónde está documentada |
|---|---|---|
| Categorías por código, no por nombre | `dim_producto.nombre_clase` está 100% vacío en el catálogo cargado | Auditoría 30, H2 |
| Crédito con cobertura parcial | Solo hay tráfico real en plazos de 0 y 30 días; los demás tramos son configuración sin historial | Auditoría 30, H4 |
| Ventas compartidas externo/interno | No implementado — requiere un CRM de cotizaciones que el EDW no tiene | Plan de integración, brecha B2 |
| Bono de visitas (solo externos) | No implementado — requiere geolocalización/plan de visitas | Plan de integración, brecha B3 |
| Split de pago al facturar/cobrar | Solo el factor de crédito simple está implementado; el split porcentual (ej. 70% al facturar / 30% al cobrar) queda para una fase futura | Plan de integración §3.1, Fase 5 |
