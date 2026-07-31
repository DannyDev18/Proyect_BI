# Manual del Módulo "Mi Ruta Inteligente de Ventas"

> **Fecha:** 2026-07-28
> **Alcance:** módulo completo tal como está implementado hoy (Fases 0-3 de
> `docs/features/plan_refactor_cartera360_ruta_inteligente.md`). Convive con el módulo
> heredado "Cartera de Clientes 360" (`/ventas/cartera360`), que sigue funcionando sin
> cambios de contrato.
> **Referencias de origen:** `docs/features/plan_refactor_cartera360_ruta_inteligente.md`
> (plan completo, decisiones DEC-1..DEC-5), `docs/auditoria/41_refactor_cartera360.md`
> (auditoría técnica, hallazgos de rendimiento y de datos), `docs/auditoria/
> 02_reglas_negocio_validadas.md` §17/§19 (reglas de Venta Cruzada y Ventas relacionadas).

---

## Parte 1 — Manual de Usuario

### 1.1 ¿Qué hace este módulo?

Cada mañana, el vendedor abre **Mi Ruta Inteligente de Ventas** (menú Ventas) y encuentra,
sin filtrar ni buscar nada:

1. **Hasta 10 clientes priorizados para hoy**, ordenados por una fórmula real: `valor
   histórico del cliente × (1 + probabilidad de abandono)`. No es una lista alfabética ni
   por fecha — es una lista de "a quién le conviene llamar primero".
2. **Por qué** cada cliente está ahí: cuántos días lleva sin comprar comparado con su
   ciclo habitual, y qué señales del modelo de fuga (`churn_rf`) más influyen en su riesgo.
3. **Qué ofrecerle**: un producto sugerido con nombre y precio reales (no un código
   suelto), calculado por el mismo motor de recomendación que usa Venta Cruzada.
4. Un botón para **registrar en un clic** qué pasó con ese contacto, y un **historial real**
   del cliente (compras, devoluciones, cobros y gestiones anteriores) para no llamar a
   ciegas.

Todo el módulo obedece una regla dura de diseño (R-0 del plan): **ningún número que veas
aquí está inventado**. Si un dato no se puede calcular con información real del sistema
(por ejemplo, "probabilidad de cerrar esta venta"), el módulo **no lo muestra** en vez de
rellenarlo con un placeholder. Donde falta un dato real, verás un estado vacío que explica
por qué, no un cero ni un texto de relleno.

### 1.2 Tarjetas del encabezado

Se redujeron a **4 tarjetas** (antes eran 8 — con la lista completa era difícil saber qué
mirar primero al abrir el módulo). Las 4 que quedan son las que empujan a hacer algo hoy
mismo:

| Tarjeta | Qué significa | Qué hacer con ella |
|---|---|---|
| **Clientes con alerta hoy** | Cuántos clientes de tu shortlist tienen riesgo alto de abandono según `churn_rf`. | Si sube, revisa primero los clientes marcados "Riesgo crítico"/"Riesgo medio" en la lista de prioridades. |
| **Ingreso potencial en riesgo** | La suma de (valor histórico × probabilidad de abandono) de tu shortlist — cuánto dinero está en juego si no actúas. | Es la magnitud del problema, no una meta — úsalo para justificar el tiempo que dedicas al módulo cada día. |
| **Valor potencial de la ruta de hoy** | La suma del ticket promedio real de los 10 clientes de tu ruta — cuánto podrías facturar hoy si cierras con todos. | Es un **potencial**, no una promesa: nadie te dice que vas a vender eso, es la referencia de "techo" del día. |
| **Avance del día** | Cuánto llevas vendido hoy, y qué porcentaje representa de tu meta diaria (tu meta mensual ÷ días hábiles restantes del mes). | Si vas atrasado, prioriza los clientes de mayor valor histórico de la ruta antes que los de solo alerta. |

> Nota: "Clientes asignados", "Clientes recuperados (mes)" y "Oportunidades activas" se
> siguen calculando en el backend (no se perdió el dato), solo se retiraron de esta fila
> para no saturar la primera pantalla — si se necesitan de vuelta como tarjetas visibles,
> es un cambio de una línea en `SmartKpiRow.tsx`, no un cambio de backend.

### 1.3 ¿La ruta rota o siempre son los mismos clientes?

**Rota.** Una vez que registras cualquier gestión con un cliente hoy, ese cliente **no
vuelve a aparecer en tu ruta hasta el día siguiente** — le cede el cupo al próximo cliente
de mayor prioridad que todavía no atendiste. Si además le programaste una "próxima acción"
para una fecha futura, tampoco compite por un cupo hasta esa fecha (mientras tanto lo
encuentras en el panel "Próximas acciones", §1.7, que tiene su **propia fuente de datos**
independiente de esta ruta — ver la nota técnica al final de §1.7 sobre por qué tiene que
ser así). Así, en vez de ver a los mismos 10 clientes de mayor riesgo todos los días, vas
cubriendo progresivamente más de tu cartera.

Si un cliente vuelve a aparecer al día siguiente es porque su riesgo/valor real todavía lo
justifica — el sistema no lo "olvida" indefinidamente, solo le da un descanso de un día
tras cada contacto.

### 1.4 Prioridades de hoy (el corazón del módulo)

Cada cliente aparece como una tarjeta con:

- **Nombre y código del cliente.**
- **Etiqueta de clasificación** (color): 🔴 Riesgo crítico, 🟠 Riesgo medio, 🟢 Estable, 🔵
  Oportunidad, ⭐ Premium. Se calcula con reglas deterministas sobre datos reales (riesgo
  del modelo, percentil de valor de tu propia cartera, segmento RFM "Campeones",
  comparación entre días sin comprar y tu ciclo habitual) — nunca una etiqueta arbitraria.
- **Dos medidores separados**: valor histórico y probabilidad de abandono. **No se suman
  en una sola barra a propósito** — la prioridad real es un *producto* de esos dos
  números, no una suma, así que mostrarlos sumados en una barra sería engañoso.
- **Motivo**, en una frase: cuántos días lleva sin comprar frente a su ciclo habitual, más
  las 1-2 señales que más pesan en su riesgo de fuga (edad de la relación, frecuencia,
  monto, ticket promedio — según el modelo).
- **Oferta sugerida** (si existe una): producto real, con nombre y precio, del motor de
  recomendación de Venta Cruzada.
- **Días sin comprar** y, si tiene una gestión pendiente, la **próxima fecha de acción**
  que tú mismo registraste.

Haz clic en cualquier tarjeta para abrir el panel de detalle.

### 1.5 Panel de detalle del cliente

Se abre un panel lateral con dos pestañas:

**Pestaña "Gestionar"** — registra en 4 campos qué pasó con el contacto:

| Campo | Opciones | Obligatorio |
|---|---|---|
| Resultado de la gestión | Contactado, Recompró, Perdido, No contestó, Reagendado, Interesado sin cierre, Objeción de precio, Objeción de stock | Sí |
| Canal | Llamada, WhatsApp, Email, Visita | No — se usa para medir efectividad por canal, **no se te recomienda uno** (el sistema no tiene tu teléfono/email para saber qué canal preferiría el cliente) |
| Próxima acción (fecha) | Cualquier fecha futura | No |
| Nota | Texto libre | No |

Al presionar **"Registrar gestión"**, el panel cambia automáticamente a la pestaña
"Historial" para que veas tu propio registro reflejado ahí mismo.

**Pestaña "Historial"** — línea de tiempo real del cliente: compras, devoluciones, cobros
(todos del EDW, con fecha y monto reales) y tus propias gestiones anteriores, ordenadas de
más reciente a más antigua. Aunque nunca hayas registrado una gestión con este cliente, el
historial **no está vacío** — ya tiene sus compras/devoluciones/cobros reales.

### 1.6 Resumen de alertas

Reemplazó a "Efectividad Comercial" en esta pantalla (decisión 2026-07-28: esa métrica
necesita volumen de gestiones que hoy no existe — D-1 — y se veía vacía casi siempre, sin
aportar nada al abrir el módulo). El Resumen de alertas es un triage visual inmediato:
cuántos clientes de tu ruta de hoy caen en cada clasificación (🔴 Riesgo crítico, 🟠
Riesgo medio, 🔵 Oportunidad, ⭐ Premium, 🟢 Estable) — útil desde el primer día, porque no
depende de que hayas registrado ninguna gestión todavía.

### 1.7 Próximas acciones

Reemplazó a "Plan semanal sugerido" (ese reparto era solo una redistribución mecánica de
la misma lista de 10 clientes que ya ves arriba — poco valor adicional). "Próximas
acciones" es tu propia agenda: la lista de clientes a los que les prometiste un
seguimiento (campo "Próxima acción" del formulario de gestión), ordenada por fecha más
próxima primero. Haz clic en cualquiera para abrir directamente su panel de detalle.

**Cómo se registra:** al gestionar un cliente (§1.5, pestaña "Gestionar"), el campo
"Próxima acción (fecha)" es opcional. Si le pones una fecha y presionas "Registrar
gestión", ese cliente aparece **de inmediato** en este panel — no hace falta recargar la
página ni esperar.

**Qué pasa con el cliente en la ruta del día:** mientras la fecha programada no haya
llegado, ese cliente **no** compite por un cupo en "Prioridades de hoy" (§1.3) — ya le
prometiste una fecha concreta, así que no tiene sentido que además reaparezca hoy. Vuelve
a ser candidato normal de la ruta priorizada recién en la fecha que programaste (o antes,
si vence).

**Qué significa cada etiqueta:**

| Etiqueta | Significado |
|---|---|
| 🔴 Vencida | La fecha ya pasó y todavía no registraste ninguna gestión nueva con este cliente. |
| 🟠 Hoy | La fecha programada es hoy. |
| 🔵 Próxima | La fecha programada todavía no llega. |

**Qué NO hace este panel (a propósito):** no envía ningún recordatorio ni notificación —
es una lista que tú mismo consultas, no una alarma. Si necesitas que se te avise, revisa
el panel al empezar el día.

> Nota técnica sobre por qué es un panel aparte: este panel **no** se calcula filtrando la
> ruta de hoy — tiene su propio endpoint (`GET /ruta/proximas-acciones`) porque la ruta de
> hoy EXCLUYE deliberadamente (§1.3) a los clientes con una próxima acción futura. Antes
> de esta corrección, el panel intentaba derivar su contenido de la misma lista que la
> ruta del día, y por eso casi nunca mostraba nada: eran, por diseño, las dos caras
> opuestas del mismo filtro.

> Nota técnica: "Efectividad Comercial" y "Plan semanal sugerido" **no se eliminaron del
> backend** — sus endpoints (`GET /ruta/efectividad`, `GET /ruta/plan-semanal`),
> servicios (`GestionService.get_efectividad_comercial`/`get_plan_semanal`) y contratos
> (`types/cartera360.ts`, `hooks/cartera360.ts`) siguen probados y disponibles. Solo se
> borraron los 2 componentes de React que los renderizaban en esta página
> (`EffectivenessPanel.tsx`/`WeekPlanner.tsx`, sin más consumidores) -- si se retoman más
> adelante (p. ej. un reporte de gerencia con más volumen de datos agregados de todos los
> vendedores), la UI se reconstruye sobre un backend que ya existe y ya está probado.

### 1.8 Lo que este módulo NO hace (a propósito)

| No incluye | Por qué |
|---|---|
| "Probabilidad de cierre de venta" | No hay un modelo entrenado para esto — el intento (`cross_sell_ranker`) se probó y no superó la línea base (ver auditoría 40). Se usa "probabilidad de recompra" real (`churn_rf`) en su lugar, etiquetada con precisión. |
| Recomendar un canal de contacto | El sistema no tiene teléfono ni email del cliente en el EDW — recomendar WhatsApp a alguien de quien no se conoce el número sería inventar. |
| Descuentos o promociones sugeridas | No existe una política de descuentos cargada en el sistema — inventar un porcentaje sería prometer dinero de la empresa sin base real. |
| Un copiloto conversacional (chat) | El proyecto no tiene ningún LLM integrado; las 6 preguntas que un copiloto respondería ya las cubren los paneles del módulo (¿a quién llamo? → la ruta; ¿por qué está en riesgo? → el motivo; ¿qué le ofrezco? → la oferta sugerida). |

### 1.9 ¿Cómo se activa/desactiva el módulo?

Una sola variable de entorno controla si el módulo está disponible: `CARTERA360_RUTA_
INTELIGENTE_ENABLED` (`true`/`false`) en el `.env` del backend. Con `false`, el menú
"Mi Ruta Inteligente" no aparece y la página vieja "Cartera 360" sigue siendo la que ve el
vendedor. **Cambiarla requiere recrear el contenedor del backend**
(`docker compose up -d backend` — un `docker compose restart` simple no relee el `.env`).

---

## Parte 2 — Manual del Desarrollador

### 2.1 Arquitectura general

```
Frontend (React)                       Backend (FastAPI)                          PostgreSQL (edw + public)
──────────────────                      ──────────────────                         ──────────────────────
VentasRuta.tsx                    →     ruta.py (router, /analytics/ventas/ruta)    edw.fact_ventas_detalle
 ├─ SmartKpiRow                          ├─ Cartera360Service.get_ruta_hoy           edw.fact_devoluciones
 ├─ RouteList → PriorityCard             ├─ GestionService (gestión/timeline/        edw.fact_cobros_cxc
 ├─ ClientDetailDrawer                   │   efectividad/plan semanal)               edw.dim_cliente
 │   ├─ QuickLogForm                     ├─ PredictionService (churn_rf,             public.gestion_cartera_eventos
 │   └─ ClientTimeline                   │   segmentation, association -- ya         public.cartera_recordatorios
 ├─ EffectivenessPanel                   │   existentes, sin modelos nuevos)         public.metas_comerciales_operativas
 └─ WeekPlanner                          └─ Cartera360Repository / PredictionRepository
```

El módulo **no entrena ningún modelo nuevo**: reutiliza `churn_rf` (riesgo de fuga),
`segmentation` (RFM) y `association` (recomendación), los mismos que ya sirven Venta
Cruzada y el resto del dashboard de Ventas.

### 2.2 Archivos clave

| Capa | Archivo | Responsabilidad |
|---|---|---|
| Router nuevo | `backend/app/api/routes/ruta.py` | 6 endpoints bajo `/analytics/ventas/ruta/*` (incluye `GET /proximas-acciones`, auditoría 43), registrado condicionalmente en `api.py` tras `settings.CARTERA360_RUTA_INTELIGENTE_ENABLED`. |
| Servicio de lectura/priorización | `backend/app/services/cartera360_service.py` (`get_ruta_hoy`, `_priorizar`) | Reutiliza el two-stage existente (`get_lista_trabajo`) y enriquece solo el top `CARTERA360_RUTA_TOP_N` (10) con segmento, SHAP, oferta y clasificación. |
| Servicio de escritura/trazabilidad | `backend/app/services/gestion_service.py` | `registrar_gestion`, `get_timeline_cliente`, `get_efectividad_comercial`, `get_plan_semanal`. Separado de `Cartera360Service` a propósito (lectura vs. escritura). |
| Repositorio | `backend/app/repositories/cartera360_repository.py` | Query de `lista_trabajo` reescrita (fix de latencia F0-2), + 7 métodos nuevos (meta mensual, ventas del día, timeline EDW, efectividad, última gestión en lote). |
| Repositorio de inferencia | `backend/app/repositories/prediction_repository.py` | `get_rfm_features_batch` nuevo (segmentación en lote); `get_rfm_features` reescrito (fix de un bug real preexistente, ver §2.5). |
| Servicio de inferencia | `backend/app/services/prediction_service.py` | `get_customer_segment_batch`, `get_churn_explanation_batch` nuevos — mismo patrón que el `churn_risk_batch` ya existente, para no hacer N+1 sobre los 10 clientes de la ruta. |
| Modelo BD | `backend/app/models/gestion_cartera_evento.py` | `GestionCarteraEvento` extendido (+`canal`/`resultado`/`proxima_accion_fecha`/`nota`), `CarteraRecordatorio` nuevo. |
| Migración | `backend/alembic/versions/0005_cartera360_ruta_inteligente.py` | 100% aditiva: `ADD COLUMN` nullable + `CREATE TABLE`, `CHECK` ampliado nunca restringido. |
| Schemas | `backend/app/schemas/cartera360.py` | Contratos nuevos bajo la sección "Mi Ruta Inteligente", ninguno de los contratos heredados se tocó. |
| Configuración | `backend/app/core/config.py` (bloque `CARTERA360_*`) | Feature flag, tamaño de la ruta, percentil de riesgo crítico, umbral de efectividad, cupos del plan semanal. |
| Frontend — tipos/servicio/hooks | `frontend/src/types/cartera360.ts`, `services/cartera360.ts`, `hooks/cartera360.ts` | Extendidos con la sección "Mi Ruta Inteligente de Ventas", sin tocar los contratos heredados de Cartera 360. |
| Frontend — store | `frontend/src/store/rutaVentasStore.ts` | Zustand, solo guarda qué cliente tiene el panel abierto. Sin `persist` (evita dejar PII en `sessionStorage`). |
| Frontend — componentes | `frontend/src/components/rutaInteligente/*` | `SmartKpiRow`, `PriorityCard`, `RouteList`, `ClientDetailDrawer`, `QuickLogForm`, `ClientTimeline`, `AlertsSummary`, `UpcomingActions`. (`EffectivenessPanel`/`WeekPlanner` se retiraron de esta página el 2026-07-28 — backend intacto, ver §1.5/1.6.) |
| Frontend — página | `frontend/src/pages/VentasRuta.tsx` | Orquestador delgado (~50 LOC), toda la lógica vive en el backend. |
| Frontend — routing | `frontend/src/router/AppRouter.tsx`, `frontend/src/constants/permissions.ts` | Ruta `/ventas/ruta`, con `nav: { label: 'Mi Ruta Inteligente' }` — reemplazó el `nav` de `ventas.cartera360` (que sigue accesible por URL directa). |

### 2.3 Endpoints

Todos bajo `/api/v1/analytics/ventas/ruta`, roles `administrador`/`gerencia`/`ventas`,
self-scope a la cartera del `id_vendedor_origen` del token (sin override — mismo criterio
RN-V3 que el resto del módulo Ventas).

| Endpoint | Método | Descripción |
|---|---|---|
| `/hoy` | GET | Ruta priorizada del día: tarjetas del header + hasta `CARTERA360_RUTA_TOP_N` clientes enriquecidos. |
| `/gestion` | POST | Registra una gestión (8 resultados posibles, canal, próxima acción, nota). |
| `/clientes/{cliente_id}/timeline` | GET | Historial real del cliente (compras/devoluciones/cobros del EDW + gestiones). RLS 403 si el cliente no pertenece a la cartera del vendedor. |
| `/efectividad` | GET | Métricas de conversión por canal; supervisores (gerencia/admin) ven el agregado global, un vendedor solo el suyo. |
| `/plan-semanal` | GET | Reparte la ruta de hoy en cupos lunes-viernes configurables. |
| `/proximas-acciones` | GET | Auditoría 43: agenda del vendedor con `proxima_accion_fecha` registrada, con estado `vencida`/`hoy`/`proxima`. Independiente de `/hoy` a propósito (ver §1.7). |

### 2.4 Configuración (`backend/app/core/config.py`, bloque `CARTERA360_*`)

| Variable | Default | Qué controla |
|---|---|---|
| `CARTERA360_RUTA_INTELIGENTE_ENABLED` | `false` | Registra o no el router `/ruta/*` al arrancar el backend — **el mecanismo de rollback**. |
| `CARTERA360_RUTA_TOP_N` | `10` | Cuántos clientes trae `/ruta/hoy` ya enriquecidos con oferta/motivo/SHAP. |
| `CARTERA360_PERCENTIL_VALOR_CRITICO` | `0.90` | Percentil de valor histórico (dentro de la propia cartera del vendedor) que, combinado con riesgo alto, clasifica a un cliente como "Riesgo crítico". |
| `CARTERA360_MIN_GESTIONES_EFECTIVIDAD` | `5` | Bajo este número de gestiones, el panel de Efectividad muestra estado vacío en vez de una tasa. |
| `CARTERA360_PLAN_CUPO_LUNES..VIERNES` | `10` cada uno | Cupos del planificador semanal. |
| `CARTERA360_DEDUPE_DOBLE_CLICK_SEGUNDOS` (heredado) | `10` | Ventana anti doble-click, compartida con el endpoint de gestión heredado. |

### 2.5 Bugs reales encontrados y corregidos durante la construcción

Documentados con evidencia completa en `docs/auditoria/41_refactor_cartera360.md`. Resumen:

1. **`get_rfm_features` escaneaba toda `fact_ventas_detalle` (525k filas) por cada
   consulta de UN cliente**, en vez de filtrar primero. Afectaba (antes de este refactor)
   también a `/analytics/ventas/clientes/{id}/segmento` y el detalle de Cartera 360 —
   preexistente, no introducido por este módulo. Corregido: 366 ms → 19 ms de ejecución
   por llamada.
2. **`get_timeline_cliente` (devoluciones) usaba columnas de `fact_ventas_detalle`
   (`num_factura`, `subtotal_neto`) que no existen en `fact_devoluciones`** (cuyo grano
   real es nota de crédito: `num_nota_credito`, `total_linea_devolucion`). Causaba un 500
   cada vez que se abría la pestaña "Historial" de cualquier cliente — este era el bug
   detrás del reporte de usuario "el historial no funciona". Corregido y verificado
   end-to-end contra un cliente real con compras/devoluciones/cobros.
3. **N+1 de segmentación RFM y explicación SHAP** sobre el top 10 de la ruta — cada
   cliente disparaba su propia consulta + su propio `TreeExplainer`. Corregido con
   `get_customer_segment_batch`/`get_churn_explanation_batch` (mismo patrón que el
   `churn_risk_batch` ya existente).
4. **Query base de `lista_trabajo`** agregaba por `(cliente_id, nombre_cliente)` — ambos
   `text`, ya unidos a `cliente_lookup` antes de agrupar — forzando un `Sort` a disco.
   Reescrita para agregar por `cliente_sk` (entero) antes de unir el lookup: 530 ms → 232
   ms.

Resultado combinado: `get_ruta_hoy` pasó de 5.37 s a ~0.7-0.9 s para la cartera más grande
real (31.093 clientes). El presupuesto `p95 < 800 ms` se cumple en la mayoría de las
corridas, no en el 100% — falta un warmup explícito de `shap.TreeExplainer` en el
`lifespan` del backend para cerrarlo del todo (el primer uso por proceso paga ~600 ms de
import/JIT de la librería `shap`; los usos siguientes cuestan <100 ms). Pendiente, no
bloqueante.

### 2.6 Cómo extender el módulo

- **Agregar un tipo de recomendación nuevo a la oferta sugerida:** hoy `get_ruta_hoy`
  toma solo la primera recomendación de `PredictionService.get_product_recommendations`
  (modelo `association`). Para usar otro motor (ej. los 4 combos de Venta Cruzada Fase 4),
  inyectar `CrossSellEngineService` en `Cartera360Service` y sustituir esa llamada — sin
  tocar el contrato de `ClienteRuta.oferta_sugerida`.
- **Agregar una clasificación de alerta nueva:** editar `Cartera360Service.
  _clasificar_alerta` — es una cadena de reglas evaluadas en orden de severidad, la
  primera que aplica gana. Agregar el código nuevo también en `CodigoAlerta` (frontend,
  `types/cartera360.ts`) y `BADGE_VARIANT` (`PriorityCard.tsx`).
- **Cambiar el tamaño de la ruta o los umbrales:** son env vars `CARTERA360_*` — no
  requiere despliegue de código, solo reiniciar el backend (`docker compose up -d
  backend`, no `restart`) con la variable nueva.
- **Promover el módulo a producción (Fase 7 del plan, pendiente):** activar `CARTERA360_
  RUTA_INTELIGENTE_ENABLED=true`, verificar que `constants/permissions.ts` mantenga el
  `nav` en `ventas.ruta`, y — solo cuando el usuario final valide el módulo — borrar
  `pages/VentasCartera360.tsx` y redirigir `/ventas/cartera360` → `/ventas/ruta`.

### 2.7 Testing

```bash
cd backend
python -m pytest tests/integration/test_cartera360_ruta_inteligente.py -v -m integration
# RLS 403 en /timeline y /gestion, smoke test de /hoy, /efectividad, /plan-semanal
python -m pytest tests/ -q -m integration   # suite completa (requiere Postgres real)
```

`tests/integration/conftest.py` fija `CARTERA360_RUTA_INTELIGENTE_ENABLED=true` para la
suite de pruebas (necesario porque el router se registra una sola vez, al importar
`app.main` — el flag debe estar activo ANTES de esa importación).

Frontend:

```bash
cd frontend
npx tsc --noEmit
npm run lint
npm run build
```

### 2.8 Limitaciones conocidas (no son bugs, son brechas de datos/diseño documentadas)

| Brecha | Detalle | Dónde está documentada |
|---|---|---|
| Sin "probabilidad de cierre de venta" | Ningún modelo entrenado la produce; el intento (`cross_sell_ranker`) no superó la línea base | `docs/auditoria/40_refactor_venta_cruzada.md` §Fase 2 |
| Sin canal recomendado | El EDW no tiene teléfono/email del cliente | Plan §4 DEC-4, D-3 |
| Timeline vacío el día 1 de gestiones propias | `public.gestion_cartera_eventos` no tenía filas al momento del refactor — se compensa con eventos reales del EDW (compras/devoluciones/cobros) | Plan §4.6, D-1 |
| Sin bucle de aprendizaje (Fase 8/7 original) | Requiere ≥2.000 eventos de telemetría; hoy hay muy por debajo de eso | Plan §8, D-1/D-2 |
| `p95 < 800 ms` no garantizado al 100% | Falta warmup de `shap.TreeExplainer` en el `lifespan` | Auditoría 41, adenda Fase 2, hallazgo F2-2 residual |
