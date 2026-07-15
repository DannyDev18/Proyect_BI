# Plan de Actualización — Módulo Administrador (Anomalías, Usuarios, MLOps)

> **Fecha:** 2026-07-14
> **Estado:** Propuesta (requiere auditoría previa `docs/auditoria/36_actualizacion_modulo_admin.md`)
> **Alcance:** `backend/app/api/routes/admin.py` (`/analytics/admin`: anomalías + audit-logs), `admin_ml.py` (`/admin/modelos`: MLOps), `users.py`/`roles.py`/`auth.py`, `frontend/src/pages/DashboardAdmin.tsx` + `UsersManagement.tsx` + `Settings.tsx`. Modelo reutilizado: `anomaly` (Isolation Forest sobre `edw.fact_logs_auditoria`).

## 0. Diagnóstico preliminar

| # | Hallazgo / sospecha | Evidencia | Severidad |
|---|---|---|---|
| A-1 | **Dashboard sin filtros:** `DashboardAdmin.tsx` consume `useAnomalyDetector()`, `useModelsStatus()` y `useAuditLogs(50)` sin parámetros — sin rango de fechas, sin filtro por usuario/severidad, y los audit-logs limitados a un `50` hardcodeado en el frontend. Para auditoría/fraude, no poder acotar por período es limitante grave. | `DashboardAdmin.tsx:33-36` | Alta |
| A-2 | **`/anomalies` sin parámetros de ventana:** el endpoint (`admin.py:16`) no recibe fechas ni límite — verificar sobre qué ventana corre el Isolation Forest en cada request y su costo (¿escanea todo `fact_logs_auditoria`, ~tabla completa, por request?). | `admin.py:16-30` | Alta (a verificar) |
| A-3 | **Anomalías sin triage:** no existe estado sobre una anomalía (nueva/revisada/descartada/confirmada). El admin ve la misma lista cada día sin poder marcar qué ya investigó — el detector pierde utilidad operativa. | ausencia en `admin.py` | Media |
| A-4 | **Gestión de usuarios (bugs recientes en esta sesión):** ya se corrigió la pérdida de foco del Drawer y el campo sucursal para rol ventas. Sospechosos restantes: validación de contraseña solo con `pattern` HTML (¿el backend valida la misma política?); `rol_id: 2` hardcodeado como default en `emptyForm` (¿2 es siempre el mismo rol en todos los despliegues? el seed podría cambiar ids); edición de usuario sin verificar colisión de email. | `UsersManagement.tsx:20-30, 311` | Media |
| A-5 | **Riesgos de seguridad ya documentados en CLAUDE.md que este módulo debe cerrar:** `docs/credenciales_sistema.md` versionado (¡con credenciales visibles en el editor ahora mismo!), CORS `"*"` por defecto, defaults inseguros de JWT/BD tolerados fuera de producción. | CLAUDE.md §Riesgos | Alta |
| A-6 | **MLOps (`/admin/modelos`):** el retrain solo funciona en dev (`ML_SOURCE_DIR` montado por override) — verificar que en producción-like el endpoint falla con mensaje claro y no con un 500 crudo; verificar que el estado de modelos refleja los 6 reales y detecta un `.pkl` faltante/corrupto. | skill backend-ml-serving | Media |

## 1. Fase 0 — Auditoría de caza de bugs (entregable: `36_actualizacion_modulo_admin.md`)

1. **Costo y ventana del detector (A-2):** medir el tiempo de respuesta de `/anomalies` con el volumen real de `fact_logs_auditoria`; documentar la ventana efectiva. Si escanea todo por request → candidato #1 a corrección.
2. **Política de contraseñas E2E (A-4):** confirmar que `users.py`/servicio valida en backend la misma regla que el `pattern` del frontend (el pattern HTML se salta con un request directo a la API).
3. **Ids de roles (A-4):** verificar contra `edw/08_seed_roles_usuarios.sql` si los ids son estables; el frontend debería seleccionar por `nombre` del catálogo, no asumir `rol_id: 2`.
4. **Auth:** expiración y refresh del JWT, comportamiento al desactivar un usuario con sesión activa (¿el token sigue siendo válido hasta expirar? ¿hay verificación de `es_activo` por request?), y rate-limiting del login (¿existe?).
5. **Checklist de hardening (A-5):** estado real de CORS, secretos por defecto, y plan de retiro de `docs/credenciales_sistema.md` del repo (mover a gestor de secretos + purga de historial git si aplica — decisión del usuario).
6. **MLOps (A-6):** probar `/admin/modelos` con un `.pkl` renombrado temporalmente en dev: el estado debe reportar el modelo caído (patrón WARNING del `ModelLoader`), no 500.

## 2. Fase 1 — Correcciones

1. **Filtros y paginación en admin (A-1/A-2):** `/anomalies` y `/audit-logs` ganan `fecha_desde/fecha_hasta`, filtro por usuario/módulo y paginación `Page[T]` (infraestructura ya existente de Bodega, espejo TS incluido). Ventana por defecto configurable `ADMIN_ANOMALIAS_VENTANA_DIAS` en `config.py`, no todo el histórico.
2. **Validación de contraseña en backend (A-4):** política única definida en `core/config.py`, aplicada en `users` service (crear y actualizar); el `pattern` del frontend queda como UX, no como seguridad.
3. **Rol por defecto por nombre, no por id (A-4).**
4. **Verificación de `es_activo` en cada request autenticado** (si la auditoría confirma que un usuario desactivado sigue operando con token vigente).
5. Hardening A-5 según decisión del usuario (retirar credenciales del repo es acción irreversible sobre historial — confirmar antes).

## 3. Fase 2 — Mejoras de valor

1. **Triage de anomalías (A-3):** tabla `public.anomalias_revisiones` (anomalía → estado, revisor, nota, fecha); el dashboard separa "nuevas" de "revisadas". Es la mejora que convierte el detector en herramienta de trabajo.
2. Notificación al admin cuando la detección encuentra anomalías nuevas de score alto (conectar con `plan_modulo_notificaciones.md`, generador ya previsto ahí).
3. Panel de salud del sistema: última corrida ETL (`edw.etl_control`), estado de los 6 modelos, conteo de logins fallidos.

## 4. Validación

- `pytest` integración: filtros de anomalías/logs, política de contraseñas por API directa, RBAC `admin_only` en todos los endpoints nuevos.
- Prueba de humo MLOps en dev (retrain) y en compose base (fallo con mensaje claro).
- El detector sigue degradando con gracia si `anomalies.pkl` falta (dashboard vivo, widget caído con error visible).

**Reglas transversales:** routers thin; excepciones de dominio; `ModelLoader` inyectado; umbrales como settings; Producción SAP intacta; actualizar auditoría 36 y `02_reglas_negocio_validadas.md`.
