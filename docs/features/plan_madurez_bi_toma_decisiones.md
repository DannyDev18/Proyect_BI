# Plan de madurez BI y soporte a la toma de decisiones

> **Fecha:** 2026-07-27
> **Tipo:** análisis de brechas + propuesta de feature (no hay código escrito todavía).
> **Pregunta que responde:** *lo construido ya es una plataforma de datos con ML; ¿qué falta
> para que sea una plataforma de **Business Intelligence y toma de decisiones**?*
> **Base del análisis:** inspección del repositorio al 2026-07-27 (rutas, servicios,
> repositorios, páginas del frontend, `docs/auditoria/00–38`, `docs/features/*`) y el objetivo
> general declarado en `docs/tesis/memoria_tesis.md`.
> **Estado:** PROPUESTA. Cada eje aprobado sigue el flujo estándar del proyecto: auditoría en
> `docs/auditoria/` con validación `SELECT` **antes** de codificar, reglas nuevas a
> `docs/auditoria/02_reglas_negocio_validadas.md`, umbrales por env var, Producción solo lectura.

---

## 0. Resumen ejecutivo

La plataforma resuelve muy bien la mitad **descendente** del ciclo de BI: extraer, modelar,
predecir y **mostrar**. Lo que falta es casi todo lo de la mitad **ascendente**: que el usuario
pueda *preguntar* lo que nadie anticipó, que confíe en que dos pantallas dicen lo mismo, que la
información lo alcance donde trabaja, y que la decisión tomada quede registrada y medida.

El objetivo general de la tesis exige apoyar decisiones **comerciales, operativas y
financieras**. Hoy las comerciales y operativas están cubiertas; **las financieras no tienen
ninguna pantalla**: los tres hechos del ciclo de caja (`fact_cobros_cxc`, `fact_pagos_cxp`,
`fact_movimientos_caja`) están cargados en el EDW y sin un solo consumidor (el módulo se
construyó y se retiró, auditoría 31).

| # | Brecha | Eje | Impacto sobre "BI y toma de decisiones" | Esfuerzo | Prioridad |
|---|---|---|---|---|---|
| G-01 | KPI falso en producción: `roi_estimado = margen × 1.15` | Confianza | **Crítico** — destruye credibilidad de todo el tablero | Bajo | **1** |
| G-02 | Sin capa semántica: "venta neta" definida en 7 archivos | Confianza | **Crítico** — riesgo de dos pantallas con cifras distintas | Medio | **2** |
| G-03 | Cero análisis ad-hoc / autoservicio | Análisis | **Alto** — no responde el "¿por qué?" no anticipado | Alto | **3** |
| G-04 | Comparación temporal solo en 4 KPIs de Gerencia | Análisis | **Alto** — un número sin contexto no es un indicador | Medio | **4** |
| G-05 | Decisiones financieras sin cobertura (CxC/CxP/caja) | Cobertura | **Alto** — objetivo general incumplido en su tercio financiero | Medio | **5** |
| G-06 | No se registra la decisión ni se mide su impacto | Ciclo | **Alto** — sin línea base no hay ROI demostrable (tesis) | Medio | **6** |
| G-07 | La información no sale de la app (sin correo, sin PDF, sin envío programado) | Difusión | Medio | Bajo | 7 |
| G-08 | ETL manual: frescura del dato no garantizada ni visible | Confiabilidad | **Alto** — un tablero desactualizado se deja de usar | Medio | 8 |
| G-09 | Sin telemetría de adopción de la plataforma | Evidencia | Medio (**alto para la tesis**) | Bajo | 9 |
| G-10 | `DashboardAdmin` con datos mock presentados como reales | Confianza | Alto | Medio | 10 |
| G-11 | Sin what-if / escenarios fuera de comisiones | Análisis | Medio | Alto | 11 |
| G-12 | Dimensiones y hechos incompletos (geografía, snapshot, feriados) | Cobertura | Medio | Alto | 12 |

**Regla de secuencia:** G-01, G-02 y G-10 van primero y no son negociables. Un usuario que
descubre **un** número inventado deja de creer en los otros cuarenta; ninguna funcionalidad
nueva compensa esa pérdida.

---

## 1. Eje Confianza — sin esto, lo demás no se usa

### G-01 · CRÍTICO — El dashboard de Gerencia muestra un ROI inventado

**Evidencia dura** (`backend/app/services/analytics_service.py:42`):

```python
roi_estimado = round(data["margen"] * 1.15, 2)  # Simulación adaptada de ROI de campaña
```

Ese valor se publica en `GPKPIGerencia.roi_estimado`, se pinta como **"Proyección ROI"** con
semáforo positivo/negativo (`analytics_service.py:127`) y ahora además tiene una tendencia
porcentual calculada contra el período anterior (`roi_estimado_tendencia_pct`) — es decir, se le
calcula la variación a una constante multiplicada por el margen. La propia tesis ya lo reconoce
como simulación (`memoria_tesis.md`, §3.3.7: *"`roi_estimado` es una simulación, no ROI real"*),
pero **la advertencia vive en el documento, no en la pantalla que ve el gerente**.

**Acción propuesta (elegir una, decisión de negocio):**

1. **Retirarlo** del contrato y del tablero. Es lo más honesto y lo más barato.
2. **Sustituirlo por un ROI real** definido con la empresa (p. ej. `margen_bruto / costo_de_
   mercadería_vendida` sobre `fact_ventas_detalle`, o retorno sobre inventario promedio cruzando
   con `fact_inventario_snapshot`), documentado como regla de negocio nueva.
3. **Renombrarlo** a lo que realmente es (`margen_proyectado`) con el factor como env var y una
   nota de método visible en la tarjeta.

**Criterio de aceptación:** ningún KPI del sistema es un literal ni un factor arbitrario sin una
regla de negocio validada y referenciada en el código.

**Barrido asociado:** auditar los demás KPIs de las 4 pantallas principales buscando el mismo
patrón (constantes mágicas dentro de un indicador de negocio). Este se encontró leyendo un
archivo; el barrido debe ser sistemático.

---

### G-02 · CRÍTICO — No existe una capa semántica: la misma métrica se define en 7 lugares

"Venta neta" es *la* métrica del negocio (base de metas, comisiones, cumplimiento y KPIs de
Gerencia) y hoy su cálculo aparece en:

```
backend/app/repositories/catalog_repository.py
backend/app/repositories/goal_repository.py
backend/app/services/commission_engine.py
backend/app/services/commission_service.py
backend/app/services/commission_simulation_service.py
backend/app/services/goals_service.py
backend/app/services/goal_ml_service.py
```

Nada garantiza que las 7 apliquen el mismo tratamiento de devoluciones, descuentos, líneas
`desinv='N'`, estado `'P'` y ventana temporal. En BI esto tiene nombre propio: *múltiples
versiones de la verdad*. El síntoma aparece tarde y es letal — un vendedor reclama que su
comisión no cuadra con el tablero de cumplimiento, y no hay forma de decir cuál de los dos está
bien.

**Acción propuesta:**

- **Diccionario de indicadores** (`docs/diccionario_indicadores.md`): una fila por métrica con
  nombre de negocio, fórmula, tablas/columnas del EDW, filtros obligatorios (regla 1 `estado='P'`,
  regla 2 `codemp='01'`, regla 5 `desinv='S'`), grano, dueño del dato y pantallas que la usan.
  Este documento también cierra una brecha real de la tesis (§3.3.7 ya extrajo 11 fórmulas a
  mano; esto las vuelve mantenibles).
- **Un solo punto de cálculo por métrica** en el código: extraer las definiciones a un módulo de
  métricas (`backend/app/services/metricas/`) o a **vistas del EDW** (`edw.v_venta_neta_*`), y
  que los 7 consumidores llamen ahí. Las vistas tienen la ventaja de que el ML entrena contra la
  misma definición que sirve el backend.
- **Test de guardia:** un test que compare la venta neta de un período calculada por cada camino
  (metas, comisiones, analytics) y falle si divergen más allá de un epsilon. Mismo patrón que
  `ml/tests/test_registry.py` o `test_alembic_schema_sync.py`.

**Criterio de aceptación:** existe el diccionario, y para un `(anio, mes, vendedor)` cualquiera
la venta neta del tablero de Gerencia, la de Metas y la de Comisiones son idénticas por test
automatizado.

---

### G-10 · ALTO — `DashboardAdmin` presenta mocks como datos reales

Ya catalogado como **M-02** en `docs/features/plan_mejoras_proyecto.md` (prioridad ALTA) y aún
abierto. Se incluye aquí porque pertenece a la misma familia que G-01: la plataforma muestra
como verdad algo que no lo es. Mientras exista, ningún argumento de "confianza en los datos" es
sostenible ante el tribunal ni ante la empresa.

---

## 2. Eje Análisis — de la pantalla fija a la pregunta propia

### G-03 · ALTO — Cero capacidad de análisis ad-hoc

Las 15 páginas del frontend (`frontend/src/pages/`) son tableros de preguntas **predefinidas**.
La plataforma responde perfectamente las preguntas que el desarrollador anticipó, y **ninguna**
de las que surgen en la reunión: *"esa caída de octubre, ¿fue una sucursal o una categoría?
¿fue un cliente o fueron todos? ¿y el año pasado pasó lo mismo?"*. Esa pregunta encadenada —
no el KPI inicial — es donde el BI genera la decisión.

Lo que hoy existe y sirve de base: filtros globales por sucursal/categoría/fecha, paginación
genérica (`Page[T]`), `Drawer` de detalle (usado en `GoalsConsole` y bodega) y un drill-down
puntual en `PrediccionComprasChart`. Falta convertir eso en un patrón transversal.

**Propuesta escalonada (de menor a mayor esfuerzo):**

| Nivel | Qué es | Esfuerzo | Recomendado |
|---|---|---|---|
| N1 | **Drill-down universal**: todo KPI y toda barra/segmento abre el detalle que lo compone (sucursal → vendedor → cliente → factura), reutilizando `Drawer` + `Page[T]` | Medio | ✅ **Sí, empezar aquí** |
| N2 | **Vistas guardadas y compartidas**: el usuario guarda una combinación de filtros con nombre y la comparte con su rol (tabla `public.vistas_guardadas`) | Bajo | ✅ Sí |
| N3 | **Explorador de métrica**: una pantalla donde se elige métrica (del diccionario G-02) × dimensión × período, sin escribir SQL | Alto | Evaluar tras N1/N2 |
| N4 | Consulta SQL libre para usuarios avanzados | Alto | ❌ No — riesgo de PII (regla 8) y de RLS evadido |

**N4 se descarta explícitamente:** todo el modelo de seguridad del proyecto (RBAC por rol, RLS
por vendedor/sucursal, anonimización en `dim_cliente` con des-anonimización controlada vía
`public.cliente_lookup`) se apoya en que el acceso pasa por la capa de servicios. Una consola
SQL lo perfora entero. Si se quisiera autoservicio real de ese nivel, la vía correcta es un
esquema de vistas ya filtradas por rol, no acceso directo.

**Criterio de aceptación (N1):** desde cualquier KPI de los 4 dashboards se llega en ≤3 clics al
detalle transaccional que lo explica, respetando el RLS del rol.

---

### G-04 · ALTO — Comparación temporal marginal

Un número solo no es un indicador; lo es cuando se compara. Hoy la comparativa existe **solo**
en 4 campos de Gerencia (`ingresos_totales_tendencia_pct`, `margen_utilidad_neta_tendencia_pct`,
`ticket_promedio_tendencia_pct`, `roi_estimado_tendencia_pct` — `backend/app/schemas/analytics.py`),
contra el período anterior de igual longitud, y **solo si se fijan fechas explícitas**. Fuera de
ahí no hay:

- comparación **año contra año** (la relevante en un negocio estacional; el propio proyecto
  documenta ~31% de crecimiento 2018→2026, regla 11),
- acumulado del año a la fecha vs. mismo acumulado del año anterior,
- serie histórica del KPI (solo se ve el valor puntual, no su trayectoria),
- comparación entre pares (sucursal vs. sucursal, vendedor vs. promedio de su sucursal).

**Propuesta:** generalizar el patrón `_tendencia_pct` de `analytics_service.py` a un componente
transversal — un `ComparadorPeriodos` en el backend (modo: período anterior / mismo período año
anterior / promedio de N períodos) aplicado a los KPIs de los 4 roles, y una tarjeta de KPI en
el frontend que muestre siempre valor + variación + microserie. Es la mejora con mejor relación
impacto/esfuerzo de todo el eje.

**Criterio de aceptación:** todo KPI de los 4 dashboards muestra variación contra un período de
referencia seleccionable, y el `None` (sin base comparable) se comunica explícitamente en vez de
mostrar 0%.

---

### G-11 · MEDIO — Sin simulación de escenarios fuera de comisiones

`CommissionSimulationService` es hoy el **único** motor de escenarios del sistema, y es un
excelente precedente: permitió a Gerencia comparar el esquema plano contra el variable con datos
reales antes de decidir. Esa misma capacidad no existe para las decisiones más frecuentes:

- *"si subo la meta 10%, ¿qué comisión pago y qué cumplimiento histórico habría tenido?"*
- *"si cambio el punto de reorden de esta categoría, ¿cuánto capital libero y cuántos quiebres
  arriesgo?"* (los insumos ya existen: `demand_rf`, `BODEGA_*`, snapshot de inventario)
- *"si recupero al 20% de los clientes en churn alto, ¿cuánta venta es?"* (`churn` + histórico)

**Propuesta:** extraer el patrón de `commission_simulation_service.py` a un contrato reutilizable
(parámetros → recálculo sobre histórico real → comparativo base vs. escenario) y aplicarlo
primero a metas (mismo módulo, mismo motor `IQRGoalCalculationEngine`) por ser el de menor
riesgo. Sin modelos ML nuevos.

---

## 3. Eje Cobertura — el tercio financiero del objetivo

### G-05 · ALTO — Las decisiones financieras no tienen ninguna pantalla

El objetivo general de la tesis compromete apoyar decisiones **"comerciales, operativas y
financieras"**. Estado real por eslabón del ciclo:

| Eslabón | Hecho del EDW | ¿Consumido? |
|---|---|---|
| Vender | `fact_ventas_detalle` (~539k) | ✅ Los 4 roles |
| Mover inventario | `fact_movimientos_inventario` (~948k) | ✅ Bodega |
| **Cobrar** | `fact_cobros_cxc` | ❌ **Nadie** |
| **Comprar/pagar** | `fact_pagos_cxp` | ❌ **Nadie** |
| **Caja** | `fact_movimientos_caja` | ❌ **Nadie** |

El módulo de Cartera y Flujo de Caja **se construyó y se retiró** por decisión de producto
(auditoría 31, encabezado explícito: *"el módulo se implementó y se retiró después por decisión
de producto (no por un problema de datos)"*), igual que Compras y Proveedores (auditoría 33). Los
fixes de ETL que salieron de esa validación (duplicación 6x en `fact_pagos_cxp`,
`fact_cobros_cxc.sucursal_sk` sin resolver) **siguen aplicados**, así que el dato está limpio y
validado.

**Esto significa que la brecha más grande de cobertura es la más barata de cerrar del documento:**
la validación de datos ya se hizo, los hallazgos ya se corrigieron y el diseño ya está escrito
(`propuesta_nuevos_modulos_roi.md` §2: DSO, DPO, aging 0-30/31-60/61-90/+90, proyección de
cobros, ranking de cobranza priorizada).

**Decisión requerida del usuario antes de estimar:** ¿por qué se retiró? Si fue alcance de la
tesis, reponerlo es la vía más directa para cumplir el objetivo general. Si fue una objeción de
negocio (p. ej. la empresa no quiere exponer cartera en la plataforma), entonces **el objetivo
general debe ajustarse en el Capítulo I** para no prometer un tercio que el sistema no entrega —
y eso hay que decidirlo antes de la defensa, no después.

---

### G-12 · MEDIO — Huecos conocidos del modelo dimensional

Ya catalogados (auditoría 05, M-05/M-08/M-12), se listan por su efecto directo sobre el análisis:

- `dim_geografia` **vacía** → imposible cualquier análisis territorial (una pregunta natural en
  una empresa multisucursal).
- `fact_inventario_snapshot` con <1% de histórico pre-2026 → no hay evolución de inventario ni
  rotación histórica real; solo fotos recientes.
- `dim_fecha.es_feriado` nunca poblado, con workaround hardcodeado en ML → la estacionalidad de
  feriados no es explicable ni auditable.
- `edw.fact_metas_comerciales` vacía (las metas viven en `public.*`) → el DW no contiene el
  hecho "meta", que es justamente el que se compara contra ventas.

No bloquean el resto del plan, pero cada uno cierra una pregunta de negocio hoy sin respuesta.

---

## 4. Eje Ciclo — de la información a la decisión medida

### G-06 · ALTO — La decisión no se registra y su impacto no se mide

Esta es, conceptualmente, la brecha más importante del documento: **una plataforma de BI que no
sabe si sus recomendaciones se siguieron ni si funcionaron es un visor de datos, no un sistema
de apoyo a la decisión.**

Lo que ya existe y va en la dirección correcta (buen precedente a generalizar):

- `public.recomendaciones_eventos` — telemetría mostrada/aceptada/rechazada de venta cruzada.
- Registro de gestión de Cartera 360 (contactado / recompró / perdido).
- `public.comision_config_auditoria` — bitácora de cambios de configuración.
- `public.ml_model_runs` — trazabilidad de promoción de modelos.

Lo que falta:

- **Línea base antes de encender:** el propio `propuesta_nuevos_modulos_roi.md` §7.5 lo exige
  (*"sin línea base no hay ROI demostrable en la tesis"*) y no se implementó en ningún módulo.
- **Bitácora de decisiones transversal:** una tabla `public.decisiones` donde una alerta o un
  indicador se enlaza con la acción tomada, el responsable, la fecha y el resultado observado a
  N días. Aplica a las 4 familias de recomendación que ya emite el sistema: transferencia
  sugerida, necesidad de compra, cliente en riesgo de fuga, anomalía detectada.
- **Cierre del lazo de las alertas:** hoy las notificaciones se marcan como *leídas*; no se
  marcan como *atendidas* ni se sabe qué pasó después.

**Valor para la tesis:** esta tabla es la fuente natural del Capítulo III para afirmar que la
plataforma *apoya* decisiones — con datos propios, no con literatura. Sin ella, el capítulo solo
puede documentar que las pantallas existen.

---

### G-07 · MEDIO — La información no sale de la aplicación

Verificado en el repositorio:

- **Excel:** existe, pero solo en Bodega (`warehouse_export.py`) y en un endpoint de Gerencia
  (`/gerencia/reportes/dashboard/excel`). Ventas, Metas y Comisiones no exportan nada.
- **PDF:** cero ocurrencias en todo el backend y el frontend.
- **Correo / envío programado:** `notification_service.py` no tiene ningún canal externo (sin
  SMTP, sin webhook). Las notificaciones solo existen dentro de la app, por *polling* de 60s —
  es decir, **solo llegan si el usuario ya está mirando la pantalla**, justo lo contrario de lo
  que una alerta necesita.

Un gerente que necesita el reporte del lunes a las 7:00 en su correo no lo tiene; entra a la
aplicación o no se entera. **Propuesta:** canal de correo en `NotificationService` (patrón de
proveedor configurable por env var), exportación PDF del tablero por rol reutilizando el
contrato tipado `ReporteBodegaResponse` (ya generaliza bien), y envío programado usando la misma
infraestructura de tareas que dispare el ETL de G-08.

---

## 5. Eje Confiabilidad — el requisito silencioso

### G-08 · ALTO — El ETL es manual: nadie garantiza la frescura del dato

`docs/hoja_de_ruta_ejecucion.md` deja el crontab para la "Fase 6" y `CLAUDE.md` lo confirma
(*"hoy la ejecución es manual"*). Consecuencias directas sobre BI:

- Un tablero que puede estar desactualizado y no lo dice se abandona en semanas. Es la causa de
  muerte más común de un proyecto de BI, y no tiene nada que ver con la calidad del modelo.
- El endpoint `/system/provenance` (auditoría 33, RN-G3) fue el paso correcto — expone estado
  real en vez del mock anterior. Falta el paso siguiente: **que la frescura sea un contrato
  visible** ("datos al 27/07/2026 06:00 — última carga OK") en cada pantalla, y una alerta cuando
  se rompe.

**Propuesta:** calendarización real del ETL (M-16 ya prevé el alertado de fallas), sello de
frescura por dominio de datos visible en la UI, y una notificación automática de "carga
atrasada" al rol administrador reutilizando el módulo de notificaciones existente.

**Relacionado, ya catalogado:** sin CI (no existe `.github/`), sin tests de ETL (`etl/tests` no
existe) ni de frontend (0 archivos `*.test.*`), frente a 33 archivos de test en el backend. M-09.

---

### G-09 · MEDIO (alto para la tesis) — No hay telemetría de adopción

`AuditService` lee `fact_logs_auditoria`, que son modificaciones del **ERP** para el detector de
anomalías — no uso de la plataforma. No existe registro de qué dashboard abre cada rol, con qué
frecuencia, qué filtros usa ni qué reporte descarga.

Sin eso no se puede responder la pregunta que cualquier tribunal hará: **"¿alguien la usa?"**.
Es además barato: un middleware de FastAPI que registre `(usuario, rol, endpoint, timestamp)` en
una tabla `public.uso_plataforma`, sin PII adicional, más una pantalla de adopción en el módulo
de Administrador. Alimenta directamente el Capítulo III y las actas de aceptación pendientes del
Anexo C.

---

## 6. Hoja de ruta sugerida

| Etapa | Contenido | Por qué en ese orden |
|---|---|---|
| **1. Higiene de confianza** | G-01 (ROI falso), G-10 (mocks del Admin), barrido de constantes mágicas en KPIs | Barato, rápido y condición previa a mostrar el sistema a cualquiera |
| **2. Una sola verdad** | G-02 (diccionario de indicadores + punto único de cálculo + test de consistencia) | Todo lo que venga después se apoya en definiciones estables |
| **3. Contexto y profundidad** | G-04 (comparación temporal transversal) → G-03 N1/N2 (drill-down + vistas guardadas) | Convierte tableros en herramienta de análisis; máximo impacto percibido |
| **4. Decisión del alcance financiero** | G-05: reponer el módulo CxC/CxP **o** ajustar el objetivo general de la tesis | Requiere decisión del usuario; condiciona el Capítulo I |
| **5. Cerrar el lazo** | G-06 (línea base + bitácora de decisiones + alertas atendidas), G-09 (telemetría de adopción) | Es lo que permite *demostrar* apoyo a la decisión, no solo afirmarlo |
| **6. Operación y difusión** | G-08 (ETL calendarizado + frescura visible + CI), G-07 (correo/PDF/envío programado) | Sostiene la adopción en el tiempo |
| **7. Extensiones** | G-11 (escenarios), G-12 (huecos dimensionales), G-03 N3 | Alto valor, alto costo; con lo anterior firme |

---

## 7. Alineación con la tesis

| Elemento de la tesis | Qué brecha lo afecta |
|---|---|
| Objetivo general — decisiones **financieras** | **G-05** (sin cobertura hoy) |
| Objetivo general — "información estratégica que apoye la toma de decisiones" | **G-06** (no se registra ni se mide la decisión) |
| Cap. III §3.3.7 — fórmulas de 11 KPIs extraídas del código | **G-02** (el diccionario las vuelve mantenibles), **G-01** (una de ellas es falsa) |
| Cap. III — evidencia de uso / implantación | **G-09**, y el Anexo C pendiente (actas de aceptación) |
| Cap. IV — recomendaciones basadas en limitaciones reales | Este documento es material directo para esa sección |
| Brecha ya registrada: **0 figuras** en el entregable LaTeX | No la cubre este plan; sigue abierta (`memoria_tesis.md`) |

---

## 8. Lo que se evaluó y NO se propone (con razón)

| Idea | Por qué se descarta |
|---|---|
| Consola SQL libre para usuarios | Perfora RBAC/RLS y la anonimización de PII (regla 8). Ver G-03 N4. |
| Herramienta BI externa (Power BI / Metabase / Superset) sobre el EDW | Técnicamente trivial y tentador, pero duplicaría la capa semántica fuera del control del proyecto y saltaría el RLS por vendedor/sucursal que vive en los servicios. Solo viable **después** de G-02, y con vistas ya filtradas por rol. |
| Más modelos ML | Mismo criterio que `propuesta_nuevos_modulos_roi.md` §6: el retorno pendiente no está en entrenar más, sino en **accionar y medir** lo que ya se sirve. |
| Análisis geográfico | `dim_geografia` vacía — es trabajo de ETL (G-12), no de módulo. |
| Productividad de personal con `fact_nomina` | Cruza remuneraciones con desempeño; requiere decisión explícita de privacidad de la empresa antes de cualquier diseño. |
| Tiempo real / streaming | El negocio decide en ciclos diarios/mensuales; el costo no se justifica. Calendarizar el ETL (G-08) resuelve el 100% de la necesidad real. |

---

## 9. Condiciones de arranque (para cualquier eje aprobado)

1. Auditoría previa en `docs/auditoria/` (siguiente número libre) con las validaciones `SELECT`
   correspondientes — **antes de codificar**.
2. Reglas de negocio nuevas (definición de venta neta canónica, aging, frescura, ROI real)
   documentadas en `docs/auditoria/02_reglas_negocio_validadas.md`.
3. Umbrales por variable de entorno (patrón `BODEGA_*` / `NOTIF_*`), nunca hardcodes.
4. Producción SAP **solo lectura**; toda métrica se calcula del EDW.
5. Cambios en `public.*` exclusivamente vía migración Alembic (`backend/alembic/`).
6. **Línea base medida antes de encender cualquier módulo nuevo** — sin ella no hay ROI
   demostrable (§7.5 de la propuesta ROI, incumplido hasta ahora en todos los módulos).
