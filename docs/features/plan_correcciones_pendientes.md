# Plan Consolidado — Correcciones Pendientes y Deuda Técnica Post-Actualización de Módulos

> **Fecha:** 2026-07-15
> **Estado:** Propuesta (consolida lo diferido/descubierto en las auditorías 32–36)
> **Contexto:** las Fases 0-1 de los 5 planes de actualización por módulo (Bodega, Admin, Gerencia, Metas y Comisiones, Ventas) están **completas y verificadas** (auditorías `32` a `36`, suites unit + integration en verde). Este plan recoge todo lo que quedó explícitamente diferido, lo descubierto durante la implementación que no se corrigió por alcance, y la deuda preexistente que sigue abierta — priorizado por riesgo real, no por módulo.

## 0. Prioridad inmediata — Estado del repositorio

| # | Ítem | Detalle | Acción |
|---|---|---|---|
| P0-1 | **Todo el trabajo de esta ronda está SIN COMMITEAR.** ~60 archivos modificados + ~40 nuevos (5 módulos actualizados, 6 auditorías, módulo de Notificaciones completo, endpoint `/system/provenance`, tests) viven solo en el working tree. Un `git checkout`/reset accidental lo pierde todo. | `git status` 2026-07-15 | Commitear en commits lógicos por módulo (sugerido: notificaciones → bodega → admin → gerencia → metas → ventas → docs), en la rama actual `main` o una rama de feature según el flujo del proyecto. **Es el paso previo a cualquier otro ítem de este plan.** |
| P0-2 | **Riesgo "etl/loaders borrados" de CLAUDE.md ya no es real.** `dim_loader.py`/`fact_loader.py` existen en el working tree y git los rastrea — el riesgo crítico documentado en CLAUDE.md §Riesgos ("el ETL no puede ejecutarse") está resuelto o nunca se materializó. | `ls etl/loaders/` 2026-07-15 | Verificar con `python -m py_compile` + una corrida de ETL en dev, y actualizar CLAUDE.md §Riesgos y §Observaciones (el "Crítico" de la auditoría 04 quedó obsoleto). |

## 1. Correcciones técnicas pendientes (bugs o deuda que distorsiona resultados)

| # | Ítem | Origen | Severidad | Acción propuesta |
|---|---|---|---|---|
| C-1 | **Drift de versiones ML entre entrenamiento y serving.** Los 6 `.pkl` fueron serializados con scikit-learn **1.9.0** / xgboost **2.1.4**, pero el backend local corre **1.8.0** / **3.2.0**. `ModelLoader.verify_library_versions` lo promueve a ERROR en cada arranque (M-01): las predicciones pueden diferir **silenciosamente** del modelo entrenado — no es un warning cosmético. | Logs de arranque en cada test de integración de esta sesión | **Alta** | O alinear `backend/requirements.txt` a las versiones con las que se entrenó, o reentrenar/republicar los 6 modelos con las versiones que corre el backend (`ml/main.py` + `publish_models.py`). Decidir una dirección y dejar ambos `requirements.txt` pineados a la misma versión — el acoplamiento es conocido (CLAUDE.md §Dependencias) pero hoy está violado. |
| C-2 | **`Select.tsx` no compila (`tsc -b` falla).** Error preexistente TS2430: la prop `size?: 'sm' \| 'md'` colisiona con `SelectHTMLAttributes.size: number`. Todo el type-check del frontend falla por este único error — cualquier error de tipos NUEVO que se introduzca queda enmascarado detrás de él. | Verificado en las 4 rondas de `tsc -b` de esta sesión | Alta (bloquea la señal de CI) | Renombrar la prop (`uiSize`) o tipar la interfaz con `Omit<SelectHTMLAttributes<HTMLSelectElement>, 'size'>`. Cambio de ~5 líneas + actualizar los ~10 consumidores que pasan `size="sm"`. |
| C-3 | **`comision_config_vendedor` sin vigencia histórica** (auditoría 35, H4). Un cambio de tipo externo/interno de un vendedor se aplica retroactivamente a cualquier período cerrado que aún no se haya congelado por primera vez (RN-CM6 acota el daño a la primera congelación, no lo elimina). | Auditoría 35, diferido explícito | Media | Agregar `vigente_desde`/`vigente_hasta` a la tabla (mismo patrón que `comision_matriz_categorias`), migración manual del esquema (el DDL de `edw/` solo corre en volumen nuevo), y `get_config_vendedor(fecha)` que resuelva por vigencia usando `fecha_referencia_periodo`. |
| C-4 | **`edw/07_public_app_tables.sql` posiblemente desalineado con los modelos ORM.** El backend crea las tablas `public.*` con `Base.metadata.create_all`, pero el DDL versionado es lo que un despliegue desde cero ejecuta. Esta ronda agregó/usó tablas nuevas (`notificaciones`, `gestion_cartera_eventos`) — verificar que TODAS las tablas de `app/models/` estén reflejadas en el DDL con los mismos constraints. | Acoplamiento documentado en CLAUDE.md §Dependencias | Media | Diff manual modelos ORM ↔ DDL; agregar las tablas/constraints faltantes al `07_public_app_tables.sql`. |
| C-5 | **Deprecations de Pydantic v2** (`class Config` → `ConfigDict`): 4+ warnings en cada corrida de tests (`config.py`, `role.py`, `user.py`). Se vuelven errores en Pydantic v3. | Warnings en toda la sesión | Baja | Migración mecánica a `model_config = ConfigDict(...)`. |
| C-6 | **`frontend/src/services/mocks/bodega.mock.ts` es código muerto** (0 consumidores tras retirar `provenance.mock.ts` esta sesión). El riesgo de CLAUDE.md "verificar que ningún dashboard consuma mocks" queda cerrado eliminándolo. | Grep de esta sesión | Baja | Eliminar el archivo y la carpeta `mocks/` si queda vacía; actualizar CLAUDE.md §Riesgos. |
| C-7 | **`datetime.utcnow()` deprecado en python-jose** (warning en cada request autenticado con Python 3.14). No es código propio, pero la librería `python-jose` está poco mantenida. | Warnings en toda la sesión | Baja | Evaluar migrar a `PyJWT` o pinear/parchear; no urgente mientras sea solo un warning. |

## 2. Hardening de seguridad (requiere decisión del usuario — diferido explícitamente en auditoría 36)

| # | Ítem | Decisión pendiente |
|---|---|---|
| S-1 | **`docs/credenciales_sistema.md` versionado en el repo** con credenciales visibles. | Mover el contenido a un gestor de secretos / `.env` no versionado y eliminar el archivo en un commit. **Purga del historial git** (`git filter-repo`) es irreversible y reescribe hashes — decidir si el repo es compartido antes de hacerlo. Rotar las credenciales expuestas independientemente de la purga. |
| S-2 | **CORS `"*"` por defecto.** Aceptable en dev; en cualquier despliegue accesible por red debe definirse `CORS_ORIGINS` explícito. | Definir la variable en el compose/entorno de despliegue. Considerar cambiar el default del código a una lista vacía + warning, para que el "*" sea opt-in. |
| S-3 | **Rate-limiting del login: no existe** (punto 4 de la Fase 0 del plan de Admin, nunca implementado). Fuerza bruta contra `/auth/login` solo está mitigada por el hash bcrypt lento. | Implementar con `slowapi` o un contador en memoria por IP/email (suficiente para un solo proceso). Complemento: lockout temporal tras N fallos. |
| S-4 | **Sin refresh token ni revocación:** el JWT de 8h sigue siendo válido tras logout (el logout es solo client-side). `es_activo` sí se verifica por request (auditoría 36 H7), lo que mitiga el caso "usuario desactivado". | Decidir si el proyecto (tesis) lo necesita; si sí: refresh tokens cortos + blacklist en memoria/BD. |

## 3. Fase 2 diferidas por módulo (mejoras de valor, no bugs)

### Admin (plan §3, auditoría 36)
1. **Triage de anomalías:** tabla `public.anomalias_revisiones` (anomalía → estado nueva/revisada/descartada/confirmada, revisor, nota, fecha); el dashboard separa "nuevas" de "revisadas". Es lo que convierte el detector en herramienta de trabajo.
2. **Panel de salud del sistema:** parcialmente cubierto por `GET /system/provenance` (última carga DW + estado de modelos, agregado en la ronda de Gerencia). Falta: detalle por tabla de `edw.etl_control` (última corrida, filas, errores) y conteo de logins fallidos (requiere S-3 primero, hoy no se registran).
3. ~~Notificación de anomalías score alto~~ — **ya cubierto**: `GET /admin/anomalies` emite `anomalia_detectada` persistida vía `NotificationService` desde la ronda de Notificaciones. Verificar si se desea umbral de score configurable en vez de todo-o-nada.

### Gerencia (plan §3, auditoría 33)
1. **KPI de cumplimiento vs metas del período** en el dashboard gerencial (reutiliza `public.metas_comerciales_operativas` vía `GoalsService`, sin ML).
2. **Comparativa período anterior** en todos los KPIs (mismo patrón `tendencia_pct` de Bodega).
3. **Export Excel/PDF del dashboard** reutilizando la infraestructura de `warehouse_export.py` (contrato tipado de reportes de la Fase 5 de Bodega) — no duplicar exportadores.

### Metas y Comisiones (plan §3, auditoría 35)
1. **Transparencia del cálculo IQR:** el drawer de revisión de meta muestra el desglose del motor (meses usados, picos recortados por IQR, tendencia aplicada, techo/piso activado). El motor ya calcula todo — es solo exponerlo en `MetaSugeridaResponse`/UI.
2. **Bitácora de cambios de configuración de comisiones** (quién cambió qué factor y cuándo): tabla `public.*` append-only. Crítico porque la config altera dinero; las vigencias actuales preservan el QUÉ pero no el QUIÉN (solo `creado_por` en matriz, nada en crédito/vendedor).
3. **Alerta de divergencia plano vs variable** > umbral configurable durante el piloto sombra — conectar con el módulo de Notificaciones (generador calculado nuevo para gerencia).

### Ventas (plan §3, auditoría 34)
1. **Churn accionable:** ~~lista de clientes en riesgo ordenada por probabilidad × venta~~ — **mayormente cubierto**: `cartera360/lista-trabajo` ya rerankea con churn real en lote (`prioridad = valor_histórico × (1 + prob)`). Evaluar si falta solo un filtro "solo riesgo alto" en la UI de Cartera 360, no un endpoint nuevo.
2. **Telemetría de venta cruzada para gerencia:** los KPIs RN-CS2 (`GET /cross-selling/kpis`) ya son accesibles a gerencia por RBAC — falta solo montarlos en algún panel del dashboard gerencial.

## 4. Deuda de datos del EDW (requiere ETL, fuera del alcance de las auditorías de módulos)

| # | Ítem | Estado |
|---|---|---|
| D-1 | `dim_geografia` vacía (0 filas) | Abierto desde auditoría 05. Decidir si se puebla (requiere extractor nuevo) o se elimina del esquema. |
| D-2 | `fact_metas_comerciales` vacía (metas viven en `public.metas_comerciales_operativas`) | Abierto. Decidir: poblarla desde `public.*` como hecho histórico, o eliminarla del DDL para no confundir. |
| D-3 | `dim_fecha.es_feriado` nunca poblado (workaround hardcodeado en el código ML) | Abierto. Poblar con calendario de feriados de Ecuador parametrizable; retirar el hardcode de `ml/`. |
| D-4 | `fact_inventario_snapshot` solo "hacia adelante" (<1% histórico pre-2026) | Limitación del ERP (el kardex no reconstruye stock histórico fácilmente). Documentado; evaluar reconstrucción por acumulación de movimientos si algún análisis lo exige. |
| D-5 | Calendarización del ETL (hoy manual; crontab planificado en Fase 6 de `hoja_de_ruta_ejecucion.md`) | Pendiente. Definir ventana de carga y monitoreo (la alerta de "DW sync hace Xd" del ProvenanceRail ya haría visible un ETL atrasado). |
| D-6 | Higiene del repo ETL/ML: scripts ad-hoc en `etl/` (`query_diag_db.py`, `test_sap.py` duplicado, etc.), `truncate_edw.py` sin salvaguardas, artefactos ML duplicados (`ml/models/`, `backend/ml_models/`, `models/` raíz, `catboost_info/` ×2) | Abierto desde CLAUDE.md §Riesgos. Mover diagnósticos a `etl/scripts/` o eliminarlos; `truncate_edw.py` con confirmación interactiva + guard de `ENV`; consolidar artefactos en `ml/models/` como única fuente. |

## 5. Validación pendiente no automatizable

1. **Sesión de validación con usuario final de Bodega** (criterio de aceptación de la Fase 5 del plan de Bodega — único pendiente de ese módulo).
2. **Verificación visual con usuario seed de cada rol** tras esta ronda: los 4 dashboards cambiaron (filtros de audit-log en Admin, aviso de forecast + ingresos en Gerencia, selector de período en Ventas, ProvenanceRail real en todos). El backend está probado por integración; el render de la UI no.
3. **Probar los 3 valores de `COMISION_MODO`** en un entorno desplegado (los tests cubren la lógica, no el arranque del sistema completo en cada modo).

## 6. Orden de ejecución sugerido

1. **P0-1** (commitear) — sin esto, todo lo demás está en riesgo.
2. **C-1** (drift de versiones ML) y **C-2** (`Select.tsx`) — restauran las dos señales de verificación (predicciones fiables, type-check verde).
3. **S-1/S-2** (credenciales + CORS) — decisión rápida del usuario, alto valor de seguridad.
4. **C-3/C-4** (vigencia de config de vendedor + DDL alineado) — cierran la integridad del sistema de comisiones y del despliegue desde cero.
5. Fase 2 por módulo (§3) según prioridad de negocio — sugerido: triage de anomalías (Admin) y transparencia IQR (Metas) primero, por ser los de mayor valor operativo declarado en sus planes.
6. Deuda de datos (§4) — coordinada con la calendarización del ETL (D-5).

**Reglas transversales:** las mismas de todos los planes — auditoría previa antes de tocar código (formato de `docs/auditoria/`), Producción SAP solo lectura, sin hardcodes (settings), routers thin, excepciones de dominio, actualizar `02_reglas_negocio_validadas.md` y CLAUDE.md al cierre de cada ítem.
