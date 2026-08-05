# Plan: Módulo de Gestión de Inventario y Reabastecimiento (MGIR)

> **Estado:** propuesta, no aplicada.
> **Origen:** petición del usuario (2026-08-04) — reestructurar Dashboard de Bodega + Simulador
> What-If + Generador de Propuestas como un módulo autónomo, y centralizar la lógica de
> inventario que hoy está duplicada en otras partes del sistema.
> **Auditoría previa obligatoria:** `docs/auditoria/52_modulo_inventario_centralizado.md`
> (Fase 0 de este plan — se crea ANTES de tocar código, convención del proyecto).
> **Antecedentes:** `docs/features/plan_reabastecimiento_inteligente.md` (F0-F10 aplicadas),
> `docs/auditoria/50_reabastecimiento_inteligente.md`, `docs/auditoria/42_correcciones_integrales_sistema.md`.

---

## 0. Lectura crítica del requerimiento

El requerimiento original describe el módulo desde las capturas de pantalla. Contrastado
contra el código real, **cinco de sus propuestas ya están satisfechas** y **tres son
inaplicables a esta arquitectura**. Decirlo por adelantado evita gastar fases enteras en
trabajo que no cambia nada.

| Propuesta del requerimiento | Estado real en el código | Acción |
|---|---|---|
| Crear `InventoryMetricsService` (SS, ROP, cobertura) | Ya existe como **motor puro sin I/O**: `backend/app/services/replenishment_engine.py` (352 líneas, 50 tests) | Conservar, **ampliar alcance** (§4.1) |
| Crear `DemandAnomalyService` | Ya existe: `detectar_cambio_brusco` / `detectar_tendencia_decreciente` en el mismo motor | Conservar |
| Crear `RecommendationService` | Ya existe: `cantidad_sugerida` + `ReplenishmentService.get_lista_reabastecimiento` | Conservar |
| Crear `SimulationService` | Ya existe: `ReplenishmentService.simular` (`POST /simular`, no persiste nada) | Conservar, **corregir rendimiento** (§4.4) |
| Exponer API REST + Swagger | Ya existe: router `/analytics/bodega/reabastecimiento` (15 endpoints) + OpenAPI en `/docs` | **No renombrar** a `/api/inventory/*` (§0.1) |
| Microservicio independiente | — | **Rechazado** (§0.1) |
| Kafka / RabbitMQ para alertas | — | **Rechazado** (§0.1) |
| Redis para caché | — | **Rechazado**, sustituido por caché en proceso (§4.4) |
| Centralizar datos maestros (artículo, categoría, bodega) | Ya centralizados en el EDW dimensional (`edw.dim_producto`, `dim_almacen`, …) | Sin acción |

### 0.1 Tres rechazos explícitos, con motivo

1. **Microservicio separado.** El sistema es un monolito modular desplegado con Docker
   Compose (`postgres_edw` + `backend` + `frontend`). Extraer MGIR a un servicio propio
   obligaría a duplicar autenticación JWT, la RLS por almacén (`resolve_almacenes_filter`,
   RN-B10, el hallazgo de seguridad más grave que este proyecto ha corregido) y la conexión
   al EDW — tres superficies de riesgo nuevas a cambio de una escalabilidad que este
   volumen de datos (~8.150 artículos evaluados) no necesita. **La independencia que el
   requerimiento busca se logra con un paquete Python con frontera explícita**, no con un
   proceso separado (§3).
2. **Broker de mensajes (Kafka/RabbitMQ).** El proyecto no tiene ninguno y las alertas ya
   funcionan por *pull*: `NotificationService` las calcula al vuelo y el frontend hace
   polling cada 60 s (decisión documentada en `docs/auditoria/31_modulo_notificaciones.md`).
   Introducir un broker para un dato que se recalcula en menos de un segundo agrega una
   pieza de infraestructura sin consumidor real.
3. **Redis.** El proyecto ya tiene un patrón de caché en proceso
   (`WarehouseService._prediccion_cache_get/_set`). El problema de rendimiento real (§2, D-6)
   se resuelve con memoización por request, no con un servicio nuevo.

### 0.2 Y un rechazo de nomenclatura

Renombrar los endpoints a `/api/inventory/*` rompería los 15 endpoints ya en producción, el
frontend que los consume y las reglas RN-RB1..RN-RB10 ya documentadas, sin ganar nada: el
prefijo actual (`/analytics/bodega/reabastecimiento`) ya es un espacio de nombres propio.
**Se conserva el contrato HTTP existente.** El módulo se vuelve independiente por dentro.

---

## 1. Alcance del módulo (MGIR)

Un paquete Python autónomo que es **el único dueño** de:

- Estadística de demanda por artículo (media, σ, coeficiente de variación, degradación por
  falta de historia).
- Stock de seguridad, punto de reorden, cobertura en días, cantidad sugerida de compra.
- Clasificación ABC (Pareto sobre valor de consumo) y XYZ (variabilidad).
- Clasificación de riesgo de quiebre y del estado de stock del artículo.
- Detección de anomalías de demanda (cambio brusco, tendencia decreciente).
- Simulación what-if de política (nivel de servicio, lead time).
- Propuestas de compra persistidas y su máquina de estados.
- Configuración editable de política y lead times.

**Fuera del módulo** (se quedan donde están, consumen MGIR): reportes de Bodega
(`warehouse_service.get_reporte_*`), export Excel/PDF, kardex, transferencias entre
almacenes, forecast ML por producto (`demand_rf`), filtros globales de Bodega.

---

## 2. Duplicidades reales encontradas (a confirmar en Fase 0)

Estos son hallazgos de lectura de código, **no hipótesis**. La Fase 0 los cuantifica contra
el EDW real antes de tocar nada.

### D-1 (ALTO) — Dos motores de punto de reorden, dos respuestas distintas para el mismo artículo

| | Motor determinista | Motor estocástico |
|---|---|---|
| Dónde | `WarehouseService._punto_reorden_efectivo` | `replenishment_engine.punto_reorden` |
| Fórmula | `salida_diaria × (LT_fijo + SS_fijo_en_días)` | `demanda_media × LT + z(nivel_servicio)·σ·√LT` |
| Ventana de demanda | 30 días (`salidas_periodo`) | hasta 36 meses (`unidades_mensuales`) |
| Lead time | constante global `BODEGA_LEAD_TIME_DIAS` | resuelto por producto > categoría > proveedor > default |
| Nivel de servicio | no existe | configurable por clase ABC |
| Consumidores | `/kpis`, `/stock-reorden`, `/necesidad-compra`, `/inventario-matriz`, `get_notificaciones`, `_transferencias_completo`, 5 reportes | `/reabastecimiento/lista`, `/resumen`, `/alertas`, `/simular`, `/propuestas` |

La coexistencia fue **deliberada** (F3 del plan anterior): A-0.7 de la auditoría 50 midió que
cambiar la fórmula altera más de un 30 % el ROP del **54,2 %** de los SKU con venta reciente
— una decisión de política de negocio, no un refactor. Pero la consecuencia práctica es que
hoy un usuario de Bodega ve el mismo artículo con dos puntos de reorden distintos en dos
pantallas (`/bodega/almacenes` vs `/bodega/reabastecimiento`) sin ninguna señal de por qué.

**Esa decisión de negocio sigue pendiente y es el eje de la Fase 5.**

### D-2 (ALTO) — Dos vocabularios de estado para el mismo artículo

- `WarehouseService._estado_stock` → `Crítico` / `Cerca` / `Seguro` / `Exceso` / `Inmovilizado`
- `replenishment_engine.evaluar_riesgo` → `critico` / `alto` / `medio` / `bajo` / `sin_demanda`

Ambos se muestran a un usuario `bodega` en la misma sesión. "Crítico" no significa lo mismo
en las dos pantallas: uno mide *stock < ROP determinista*, el otro *cobertura vs. lead time*.

### D-3 (MEDIO) — Estadística de demanda calculada dos veces, desde dos consultas distintas

`WarehouseRepository.get_inventario_productos` (salidas de 30 días) y
`get_metricas_reabastecimiento` (salidas mensuales de 36 meses) golpean el mismo snapshot con
dos agregaciones diferentes. Una petición que hoy pinta el Dashboard de Bodega completo
ejecuta ambas.

### D-4 (MEDIO) — Coeficiente de variación con tres calibraciones

- `replenishment_engine`: `CORTE_XYZ_X=0.39` / `CORTE_XYZ_Y=0.61` (terciles reales del catálogo)
- `WarehouseService._justificacion_transferencia`: `BODEGA_CV_ALTA=1.2` / `BODEGA_CV_MEDIA=2.5`
- `goal_calculation_engine._coeficiente_variacion`: dominio de metas comerciales — **no tocar**,
  no es inventario.

Los dos primeros miden lo mismo (variabilidad de demanda de un SKU) con cortes que difieren en
un factor de 3-4×. La auditoría 50 ya documentó que reutilizar los de transferencias dejaba al
96,6 % del catálogo en una sola clase XYZ.

### D-5 (MEDIO) — Dos respuestas a "¿qué compro?"

`GET /necesidad-compra` (RN-B1/RN-B4, ordena por volumen de ventas) y
`GET /reabastecimiento/lista` (ordena por riesgo de quiebre) responden la misma pregunta de
negocio con criterios opuestos, y ambas están vivas en el frontend.

### D-6 (ALTO, rendimiento) — La lista completa se recalcula N veces por interacción

`get_lista_reabastecimiento` evalúa **todo el catálogo filtrado** (~8.150 filas: consulta +
Pareto + estadística + SS/ROP por fila) y no cachea nada. La llaman:
`get_resumen`, `get_alertas`, `get_explicacion`, `crear_propuesta` y `simular` (**dos veces**:
actual + simulado). Abrir la página de Reabastecimiento con la campana de notificaciones
activa dispara varias pasadas completas sobre el mismo dato.

### D-7 (BAJO) — Alertas por dos caminos

`NotificationService._generar_bodega` llama a `WarehouseService.get_notificaciones` **y** a
`ReplenishmentService.get_alertas`. La no-superposición es deliberada y está documentada, pero
el reparto de qué señal vive en cuál generador no es evidente para quien agregue la siguiente.

---

## 3. Arquitectura objetivo

Paquete nuevo `backend/app/inventory/`, con frontera explícita y una sola puerta de entrada:

```
backend/app/inventory/
├── __init__.py            # API pública del módulo: SOLO lo que otros módulos importan
├── engine.py              # ← replenishment_engine.py movido tal cual (motor puro, sin I/O)
├── service.py             # ← replenishment_service.py + lo absorbido de WarehouseService
├── config_service.py      # ← replenishment_config_service.py
├── repository.py          # consultas de inventario extraídas de WarehouseRepository
├── proposals.py           # propuestas de compra (repo + máquina de estados)
└── schemas.py             # ← schemas/replenishment.py
```

Reglas de frontera (verificadas por un test de guardia, §4.6; **ajustado durante la
implementación real, ver `docs/auditoria/52_...md` §Aplicado/Fase 7**: la regla 1 original
—"nadie importa `engine` directamente"— resultó incompatible con la Fase 2, que exige
que `WarehouseService` llame a `engine` para las fórmulas absorbidas. La invariante que
realmente se enforza es la regla 2):

1. El resto del sistema importa la orquestación (`ReplenishmentService`,
   `ReplenishmentConfigService`, los repositorios) de `app.inventory` (`__init__.py`);
   `engine.py` sí se importa directamente donde haga falta el motor puro (Fase 2, tests).
2. `engine.py` **no importa nada de `app.repositories`, `app.models`, `app.database`,
   `app.core.config` ni `sqlalchemy`** — sigue siendo puro y testeable sin base de datos
   (verificado por AST en `test_inventory_module_boundary.py`, no solo por convención).
3. `WarehouseService` pasa a **consumir** `app.inventory.engine`, no a reimplementar sus
   fórmulas.

Esto da la independencia que pide el requerimiento (un dueño, una frontera, un contrato) sin
un proceso, un broker ni un despliegue nuevos.

---

## 4. Fases

### Fase 0 — Auditoría previa (obligatoria, solo `SELECT`, sin escribir código)

Salida: `docs/auditoria/52_modulo_inventario_centralizado.md`.

- **A-0.1** Inventario exhaustivo de consumidores de cada fórmula duplicada (D-1..D-4).
  Método: `grep` + lectura, tabla `función → llamadores → endpoint → pantalla`.
- **A-0.2** Cuantificar D-1 contra el EDW real: para el catálogo completo, ¿en cuántos SKU
  discrepan el estado determinista y el riesgo estocástico? Tabla cruzada
  `estado_stock × riesgo` con conteos reales. **Este número decide la Fase 5.**
- **A-0.3** Medir D-6: latencia real de `GET /reabastecimiento/resumen`, `/lista`, `/alertas`
  y `POST /simular` contra `bi_backend`, y número de pasadas completas por request.
- **A-0.4** Confirmar que ningún módulo **fuera** de Bodega (Gerencia, Ventas, Admin) calcula
  stock/ROP/cobertura por su cuenta. Hipótesis a refutar: creo que no, pero el requerimiento
  afirma que sí y debe verificarse antes de asumirlo.
- **A-0.5** Verificar que la RLS por almacén (`resolve_almacenes_filter`, RN-B10) se aplica en
  **todas** las consultas que el módulo nuevo va a heredar — un refactor de repositorio es
  exactamente el momento en que una restricción de seguridad se pierde en silencio.
- **A-0.6** Inventariar los tests que cubren hoy cada fórmula, para saber cuáles deben seguir
  verdes sin modificarse (red de seguridad del refactor).

**Criterio de salida:** si A-0.2 muestra discrepancia baja (< 10 % del catálogo), la Fase 5
puede unificar directamente; si es alta, la Fase 5 se convierte en una decisión de gerencia
con evidencia, no en un cambio de código.

### Fase 1 — Crear el paquete, sin cambiar comportamiento

Refactor puramente mecánico, **cero cambios de lógica**:

- Mover `replenishment_engine.py` → `app/inventory/engine.py`,
  `replenishment_service.py` → `app/inventory/service.py`,
  `replenishment_config_service.py` → `app/inventory/config_service.py`,
  `replenishment_config_repository.py` + `replenishment_proposal_repository.py` →
  `app/inventory/repository.py` / `proposals.py`,
  `schemas/replenishment.py` → `app/inventory/schemas.py`.
- `app/inventory/__init__.py` reexporta la API pública.
- Actualizar imports en `dependencies.py`, `routes/replenishment.py`, `notification_service.py`
  y los tests.
- **No se toca el router ni ningún contrato HTTP.**

**Validación:** `pytest backend/tests/unit` con exactamente el mismo conteo de tests y 0 fallas;
`GET /reabastecimiento/resumen` devuelve un JSON byte a byte idéntico al de antes del refactor
(capturado antes de empezar).

### Fase 2 — Absorber la estadística de inventario que hoy vive en `WarehouseService`

Mover al motor puro, **conservando la fórmula exacta actual** (no es el momento de cambiarla):

- `_salida_diaria`, `_punto_reorden_efectivo`, `_dias_inventario`, `_estado_stock` →
  `engine.py`, como funciones puras nuevas (`demanda_diaria_simple`, `punto_reorden_determinista`,
  `dias_inventario`, `estado_stock`), con los mismos `settings.BODEGA_*` recibidos por parámetro
  (el motor no lee `settings`, regla de frontera §3.2).
- `WarehouseService._enriquecer_producto` pasa a llamarlas en vez de tener el cálculo inline.

Con esto, **las dos fórmulas de D-1 conviven dentro del mismo módulo**, una al lado de la otra,
con la diferencia documentada en un solo archivo en vez de repartida en dos servicios.

**Validación:** los tests existentes de `test_warehouse_estado_stock.py` y
`test_replenishment_engine.py` deben pasar **sin modificarse**. Si hay que tocar un test, la
fase cambió comportamiento y hay que revisar por qué.

### Fase 3 — Unificar el coeficiente de variación (D-4)

- Una sola función `engine.coeficiente_variacion` (ya existe) usada también por
  `_justificacion_transferencia`.
- Los **cortes** siguen siendo dos juegos distintos y explícitos
  (`CORTE_XYZ_*` para clasificación XYZ, `BODEGA_CV_*` para decidir transferencias), porque la
  auditoría 50 ya demostró que son decisiones distintas — pero pasan a estar declarados juntos y
  documentados como tales, en vez de parecer una inconsistencia.

### Fase 4 — Rendimiento: una sola pasada por request (D-6)

- `get_lista_reabastecimiento` se parte en `_evaluar_catalogo(filtros, overrides)` (caro,
  memoizable) + los post-filtros y el orden (baratos).
- Memoización **por request** con clave `(filtros, overrides, almacenes_permitidos)` — la RLS
  **debe** entrar en la clave, o un usuario vería el catálogo cacheado de otro. Ámbito de la
  caché: el objeto servicio, que FastAPI ya construye por request vía `Depends`.
- `simular` deja de hacer dos pasadas completas: el resumen actual sale de la evaluación
  memoizada y solo el simulado se recalcula.
- **Test obligatorio:** `call_count == 1` sobre `get_metricas_reabastecimiento` en un flujo
  resumen + alertas (mismo patrón de guarda que ya existe en `test_commission_simulation_service.py`).

**Validación:** repetir la medición A-0.3 y reportar el antes/después real.

### Fase 5 — Decisión de política: qué hacer con los dos motores (D-1, D-2, D-5)

**Esta fase no es un refactor: es una decisión de negocio que necesita a gerencia.** El plan
entrega la evidencia (A-0.2) y tres opciones, no elige por su cuenta:

- **(a) Convivencia explícita.** Cada pantalla declara qué motor usa y por qué. Cambio mínimo,
  la ambigüedad de D-2 persiste pero deja de ser invisible.
- **(b) Estocástico como oficial**, determinista conservado tras una env var de rollback
  (mismo patrón que `COMISION_MODO`, ya probado en este proyecto). `/necesidad-compra` pasa a
  ser una vista del motor único. Requiere aceptar el cambio de ROP en el 54,2 % del catálogo
  medido en A-0.7.
- **(c) Determinista para el día a día, estocástico para planeación de compra.** Formaliza la
  separación actual con vocabularios distintos a propósito.

Sea cual sea la elegida, el vocabulario de estado (D-2) se unifica: **un artículo tiene un
estado y un riesgo, con nombres que no se pisan**, y la traducción vive en un solo sitio.

### Fase 6 — Frontend: el módulo como un espacio propio

- Ruta padre `/bodega/inventario` con vistas hijas: **Centro de Decisiones** (KPIs),
  **Lista Inteligente**, **Simulador**, **Propuestas**, **Política**. Hoy las cinco están
  apiladas en `BodegaReabastecimiento.tsx` (545 líneas).
- Extraer componentes reutilizables a `components/bodega/` (hoy solo tiene `BodegaFilterBar` y
  `PrediccionComprasChart`): tabla de artículos con fila expandible, panel de KPIs de riesgo,
  badge de riesgo/estado, formulario de política.
- `BodegaFilterBar` se reutiliza tal cual — ya es el filtro compartido del módulo.
- Sin cambios de contrato: el frontend sigue consumiendo los mismos endpoints.

### Fase 7 — Gobernanza y cierre

- Test de guardia de frontera (§3): falla si alguien importa `app.inventory.engine` o
  `app.inventory.repository` desde fuera del paquete, o si `engine.py` importa I/O.
- Reglas nuevas en `docs/auditoria/02_reglas_negocio_validadas.md` §25 (continúa RN-RB10).
- Actualizar `CLAUDE.md` (§Objetos importantes) y el reporte de auditoría 52 con lo aplicado.
- OpenAPI ya se genera solo; agregar descripciones de negocio a los endpoints del módulo para
  que `/docs` sea la documentación que pide el requerimiento.

---

## 5. Riesgos

| Riesgo | Mitigación |
|---|---|
| Un refactor de repositorio pierde la RLS por almacén (RN-B10) | A-0.5 la inventaría antes; `test_bodega_rls.py` debe seguir verde en cada fase |
| La Fase 2 cambia un número sin querer | Los tests existentes deben pasar **sin modificarse**; cualquier test tocado es señal de alarma |
| La caché de Fase 4 filtra datos entre usuarios | La RLS entra en la clave de caché; test explícito de aislamiento |
| La Fase 5 se aplica sin decisión de gerencia | Fase 5 **no toca código** hasta tener la decisión por escrito |
| El alcance se desborda a Gerencia/Ventas | A-0.4 acota: si esos módulos no calculan inventario, quedan fuera |

---

## 6. Orden recomendado y corte de valor mínimo

Fases 0 → 1 → 2 → 4 son el **corte mínimo con valor real**: dejan el módulo con frontera,
dueño único de las fórmulas y sin el problema de rendimiento, sin ninguna decisión de negocio
pendiente y sin cambio de contrato. Fases 3, 6 y 7 son incrementales. **La Fase 5 se agenda
aparte** — es una conversación con gerencia, no una sesión de código.

No hay migración de esquema en ninguna fase salvo que la Fase 5 opte por (b); en ese caso, la
siguiente sería `0019_*`.
