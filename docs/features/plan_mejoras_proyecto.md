# Plan de mejoras del proyecto — Plataforma BI

> **Fecha:** 2026-07-12
> **Método:** análisis por capas usando las 4 skills especializadas del proyecto
> (`etl-edw-auditor`, `ml-training-pipeline`, `backend-ml-serving`, `frontend-design`),
> contrastado con evidencia verificada en código/artefactos (no supuesta) y con los
> hallazgos abiertos de las auditorías 00–24. Cada mejora cita su evidencia; lo no
> verificable se marca **Pendiente de validar**.
> **Criterio de prioridad** (regla del auditor del proyecto):
> **ALTA** = produce datos/resultados incorrectos hoy · **MEDIA** = riesgo operativo,
> rendimiento o mantenibilidad · **BAJA** = refactor/estilo/documentación.

---

## 0. Resumen ejecutivo (qué haría primero)

| # | Mejora | Prioridad | Esfuerzo | Eje |
|---|---|---|---|---|
| M-01 | Alinear versión de scikit-learn entrenamiento↔serving (drift real 1.9.0 vs 1.8.0) | **ALTA** | Bajo | ML |
| M-02 | Eliminar mocks del `DashboardAdmin` (muestra datos falsos como reales) | **ALTA** | Medio | Frontend |
| M-03 | Sacar `docs/credenciales_sistema.md` del repositorio + rotar credenciales | **ALTA** | Bajo | Seguridad |
| M-04 | Desplegar ETL+EDW en servidor de la empresa (histórico de snapshots) | **ALTA** | Alto | Ops — plan ya escrito |
| M-05 | Poblar `dim_fecha.es_feriado` y eliminar el workaround hardcodeado en ML | MEDIA | Medio | EDW/ML |
| M-06 | Salvaguardas en `truncate_edw.py` + limpiar scripts ad-hoc de `etl/` | MEDIA | Bajo | ETL |
| M-07 | CORS restringido y checklist de secretos para producción | MEDIA | Bajo | Seguridad |
| M-08 | Backfill histórico de `fact_inventario_snapshot` desde kardex | MEDIA | Alto | EDW |
| M-09 | CI mínima (pytest + tsc/oxlint en cada push) | MEDIA | Medio | Ops |
| M-10 | Refactor UI "Signal Deck 2.0" | MEDIA | Alto | Frontend — plan ya escrito |

Los detalles y el resto de mejoras (M-11..M-24) están por eje a continuación.

---

## 1. Eje ML — entrenamiento y serving

### M-01 · ALTA — Drift de versiones de scikit-learn entre entrenamiento y serving

- **Evidencia (verificada hoy):** `ml/models/*.meta.json` registra
  `"scikit-learn": "1.9.0"` (versión con que se serializaron los `.pkl`), pero el
  entorno que los deserializa tiene `1.8.0`. Los tests de integración emiten
  `InconsistentVersionWarning: Trying to unpickle estimator KMeans from version 1.9.0
  when using version 1.8.0` para KMeans, Pipeline, ExtraTreeRegressor e IsolationForest.
- **Impacto:** es exactamente el riesgo H-20 ya documentado, materializado. sklearn no
  garantiza compatibilidad de pickles entre versiones: puede producir **predicciones
  silenciosamente distintas** (peor que un crash) en segmentación RFM, demanda y
  anomalías.
- **Causa raíz:** los `requirements.txt` usan rangos laxos (`scikit-learn>=1.3,<2.0` en
  `ml/`, `>=1.2,<2.0` en `backend/`) — permiten que cada entorno resuelva una versión
  distinta según cuándo se instaló.
- **Acción:**
  1. Fijar **versiones exactas e idénticas** (pin `==`) de sklearn/xgboost/lightgbm/
     catboost/joblib en `ml/requirements.txt` y `backend/requirements.txt`.
  2. Reinstalar ambos entornos y **reentrenar + republicar** los 6 modelos
     (`cd ml && python main.py` → `contract_validator` → `publish_models.py`).
  3. Agregar una verificación al arranque del backend: si
     `meta.library_versions["scikit-learn"] != sklearn.__version__`, log `ERROR`
     (hoy solo lo avisa un warning de sklearn que nadie mira).
- **Validación:** tests de integración sin `InconsistentVersionWarning`; métricas del
  sidecar equivalentes a las previas (backtest comparativo, regla del pipeline ML).

### M-11 · MEDIA — Resolver `known_serving_mismatch` H-14b (ventas global vs filtro por sucursal)

- **Evidencia:** campo `known_serving_mismatch` del contrato de ventas; el modelo
  entrena la serie global pero el endpoint permite filtrar por sucursal/vendedor
  (decisión pendiente documentada en auditoría 21 §3.4).
- **Acción:** decidir con el usuario de negocio: (a) entrenar modelos por sucursal, o
  (b) declarar la limitación en la UI (badge "proyección global escalada"). Documentar
  la decisión y cerrar el campo del contrato.

### M-12 · MEDIA — `es_feriado` real en `dim_fecha` (comparte causa con M-05)

- **Evidencia:** `ml/src/features/build_features.py` aproxima feriados con una lista
  fija hardcodeada de feriados de Ecuador (deuda declarada en la propia skill);
  `dim_fecha.es_feriado` nunca se puebla (auditoría 05).
- **Impacto:** feriados móviles (Carnaval, Viernes Santo) mal marcados → señal de
  calendario ruidosa en ventas y demanda.
- **Acción:** poblar `es_feriado` en `dim_fecha` vía `etl/transformers/dim_tiempo.py`
  (algorítmico + tabla de feriados nacionales parametrizada), migrar
  `build_features.py` y `backend/app/ml/preprocessing.py` a leer la columna (mismo
  cambio en ambos lados — regla de sincronía), reentrenar con backtest comparativo.

### M-13 · BAJA — Limpiar artefactos ML duplicados

- **Evidencia:** `.pkl` legacy duplicados en `models/` (raíz), `backend/ml_models/` y
  nombres viejos (`*_rf_model.pkl`) en `ml/models/`; `catboost_info/` en la raíz y en
  `ml/` (residuos de entrenamiento). El backend solo consume los nombres bajo contrato.
- **Acción:** eliminar `models/` raíz y `backend/ml_models/` del repo, agregar
  `catboost_info/` a `.gitignore`, dejar solo `ml/models/*.pkl + *.meta.json`.

## 2. Eje EDW / datos

### M-05 · MEDIA — Hallazgos abiertos de la auditoría 05 (verificar y cerrar)

Tres huecos de datos conocidos que siguen abiertos; cada uno con acción concreta:

| Hueco | Evidencia | Acción propuesta |
|---|---|---|
| `dim_geografia` con 0 filas | Auditoría 05; los dashboards no la consumen aún | Decidir: poblarla desde `clientes.codciu/codprv` del ERP (validar cobertura con SELECT) **o** decomisionarla formalmente del DDL para no arrastrar una dimensión muerta. **Pendiente de validar** qué % de clientes tiene ciudad/provincia utilizable. |
| `fact_metas_comerciales` vacía | Las metas viven en `public.metas_comerciales_operativas` | Decomisionarla del DDL (las metas operativas ya tienen dueño) o crear el task que la materialice desde `public.*` para análisis histórico dimensional. Recomendación: decomisionar — evita doble fuente de verdad (misma lógica que la decomisión de `goals_rf`, auditoría 20). |
| `dim_fecha.es_feriado` sin poblar | Ver M-12 | Cerrarlo junto con M-12 (un solo cambio ETL). |

### M-08 · MEDIA — Backfill histórico de `fact_inventario_snapshot`

- **Evidencia:** el snapshot solo existe "hacia adelante" (<1% pre-2026); el ERP no
  guarda historial de stock (`vi_mv_existencias` es solo estado actual), pero
  `fact_movimientos_inventario` sí tiene ~948k movimientos históricos con dirección
  validada (regla de negocio 3).
- **Acción:** script one-off que reconstruya el stock por (producto, almacén, día)
  restando/sumando movimientos hacia atrás desde el snapshot más antiguo disponible, y
  lo materialice como snapshots históricos (marcados con un flag `es_reconstruido` para
  distinguirlos de fotos reales). Requiere auditoría previa propia: reconciliar la
  reconstrucción de N días atrás contra un snapshot real conocido para medir el error
  acumulado (mermas/ajustes no kardexados).
- **Beneficio:** habilita KPIs de tendencia de inventario y (potencialmente) mejores
  features de demanda — que hoy están bloqueados por el <1% de cobertura (ya se
  descartó el snapshot como exógena por esto, `ml/REPORTE_MEJORA_MODELOS.md`).

### M-14 · MEDIA — Reconciliación periódica Producción vs EDW automatizada

- **Evidencia:** `etl/validator/` ya tiene queries de chequeo (conteos, duplicados,
  huérfanos) pero se ejecutan a mano; las auditorías 02/05 validaron una sola vez.
- **Acción:** empaquetar el validator como paso post-carga del orquestador (o tarea
  semanal en el servidor del plan de despliegue): conteo origen-vs-destino con el mismo
  recorte, % de FKs al centinela `-1`, huecos de fechas. Resultado a `edw.etl_control`
  o log — así la deriva de datos se detecta en días, no en la siguiente auditoría.

## 3. Eje ETL

### M-06 · MEDIA — Higiene y salvaguardas del pipeline

- **Evidencia (verificada):** conviven con el pipeline productivo:
  `etl/query_diag_db.py`, `etl/query_nc.py`, `etl/query_notas_credito.py`,
  `etl/test_sap.py` (duplicado en `etl/connectors/`), y `etl/truncate_edw.py`
  (destructivo, sin confirmación ni protección por entorno).
- **Impacto:** riesgo real ahora que habrá un EDW de producción (plan de despliegue):
  un `python truncate_edw.py` accidental en el servidor borra el histórico de
  snapshots irrecuperable.
- **Acción:**
  1. Mover los scripts exploratorios a `etl/scripts_diagnostico/` (fuera del `COPY` del
     Dockerfile) o eliminarlos si ya cumplieron su propósito.
  2. `truncate_edw.py`: exigir confirmación interactiva + variable
     `ETL_PERMITIR_TRUNCATE=true` + abortar si `ENV=production`.
  3. Deduplicar `test_sap.py` (dejar solo el de `connectors/`).

### M-15 · MEDIA — Tests del ETL (hoy: 0 ejecutables)

- **Evidencia:** `pytest` está declarado en `etl/requirements.txt` pero no existe
  `etl/tests/` con casos del núcleo (transformers SCD2, dirección de kardex,
  idempotencia del DELETE por fecha, render de tokens).
- **Acción:** suite unitaria con DataFrames sintéticos para: `dim_transformer` (SCD2 no
  duplica vigentes), `fact_transformer` (kardex EN/AC vs SA/AD), `render_sql` (tokens
  en cada rama de UNION ALL — el bug C-2 ya ocurrió), y la lógica snapshot-vs-incremental
  del orquestador. Sin tocar SAP: todo con fixtures.

### M-16 · BAJA — Alertado de fallas del ETL programado

- **Contexto:** el plan de despliegue deja logs y `etl_control`, pero nadie es
  notificado si la corrida de las 06:00 falla.
- **Acción:** paso final del `run_etl.ps1` que envíe correo (SMTP de la empresa) o
  webhook cuando `LASTEXITCODE != 0` o cuando falte el snapshot de hoy en la query de
  salud (§13 de la guía de instalación).

## 4. Eje Backend

### M-17 · MEDIA — Paginación a nivel SQL donde el orden lo permita

- **Evidencia:** la paginación global (auditoría 24) es en memoria por diseño
  declarado (H24-2): los 4 endpoints de Bodega ordenan por campos calculados en Python.
  El payload al cliente ya es chico, pero el cómputo interno sigue siendo O(total).
- **Acción (cuando el inventario crezca):** trasladar el cálculo de
  estado/días-de-inventario a SQL (columnas derivadas con los umbrales `BODEGA_*` como
  parámetros) para poder ordenar+`LIMIT/OFFSET` en Postgres. El contrato `Page[T]` ya
  lo soporta sin cambios de frontend — la infraestructura quedó preparada a propósito.

### M-18 · MEDIA — Cache de predicción compartido entre workers

- **Evidencia:** el cache TTL de `get_prediccion_compras_mes` es un dict por proceso
  (limitación declarada, auditoría 24). Con `uvicorn --workers N` cada worker paga el
  frío (~7 s medidos) por separado.
- **Acción:** solo si el despliegue usa multi-worker: mover el cache a una tabla
  `public.cache_predicciones` (el EDW ya está; no agregar Redis por una sola clave) con
  la misma llave `(categoria, sucursal, almacen, proveedor)` y TTL.

### M-19 · BAJA — Migrar `class Config` a `ConfigDict` (Pydantic v2)

- **Evidencia:** warnings `PydanticDeprecatedSince20` en cada corrida de pytest
  (`app/core/config.py:9`, `app/schemas/role.py:16`, `app/schemas/user.py:10,26`).
  Pydantic v3 los convertirá en errores.
- **Acción:** reemplazo mecánico por `model_config = ConfigDict(...)` en los 4 puntos.

### M-20 · BAJA — Deuda menor de serving

- `datetime.utcnow()` deprecado en `python-jose` (warning en cada login) — se resuelve
  actualizando la librería o migrando a `PyJWT` (evaluar; jose está sin mantenimiento
  activo). **Pendiente de validar** compatibilidad de tokens emitidos.
- Verificación de arranque: exponer en `/health` la versión de sklearn del proceso y la
  del sidecar de cada modelo (complementa M-01).

## 5. Eje Seguridad

### M-03 · ALTA — Credenciales reales versionadas en el repositorio

- **Evidencia (verificada):** `docs/credenciales_sistema.md` está rastreado por git
  (`git ls-files` lo confirma). Además `.env` local contiene la contraseña real del ERP
  y del usuario `dba`.
- **Impacto:** cualquier persona con acceso al repo (o a un remoto futuro) obtiene
  credenciales del ERP de producción.
- **Acción:**
  1. Eliminar el archivo del repo y agregarlo a `.gitignore`.
  2. **Purgar el historial** (`git filter-repo`) antes de subir el repo a cualquier
     remoto — borrar solo el archivo no borra sus versiones pasadas.
  3. Rotar las credenciales expuestas (SAP y Postgres) — coordinado con TI.
  4. Solicitar usuario SAP de solo-SELECT dedicado (hoy se usa `dba`, que puede
     escribir — viola en espíritu la restricción "Producción solo lectura").

### M-07 · MEDIA — Endurecimiento para producción

- **Evidencia:** CORS default `"*"` (`app/core/config.py`); defaults inseguros
  tolerados fuera de `ENV=production` (fail-fast ya existe, correcto); puerto 5433
  quedará expuesto en el servidor (plan de despliegue lo restringe por firewall).
- **Acción:** checklist de go-live: `CORS_ORIGINS` explícito, `ENV=production`,
  `JWT_SECRET`/`PG_PASSWORD` nuevos, `.env` con permisos 600, firewall 5433 por IP.
  (La mitad ya está operacionalizada en `docs/deploy/instalacion_windows_server_paso_a_paso.md` §5/§11 — esto solo lo formaliza como checklist único.)

## 6. Eje Frontend

### M-02 · ALTA — `DashboardAdmin` muestra datos mock como si fueran reales

- **Evidencia (verificada):** `frontend/src/pages/DashboardAdmin.tsx:7` importa
  `AUDIT_ENTRIES, MODEL_STATUS` desde `services/mocks/admin.mock.ts`. Existen además
  `bodega.mock.ts` y `provenance.mock.ts` (**Pendiente de validar** si algo más los
  consume).
- **Impacto:** el rol administrador ve un log de auditoría y un estado de modelos
  **ficticios** — datos incorrectos presentados como reales, la categoría de mayor
  severidad del proyecto.
- **Acción:** el backend ya expone lo necesario: `edw.fact_logs_auditoria` (auditoría
  del ERP) y los sidecars `.meta.json` vía `ModelLoader` (estado/métricas de modelos).
  Crear los endpoints faltantes en `/analytics/admin` + `/admin/modelos` si no existen,
  conectar el dashboard, y borrar `services/mocks/` completo para que no pueda volver a
  pasar.

### M-10 · MEDIA — Refactor visual "Signal Deck 2.0"

- Plan detallado ya escrito: `docs/features/plan_refactor_ui.md` (tokens sin fugas,
  10 primitivas nuevas, motion orquestado, accesibilidad AA, página piloto
  `DashboardBodega`). Se referencia aquí para el roadmap; no se duplica.

### M-21 · MEDIA — Code-splitting del bundle

- **Evidencia:** `vite build` advierte un chunk de **932 kB** (Recharts + todas las
  páginas en un solo bundle).
- **Acción:** `React.lazy` por página en `AppRouter.tsx` (los dashboards por rol son la
  frontera natural: un usuario de bodega nunca carga el código de gerencia) +
  `manualChunks` para Recharts. Meta: chunk inicial < 300 kB.

## 7. Eje documentación y gobernanza

### M-22 · BAJA — Cerrar inconsistencias código↔documentación (lista de CLAUDE.md)

| Ítem | Acción |
|---|---|
| No existe README raíz | Crear README con: qué es, arquitectura (diagrama de CLAUDE.md), cómo levantar (`docker compose up`), enlaces a docs. |
| `docs/matriz_trazabilidad.md` con rutas de endpoints obsoletas | Regenerarla desde `backend/app/api/routes/api.py` (el código es la fuente de verdad declarada). |
| Reportes 00–05 referencian carpeta `prompts/` inexistente | Nota de fe de erratas en cada reporte o restaurar la carpeta si existe fuera del repo. |
| `.agent/workflows/ejecutar-etl.md` referencia `c:\Tesis` | Corregir a `c:\Proyect_BI`. |
| `docs/auditoria/00_planificacion.md` con rutas backend viejas | Nota de actualización (no reescribir historia del reporte). |

### M-23 · BAJA — Guía de operación para la empresa

- Manual corto para el usuario final/TI de la empresa (distinto de la tesis): cómo
  entrar a cada dashboard por rol, qué significa cada KPI/semáforo, qué hacer si el
  ETL falla (apunta a §13 de la guía de instalación). Útil también como anexo de tesis.

## 8. Eje operaciones / CI

### M-04 · ALTA — Despliegue en servidor (ya planificado)

- Plan y paso a paso ya escritos:
  `docs/deploy/plan_despliegue_windows_server.md` +
  `docs/deploy/instalacion_windows_server_paso_a_paso.md`. Es ALTA porque cada día sin
  ejecutar es histórico de snapshots perdido para siempre. Este plan de mejoras lo
  incluye para el roadmap, no lo re-diseña.

### M-09 · MEDIA — Integración continua mínima

- **Evidencia:** validaciones existentes (87 tests unit backend, tsc, oxlint, contract
  validator de ML) se corren a mano; nada impide commitear código roto.
- **Acción:** GitHub Actions (o el runner que la empresa permita) con dos jobs:
  - `backend`: `pip install -r requirements.txt && pytest tests/unit` (los de
    integración quedan fuera: requieren EDW vivo).
  - `frontend`: `npm ci && tsc --noEmit && oxlint && vite build`.
  - Opcional job `ml`: `python -m src.contracts.contract_validator` en modo estático.

### M-24 · BAJA — Renovar el Postgres del compose con versión menor fijada

- **Evidencia:** `postgres:16-alpine` sin tag menor — un `pull` futuro puede cambiar la
  versión bajo los pies del volumen. **Acción:** fijar `postgres:16.6-alpine` (o la
  menor vigente) y documentar el procedimiento de upgrade.

---

## 9. Roadmap sugerido

```
Fase A — Correcciones de datos incorrectos (1 semana)
  M-01 versiones sklearn + reentrenar          M-02 mocks del DashboardAdmin
  M-03 credenciales fuera del repo + rotación

Fase B — Producción confiable (1–2 semanas, en paralelo con A)
  M-04 despliegue en servidor (plan existente) M-06 salvaguardas truncate/scripts
  M-07 checklist go-live                       M-16 alertas del ETL

Fase C — Calidad de datos (2–3 semanas)
  M-05 hallazgos auditoría 05                  M-12 es_feriado real
  M-14 reconciliación automatizada             M-15 tests del ETL
  M-08 backfill de snapshots (requiere su propia auditoría previa)

Fase D — Producto y mantenibilidad (continuo)
  M-10 refactor UI                             M-21 code-splitting
  M-09 CI                                      M-17/M-18 paginación SQL + cache compartido
  M-11 decisión H-14b                          M-13/M-19/M-20/M-22/M-23/M-24 deuda menor
```

Reglas de ejecución (flujo CLAUDE.md): toda mejora que toque datos o metodología ML
lleva **auditoría previa** en `docs/auditoria/` (siguiente número libre: 25); las de
ETL/EDW se validan contra Producción **solo con SELECT**; cambios de features ML se
replican en `backend/app/ml/preprocessing.py` en el mismo cambio y pasan backtest
comparativo antes de publicar.
