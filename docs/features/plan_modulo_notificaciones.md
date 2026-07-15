# Plan de Implementación — Módulo de Notificaciones Inteligentes Segmentadas por Rol

> **Fecha:** 2026-07-14
> **Estado:** Propuesta (pendiente de auditoría previa según flujo de `CLAUDE.md` §Flujo de trabajo)
> **Alcance:** Backend FastAPI + Frontend React. Sin modelos ML nuevos (reutiliza `demand_rf`, `churn_rf`, `anomaly`, `sales_rf` ya servidos por `backend/app/ml/`).

## 1. Punto de partida (lo que YA existe — no reinventar)

| Pieza existente | Ubicación | Estado |
|---|---|---|
| Notificaciones de Bodega calculadas al vuelo | `backend/app/services/warehouse_service.py::get_notificaciones` (§4, RN-B7) | 4 tipos: stock crítico, agotamiento proyectado <7 días, transferencias sugeridas, reporte mensual. Sin persistencia ni estado de lectura. |
| Endpoint | `GET /analytics/bodega/notificaciones` (`warehouse.py:317`, `bodeguero_checker`) | Solo rol bodega. |
| Campana UI | `frontend/src/components/bodega/NotificationBell.tsx`, montada en `Header.tsx` solo si `canAccess(user.role, 'bodega')` | Dropdown con prioridades; sin marcar-leído. |
| Toasts efímeros | `frontend/src/store/toastStore.ts` | Feedback de acciones, no es centro de notificaciones. |
| Predicciones servidas | `prediction_service.py` (6 casos de uso con degradación con gracia) | Fuente de las notificaciones "inteligentes". |

**Decisión de diseño:** generalizar el patrón Bodega a los 4 roles, agregando **persistencia + estado de lectura + segmentación RBAC/RLS**. Las notificaciones de Bodega existentes se conservan como generador (no se rompe el contrato actual).

## 2. Decisiones de arquitectura

1. **Sin WebSockets en v1.** Polling con TanStack Query (`refetchInterval` 60s) — ya es el patrón del proyecto, no agrega infraestructura (el stack no tiene broker ni Socket.IO). WebSockets queda como fase opcional futura.
2. **Generación híbrida:** notificaciones **calculadas** (al vuelo, como Bodega hoy — siempre frescas, sin job) + notificaciones **persistidas** (eventos puntuales que necesitan estado de lectura: anomalía detectada, meta generada, liquidación de comisión disponible). Solo las persistidas van a la tabla nueva.
3. **Tabla en `public.*`** (no `edw.*`): es dato operativo de la app, igual que `metas_comerciales_operativas` y `recomendaciones_eventos`. Se crea vía `Base.metadata.create_all` + DDL en `edw/07` (aplicación manual en BD existente, restricción documentada).
4. **Plantillas por rol en el servicio**, no en el router ni en el frontend: dict `PLANTILLAS[evento][rol] -> callable(data) -> {titulo, mensaje, accion_url, prioridad}` en `notification_service.py`. El frontend solo renderiza el payload.
5. **RBAC + RLS obligatorios:** cada endpoint con su `PermissionChecker`; ventas filtra por `id_vendedor_origen`, bodega por `codalm`/`todos_los_almacenes` (mismo patrón de `warehouse.py`).
6. **Umbrales configurables** vía env vars `NOTIF_*` en `backend/app/core/config.py` (patrón `BODEGA_*` / `CROSS_SELL_*`). Nada hardcodeado.

## 3. Modelo de datos — `public.notificaciones`

```sql
CREATE TABLE public.notificaciones (
    id              BIGSERIAL PRIMARY KEY,
    tipo_evento     VARCHAR(50)  NOT NULL,   -- 'anomalia_detectada', 'meta_generada', ...
    rol_destino     VARCHAR(20)  NOT NULL REFERENCES public.roles(nombre) -- catálogo cerrado (regla 9)
    usuario_id      INTEGER      NULL REFERENCES public.usuarios(id),     -- NULL = todo el rol
    titulo          VARCHAR(200) NOT NULL,
    mensaje         TEXT         NOT NULL,
    accion_url      VARCHAR(300) NULL,       -- ruta SPA, ej. '/bodega/stock-reorden'
    prioridad       VARCHAR(10)  NOT NULL DEFAULT 'media',  -- alta|media|baja
    contexto        JSONB        NULL,       -- codart, id_vendedor_origen, etc. (para RLS y dedupe)
    leida_por       JSONB        NOT NULL DEFAULT '[]',     -- ids de usuario que la leyeron (destino = rol)
    fecha_creacion  TIMESTAMP    NOT NULL DEFAULT now(),
    fecha_expira    TIMESTAMP    NULL        -- auto-ocultar (ej. reporte mensual)
);
CREATE INDEX idx_notif_rol_fecha ON public.notificaciones (rol_destino, fecha_creacion DESC);
```

Nota: `leida_por` como JSONB de ids evita una tabla puente para el caso "notificación a todo un rol"; si el volumen crece, migrar a `public.notificaciones_lecturas`.

## 4. Backend — capas (routes → services → repositories, regla del proyecto)

### 4.1 Nuevos archivos
- `backend/app/models/notification.py` + `backend/app/schemas/notification.py` (`NotificacionOut`, reutiliza `Page[T]` de `schemas/pagination.py` para el historial).
- `backend/app/repositories/notification_repository.py` — CRUD + filtro por rol/usuario/RLS + dedupe por `(tipo_evento, contexto)` en ventana de 24h.
- `backend/app/services/notification_service.py` — orquestador:
  - `get_notificaciones(user)` → une **calculadas** (delegando a los generadores por rol) + **persistidas** no leídas/no expiradas.
  - `marcar_leida(user, notif_id)` / `marcar_todas(user)`.
  - `emitir(tipo_evento, rol_destino, data, usuario_id=None)` — punto único de emisión persistida, aplica plantilla y dedupe.
  - Cada generador envuelto en `try/except + logger.error + lista vacía` (patrón de degradación de `prediction_service.py` — un generador caído no tumba la campana).
- `backend/app/api/routes/notifications.py` — router registrado en `api.py` con prefijo `/notificaciones`:
  - `GET /notificaciones` (todas: calculadas + persistidas, por rol del token)
  - `POST /notificaciones/{id}/leer`, `POST /notificaciones/leer-todas`
  - `GET /notificaciones/historial` (paginado `Page[T]`)

### 4.2 Generadores por rol (reutilizando servicios existentes, cero ML nuevo)

| Rol | Evento | Fuente reutilizada | Tipo |
|---|---|---|---|
| bodega | Stock crítico / agotamiento / transferencias / reporte mensual | `warehouse_service.get_notificaciones` (tal cual, RN-B7) | Calculada |
| gerencia | Desvío del forecast semanal (real vs `sales_rf` > umbral `NOTIF_DESVIO_FORECAST_PCT`) | `prediction_service` (forecast) + repo de ventas | Calculada |
| gerencia | Metas propuestas pendientes de aprobar / liquidaciones en modo sombra con divergencia | `GoalMLService` / `comision_liquidaciones` | Persistida (al generar) |
| ventas | Clientes propios con churn alto nuevo (`churn_rf`, filtro RLS por `id_vendedor_origen`) | `prediction_service.predict_churn` | Calculada |
| ventas | Mi comisión del mes liquidada / meta asignada | flujo de metas existente | Persistida |
| administrador | Anomalía detectada (`anomaly`/isolation forest sobre `fact_logs_auditoria`) | `prediction_service.detect_anomalies` | Persistida (al correr detección) |
| administrador | Modelo ML no cargado (`/health` interno: `modelos_ml_listos=false`) | `ModelLoader` | Calculada |

Los puntos de emisión persistida se agregan **dentro de los servicios existentes** (ej. al final de `GoalMLService.generate_proposals` → `notification_service.emitir('metas_generadas', 'gerencia', ...)`), nunca en los routers.

### 4.3 Config nueva (`app/core/config.py`)
`NOTIF_POLL_SEGUNDOS` (frontend lo lee de un endpoint de config o se fija en 60), `NOTIF_DESVIO_FORECAST_PCT`, `NOTIF_CHURN_UMBRAL`, `NOTIF_MAX_POR_TIPO` (default 10, como Bodega hoy), `NOTIF_DEDUPE_HORAS` (24).

## 5. Frontend

1. **Generalizar la campana:** mover `components/bodega/NotificationBell.tsx` → `components/layout/NotificationBell.tsx`; consumir el endpoint unificado `GET /notificaciones` (el backend ya segmenta por rol del JWT). En `Header.tsx` se muestra para **todos** los roles (hoy solo bodega).
2. Nuevos: `src/types/notifications.ts`, `src/services/notifications.ts`, `src/hooks/useNotificaciones.ts` (`useQuery` con `refetchInterval: 60_000`, key en `constants/queryKeys.ts`).
3. UI de la card: título + mensaje + botón de acción (`accion_url` → `navigate`) + marcar leída (solo persistidas; las calculadas no llevan estado). Badge rojo si hay prioridad alta (se conserva el diseño actual).
4. Toast automático **solo** cuando el polling trae una persistida nueva de prioridad alta (reutiliza `toastStore`), para no ser ruidoso.
5. Compatibilidad: `useNotificacionesBodega` y el endpoint `/analytics/bodega/notificaciones` se conservan hasta migrar; se eliminan en la fase 4 tras validar paridad.

## 6. Fases y entregables

| Fase | Entregable | Validación |
|---|---|---|
| 0 | Reporte `docs/auditoria/31_modulo_notificaciones.md` (obligatorio ANTES de tocar código, flujo `CLAUDE.md`) + reglas RN-N1..N4 en `02_reglas_negocio_validadas.md` | Revisión doc |
| 1 | Tabla `public.notificaciones` (modelo SQLAlchemy + DDL `edw/07`, aplicación manual), repository, service con generadores **calculados** (bodega reutilizado + admin salud ML), router unificado | `pytest backend/tests/unit/test_notification_service.py` (generadores con repos fake), integración del router con RBAC (4 roles: cada uno solo ve lo suyo) |
| 2 | Emisión persistida (metas, liquidaciones, anomalías), estado de lectura, dedupe, historial paginado | `pytest` integración: emitir → leer → no reaparece; dedupe 24h |
| 3 | Frontend: campana global, hook con polling, toast de alta prioridad | oxlint + prueba manual con los 4 roles (usuarios seed de `edw/08`) |
| 4 | Generadores calculados de gerencia (desvío forecast) y ventas (churn RLS); deprecar campana/endpoint viejos de bodega | paridad de contenido vs endpoint viejo; `test_analytics_ml_endpoints.py` sigue verde |
| 5 (opcional) | WebSockets (salas por rol) si el polling queda corto | — |

## 7. Riesgos y salvaguardas

- **Rendimiento del polling:** los generadores calculados de bodega recorren inventario completo; cachear el resultado en el servicio (TTL = intervalo de polling) para no recalcular por cada usuario conectado.
- **Ruido:** límite por tipo (`NOTIF_MAX_POR_TIPO`) + fila resumen (patrón ya usado en bodega, `warehouse_service.py:966-971`).
- **RLS:** un vendedor jamás debe ver notificaciones de churn de clientes de otro vendedor — test de integración explícito por rol.
- **Degradación:** ningún generador puede lanzar hacia el router; excepciones de dominio (`app/core/exceptions.py`), nunca `HTTPException` en servicios.
- **No tocar Producción SAP:** todo se calcula sobre el EDW/`public.*`; ningún generador consulta el ERP.
