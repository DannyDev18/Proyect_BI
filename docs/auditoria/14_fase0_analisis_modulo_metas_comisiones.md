# 14 — Fase 0: Análisis arquitectónico del módulo Metas y Comisiones

- **Fecha:** 2026-07-09
- **Objetivo:** analizar el repositorio actual (backend, EDW, frontend, ML) para determinar cómo integrar un módulo completo de Metas y Comisiones (generación inteligente de metas, seguimiento de cumplimiento, cálculo de comisiones, dashboard vendedor, dashboard gerencia) sin romper la arquitectura existente.
- **Alcance:** backend (`backend/app/`), EDW (`edw/*.sql` + consultas reales contra `bi_postgres_edw`), frontend (`frontend/src/`), infraestructura ML relacionada con metas.
- **Método:** revisión estática de código + `\d` y `SELECT` de solo lectura contra el EDW real vía `docker exec bi_postgres_edw psql`. **Cero escrituras** a Producción ni al EDW. No se creó código, tablas ni componentes.
- **Estado:** ⏸️ Análisis. Sin implementación. Esperando confirmación para pasar a Fase 1.

---

## 1. Arquitectura actual encontrada

El sistema **ya tiene un módulo de Metas construido como MVP funcional**, no es territorio vacío. La "Comisión" hoy es solo un atributo estático dentro de ese módulo, sin lógica de liquidación.

**Backend** — patrón en capas estricto `routes → services → repositories`, RBAC con 4 roles fijos (`gerencia`, `administrador`, `ventas`, `bodega`; **no existe rol `VENDEDOR` ni `SUPERVISOR`**), excepciones de dominio (`DomainError` y subclases) traducidas a HTTP en `main.py`, filtrado de datos por `current_user.sucursal` vía `resolve_sucursal_filter()` — **nunca por vendedor individual**.

**EDW** — modelo estrella clásico Kimball: `fact_ventas_detalle` (520,760 filas, 2018-01-02 a 2026-07-09) con FKs a `dim_vendedor`, `dim_sucursal`, `dim_producto`, `dim_cliente`, `dim_fecha`, `dim_estado_documento`. Existe además una fact vacía (`edw.fact_metas_comerciales`, 0 filas) que fue diseñada para metas pero nunca se pobló — las metas reales viven en `public.metas_comerciales_operativas` (9 filas).

**Frontend** — router anidado con `RouteKey` punteado (`gerencia.metas` ya registrado), patrón página→hook→servicio→tipos→queryKeys consistente, `ChartCard` + Recharts reutilizable. Ya existe `/gerencia/metas` con `GoalsConsole.tsx` funcional (generación ML, aprobación/rechazo). El rol `ventas` ya ve 4 KPIs de meta embebidos en su dashboard, pero **no tiene una vista dedicada** de comisiones/metas propia.

**ML** — `goals_rf_model`/`goals_best_model` (RandomForest) predice un *ratio de crecimiento* con 7 features, aplicado sobre el mes anterior con 3 cappings en cascada (0.8–1.2) y un `factor_presion` libre. Contrato declarativo en `ml/contracts/models/goals.json` (según Fase 0 de la capa de contratos ML, doc 12/13).

---

## 2. Archivos relevantes encontrados

### Backend
| Archivo | Rol |
|---|---|
| `backend/app/api/routes/goals.py` | Router, prefijo `/gerencia/goals`, guard `PermissionChecker(["gerencia","administrador"])` |
| `backend/app/services/goals_service.py:20-124` | Lógica: `generate_proposals`, `_predict_goal_amount`, cappings `GROWTH_RATIO_MIN/MAX`, `META_VS_PROMEDIO_MOVIL_MIN/MAX`, `META_VS_ANIO_ANTERIOR_MIN` (todos 0.8–1.2) |
| `backend/app/repositories/goal_repository.py:26-213` | SQL contra `edw.fact_ventas_detalle` + CRUD ORM contra `public.metas_comerciales_operativas`; `get_commission_tracking`/`get_commission_report` (líneas 177-197) — **solo LEFT JOIN meta↔vendedor, sin venta real del período ni comisión devengada** |
| `backend/app/models/goal.py:6-51` | `Goal` → `public.metas_comerciales_operativas`; ya trae `comision_base_pct`, `bono_sobrecumplimiento` |
| `backend/app/models/user.py:7-34` | `User` con `id_vendedor_origen` (puente a `edw.dim_vendedor.codven`); docstring explícito: `usuarios` es independiente del EDW |
| `backend/app/core/deps.py:35-110` | `get_current_user`, `PermissionChecker`, JWT |
| `backend/app/api/dependencies.py:35-36,85-89,108-128` | DI factories + `resolve_sucursal_filter` (solo por sucursal) |
| `backend/app/core/exceptions.py` | Jerarquía `DomainError` a reutilizar |

### EDW
| Archivo/objeto | Rol |
|---|---|
| `edw/02_dimensiones.sql`, `edw/03_hechos.sql` | DDL de `dim_vendedor`, `fact_ventas_detalle`, `fact_metas_comerciales` |
| `edw/07_public_app_tables.sql` | DDL de `public.metas_comerciales_operativas`, `public.usuarios` |
| `edw.fact_metas_comerciales` | Existe, vacía, diseñada para metas granulares por producto — no usada hoy |

### Frontend
| Archivo | Rol |
|---|---|
| `frontend/src/router/AppRouter.tsx:74-84` | Ruta anidada `/gerencia` → hijo `metas` (patrón a replicar) |
| `frontend/src/constants/permissions.ts:10,28-32` | `RouteKey='gerencia.metas'` ya declarado; `ROUTES` con `allowedRoles` |
| `frontend/src/components/goals/GoalsConsole.tsx` | Consola de gerencia: generación ML + tabla aprobación |
| `frontend/src/hooks/goals.ts`, `services/goals.ts`, `types/goals.ts` | Dominio `goals` completo del lado gerencia |
| `frontend/src/pages/DashboardVentas.tsx:44-91` | Consume `useSalesGoals()` → KPIs de meta embebidos (vista vendedor parcial) |
| `frontend/src/components/ui/ChartCard.tsx`, `utils/chartTheme.ts` | Contenedor de gráfico + tema Recharts reutilizable |

### ML
| Archivo | Rol |
|---|---|
| `ml/contracts/models/goals.json` | Contrato del modelo de metas (7 features) |
| `ml/src/training/train_goals_prediction.py` | Entrenamiento |
| `backend/app/ml/inference.py` (`predict_goal_growth_ratio`) | Serving |

---

## 3. Tablas existentes relacionadas (verificado con `\d` y `SELECT` reales)

| Tabla | Filas | Grano | Campos clave para Metas/Comisiones |
|---|---|---|---|
| `edw.fact_ventas_detalle` | 520,760 | 1 fila = 1 línea de factura | `fecha_sk`, `producto_sk`, `cliente_sk`, `sucursal_sk`, `vendedor_sk`, `estado_documento_sk`, `subtotal_neto`, `total_linea`, `cantidad`, `margen_bruto` (nullable), `pct_margen` |
| `edw.dim_vendedor` | 25 (24 activos + centinela `-1`) | 1 fila = 1 vendedor SAP | `codven` (VEN01…VEN24), `nombre_vendedor`, `comision` (numeric 5,2 — **campo de comisión ya existe en la dimensión, sin uso actual verificado**) |
| `edw.dim_sucursal` | 8 | — | `codigo_sucursal`, `nombre_sucursal` |
| `edw.dim_producto` | — | SCD2 | `clase`/`nombre_clase`, `subclase`/`nombre_subclase` → **categoría disponible para metas por categoría** |
| `edw.dim_fecha` | 7,671 (2010–2030) | día | `anio`, `mes`, `trimestre`, `semestre`, `es_feriado` (nunca poblado, deuda conocida) → granularidad mensual disponible sin trabajo extra |
| `edw.dim_estado_documento` | 2 | junk dim | `es_devolucion`, `estado_factura` — filtro obligatorio de población en cualquier cálculo de venta real |
| `edw.fact_metas_comerciales` | **0** | diseñada: fecha×vendedor×sucursal×producto | FK completas a las 4 dims; **existe pero nunca se cargó** — candidata natural para metas granulares por producto, hoy no usada |
| `public.metas_comerciales_operativas` | 9 | mes×vendedor×sucursal (agregado, sin producto) | `anio`, `mes`, `id_vendedor_origen` (**confirmado: coincide 1:1 con `dim_vendedor.codven`**, ej. `VEN01`), `sucursal` (texto libre, no FK a `dim_sucursal`), `monto_meta`, `unidades_meta`, `comision_base_pct`, `bono_sobrecumplimiento`, `estado` (PROPUESTA/APROBADA/RECHAZADA — **esto es el estado de aprobación de la META, no de pago de comisión**) |
| `public.usuarios` | — | 1 fila = 1 usuario de la app | `id_vendedor_origen` (FK lógica opcional a `dim_vendedor.codven`), `sucursal`, `rol_id` |

**Hallazgo de calidad de datos (nuevo, verificado por SELECT):** el usuario semilla `id=4, nombre="Vendedor Costa"` tiene `id_vendedor_origen='102'`, que **no coincide con ningún `codven` real** (los códigos reales son `VEN01`…`VEN24`). Es un dato de prueba inconsistente con el patrón real — no bloquea el diseño, pero si se usa para pruebas de "vista propia del vendedor" no traerá datos. Además, **24 de 25 vendedores activos en `dim_vendedor` no tienen ningún usuario de `public.usuarios` vinculado** — hoy la plataforma no tiene login para vendedores individuales, solo para el rol agregado `ventas`.

---

## 4. Propuesta de arquitectura futura

**No crear un módulo aislado.** El patrón existente (`goals.py` → `goals_service.py` → `goal_repository.py` → `models/goal.py`) ya está etiquetado conceptualmente "🎯 Metas y Comisiones" (`api/routes/api.py:16`) y ya tiene los campos de comisión embebidos en `Goal`. La arquitectura futura **extiende** ese vertical en vez de duplicarlo:

- **Separar por responsabilidad, no por capa técnica**: mantener `Goal` (`metas_comerciales_operativas`) como la meta *propuesta/aprobada* (mutable, editable por gerencia), y modelar la comisión *devengada/liquidada* como una entidad nueva e **inmutable** (ver §5) — evita mezclar "meta editable" con "historial de pago", que es un antipatrón que el propio esquema actual ya empieza a insinuar (`estado` de `Goal` solo cubre aprobación, no liquidación).
- **Backend**: nuevo repositorio `commission_repository.py` que calcule cumplimiento real haciendo el JOIN que hoy falta: `metas_comerciales_operativas` (o su reemplazo) ⋈ `fact_ventas_detalle` filtrado por `dim_estado_documento` (población válida) agrupado por `vendedor_sk`/mes, para obtener venta real vs. meta. Reutilizar `resolve_sucursal_filter` y extenderlo con un filtro por `id_vendedor_origen` cuando el rol sea "vendedor individual".
- **Rol vendedor individual**: hoy **no existe** un rol `VENDEDOR` distinto de `ventas` (catálogo cerrado de 4 roles en `public.roles`, seed en `edw/08_seed_roles_usuarios.sql`). Dos caminos, a decidir con el usuario antes de Fase 1:
  1. Mantener el rol `ventas` agregado y filtrar "mis comisiones" por `current_user.id_vendedor_origen` (cambio de comportamiento, no de catálogo de roles — más barato).
  2. Añadir un 5º rol `vendedor` al catálogo cerrado (cambio de regla de negocio documentada en `docs/auditoria/02_reglas_negocio_validadas.md`, requiere migración de `public.roles`/seed — más invasivo).
- **EDW**: no se requiere modificar el modelo dimensional existente. `fact_metas_comerciales` (vacía, ya con grano fecha×vendedor×sucursal×producto) es candidata a poblarse solo si se decide llevar las metas a nivel de detalle por producto; si las metas siguen siendo mensuales agregadas por vendedor/sucursal, `public.metas_comerciales_operativas` sigue siendo suficiente y no hace falta tocar `edw.*`.
- **Frontend**: extender el dominio `goals` existente (mismo archivo `types/goals.ts`/`services/goals.ts`/`hooks/goals.ts`, no fragmentar en `goalsVendedor.ts`), añadir una ruta hija nueva bajo `ventas` (hoy `ventas` es ruta simple, no padre con `index`+hijos — hay que convertirla al mismo patrón que `gerencia`), y un nuevo `RouteKey` tipo `ventas.metas` o `ventas.comisiones`.

---

## 5. Tablas nuevas necesarias

Evaluadas contra lo que ya existe — **evitar crear lo que ya está cubierto**:

| Tabla propuesta en el enunciado | Veredicto |
|---|---|
| `bi_metas` | ❌ No crear — ya existe `public.metas_comerciales_operativas`, cumple el mismo propósito |
| `bi_usuario_vendedor` | ❌ No crear — ya existe el puente `public.usuarios.id_vendedor_origen ↔ edw.dim_vendedor.codven` |
| `bi_meta_detalle_categoria` | 🟡 Evaluar — si se requiere meta por categoría de producto (no solo vendedor/sucursal), `edw.dim_producto.clase`/`nombre_clase` ya tiene la categoría; se necesitaría una tabla nueva de metas a ese grano (o poblar `edw.fact_metas_comerciales`, que ya tiene `producto_sk`) |
| `bi_comisiones` (comisión **liquidada**) | ✅ Necesaria — no existe hoy nada que registre comisión ya calculada/pagada por período. Debe ser **append-only/inmutable** (a diferencia de `metas_comerciales_operativas`, que es editable), con snapshot de: `vendedor`, `periodo (anio/mes)`, `venta_real` (calculada del EDW en el momento de liquidar), `monto_meta` (copiado, no referenciado, para que cambios futuros a la meta no alteren comisiones ya liquidadas), `pct_cumplimiento`, `comision_base_pct` (copiado), `bono_aplicado`, `comision_calculada`, `estado_pago` (PENDIENTE/PAGADA), `fecha_liquidacion` |
| `bi_reglas_comision` | 🟡 Evaluar — hoy `comision_base_pct` y `bono_sobrecumplimiento` son campos planos por fila de meta (un único tramo). Si el negocio requiere tramos (ej. 2% hasta 100% de meta, 4% sobre excedente), se necesita una tabla de reglas parametrizadas; si el esquema actual de 2 campos alcanza, no hace falta. **Pendiente de validar con el usuario/negocio real**, no asumir. |

**Conclusión de esta sección**: de las 5 tablas propuestas en el enunciado como ejemplo, **solo 1 es claramente necesaria** (`bi_comisiones`/liquidación), 2 dependen de una decisión de negocio pendiente de confirmar (categoría, tramos), y 2 ya están cubiertas por tablas existentes.

---

## 6. Endpoints necesarios

Extendiendo `backend/app/api/routes/goals.py` (mismo router, mismo prefijo `/gerencia/goals`, o un sub-router `/gerencia/goals/commissions`):

| Endpoint | Rol permitido | Propósito | Reutiliza |
|---|---|---|---|
| `GET /gerencia/goals/tracking` | ya existe | seguimiento de metas (gerencia) | — |
| `GET /gerencia/goals/commissions?anio&mes` | gerencia, administrador | cumplimiento real + comisión calculada por vendedor (JOIN con `fact_ventas_detalle` que hoy falta) | `resolve_sucursal_filter`, `PermissionChecker` |
| `POST /gerencia/goals/commissions/{id}/settle` | gerencia, administrador | liquidar/marcar como pagada una comisión de un período | patrón `review` existente de `Goal` |
| `GET /ventas/goals/mine` o `GET /ventas/commissions/mine` | ventas (filtrado por `id_vendedor_origen` del usuario actual) | vista propia del vendedor: su meta, su venta real, su comisión estimada/liquidada | extensión de `resolve_sucursal_filter` con filtro por vendedor |

Todos deben lanzar excepciones de dominio existentes (`NotFoundError`, `ConflictError` si se intenta liquidar dos veces, etc.), nunca `HTTPException` directa, siguiendo la regla ya establecida en `main.py`.

---

## 7. Componentes frontend necesarios

| Componente/página | Tipo | Nota |
|---|---|---|
| `frontend/src/pages/DashboardComisionesVendedor.tsx` (nombre a definir) | Página nueva | Anidada bajo `/ventas`, requiere convertir la ruta `ventas` de simple a padre+`index` (mismo patrón que `gerencia` en `AppRouter.tsx:74`) |
| Extensión de `frontend/src/components/goals/` | Componente nuevo, ej. `CommissionTracker.tsx` | Tabla de cumplimiento + comisión, reutiliza `ChartCard`/`chartTheme` |
| Extensión de `frontend/src/hooks/goals.ts` | Hook nuevo, ej. `useCommissionTracking`, `useMyCommission` | Mismo archivo, no fragmentar dominio |
| Extensión de `frontend/src/services/goals.ts` | Funciones nuevas | Llamadas a los endpoints de §6 |
| Extensión de `frontend/src/types/goals.ts` | Tipos nuevos, ej. `CommissionRecord` | `{ vendedor, periodo, venta_real, monto_meta, pct_cumplimiento, comision_calculada, estado_pago }` |
| `frontend/src/constants/permissions.ts` | Nuevo `RouteKey` | ej. `'ventas.comisiones'`, `allowedRoles: ['ventas','administrador','gerencia']` |
| `frontend/src/components/layout/Sidebar.tsx` | Registro de icono | mismo patrón que `SUB_NAV_ICONS['gerencia.metas']` |

---

## 8. Riesgos encontrados

| # | Riesgo | Evidencia | Severidad |
|---|---|---|---|
| R-1 | **No hay cálculo de cumplimiento real ni de comisión devengada hoy** — `get_commission_tracking` solo trae la meta configurada, sin JOIN a `fact_ventas_detalle` | `goal_repository.py:177-197` (confirmado por agente Explore) | Alta — es el corazón funcional pedido y no existe |
| R-2 | **No existe rol "vendedor" individual**; el filtrado actual es solo por sucursal, no por vendedor | `models/role.py:9-17`, `dependencies.py:108-128` | Alta — bloquea el "dashboard vendedor" tal como se pide (`WHERE id_vendedor = usuario_actual`) hasta decidir el camino de §4 |
| R-3 | **24/25 vendedores activos no tienen usuario de plataforma vinculado**; el único vinculado (`id_vendedor_origen='102'`) no coincide con ningún `codven` real | `SELECT` directo contra `public.usuarios`/`edw.dim_vendedor` (esta auditoría) | Alta — sin esto, ningún vendedor puede hacer login y ver "su" dashboard; es un prerrequisito operativo, no solo técnico |
| R-4 | Mezclar "meta editable" (`estado` PROPUESTA/APROBADA/RECHAZADA) con "comisión liquidada" en la misma tabla sería un antipatrón — ya insinuado en el esquema actual | `metas_comerciales_operativas` DDL (`edw/07_public_app_tables.sql`) | Media — mitigado si `bi_comisiones` (§5) se modela como tabla separada e inmutable desde el inicio |
| R-5 | `sucursal` en `metas_comerciales_operativas` es texto libre, no FK a `edw.dim_sucursal` | `\d public.metas_comerciales_operativas` (esta auditoría) | Media — riesgo de inconsistencia de nombres al cruzar con el EDW; considerar normalizar en la reconstrucción |
| R-6 | `edw.fact_metas_comerciales` existe y está vacía — tentación de usarla sin validar si su grano (por producto) es el que realmente necesita el negocio | `\d edw.fact_metas_comerciales`, hallazgo ya documentado en auditoría 05 | Baja — no usar sin decisión de negocio explícita sobre metas por producto |
| R-7 | El campo `dim_vendedor.comision` (numeric 5,2) existe en el EDW sin consumidor identificado en el código revisado — posible fuente de verdad alternativa/duplicada frente a `comision_base_pct` de `metas_comerciales_operativas` | `\d edw.dim_vendedor` (esta auditoría) | Baja — aclarar cuál es la fuente oficial de % de comisión antes de construir la regla de cálculo |
| R-8 | El modelo ML de metas (`goals_rf_model`) predice el **monto de la meta**, no tiene relación con el cálculo de comisión — no confundir "meta inteligente" (ya cubierta) con "comisión inteligente" (no solicitada como ML todavía, según el enunciado) | `goals_service.py:30-88`, contexto de la Fase 0 de contratos ML (docs 12/13) | Informativo |

---

## 9. Plan recomendado de implementación por fases

1. **Fase 0.5 (decisión de negocio, previa a código):** confirmar con el usuario/negocio real: (a) modelo de roles para vendedor individual (§4, dos caminos), (b) si existen tramos de comisión o es un único porcentaje plano, (c) si las metas deben desagregarse por producto/categoría o el nivel mensual actual (vendedor×sucursal) es suficiente, (d) plan de alta de usuarios de plataforma para los 24 vendedores sin vincular (R-3).
2. **Fase 1 — Backend, cálculo de cumplimiento real:** extender `goal_repository.py` (o nuevo `commission_repository.py`) con el JOIN faltante `metas_comerciales_operativas ⋈ fact_ventas_detalle` (filtrado por `dim_estado_documento`), sin tocar el modelo dimensional. Nuevo endpoint `GET /gerencia/goals/commissions`.
3. **Fase 2 — Backend, liquidación:** tabla nueva `bi_comisiones` (inmutable, según decisión de §5/1), servicio de liquidación con excepciones de dominio, endpoint `POST .../settle`.
4. **Fase 3 — Backend, vista vendedor:** según la decisión de Fase 0.5(a), extender `resolve_sucursal_filter` o equivalente para filtrar por `id_vendedor_origen`; endpoint `GET /ventas/commissions/mine`.
5. **Fase 4 — Frontend, dashboard vendedor:** convertir ruta `ventas` a padre+hijo, nueva página/hook/servicio/tipos siguiendo el patrón de `gerencia.metas`, nuevo `RouteKey`.
6. **Fase 5 — Frontend, dashboard gerencia extendido:** ampliar `GoalsConsole.tsx` (o componente hermano) con cumplimiento real y estado de liquidación, reutilizando `ChartCard`.
7. **Fase 6 (opcional, futura, fuera de este alcance salvo pedido explícito):** si el negocio confirma necesidad de metas por producto/categoría, evaluar poblar `edw.fact_metas_comerciales` vía ETL en vez de tablas nuevas en `public.*`.

Cada fase debe seguir el flujo de trabajo estándar del proyecto: auditoría antes de modificar código, validación con `SELECT` contra el EDW real, tests (`pytest` backend), y actualización de `docs/auditoria/02_reglas_negocio_validadas.md` si surge una regla de negocio nueva (ej. la definición exacta de "comisión devengada").

---

**⏸️ Fin de la Fase 0. Sin código, sin tablas, sin componentes. Esperando confirmación del usuario, en particular sobre los puntos de la Fase 0.5 (§9.1), antes de iniciar la implementación.**
