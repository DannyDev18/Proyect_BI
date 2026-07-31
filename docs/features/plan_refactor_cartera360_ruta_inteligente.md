# Plan de refactorización — Cartera de Clientes 360 → "Mi Ruta Inteligente de Ventas"

**Fecha:** 2026-07-28
**Módulo:** Ventas — Cartera de Clientes 360
**Estado:** EN IMPLEMENTACIÓN — Fase 0 (auditoría), Fase 1 (cimientos BD + contratos), Fase 2
(motor de priorización, `GET /ruta/hoy` + `POST /ruta/gestion` + `GET /ruta/clientes/{id}/timeline`
+ `GET /ruta/efectividad` + `GET /ruta/plan-semanal`) y Fase 3 (frontend `/ventas/ruta`) aplicadas
y validadas el 2026-07-28 contra el EDW real, detrás del feature flag
`CARTERA360_RUTA_INTELIGENTE_ENABLED` (default `false`, backend) -- la ruta del frontend
(`/ventas/ruta`) está registrada y accesible por URL directa, pero SIN entrada en el Sidebar hasta
que el flag se active en producción (mismo "dark launch" reflejado en `constants/permissions.ts`,
sin `nav` en `ROUTES['ventas.ruta']`). Detalle completo en `docs/auditoria/41_refactor_cartera360.md`
(Fase 0 + adenda Fase 1-3). Las Fases 4-6 del plan original quedan cubiertas por lo ya construido en
Fase 2-3 (gestión extendida de 8 resultados + canal + nota, timeline con eventos EDW reales,
explicabilidad vía `motivo` con SHAP, planificador semanal) -- no quedan como fases separadas
pendientes. Fase 7 (retiro de la página vieja `/ventas/cartera360`, activar el flag en producción)
diferida hasta validación con usuario final -- es la única fase que queda por decisión de negocio,
no técnica.

**Nota sobre `RouteTable` virtualizada (criterio de aceptación 12 del plan):** el diseño final
(criterio 1: "≤10 clientes priorizados, sin scroll") hace que la tabla/lista de la ruta del día NO
necesite virtualización -- el backend ya trunca a `CARTERA360_RUTA_TOP_N=10` antes de responder. La
virtualización solo aplicaría a una vista de la cartera completa (73.502 clientes, D-4), que sigue
siendo la tabla de `/ventas/cartera360` (sin cambios). Se documenta como ajuste consciente al
criterio 12, no como un punto omitido.
**Auditoría previa obligatoria:** `docs/auditoria/41_refactor_cartera360.md` (Fase 0 de este plan, aún no ejecutada)
**Planes relacionados:** `docs/features/plan_refactor_venta_cruzada_ia.md` (mismo patrón, ya cerrado), `docs/features/plan_actualizacion_modulo_ventas.md`

---

## 0. Resumen ejecutivo

El módulo pasa de **informativo** (una tabla + 3 KPIs descriptivos) a **accionable** (ruta diaria
priorizada, motivo explicable, oferta sugerida y registro de gestión de un clic que retroalimenta
el sistema).

**El plan se apoya en una restricción dura, heredada del refactor de Venta Cruzada y confirmada
como regla del proyecto:**

> **R-0 — Cero datos inventados.** Ningún campo de ningún response puede ser simulado, estimado
> con un placeholder, ni rellenado con una constante "razonable". Todo dato sale de (a) una
> consulta real al EDW, (b) un modelo ML ya entrenado y promovido, o (c) un cálculo determinista
> sobre (a)/(b) cuya fórmula esté documentada. **Si un campo del diseño no tiene fuente real, se
> OMITE del contrato — no se rellena.**

Esta regla es la que decide el destino de 6 de los 10 cambios pedidos en el prompt original
(ver §4, tabla de viabilidad). No es una limitación del plan: es lo que separa un asistente
comercial confiable de un demo que el vendedor deja de usar la segunda semana.

---

## 1. Diagnóstico técnico del estado actual

### 1.1 Inventario real del módulo (verificado en código, no supuesto)

| Capa | Archivo | LOC | Estado |
|---|---|---|---|
| Router | [backend/app/api/routes/cartera360.py](../../backend/app/api/routes/cartera360.py) | 73 | Thin, correcto. 4 endpoints. |
| Servicio | [backend/app/services/cartera360_service.py](../../backend/app/services/cartera360_service.py) | 88 | Compone `PredictionService`. Two-stage shortlist ya implementado. |
| Repositorio | [backend/app/repositories/cartera360_repository.py](../../backend/app/repositories/cartera360_repository.py) | 207 | 3 queries EDW + 2 métodos ORM sobre `public.gestion_cartera_eventos`. |
| Esquemas | [backend/app/schemas/cartera360.py](../../backend/app/schemas/cartera360.py) | 57 | 7 modelos Pydantic. |
| Modelo BD | [backend/app/models/gestion_cartera_evento.py](../../backend/app/models/gestion_cartera_evento.py) | 29 | 1 tabla, 3 eventos válidos. |
| Página | [frontend/src/pages/VentasCartera360.tsx](../../frontend/src/pages/VentasCartera360.tsx) | 169 | **Monolito de 169 líneas: 3 KPIs + 1 DataTable + 1 Drawer, cero componentes propios.** |
| Hooks / servicio / tipos | `frontend/src/{hooks,services,types}/cartera360.ts` | 125 | Correctos, sin deuda. |

**Total del módulo: ~750 LOC.** Es un módulo pequeño; el refactor no es una reescritura de un
sistema grande sino la construcción de ~6× más superficie funcional sobre una base sana.

### 1.2 Endpoints actuales

| Endpoint | Qué hace hoy | Veredicto |
|---|---|---|
| `GET /analytics/ventas/cartera360/lista-trabajo` | Cartera completa → shortlist por valor × alerta → churn real en lote → rerank | **Conservar y extender.** El two-stage es correcto y necesario (H1 auditoría 32: hasta ~31.000 clientes por `codven`). |
| `GET .../clientes/{id}/detalle` | churn + segmento RFM + recomendaciones, bajo demanda | **Conservar y extender** (falta perfil, timeline, explicación). |
| `POST .../gestion` | Registra `contactado`/`recompro`/`perdido`, con dedupe de doble-clic | **Extender** (canal, resultado, próxima acción, nota). |
| `GET .../tasa-recuperacion` | `recompras / total_gestiones` | **Reemplazar** por Efectividad Comercial (§4.8). El endpoint se conserva deprecado un ciclo. |

### 1.3 Deficiencias confirmadas contra el código

Del diagnóstico del prompt, **confirmadas** leyendo el código:

- ✅ **No hay priorización visible.** Sí existe un score (`prioridad = valor_historico × (1 + p_abandono/100)`) pero **el frontend nunca lo muestra ni ordena por él** — la `DataTable` no declara `prioridad` como columna. El backend ya calcula la señal y la UI la tira a la basura.
- ✅ **El riesgo no es explicable.** `probabilidad_abandono` se muestra como porcentaje pelado. La explicación SHAP **ya existe** (`PredictionService.get_churn_explanation`, Fase 6 de Venta Cruzada) y este módulo no la consume.
- ✅ **No hay ofertas en la lista.** Las recomendaciones existen pero solo dentro del Drawer, y se muestran como **códigos de producto crudos** (`p.producto_cod`) sin nombre, precio ni motivo.
- ✅ **No hay historial.** `gestion_cartera_eventos` es append-only pero **no se lee nunca por cliente** — solo se agrega para la tasa global.
- ✅ **No hay aprendizaje.** No hay ningún consumidor de los eventos de gestión más allá del ratio.
- ✅ **KPIs descriptivos.** Los 3 KPIs (`clientes`, `con alerta`, `tasa`) no son clicables ni filtran nada.
- ✅ **Sin jerarquía visual.** Todo el peso visual está en una tabla de 6 columnas ordenada por el orden que devuelve el backend, sin agrupación por urgencia.

**Refutadas / matizadas** (el prompt asume peor estado del real):

- ❌ "No integra los modelos ML": integra **3 de 6** (churn, segmentación, recomendación) y el two-stage batch está bien resuelto. El problema es de **exposición**, no de integración.
- ❌ "Exceso de tablas": hay **una** tabla. El problema es lo contrario — falta estructura.
- ❌ "No existe trazabilidad": la tabla de gestiones existe, con dedupe anti doble-clic (H-V5 auditoría 34). Falta explotarla.

### 1.4 Hallazgos duros de datos (medidos, no estimados)

Consultas ejecutadas contra el EDW real durante la elaboración de este plan:

| # | Hallazgo | Medición | Consecuencia para el plan |
|---|---|---|---|
| **D-1** | **`public.gestion_cartera_eventos` está VACÍA (0 filas).** | `SELECT count(*) → 0` | **Arranque en frío total.** Todo lo que dependa de historial de gestiones (efectividad por canal, aprendizaje continuo, "qué estrategia funcionó antes", ranking de canales) **no tiene dato el día 1**. Ver §4.8 y §4.10. |
| **D-2** | `public.recomendaciones_eventos` tiene **89 filas** (eran 79 en el plan de Venta Cruzada). | `SELECT count(*) → 89` | Mismo veredicto que Fase 7 de Venta Cruzada: **muy por debajo del umbral de ≥2.000 eventos** para usar aceptación como feature. El bucle de aprendizaje se difiere igual aquí. |
| **D-3** | **No existe ningún dato de contacto en el EDW.** `public.cliente_lookup` tiene solo `(hash_anonimo, id_cliente_transaccional, nombre_cliente, created_at)`; `edw.dim_cliente` tiene `ciudad`/`zona`/`clase_cliente`/`dias_credito`/`limite_credito` pero **ni teléfono ni email**. | `\d` de ambas tablas | **"Canal recomendado" no tiene fuente real.** No se puede recomendar WhatsApp a un cliente del que no se conoce el número. Ver decisión **DEC-4**. |
| **D-4** | `public.cliente_lookup` tiene **73.502 clientes**. | `SELECT count(*)` | Confirma H1 de la auditoría 32: cualquier operación por-cliente sobre la cartera completa debe seguir siendo two-stage. **La virtualización del frontend no es opcional.** |
| **D-5** | El proyecto **no tiene ningún LLM integrado** — ni cliente de API, ni dependencia, ni env var. La decisión de "explicación por plantilla determinista, sin LLM" ya se tomó y aplicó en Venta Cruzada Fase 3. | `backend/requirements.txt`, plan de Venta Cruzada §3 | **El "Copiloto IA conversacional" no puede ser un chat LLM** sin una decisión de negocio nueva (costo, PII, dependencia externa). Ver decisión **DEC-5**. |
| **D-6** | El intento de entrenar un ranker supervisado de recomendación (`cross_sell_ranker`, Fase 2 de Venta Cruzada) **fracasó y no se promovió** (Precision@5 = 0.0369 vs. línea base 0.0782). | `ml/REPORTE_MEJORA_MODELOS.md`, `docs/auditoria/40_...md` §Fase 2 | **No hay modelo de "probabilidad de cierre de venta" ni de "probabilidad de compra por producto"**, y el precedente dice que entrenarlo con los datos actuales no funciona. Ver decisión **DEC-3**. |

---

## 2. Componentes afectados

### 2.1 Backend

| Archivo | Acción | Riesgo |
|---|---|---|
| `app/api/routes/cartera360.py` | Extender: +6 endpoints | Bajo |
| `app/services/cartera360_service.py` | **Dividir** en `cartera360_service.py` (lectura/priorización) + `gestion_service.py` (escritura/timeline/efectividad) | Bajo |
| `app/repositories/cartera360_repository.py` | Extender: +5 queries EDW | **Medio** (SQL sobre `fact_ventas_detalle`, 539k filas) |
| `app/schemas/cartera360.py` | Reescribir contratos (breaking) | **Alto** (rompe el frontend actual → migración coordinada, §7) |
| `app/models/gestion_cartera_evento.py` | Extender columnas + nuevos modelos | Medio (migración Alembic) |
| `app/api/dependencies.py` | +2 providers | Bajo — **cuidado**: definir antes del primer uso (bug ya cometido, ver CLAUDE.md 2026-07-16) |
| `app/core/config.py` | +6 settings `CARTERA360_*` | Bajo |
| `alembic/versions/0005_*.py` | **Nueva migración** | **Alto** (esquema `public`, se aplica solo en arranque del backend) |

### 2.2 Frontend

| Archivo | Acción |
|---|---|
| `pages/VentasCartera360.tsx` | **Reescribir** como orquestador delgado (~80 LOC), renombrar ruta a `/ventas/ruta` |
| `components/rutaInteligente/*` | **Nuevo directorio**, ~12 componentes (§4) |
| `store/rutaVentasStore.ts` | **Nuevo** (Zustand, sin `persist` — trae PII, mismo criterio que `crossSellStore.ts`) |
| `hooks/cartera360.ts` | Extender: +6 hooks |
| `services/cartera360.ts`, `types/cartera360.ts` | Extender |
| `constants/queryKeys.ts` | +6 claves |
| `router/AppRouter.tsx`, `components/layout/Sidebar.tsx` | Renombrado de ruta + label |

### 2.3 Base de datos (esquema `public`, vía Alembic)

| Tabla | Acción | Justificación |
|---|---|---|
| `gestion_cartera_eventos` | **ALTER**: +`canal`, +`resultado`, +`proxima_accion_fecha`, +`nota`; ampliar el `CHECK` de `evento` a los 8 resultados del prompt §7 | Necesario para timeline y efectividad. **Compatible hacia atrás**: columnas nullable, el `CHECK` se amplía (nunca se restringe). |
| `cartera_recordatorios` | **NUEVA** | Recordatorios/reagendados con estado. |
| `cartera_notas` | **DESCARTADA** | Redundante: `gestion_cartera_eventos.nota` cubre el caso. Evitar tablas por simetría con el prompt. |
| `cartera_feedback_ia` | **DIFERIDA a Fase 7** | Sin volumen (D-1/D-2), una tabla vacía es deuda, no capacidad. |

---

## 3. Dependencias e impacto sobre otros módulos

```
                    ┌─ PredictionService ──┬── churn_rf  (riesgo + SHAP)
                    │  (NO se modifica)    ├── segmentation (RFM)
Cartera360Service ──┤                      └── association (recomendaciones)
                    ├─ CrossSellEngineService (perfil, combos)  ← REUTILIZAR, no duplicar
                    ├─ GoalsService / GoalRepository (meta mensual → objetivo diario)
                    └─ Cartera360Repository (EDW)
```

**Impacto sobre módulos existentes:**

| Módulo | Impacto | Mitigación |
|---|---|---|
| **Notificaciones** | `NotificationService` consume `Cartera360Service.get_lista_trabajo` para el generador de churn alto de Ventas. **Cambiar el contrato de retorno lo rompe.** | El método actual se conserva con su firma; los campos nuevos se agregan (aditivo). Test de regresión obligatorio. |
| **Venta Cruzada** | Comparte `Cartera360Repository` (`get_perfil_cliente`, `get_productos_favoritos_cliente`) vía `CrossSellEngineService`. | Solo agregar métodos; **prohibido modificar la firma de los 3 existentes**. |
| **Metas y Comisiones** | Se lee `metas_comerciales_operativas` para el objetivo del día. Solo lectura. | Ninguna. |
| **Dashboard Ventas / Gerencia** | Sin acoplamiento directo. | Ninguna. |
| **RBAC / RLS** | Todo el módulo es self-scope al `id_vendedor_origen` del token (RN-V3, sin override). | **Todo endpoint nuevo hereda `_requerir_vendedor` + `_verificar_pertenencia_cartera`.** Test de 403 por endpoint, obligatorio (H-V2 auditoría 34 se coló exactamente por saltarse esto). |

---

## 4. Viabilidad de los 10 cambios pedidos (contra R-0)

Esta es la sección de decisión. **Verde** = dato real disponible. **Ámbar** = derivable con fórmula
documentada. **Rojo** = sin fuente real, requiere decisión del usuario.

### 4.1 Header → tarjetas inteligentes accionables

| Tarjeta pedida | Fuente real | Veredicto |
|---|---|---|
| Clientes asignados | `COUNT` de la cartera del `codven` (EDW) | 🟢 |
| Clientes con alerta hoy | `COUNT` con `riesgo_alto` (umbral `CHURN_UMBRAL_RIESGO_ALTO`) | 🟢 |
| Clientes recuperados | `gestion_cartera_eventos` con `evento='recompro'` en el mes | 🟢 **valor real = 0 hoy (D-1)**, sube con el uso |
| Ingreso potencial en riesgo | `Σ (valor_historico × p_abandono/100)` de la cartera | 🟡 fórmula documentada, insumos reales |
| Oportunidades activas | `COUNT` de clientes con recomendación sobre `CROSS_SELL_MIN_LIFT` | 🟢 |
| **Valor esperado del día** | requiere probabilidad de cierre | 🔴 **ver DEC-3** |
| Objetivo diario | meta mensual del vendedor ÷ días hábiles restantes | 🟡 prorrateo, fórmula documentada |
| Avance del día | ventas del día del `codven` (EDW) ÷ objetivo diario | 🟢 |

→ Se implementan **7 de 8**. "Valor esperado del día" se reemplaza por **"Valor potencial de la
ruta de hoy"** = `Σ ticket_promedio` de los clientes de la ruta (dato real por cliente), etiquetado
explícitamente como potencial, no esperado.

### 4.2 Panel de prioridades — 🟢 **es el corazón del refactor**

Todos los campos tienen fuente salvo dos:

- **Score IA** 🟡 = `prioridad` (ya calculado), normalizado 0-100, **con desglose visible** de sus 2
  factores reales (valor histórico, probabilidad de abandono). Mismo criterio que la Fase 5 de
  Venta Cruzada: como el score es un **producto**, se renderizan medidores independientes, nunca
  una barra apilada aditiva (que sería una representación visual falsa).
- **Probabilidad de compra** → **`probabilidad_recompra` real** (DEC-3A): `100 − p_abandono` de
  `churn_rf`. Etiquetada en la UI como "Prob. de recompra", nunca como "prob. de cierre".
- **Tiempo restante** 🟡 = `frecuencia_promedio_dias − dias_sin_comprar`, es decir, cuántos días
  quedan antes de que el cliente cruce su propio ciclo de compra. Real y explicable.
- **Motivo** 🟢 = plantilla determinista sobre las señales reales (días sin comprar vs. su
  frecuencia, top-2 features SHAP de churn, caída de ticket). Sin LLM (DEC-5).

### 4.3 Tabla principal — 🟢 **10 de las 12 columnas pedidas**

- `Canal recomendado` → **eliminada** (DEC-4C).
- `Probabilidad de cierre` → **sustituida** por `Prob. de recompra` (DEC-3A).
- `Oferta sugerida` pasa de código crudo a `{codart, nombre, precio, motivo}` reutilizando el
  enriquecimiento que **ya existe** en `CrossSellEngineService`.
- El resto (Cliente, Estado, Última compra, Frecuencia histórica, Motivo para contactar, Valor
  potencial, Última gestión, Próxima acción, botón Gestionar) es directo.

### 4.4 Alertas inteligentes (panel lateral) — 🟢

Las 6 clasificaciones se derivan de señales reales ya disponibles:

| Clasificación | Regla determinista |
|---|---|
| 🔴 Riesgo crítico | `riesgo_alto` **y** `valor_historico` en el top decil |
| 🟠 Riesgo medio | `riesgo_alto` |
| 🟢 Estable | `dias_sin_comprar < frecuencia_promedio_dias` |
| 🔵 Oportunidad | tiene recomendación sobre umbral y no está en riesgo |
| ⭐ Premium | segmento RFM = "Campeones" (del modelo `segmentation`) |
| 🚀 Crecimiento | ticket 12m > ticket histórico (crecimiento medido, no supuesto) |

**Los umbrales van a `config.py` como `CARTERA360_*`, nunca hardcodeados** (restricción del proyecto).

### 4.5 Motor de recomendaciones — 🟡 parcial, honesto

De los 9 tipos pedidos, tienen base real: **Cross-selling** (modelo `association`),
**Reposición** (frecuencia de recompra del mismo producto, medible en el EDW),
**Reactivación** (regla sobre `dias_sin_comprar`), **Renovación** (subcaso de reposición),
**Combos** (los 4 combos reales de Venta Cruzada Fase 4, ya implementados).

**Sin base real:** *Up-selling* (requiere jerarquía de gama de producto — `dim_producto` no la
tiene), *Nuevos productos* (requiere fecha de alta del artículo — verificar en Fase 0),
*Descuentos* / *Promociones* (**no existe política de descuentos en el EDW**; inventar un % sería
prometer dinero de la empresa a partir de una constante hardcodeada — **descartado sin apelación**).

→ Se implementan **5 de 9** tipos. Los 4 restantes se documentan como no-viables con su causa.
Cada recomendación lleva **motivo** 🟢 y **beneficio esperado** 🟡 (`precio × margen` reales);
**"probabilidad de éxito" se OMITE** (mismo motivo que DEC-3).

### 4.6 Timeline — 🟢 estructura, ⚠️ vacío al inicio

Los 10 tipos de evento son válidos como **taxonomía de captura**. Pero **hoy hay 0 gestiones
(D-1)**: el timeline arranca vacío para todos los clientes. Se complementa con **eventos reales que
sí existen en el EDW**: compras (`fact_ventas_detalle`), devoluciones (`fact_devoluciones`) y
cobros (`fact_cobros_cxc`) — así el timeline tiene contenido real desde el día 1 aunque nadie haya
registrado una gestión todavía. **Este es el diseño que hace el módulo usable en la semana 1.**

### 4.7 Registro de gestiones — 🟢

Los 8 resultados se agregan ampliando el `CHECK` de `evento`. **"Toda acción alimenta el modelo
ML" es falso hoy y debe decirse:** ningún modelo se reentrena con estos eventos (el prompt mismo
prohíbe reentrenar). Lo que sí es cierto y se implementa: cada gestión alimenta el **cálculo de
efectividad** (§4.8) y queda disponible como dataset para un futuro entrenamiento (Fase 7, §9).

### 4.8 Efectividad Comercial — 🟢 estructura, ⚠️ **vacío al inicio (D-1)**

Reemplaza "Tasa de recuperación". Todas las métricas (contactados, ventas, conversión, tiempo
promedio, ingresos, ranking) se calculan sobre gestiones reales cruzadas con `fact_ventas_detalle`.

**Con 0 filas, el panel muestra un estado vacío real** ("aún no hay gestiones registradas; el panel
se activa a partir de N gestiones") — **nunca ceros, nunca datos de ejemplo** (RN-CS5).

### 4.9 Planificador semanal — 🟡 reglas deterministas

El mapeo lunes-viernes del prompt es una **regla de negocio propuesta, no derivada de datos**. Se
implementa como tal, con los cupos configurables (`CARTERA360_PLAN_*`), y se etiqueta en la UI como
"plan sugerido" — no como una optimización aprendida.

### 4.10 Copiloto IA — ❌ **descartado (DEC-5C)**

Fuera de alcance. Las 6 preguntas quedan respondidas por los paneles del módulo, sin superficie
conversacional.

---

## 5. Decisiones de alcance — RESUELTAS (2026-07-28)

> Las 5 decisiones se cerraron con el usuario antes de escribir código. Se conserva el razonamiento
> completo de cada una porque justifica omisiones que de otro modo se leerían como descuidos.

| # | Decisión tomada | Efecto en el plan |
|---|---|---|
| **DEC-1** | Extender `components/ui/`, **sin shadcn** | 3 primitivos nuevos (`Timeline`, `Sheet`, `Command`→ ya no aplica, ver DEC-5). Sin dependencias nuevas |
| **DEC-2** | **Sin react-hook-form y sin zod** | El formulario de gestión usa `useState`; la capa `services/` sigue confiando en el tipo TS |
| **DEC-3** | **`probabilidad_recompra` real** (`100 − p_abandono` de `churn_rf`) | Sustituye "probabilidad de cierre" en tarjetas y tabla, etiquetada literalmente |
| **DEC-4** | **Omitir la columna "Canal recomendado"** | Fuera de tabla y tarjetas. **El `canal` sí se sigue capturando** en el formulario de gestión — es la dimensión del panel de Efectividad Comercial (§4.8). Lo que se descarta es *recomendar* un canal, no *registrarlo* |
| **DEC-5** | **Descartar el copiloto** | **Fase 7 eliminada** (−2 jornadas). El primitivo `Command` deja de ser necesario |

### DEC-1 — Shadcn/ui: **NO adoptar**

El frontend tiene un sistema de diseño propio consolidado: **24 componentes** en
`components/ui/` (`DataTable`, `Drawer`, `KpiCard`, `EmptyState`, `Pagination`, `Toast`…) usados
por **15 páginas**. Introducir shadcn crearía dos lenguajes visuales conviviendo, y shadcn asume
`class-variance-authority` + Radix + una convención de theming que choca con el Tailwind 4 actual.
**Resuelto:** extender `components/ui/` con los 2 primitivos que faltan (`Timeline`, `Sheet`
lateral) siguiendo el estilo existente — `Command` se cae junto con el copiloto (DEC-5).
`framer-motion` **ya está instalado** (v12) — las microanimaciones pedidas no requieren
dependencia nueva.

### DEC-2 — react-hook-form + zod: **ninguno de los dos**

No hay formulario complejo en este módulo (el registro de gestión son 4 campos). RHF sería una
dependencia nueva para un caso que `useState` resuelve. **zod** sí aporta valor real: validar en
runtime que el response del backend cumple el contrato (hoy se confía ciegamente en el tipo TS).
**Resuelto: ninguno.** El formulario de gestión (4 campos) se resuelve con `useState`, y la capa
`services/` sigue confiando en el tipo TS como el resto de la aplicación. Consecuencia asumida: un
cambio de contrato del backend no se detecta en runtime, solo en compilación — igual que hoy.

### DEC-3 — "Probabilidad de cierre / de compra": 🔴 **no existe y el precedente dice que no se puede entrenar hoy**

El intento formal ya se hizo y falló (**D-6**: `cross_sell_ranker`, Precision@5 = 0.0369 vs. 0.0782
de la línea base — no promovido). Además, el prompt prohíbe reentrenar. Opciones:

- **(A) ELEGIDA — reemplazar por `probabilidad_recompra` real.** `100 − probabilidad_abandono`
  de `churn_rf`, ya calculado y ya usado con este mismo criterio en Venta Cruzada Fase 3. Es una
  probabilidad **real y validada**, solo que responde "¿este cliente volverá a comprar?" en vez de
  "¿cerrará esta venta?". Se etiqueta con precisión en la UI.
- (B) Omitir el campo por completo.
- (C) Entrenar un 8º modelo sobre resultados de gestión — **imposible hoy: 0 filas (D-1)**. Viable
  como Fase 7 a partir de ~2.000 gestiones.

**Se descarta explícitamente** cualquier fórmula tipo `score × 0.7 + 0.3` presentada como
probabilidad: sería exactamente el placeholder que R-0 prohíbe.

### DEC-4 — "Canal recomendado": 🔴 **no hay datos de contacto en el EDW (D-3)**

Ni teléfono ni email existen en `cliente_lookup` ni en `dim_cliente`. Opciones:

- (A) Canal como dato que el vendedor aporta, con recomendación emitida al acumular historial.
- (B) Ampliar el ETL para traer teléfono/email de SAP → **cambio de alcance**: toca `etl/`, PII
  nueva fuera de `cliente_lookup`, y obliga a una decisión de protección de datos. Requiere la
  skill `etl-edw-auditor` y un plan aparte.
- **(C) ELEGIDA — omitir la columna.** No se recomienda canal en ninguna vista.

  **Matiz importante:** se omite *recomendar* el canal, no *registrarlo*. El formulario de gestión
  sigue capturando `canal` (llamada/WhatsApp/email/visita) porque es la **dimensión del panel de
  Efectividad Comercial** (§4.8, pedido explícito del prompt: "Canal / Contactados / Ventas /
  Conversión / Ranking"). Sin ese campo, ese panel no existiría. La columna `canal` de
  `gestion_cartera_eventos` se mantiene en la migración `0005`.

### DEC-5 — Copiloto IA conversacional: 🔴 **no hay LLM en el proyecto (D-5)**

- (A) "Consultas rápidas" determinista: paleta de comandos con las 6 preguntas como intenciones
  fijas sobre endpoints reales.
- (B) Integrar un LLM real (Claude API) → decisión de negocio nueva: costo recurrente, envío de
  datos de clientes a un tercero, dependencia externa en el path del vendedor.
- **(C) ELEGIDA — descartar el copiloto.** **La Fase 7 se elimina del plan** (−2 jornadas) y el
  primitivo `Command` deja de ser necesario (DEC-1). Las 6 preguntas del prompt quedan cubiertas
  de forma implícita por los paneles del módulo: "¿a quién llamo hoy?" es la ruta priorizada
  (§4.2), "¿por qué está en riesgo?" es el panel SHAP (§4.5) y "¿qué le ofrezco?" es el panel de
  ofertas (§4.5). Lo que se pierde es la superficie conversacional, no la respuesta.

---

## 6. Riesgos

| # | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| R-1 | **Regresión de rendimiento**: cartera de ~31k clientes + queries nuevas por cliente | Alta | Alto | Two-stage obligatorio; **presupuesto de latencia: p95 < 800 ms** en `/ruta`; medir ANTES (Fase 0) y DESPUÉS de cada fase; `EXPLAIN ANALYZE` de cada query nueva sobre `fact_ventas_detalle` |
| R-2 | **Romper Notificaciones** (consume `get_lista_trabajo`) | Media | Alto | Cambios aditivos en ese método; test de regresión de `NotificationService` en cada fase |
| R-3 | **Fuga de RLS en endpoints nuevos** (ya ocurrió: H-V2 auditoría 34) | Media | **Crítico** | `_verificar_pertenencia_cartera` en todo endpoint por-cliente + **test de 403 obligatorio por endpoint**, sin excepción |
| R-4 | **Migración Alembic falla en arranque** → backend no levanta | Baja | Crítico | Solo `ADD COLUMN` nullable + `CREATE TABLE`; ampliar `CHECK` nunca restringirlo; probar contra Postgres desechable (patrón de la auditoría 37) antes de tocar la BD de desarrollo |
| R-5 | **Contrato breaking frontend↔backend** | Alta | Medio | Versionado por ruta nueva (`/ruta/*`) conviviendo con `/cartera360/*` un ciclo; §7 |
| R-6 | **Módulo vacío el día 1** (D-1: 0 gestiones) → el vendedor lo abandona | **Alta** | **Alto** | Timeline poblado con eventos reales del EDW (compras/devoluciones/cobros) desde el día 1 (§4.6); estados vacíos que explican **cuándo** se activa cada panel, no ceros |
| R-7 | **Sobre-promesa de "IA"** en la UI | Media | Medio | Etiquetado literal por origen: "Modelo de fuga (churn_rf)", "Coocurrencia de facturas", "Regla del sistema". Precedente ya aplicado (R-3 de Venta Cruzada) |
| R-8 | **Alcance**: 10 cambios + reescritura frontend en un solo push | Alta | Alto | 8 fases independientes, cada una desplegable y con valor propio (§8) |

---

## 7. Estrategia de migración

**Estrangulamiento (strangler fig), no big-bang.**

1. **Convivencia de rutas.** Los 4 endpoints `/cartera360/*` **se conservan intactos** durante todo
   el refactor. Los nuevos viven bajo `/analytics/ventas/ruta/*`. Notificaciones sigue consumiendo
   los viejos sin enterarse.
2. **Convivencia de páginas.** `/ventas/cartera360` (actual) y `/ventas/ruta` (nueva) coexisten. El
   Sidebar apunta a la nueva desde la Fase 3; la vieja queda accesible por URL directa como
   escape hatch.
3. **Retiro.** Solo tras la validación con usuario final (Fase 8): se borra `VentasCartera360.tsx`,
   se redirige `/ventas/cartera360` → `/ventas/ruta`, y `/cartera360/tasa-recuperacion` se marca
   `deprecated=True` en OpenAPI un ciclo antes de eliminarse.
4. **BD sin ruptura.** Todo `ADD COLUMN` es nullable; `evento` amplía su `CHECK`. Las 0 filas
   actuales (D-1) hacen la migración de datos trivial — **ventana ideal para el cambio de esquema**.

---

## 8. Orden de implementación y esfuerzo

Cada fase es independiente, desplegable y aporta valor por sí sola (lección de la Fase 2 fallida de
Venta Cruzada: si la fase central falla, las demás deben sobrevivir).

| Fase | Contenido | Skill del proyecto | Esfuerzo | Bloquea a |
|---|---|---|---|---|
| **0. Auditoría** | `docs/auditoria/41_refactor_cartera360.md`. Medir latencia base de `/lista-trabajo`; `EXPLAIN ANALYZE`; verificar si `dim_producto` tiene fecha de alta (§4.5); confirmar volumen real de cartera por `codven` de vendedores reales; validar los 5 DEC | `etl-edw-auditor` | **1.5 d** | todo |
| **1. Cimientos BD + contratos** | Migración `0005`; extender modelo; nuevos schemas Pydantic; `gestion_service.py` nuevo; settings `CARTERA360_*` | `backend-ml-serving` | **2 d** | 2,4,5 |
| **2. Motor de priorización** | `GET /ruta/hoy`: score con desglose, motivo por plantilla, clasificación de alertas, tarjetas del header. Reutiliza el two-stage existente | `backend-ml-serving` | **3 d** | 3 |
| **3. Frontend — ruta + prioridades** | `/ventas/ruta`, `rutaVentasStore`, `PriorityCard`, `SmartKpiRow`, `RouteTable` **virtualizada**, `AlertsSidebar`, skeletons, empty states, dark mode, WCAG AA | `frontend-design` + `dataviz` | **4 d** | — |
| **4. Gestión + timeline** | `POST /ruta/gestion` (8 resultados, canal, próxima acción, nota); `GET /ruta/clientes/{id}/timeline` **poblado con eventos reales del EDW**; `QuickLogForm`, `ClientTimeline`, recordatorios | `etl-edw-auditor` (SQL) | **3 d** | 6 |
| **5. Recomendaciones + explicabilidad** | 5 tipos viables (§4.5) reutilizando `CrossSellEngineService`; panel SHAP de churn reutilizando `get_churn_explanation`; `OfferPanel`, `WhyPanel` | `backend-ml-serving` | **3 d** | — |
| **6. Efectividad + planificador** | `GET /ruta/efectividad` (dimensión canal, estado vacío real), `GET /ruta/plan-semanal`; `EffectivenessPanel`, `WeekPlanner` | — | **2 d** | — |
| ~~7. Copiloto~~ | **ELIMINADA** (DEC-5C) | — | — | — |
| **7. Retiro + validación** | Borrar página vieja, redirect, deprecar endpoint, suite completa, sesión con usuario final | — | **1.5 d** | — |
| **(8. Diferida)** | Bucle de aprendizaje: reentrenar con resultados de gestión | `ml-training-pipeline` | — | **bloqueada hasta ≥2.000 gestiones (D-1/D-2)** |

**Total: ~20 jornadas de desarrollo.** Ruta crítica: 0 → 1 → 2 → 3. Las fases 4-6 son paralelizables
tras la 3.

---

## 9. Plan de rollback

| Nivel | Mecanismo | Tiempo |
|---|---|---|
| **Feature flag** | `CARTERA360_RUTA_INTELIGENTE_ENABLED` (default `false` hasta Fase 8). Apagado ⇒ el Sidebar apunta a la página vieja y `/ruta/*` responde 404. **Mismo patrón que `COMISION_MODO`, cuyo rollback documentado es cambiar una env var.** | segundos |
| **Frontend** | La página vieja no se borra hasta Fase 8: revertir el link del Sidebar | 1 commit |
| **Backend** | Endpoints nuevos bajo prefijo propio: quitar el `include_router` de `/ruta` no toca nada existente | 1 commit |
| **BD** | `downgrade()` de la migración `0005`: `DROP` de las 2 tablas nuevas y de las 4 columnas nuevas. **Sin pérdida de datos preexistentes** — las columnas son nuevas y la tabla está vacía hoy (D-1) | 1 comando |
| **Por fase** | Cada fase es un commit atómico con su test; `git revert` de una fase no rompe las anteriores | minutos |

---

## 10. Criterios de aceptación

**Funcionales**

1. Al abrir `/ventas/ruta`, el vendedor ve **≤10 clientes priorizados** con acción concreta, sin scroll ni filtros previos.
2. Cada cliente muestra **por qué** está ahí, con las señales reales que lo pusieron (SHAP de churn + días vs. su frecuencia), no solo un porcentaje.
3. Registrar una gestión completa toma **≤3 clics** y aparece en el timeline sin recargar.
4. Toda oferta sugerida muestra **nombre y precio reales** del producto, no un código crudo.
5. **Ningún campo del response está simulado (R-0).** Auditable: cada campo del contrato tiene documentada su fuente (query EDW / modelo / fórmula) en la auditoría 41.
6. Los paneles sin datos (efectividad, timeline sin gestiones) muestran **estado vacío explicativo**, nunca ceros ni ejemplos.

**Técnicos**

7. `p95 < 800 ms` en `/ruta/hoy` con la cartera más grande medida en Fase 0; `< 300 ms` en los endpoints por-cliente.
8. **RLS: test de 403 por cada endpoint nuevo por-cliente**, sin excepción (R-3).
9. Suite backend sin fallos nuevos (línea base: 282 passed / 3 skipped / 8 failed preexistentes).
10. `tsc` y `oxlint` limpios en todo archivo nuevo o tocado.
11. `VentasCartera360.tsx` (169 LOC monolíticas) → orquestador **≤100 LOC** + componentes ≤150 LOC c/u.
12. Tabla principal **virtualizada** (D-4: 73.502 clientes en el lookup).
13. Cero regresiones en Notificaciones (test explícito de `NotificationService`).

**Documentales**

14. `docs/auditoria/41_refactor_cartera360.md` con hallazgos por fase.
15. Reglas nuevas **RN-C1..RN-Cn** en `docs/auditoria/02_reglas_negocio_validadas.md` §19.
16. Toda decisión no-viable (§4.5, DEC-3, DEC-4, DEC-5) documentada **con su causa**, no omitida en silencio.

---

## 11. Lo que este plan NO hará (y por qué)

Declararlo por adelantado evita que se lea como un descuido:

| Pedido | Motivo |
|---|---|
| Reentrenar o crear modelos ML | Prohibido por el prompt; y el precedente `cross_sell_ranker` (D-6) muestra que con los datos actuales no funciona |
| Copiloto conversacional (de cualquier tipo) | Descartado en DEC-5C. Sin LLM en el proyecto (D-5) y sin superficie de chat determinista |
| Recomendar un canal de contacto | Sin teléfono ni email en el EDW (D-3); DEC-4C. El canal **sí se registra** para medir efectividad |
| Recomendar descuentos/promociones | No existe política de descuentos en el EDW; inventar un % es prometer dinero de la empresa desde una constante |
| "Probabilidad de cierre de venta" | Sin modelo (D-6); se ofrece `probabilidad_recompra` real (DEC-3A) |
| Up-selling | `dim_producto` no tiene jerarquía de gama |
| Adoptar shadcn/ui | 24 componentes propios en 15 páginas; crearía dos lenguajes visuales (DEC-1) |
| react-hook-form / zod | DEC-2: el único formulario tiene 4 campos; la validación de contrato sigue siendo en compilación, como en el resto de la app |
| Tabla `cartera_feedback_ia` | Sin volumen (D-1/D-2); una tabla vacía es deuda, no capacidad |

---

## 12. Skills del proyecto por fase

| Skill | Cuándo | Por qué |
|---|---|---|
| `etl-edw-auditor` | Fase 0, Fase 4 | Todo SQL nuevo sobre `fact_ventas_detalle`/`fact_cobros_cxc`/`fact_devoluciones` y la verificación de reglas del DW |
| `backend-ml-serving` | Fases 1, 2, 5 | Endpoints que consumen `churn_rf`/`segmentation`/`association`; **regla dura: no instanciar `ModelLoader`, inyectar `ModelLoaderDep`; features vía `loader.get_features()`, nunca `feature_names_in_`; degradación con `try/except` obligatoria** |
| `frontend-design` | Fase 3 | Jerarquía visual, dark mode, WCAG AA |
| `dataviz` | Fase 3 | Medidores de score, gauge de avance del día |
| `ml-training-pipeline` | Fase 8 (diferida) | Solo si se retoma el bucle de aprendizaje |

---

## 13. Nomenclatura

| Antes | Después | Motivo |
|---|---|---|
| "Cartera de Clientes 360" | **"Mi Ruta Inteligente de Ventas"** | Del prompt; el nombre expresa acción, no repositorio de datos |
| Ruta `/ventas/cartera360` | `/ventas/ruta` | Coherente con el nombre |
| "Tasa de recuperación" | **"Efectividad Comercial"** | Del prompt (§4.8) |
| `Cartera360Service` | `Cartera360Service` + `GestionService` | Separar lectura/priorización de escritura/trazabilidad |

**Nota:** el prefijo interno `cartera360` **se conserva** en nombres de archivos, tablas y settings.
Renombrarlo tocaría `Cartera360Repository` (compartido con Venta Cruzada), `CARTERA360_*`,
`VENTAS360_*` y `public.gestion_cartera_eventos` sin ningún beneficio funcional — churn de nombres
por churn de nombres. El renombrado es de **cara al usuario**, no de código.

---

## 14. Próximo paso

Las 5 decisiones de §5 están resueltas (2026-07-28). Queda:

1. **Autorizar la Fase 0** (auditoría) — única fase que no modifica código de producción. Sus
   hallazgos pueden ajustar las fases 1-7 antes de que exista deuda.
2. Confirmar si se ejecutan las 7 fases o un subconjunto (la ruta crítica hasta tener el módulo
   accionable es 0 → 1 → 2 → 3, ~10.5 jornadas; las fases 4-6 son incrementos independientes).

**Preguntas que la Fase 0 debe cerrar antes de la Fase 1:**

- Latencia base real de `/lista-trabajo` con el `codven` de mayor cartera (línea base para R-1).
- `EXPLAIN ANALYZE` de las 5 queries nuevas sobre `fact_ventas_detalle` / `fact_cobros_cxc` /
  `fact_devoluciones`.
- ¿`dim_producto` tiene fecha de alta del artículo? Decide si "Nuevos productos" entra en §4.5.
- Volumen real de cartera por vendedor activo (confirmar o refutar el techo de ~31k de la
  auditoría 32).
