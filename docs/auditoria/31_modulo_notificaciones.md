# Auditoría 31 — Módulo de Notificaciones Inteligentes Segmentadas por Rol

- **Fecha:** 2026-07-14
- **Alcance:** implementación del módulo descrito en `docs/features/plan_modulo_notificaciones.md`. Capas afectadas: backend (`backend/app/`) y frontend (`frontend/src/`). **NO se modifica** `etl/` ni `ml/` (sin extractores, transformers ni modelos nuevos: se reutilizan `demand_rf`, `churn_rf`, `isolation_forest`, `sales_rf` ya servidos por `backend/app/ml/`).
- **Método:** lectura del código existente que ya implementa el patrón a generalizar (`warehouse_service.py::get_notificaciones`, `NotificationBell.tsx`, `toastStore.ts`), del patrón de capas del proyecto (routes → services → repositories, excepciones de dominio, paginación genérica, configuración por env vars) y de los puntos de integración propuestos (`goal_ml_service.py`, `prediction_service.py`). Sin acceso a Producción SAP (no aplica: módulo 100% sobre `public.*`/EDW ya cargado).

## 1. Punto de partida verificado (código real, no el resumen del plan)

| Pieza | Ubicación exacta | Detalle verificado |
|---|---|---|
| Generador de Bodega | `backend/app/services/warehouse_service.py:944-1010`, método `get_notificaciones(self, sucursal=None, almacen=None) -> list[dict]` | Devuelve `list[dict]` con claves `tipo`, `prioridad`, `mensaje`, `codart`. **No existe campo `accion_url` hoy** — el plan lo asume; hay que añadirlo al generalizar, no está en el dict actual. 4 tipos: `stock_critico` (top 10, líneas 957-965) + `stock_critico_resumen` si hay más de 10 (líneas 966-971, el "límite por tipo" que el plan referencia), `prediccion_agotamiento` (<7 días, 979-987), `transferencia_sugerida` (top 5, 991-999), `reporte_semanal` (1001-1008, dispara 5 días antes de fin de mes — el plan lo llama "reporte mensual" pero el `tipo` real en código es `reporte_semanal`; se mantiene el nombre de campo existente para no romper el contrato de Bodega). |
| Endpoint | `backend/app/api/routes/warehouse.py:317-326`, `GET /notificaciones` bajo prefijo `/analytics/bodega` | `dependencies=[Depends(bodeguero_checker)]`; `bodeguero_checker = PermissionChecker(allowed_roles=["administrador", "gerencia", "bodega"])` (línea 43, importado de `app.core.deps`). Nota: **ya incluye `gerencia` y `administrador`**, no solo `bodega` — el plan que dice "Solo rol bodega" es impreciso; hay que preservar ese acceso ampliado al generalizar. |
| Campana UI | `frontend/src/components/bodega/NotificationBell.tsx` (77 líneas) | Sin props; usa `useNotificacionesBodega(null)`; estado local `open`/click-outside/Escape; `prioridadStyles` mapea `alta/media/baja`; badge con cap en 99+. Generalizar implica parametrizar el hook de datos y el título. |
| Toasts | `frontend/src/store/toastStore.ts` (31 líneas) | Zustand, `push(message, variant='success'|'error')`, autodescarta a 4s. **Solo soporta 2 variantes** (`success`/`error`), no hay variante `info`/`alta-prioridad` — para el toast de alta prioridad del plan (§5.4) se reutiliza `variant='error'` o se extiende el store; se decide extender con una tercera variante `warning` para no forzar semántica incorrecta. |
| Predicciones | `backend/app/services/prediction_service.py` | Patrón de degradación con gracia confirmado: `try/except Exception as e: logger.error(...); return <default seguro>` en cada caso de uso. Nombres reales relevantes: `get_churn_risk(self, cliente_id)` (líneas 284-299, **no filtra por vendedor** — no hay RLS de vendedor en este método hoy, filtra solo por `cliente_id`) y `get_anomaly_status(self, transaccion_id)` (líneas 331-346, opera sobre **una transacción puntual**, no escanea `fact_logs_auditoria` completa). El plan asume `predict_churn`/`detect_anomalies` como métodos que barren una cartera/tabla — **no existen así**; los generadores nuevos deben construir la iteración (sobre cartera del vendedor / sobre logs recientes) en el servicio de notificaciones, no asumir que ya existe. |
| Punto de emisión de metas | `backend/app/services/goal_ml_service.py:142-184`, `generate_proposals` | Termina en línea 184 con `commit(); return registros_afectados`. No emite ningún evento hoy. Punto de inserción: entre el `commit()` (línea 183) y el `return` — **después** del commit para no emitir notificación de una transacción que pudo fallar. |
| Excepciones de dominio | `backend/app/core/exceptions.py` | Jerarquía `DomainError` → `NotFoundError`, `ConflictError`, `ValidationError`, `PermissionDeniedError`, `ModelNotLoadedError`, `ExternalDataError`, `ModelContractError`. Los generadores de notificaciones deben usar estas (nunca `HTTPException`), consistente con la regla de capas del proyecto. |
| Registro de modelos ORM | `backend/app/database/base.py` | Sin autodiscovery: cada modelo se importa a mano (`from app.models.x import X  # noqa: F401`). El modelo `Notification` **debe añadirse ahí explícitamente** o `Base.metadata.create_all` (invocado en `main.py:34`) no lo creará. |
| DDL espejo en `edw/07` | `edw/07_public_app_tables.sql` (182 líneas) | Estilo: `CREATE TABLE IF NOT EXISTS public.x (...)`, `COMMENT ON TABLE`/`COMMENT ON COLUMN` citando el reporte de auditoría, `CHECK` inline, índices al final del bloque. Nota explícita en líneas 111-113: tablas que viven en ambos caminos (ORM + DDL) deben mantenerse sincronizadas manualmente — **riesgo real, no hipotético**, ya documentado para otras tablas de este mismo archivo. |
| Paginación genérica | `backend/app/schemas/pagination.py` | `PaginationParams(page≥1, page_size 1..200 default 25)`, `Page[T]` genérico, `paginar(items, params)` pagina **en memoria** (no en SQL) — a tener en cuenta si el historial de notificaciones crece mucho; aceptable para v1 dado el volumen esperado (eventos puntuales, no un log de alto volumen). |
| Catálogo de roles | `edw/07_public_app_tables.sql:9-21` (`public.roles`) + seed `edw/08_seed_roles_usuarios.sql:9-12` | 4 roles exactos: `gerencia`, `administrador`, `ventas`, `bodega`. La FK `rol_destino → public.roles(nombre)` del plan es correcta y aplicable. |
| Patrón de test de servicio | `backend/tests/unit/test_goal_ml_service.py` | Repos mockeados con `MagicMock()`, se inyectan en el service, se configuran `return_value`/`side_effect`, se assertan resultado y llamadas. Aplica igual para `test_notification_service.py`. |

## 2. Hallazgos previos a la implementación

| # | Hallazgo | Severidad | Acción |
|---|---|---|---|
| H31-1 | El plan asume que `get_notificaciones` de Bodega ya expone `accion_url`; el campo no existe en el dict actual (`warehouse_service.py:944-1010`). | Media | Se añade `accion_url` al dict de cada notificación calculada de Bodega (retrocompatible: es un campo nuevo, no se quita ninguno) antes de unificar el formato en `notification_service.get_notificaciones`. |
| H31-2 | El plan dice que el endpoint de Bodega es "solo rol bodega"; en realidad `bodeguero_checker` permite `administrador`, `gerencia` y `bodega` (`warehouse.py:43`). | Baja | El router unificado `/notificaciones` debe replicar el acceso real por rol vía el JWT (cada quien ve lo suyo), no restringir de más ni de menos respecto al comportamiento actual de Bodega. |
| H31-3 | `prediction_service.get_churn_risk`/`get_anomaly_status` operan sobre un cliente/transacción puntual, no sobre una cartera o tabla completa — los generadores de "churn nuevo por vendedor" y "anomalía detectada" descritos en el plan (§4.2) no tienen una fuente batch lista para reutilizar. | Media | El generador de notificaciones debe construir la iteración batch en `notification_service.py` (consultar cartera del vendedor vía repositorio existente, o logs recientes de `fact_logs_auditoria`) y llamar a los métodos puntuales por cada candidato — documentado como diseño explícito en la Fase 4, no un defecto a corregir. |
| H31-4 | `toastStore.ts` solo soporta variantes `success`/`error`; el plan pide un toast diferenciado para prioridad alta. | Baja | Se extiende el store con una variante `warning` (cambio aditivo, sin romper los usos actuales de `success`/`error`). |
| H31-5 | Riesgo de desincronización DDL (`edw/07`) vs modelo SQLAlchemy, ya documentado como patrón de riesgo general del proyecto para tablas `public.*`. | Baja (aceptada, no bloqueante) | Se mantiene el mismo procedimiento manual que ya usa el proyecto para `recomendaciones_eventos`/comisiones: cambios de esquema en BD existente se aplican a mano; ambos archivos se generan en el mismo commit. |
| H31-6 | `Page[T].paginar` pagina en memoria; si el historial de notificaciones crece sin límite (sin purga), el endpoint de historial se degrada. | Baja | Aceptado para v1 (volumen bajo: solo eventos persistidos, no cálculo). Se documenta como límite conocido, no se resuelve en esta fase (no hay requerimiento de purga en el plan). |

## 3. Reglas de negocio nuevas (registradas en `02_reglas_negocio_validadas.md`)

- **RN-N1 (segmentación por rol y RLS):** toda notificación tiene `rol_destino` (catálogo cerrado de `public.roles`) y opcionalmente `usuario_id` (NULL = visible a todo el rol). Ventas filtra estrictamente por `id_vendedor_origen` del token; Bodega por `codalm`/`todos_los_almacenes`, replicando el mismo criterio RLS que ya usan sus endpoints de analítica. Un usuario nunca ve notificaciones fuera de su alcance de datos, aunque comparta rol con otro usuario.
- **RN-N2 (calculadas vs. persistidas):** las notificaciones **calculadas** (stock, forecast, churn) se generan al vuelo en cada `GET /notificaciones`, sin estado de lectura ni fila en base de datos. Las **persistidas** (metas generadas, liquidaciones, anomalías) se insertan una única vez vía `notification_service.emitir(...)`, con deduplicación de `(tipo_evento, contexto)` en una ventana de `NOTIF_DEDUPE_HORAS` (default 24h) para no repetir el mismo evento en cada polling.
- **RN-N3 (estado de lectura por rol destino):** cuando `usuario_id IS NULL` (notificación a todo el rol), `leida_por` acumula los ids de cada usuario que la marcó leída; la notificación deja de considerarse "no leída" para ese usuario específico sin afectar a los demás miembros del rol.
- **RN-N4 (degradación con gracia):** cada generador (calculado o disparador de emisión persistida) se ejecuta envuelto en `try/except Exception as e: logger.error(...)`, devolviendo lista vacía en caso de fallo — un generador caído nunca debe tumbar el resto de la campana ni el request completo, siguiendo el mismo patrón ya validado en `prediction_service.py`.

## 4. Decisiones de arquitectura (confirmadas tras la investigación)

1. Sin ETL/DDL nuevo en `edw.*` — todo el dato fuente ya está cargado (EDW) o es operativo de la app (`public.*`), igual que `recomendaciones_eventos` y las tablas de comisiones.
2. Capas backend: `notification_repository.py` (CRUD + filtro RLS + dedupe) → `notification_service.py` (orquestador: calculadas + persistidas, plantillas por rol, `emitir`/`marcar_leida`/`marcar_todas`) → `routes/notifications.py` bajo `/notificaciones`, cada endpoint con su `PermissionChecker` acorde a lo verificado en H31-2.
3. El generador de Bodega existente (`warehouse_service.get_notificaciones`) se reutiliza tal cual como fuente calculada, añadiendo solo el campo `accion_url` (H31-1); el endpoint viejo `/analytics/bodega/notificaciones` se conserva sin cambios de contrato hasta la Fase 4 (paridad validada antes de deprecar).
4. `Notification` (modelo SQLAlchemy) se añade a `backend/app/database/base.py` explícitamente (sin autodiscovery, confirmado); el DDL espejo va en `edw/07_public_app_tables.sql` en el mismo commit para evitar la desincronización de H31-5.
5. Sin dependencias nuevas: se reutilizan `Page[T]`/`PaginationParams`, `PermissionChecker`, `DomainError` y el patrón de configuración `NOTIF_*` en `config.py`.

## 5. Estado

- [x] Auditoría previa creada antes de modificar código (este documento)
- [x] Reglas RN-N1..N4 registradas en `docs/auditoria/02_reglas_negocio_validadas.md`
- [x] Fase 1 — tabla `public.notificaciones` (`backend/app/models/notification.py` + DDL espejo en
      `edw/07_public_app_tables.sql`), `notification_repository.py`, `notification_service.py`
      (generadores calculados: Bodega reutilizado con `accion_url` nuevo — H31-1 — y salud de
      modelos ML de Admin), router unificado `backend/app/api/routes/notifications.py` bajo
      `/notificaciones`, 13 tests en `backend/tests/unit/test_notification_service.py` (131/131
      tests unitarios del backend en verde).
- [x] Fase 2 — emisión persistida cableada en dos puntos reales verificados en el código
      (no los nombres asumidos por el plan original, ver H31-3): `GoalMLService.generate_proposals`
      emite `metas_generadas` a `gerencia` tras el commit (`backend/app/services/goal_ml_service.py`,
      inyección de `NotificationService` opcional vía `app/api/dependencies.py`), y
      `GET /admin/anomalies` (`backend/app/api/routes/admin.py`) emite `anomalia_detectada` a
      `administrador` cuando `PredictionService.get_anomaly_status` marca la transacción como
      anómala. Dedupe de 24h (RN-N2) evita reinsertar si se repite el mismo evento. Estado de
      lectura (`POST /notificaciones/{id}/leer`, `/leer-todas`) e historial paginado
      (`GET /notificaciones/historial`) ya implementados como parte del router unificado de
      Fase 1 (decisión de diseño: ambos endpoints dependen del mismo modelo/repository, separarlos
      en dos entregas habría sido artificial).
      **Decisión de alcance:** se descarta (por ahora) emitir `liquidacion_disponible` desde
      `CommissionService._persistir_snapshot` — ese método corre por vendedor en cada
      request de consulta de comisión (no es un job batch), y resolver `usuario_id` desde
      `id_vendedor_origen` requeriría acoplar `CommissionService` a `UserRepository` en un
      módulo ya señalado como frágil en `CLAUDE.md` (Comisiones Variables, piloto en sombra).
      El dedupe de 24h mitigaría el spam pero el riesgo/beneficio no lo justifica sin pedido
      explícito; queda documentado como trabajo futuro, no como pendiente de esta fase.
- [x] Fase 3 — frontend: `components/bodega/NotificationBell.tsx` movido a
      `components/layout/NotificationBell.tsx` (generalizado para los 4 roles, con acción
      "Ver"/navegación, marcar leída individual y "marcar todas"), montado en `Header.tsx`
      para cualquier usuario autenticado (antes solo si `canAccess(user.role, 'bodega')`).
      Nuevos `types/notifications.ts`, `services/notifications.ts`,
      `hooks/useNotificaciones.ts` (`useQuery` con `refetchInterval: 60_000`, clave
      `qk.notificaciones.lista()`), `useMarcarNotificacionLeida`/`useMarcarTodasLeidas`/
      `useHistorialNotificaciones`. Toast de alta prioridad (H31-4): `toastStore.ts` gana
      la variante `warning` (antes solo `success`/`error`), disparado únicamente para
      persistidas nuevas de prioridad alta (no en el primer tick, para no toastear el
      historial completo al cargar la página). `tsc -b` sin errores nuevos (el único error
      restante, `Select.tsx`, es preexistente y no relacionado, verificado con `git stash`).
- [x] Fase 4 — generadores calculados nuevos: **gerencia** (`_generar_gerencia`, desvío del
      forecast semanal) reutiliza `PredictionService.get_sales_forecast` y su
      `metricas.crecimiento_esperado` ya calculado -- no existe hoy un backtest real-vs-
      predicho por período en el código (H31-3), así que se usa esta señal honesta (%
      de la venta proyectada vs. la tendencia reciente) en vez de inventar una comparación
      que el modelo no expone; umbral `NOTIF_DESVIO_FORECAST_PCT`. **Ventas**
      (`_generar_ventas`, churn alto con RLS) reutiliza íntegro
      `Cartera360Service.get_lista_trabajo(codven)` (auditoría 32) en vez de reimplementar
      el shortlist+churn-batch -- el RLS por vendedor (RN-V3) y el churn real del modelo
      vienen gratis de ese servicio; umbral `NOTIF_CHURN_UMBRAL`. Reordenamiento de
      `backend/app/api/dependencies.py` para resolver el ciclo de definición
      (`get_cartera360_service` ahora se define antes de `get_notification_service`, que a
      su vez se define antes de `get_goal_ml_service`) -- sin cambios de comportamiento en
      los servicios ya existentes, solo orden de las fábricas de DI. 18/18 tests en
      `test_notification_service.py` (136/136 tests unitarios del backend en verde).
      **Deprecación del endpoint/hook viejos de Bodega** (paridad validada: ambos leían el
      mismo `WarehouseService.get_notificaciones`, y el nuevo router unificado lo sigue
      llamando igual; se confirmó que el frontend no tenía otro consumidor del endpoint
      viejo): se eliminó `GET /analytics/bodega/notificaciones`
      (`backend/app/api/routes/warehouse.py`, con nota explicando el reemplazo),
      `NotificacionBodega` (schema Pydantic y tipo TS, sin otros usos), y
      `useNotificacionesBodega`/`getNotificacionesBodega` del frontend (código muerto tras
      mover la campana en Fase 3). `tsc -b` y `oxlint` sin errores nuevos.
- [x] **Corrección post-implementación (2026-07-14):** `accion_url` de varias notificaciones
      apuntaba a rutas del frontend que no existen en `AppRouter.tsx` -- error propio,
      inventadas por analogía con los nombres de los endpoints del backend en vez de
      verificar el router real. `DashboardBodega`/`DashboardAdmin` son páginas únicas sin
      sub-rutas por sección (sin tabs direccionables por URL). Corregido:
      `/bodega/stock-reorden`, `/bodega/necesidad-compra`, `/bodega/transferencias-sugeridas`
      → `/bodega`; `/bodega/reportes/analisis-mensual` → `/bodega/reportes` (esta sí existe);
      `/admin/modelos` y `/admin/anomalies` → `/admin`; `/gerencia/goals` → `/gerencia/metas`
      (la ruta real del árbol de metas es `metas` anidada bajo `gerencia`, no `goals`).
      `/gerencia` (desvío forecast) y `/ventas/cartera360` (churn) ya eran correctas.
- [ ] Fase 5 (opcional, fuera de este alcance) — WebSockets
