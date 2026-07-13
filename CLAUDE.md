# CLAUDE.md — Contexto del Proyecto

> **Proyecto:** Plataforma Inteligente de Analítica Empresarial y Predicción de Ventas para Empresas Multisucursal (proyecto de tesis).
> **Última actualización de este documento:** 2026-07-13 (módulo de Venta Cruzada / Cross-Selling: re-análisis del modelo, asistente de venta y telemetría de conversión, ver `docs/auditoria/25_modulo_cross_selling.md`).

## Descripción del proyecto

Plataforma de Business Intelligence de punta a punta: extrae datos del ERP transaccional (SAP SQL Anywhere 17), los carga en un Enterprise Data Warehouse (EDW) dimensional en PostgreSQL 16, entrena 6 modelos de Machine Learning sobre el EDW y los sirve mediante una API FastAPI con autenticación JWT + RBAC, consumida por una SPA React con dashboards por rol (Gerencia, Ventas, Bodega, Administrador). El módulo de Metas y Comisiones NO usa ningún modelo ML (el modelo `goals_rf` fue decomisionado, ver `docs/auditoria/20_decomision_goals_rf.md`): la meta se calcula con estadística pura (IQR + tendencia reciente) sobre el histórico de Venta Neta del EDW.

El DW es la **fuente oficial** para:

- Predicción de ventas
- Predicción de reposición (demanda)
- Dashboard Gerencial
- Dashboard de Bodega
- Venta Cruzada (recomendaciones)
- Segmentación de Clientes (RFM)
- Metas y Comisiones
- Detección de anomalías (auditoría/fraude)

## Arquitectura

```
SAP SQL Anywhere 17 (ERP producción, SOLO LECTURA)
        │  SELECT vía pyodbc (etl/connectors/sqlany_connector.py)
        ▼
ETL Python (etl/orchestrator.py)
  - extractors/*.sql con tokens {CODEMP}, {ESTADO}, {FECHA_DESDE}
  - transformers/ (dims SCD2, hechos, dim_tiempo algorítmica)
  - loaders/ (dimensiones, hechos append-only con idempotencia)
  - control de cargas en edw.etl_control (incremental por última corrida OK)
        ▼
PostgreSQL 16 "postgres_edw" (Docker, puerto host 5433) — UN solo servidor, 3 esquemas:
  - edw.*    → DW multiestrella: 11 dimensiones + 11 tablas de hechos
  - public.* → app (roles, usuarios RBAC, cliente_lookup con PII real,
               metas_comerciales_operativas)
  - ml.*     → vistas para notebooks/entrenamiento (ml.v_ventas_cruzadas_desanonima)
        ▼                                    ▼
Backend FastAPI (backend/)            Pipeline ML (ml/)
  - JWT + RBAC (4 roles)                - ml/main.py entrena 6 modelos desde el EDW
  - KPIs y analytics por rol            - exporta .pkl a ml/models/
  - inferencia de los .pkl              - publish_models.py reinicia el backend
  - reentrenamiento (admin)               (volumen Docker ./ml/models:/app/ml_models:ro)
        ▼
Frontend React 19 + Vite + TS (frontend/, puerto 5173)
  - Dashboards por rol, Zustand + TanStack Query + Recharts
```

- **Origen de datos:** SAP SQL Anywhere 17 (`codemp='01'`, ~500 tablas OLTP; inventario en [docs/identificacion_bd.md](docs/identificacion_bd.md)).
- **Staging:** no hay capa de staging separada; los extractores SQL leen del ERP y los transformers en pandas producen directamente las tablas del EDW.
- **Data Marts:** no existen como capa separada; los "marts" son las vistas por rol servidas por la API.
- **Orquestación:** Docker Compose (`postgres_edw`, `backend`, `frontend`, y perfiles opcionales `etl` y `ml` que se ejecutan manualmente con `docker compose run`). No hay Airflow/dbt/SSIS.
- **Despliegue:** los DDL de `edw/` se ejecutan automáticamente al inicializar el contenedor de PostgreSQL (`/docker-entrypoint-initdb.d`) — **solo en volumen nuevo**.

## Tecnologías

- **Base de datos:** PostgreSQL 16 (EDW + app), SAP SQL Anywhere 17 (origen, solo lectura).
- **ETL:** Python 3 (pandas, SQLAlchemy 2, pyodbc, psycopg2, python-dotenv).
- **Backend:** FastAPI, Pydantic v2 / pydantic-settings, SQLAlchemy 2, python-jose (JWT), passlib+bcrypt, uvicorn.
- **ML:** scikit-learn, XGBoost, LightGBM, CatBoost, Optuna, mlxtend (Apriori), joblib, JupyterLab.
- **Frontend:** React 19, TypeScript, Vite 8, Tailwind CSS 4, Zustand, TanStack React Query, React Router 7, Recharts, Axios, oxlint.
- **Infraestructura:** Docker + Docker Compose (con `docker-compose.override.yml` para dev: hot-reload y mount de `ml/`).
- **Pruebas:** pytest (backend: `backend/tests/unit` y `backend/tests/integration`; etl: pytest declarado en requirements).

## Estructura del proyecto

| Ruta | Propósito |
|---|---|
| `etl/` | Pipeline ETL SAP → EDW. `orchestrator.py` (entrypoint), `extractors/*.sql` (24 extractores tokenizados), `transformers/`, `loaders/`, `connectors/`, `config/settings.py`, `tasks/generar_metas_operativas.py`. |
| `edw/` | DDL del DW en orden de ejecución: `01_schema.sql` … `09_vistas_ml.sql` (esquema, dims, hechos, índices, `etl_control`, verificación, tablas `public.*`, seed de roles/usuarios, vistas ML). |
| `backend/` | API FastAPI. `app/api/routes/` (routers), `app/services/` (lógica de negocio), `app/repositories/` (acceso a datos), `app/ml/` (carga e inferencia de .pkl), `app/models/` + `app/schemas/`, `app/core/` (config, seguridad, excepciones), `tests/`. |
| `ml/` | Entrenamiento. `main.py` (orquestador de los 6 modelos), `src/` (data/features/training/prediction/utils), `notebooks/` (EDA y experimentos), `models/` (.pkl publicados), `publish_models.py`, `REPORTE_MEJORA_MODELOS.md`. |
| `frontend/` | SPA React. `src/pages/` (dashboards por rol), `src/services/` (API + interceptores JWT), `src/store/` (Zustand), `src/hooks/`, `src/components/`, `src/router/AppRouter.tsx`. |
| `docs/` | Documentación: `arquitectura_dw.md` (diseño completo del EDW), `auditoria/` (reportes de auditoría), `features/`, `tesis/`, `matriz_trazabilidad.md`, `identificacion_bd.md`, `hoja_de_ruta_ejecucion.md`. |
| `.agent/` | Skills y workflows del agente (`workflows/ejecutar-etl.md`, `workflows/configurar-entorno.md`). |
| `docker-compose.yml` / `.env(.example)` | Orquestación y variables de entorno. |

## Reglas de negocio

Validadas contra Producción vía SELECT; detalle completo en [docs/auditoria/02_reglas_negocio_validadas.md](docs/auditoria/02_reglas_negocio_validadas.md):

1. **Estado de documento:** `estado = 'P'` (Procesada) es el único estado válido; `'A'` = anulada. Parametrizado como `ESTADO_VALIDO` (token `{ESTADO}`).
2. **Empresa:** toda la operación es `codemp = '01'`. Parametrizado como `CODEMP` (token `{CODEMP}`) para multi-empresa futura.
3. **Dirección de movimientos de Kardex:** `cantot` siempre es positivo (magnitud). La dirección la da `tipdoc`: entrada = `('EN','AC')`, salida = `('SA','AD')`. Nunca usar el signo de la cantidad.
4. **Transferencias (`tiporg='TRA'`):** cada ítem genera exactamente 2 filas (SA=bodega origen, EN=bodega destino) pareadas por `(codemp, numdoc, numren, codart)`. El kardex no expone cantidad solicitada ni estado de la transferencia (limitación del ERP).
5. **Descarga de inventario:** el costo de inventario solo aplica cuando `renglonesfacturas.desinv = 'S'` (líneas `'N'` son servicios/no inventariables).
6. **Stock:** la fuente de existencias por bodega es la vista `vi_mv_existencias` del ERP; el costo se toma de `articulos.ultcos`.
7. **Historial:** `Dim_Producto` y `Dim_Cliente` son SCD Tipo 2 (`es_vigente`, `fecha_inicio/fin_vigencia`).
8. **Anonimización PII:** los clientes se anonimizan con hash + salt (`PII_SALT`); la única tabla con PII real es `public.cliente_lookup`, aislada fuera del esquema `edw` a propósito. El ETL aborta si `PII_SALT` falta o usa el valor inseguro heredado.
9. **RBAC:** 4 roles fijos de negocio: `gerencia`, `administrador`, `ventas`, `bodega` (catálogo cerrado en `public.roles`; seed en `edw/08_seed_roles_usuarios.sql`). Ventas/bodega ven datos filtrados por su sucursal / código SAP.
10. **Metas y Comisiones (grano vendedor, 100% estadística, sin ML):** las metas operativas viven en `public.metas_comerciales_operativas` con grano `(anio, mes, id_vendedor_origen)` -- NO por sucursal, porque `edw.dim_vendedor` no tiene sucursal propia y un vendedor transacciona en múltiples sucursales (docs/auditoria/19_...md). Se generan vía `POST /gerencia/goals/generate` → `GoalMLService.generate_proposals`, que usa `IQRGoalCalculationEngine` (24 meses de Venta Neta, recorte de picos por IQR, tendencia rodante de los últimos meses, techo/piso de sanidad contra la tendencia reciente). El modelo `goals_rf` fue decomisionado (docs/auditoria/20_...md): no queda ningún modelo ML en este módulo. `edw.fact_metas_comerciales` existe pero está vacía.
11. **Ventana de entrenamiento de ventas (inferida, justificada en `ml/main.py`):** el modelo de ventas entrena solo con los últimos 3 años (`VENTANA_ENTRENAMIENTO_VENTAS_ANIOS`) por quiebre estructural del negocio (~31% de crecimiento 2018→2026); mejoró el R² de −0.03 a +0.21 en backtest.
12. **Registros centinela:** toda dimensión tiene una fila `-1` ("desconocido") usada cuando una llave foránea no resuelve; prohibido el fallback a filas arbitrarias (`LIMIT 1`), eliminado en auditoría 04.

## Restricciones

- **La base de datos de Producción (SAP) es de SOLO LECTURA.**
  - Nunca ejecutar `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `ALTER` o `MERGE` sobre Producción.
  - Toda validación contra Producción debe hacerse exclusivamente con `SELECT`.
- No asumir que el SQL existente es correcto (los extractores ya tuvieron bugs críticos corregidos; ver `docs/auditoria/03_cambios_aplicados.md`).
- Detectar y eliminar hardcodes; los valores de negocio van en `etl/config/settings.py` / variables de entorno, y en los extractores como tokens (`{CODEMP}`, `{ESTADO}`, `{FECHA_DESDE}` — cada rama de un `UNION ALL` lleva su propio token).
- Toda regla de negocio debe estar documentada (en `docs/auditoria/02_reglas_negocio_validadas.md` o en la sección correspondiente).
- Los DDL de `edw/` solo se ejecutan al crear el volumen de Docker; cambios de esquema en una BD existente requieren aplicación manual.
- Fail-fast de seguridad: el ETL aborta sin `PII_SALT` válido; el backend con `ENV=production` aborta si `JWT_SECRET` o `POSTGRES_PASSWORD` conservan el valor por defecto inseguro.
- El backend en producción NO tiene acceso al código de `ml/` (solo a los `.pkl` vía volumen de solo lectura); el reentrenamiento (`POST /admin/modelos/retrain`) solo funciona en dev con `docker-compose.override.yml`.
- Las librerías xgboost/catboost/lightgbm son dependencias de **runtime** del backend (los `.pkl` de joblib requieren la misma librería que los serializó); no removerlas aunque parezca deuda.
- `etl/truncate_edw.py` es destructivo sobre el EDW — usar solo de forma deliberada en desarrollo.

## Convenciones de desarrollo

- **Idioma:** código, comentarios, docs y nombres de negocio en español; snake_case en SQL y Python.
- **EDW:** dimensiones `dim_*` con surrogate keys `*_sk` (SERIAL), hechos `fact_*` (BIGSERIAL) con FKs a dims; SCD2 con `es_vigente`/vigencias; toda tabla lleva `fecha_carga`.
- **Extractores:** un archivo `etl/extractors/<entidad>_extractor.sql` por entidad, tokenizado; se registran en `PIPELINE_CONFIG` de `orchestrator.py` (SQL no referenciado ahí es código muerto).
- **Backend en capas:** `routes` → `services` → `repositories`. Los servicios lanzan excepciones de dominio (`app/core/exceptions.py`), nunca `HTTPException`; los handlers globales en `main.py` las traducen a HTTP. Sin lógica de negocio en `main.py` ni en los routers.
- **Frontend:** servicios por dominio en `src/services/`, tipos en `src/types/`, hooks de datos por rol en `src/hooks/`, permisos en `src/constants/permissions.ts`.
- **Configuración:** todo por variables de entorno con `.env` (plantilla en `.env.example`); nunca commitear secretos reales.
- **Comentarios:** los comentarios explican *por qué* (regla de negocio, hallazgo de auditoría), con referencia al reporte que lo valida.

## Flujo de trabajo esperado (para agentes de IA)

Antes de modificar código:

1. **Analizar contexto:** leer este documento, la documentación en `docs/` y el código afectado.
2. **Detectar dependencias:** qué extractores, transformers, tablas, servicios o dashboards dependen del componente.
3. **Evaluar impacto:** especialmente sobre datos ya cargados (idempotencia, SCD2) y sobre los contratos API/frontend.
4. **Generar auditoría:** crear un reporte en `docs/auditoria/` ANTES de modificar código (formato de los reportes existentes: fecha, alcance, método, hallazgos con severidad, acción).
5. **Proponer cambios:** documentar el cambio y su justificación (regla de negocio validada, no supuesta).
6. **Implementar:** respetando las restricciones (Producción solo lectura, sin hardcodes).
7. **Validar:** contra Producción solo con `SELECT`; contra el EDW con las verificaciones de `edw/06_verificacion.sql` y los tests (`pytest` en `backend/`); `py_compile` para el código Python del ETL.
8. **Documentar:** actualizar el reporte de auditoría con lo aplicado y las reglas de negocio nuevas en `docs/auditoria/02_reglas_negocio_validadas.md`.

## Auditoría

- Todos los reportes se guardan en `docs/auditoria/`. Existentes:
  - `00_planificacion.md` — inventario y arquitectura del proyecto.
  - `01_auditoria_extractores.md` — hallazgos en los extractores SQL.
  - `02_reglas_negocio_validadas.md` — reglas validadas contra SAP vía SELECT.
  - `03_cambios_aplicados.md` — correcciones aplicadas (idempotencia C1, tokens C2, dirección de kardex, etc.).
  - `04_auditoria_pipeline_python.md` — auditoría del núcleo Python del ETL.
  - `05_auditoria_ml_calidad_datos.md` — auditoría del pipeline ML y calidad de datos del EDW.
- La trazabilidad operativa de cargas vive en `edw.etl_control` (tabla + `edw/05_etl_control.sql`).
- `edw.fact_logs_auditoria` consolida modificaciones críticas del ERP para el detector de anomalías.
- Los reportes 00–05 referencian prompts por fase en una carpeta `prompts/` que ya no existe en el repo (ver Observaciones).

## Calidad de datos

Validaciones existentes:

- **Idempotencia de hechos:** antes de cargar, se borra por fecha real vía `dim_fecha` (`DELETE ... WHERE fecha_sk IN (SELECT fecha_sk FROM edw.dim_fecha WHERE fecha_completa >= :desde)`) y se hace append; el control incremental usa `edw.etl_control` (`estado='SUCCESS'`).
- **Integridad referencial:** FKs de todas las facts hacia las dims; llaves no resueltas van al registro centinela `-1` y se loguea `WARNING` con conteo de filas afectadas por columna.
- **SCD2 seguro:** `load_dim_scd2` verifica explícitamente la existencia de la tabla (no `except Exception` genérico) para no duplicar historial vigente.
- **Verificación post-carga:** `edw/06_verificacion.sql`.
- **Reconciliación con producción:** las reglas y volúmenes se validaron contra SAP con SELECT (auditorías 02 y 05); los 24 extractores se verificaron ejecutándose contra SAP (24/24 OK).
- **Hallazgos abiertos** (auditoría 05, no corregidos): `dim_geografia` vacía (0 filas), `edw.fact_metas_comerciales` vacía (metas solo en `public.metas_comerciales_operativas`), `dim_fecha.es_feriado` nunca poblado (workaround hardcodeado en código ML), `fact_inventario_snapshot` solo poblada "hacia adelante" (<1% histórico pre-2026).

## Objetos importantes

- **Dimensiones (11):** `dim_fecha` (conformada, generada algorítmicamente 2010–2030 parametrizable), `dim_producto` (SCD2), `dim_cliente` (SCD2, anonimizada), `dim_sucursal`, `dim_almacen`, `dim_proveedor`, `dim_vendedor`, `dim_empleado`, `dim_usuario`, `dim_formapago`, `dim_geografia` (vacía).
- **Hechos (11):** `fact_ventas_detalle` (~539k filas, principal), `fact_movimientos_inventario` (~948k), `fact_movimientos_caja`, `fact_cobros_cxc`, `fact_compras`, `fact_inventario_snapshot`, `fact_pagos_cxp`, `fact_devoluciones`, `fact_nomina`, `fact_metas_comerciales` (vacía), `fact_logs_auditoria`.
- **Tablas `public.*`:** `roles`, `usuarios` (auth de la plataforma), `cliente_lookup` (única tabla con PII real), `metas_comerciales_operativas`, `recomendaciones_eventos` (telemetría de Venta Cruzada, docs/auditoria/25_modulo_cross_selling.md).
- **Vistas:** `ml.v_ventas_cruzadas_desanonima` (une ventas con identidad real vía lookup, para notebooks); origen ERP: `vi_mv_existencias`.
- **Control:** `edw.etl_control` (idempotencia/auditoría del ETL).
- **Pipelines / entrypoints:** `etl/orchestrator.py` (ETL completo), `ml/main.py` (entrena los 6 modelos), `ml/publish_models.py` (recarga el backend). Las metas comerciales se generan desde el backend (`GoalMLService.generate_proposals`, `POST /gerencia/goals/generate`), no desde un task del ETL -- `docs/matriz_trazabilidad.md`/versiones previas de este documento referenciaban un `etl/tasks/generar_metas_operativas.py` que no existe en el repositorio (inconsistencia ya corregida aquí, ver `docs/auditoria/20_...md`).
- **Modelos ML (6, en `ml/models/*.pkl`, servidos por `backend/app/ml/`):** `sales_rf_model` / `sales_best_model` (predicción de ventas — Gerencia), `demand_rf_model` / `demand_best_model` (demanda — Bodega), `kmeans_rfm_model` (segmentación RFM, K=4 — Ventas), `churn_classifier` / `churn_best_classifier` (riesgo de fuga), `association` / `recommendation.pkl` (venta cruzada — filtrado colaborativo item-item por similitud coseno, contrato v0.2.0, ganador de la competencia documentada en `ml/REPORTE_MEJORA_MODELOS.md` y `docs/auditoria/25_modulo_cross_selling.md`; expone `score` genérico, NO `lift`), `isolation_forest_model` (anomalías — Admin). El modelo de metas (`goals_rf`) fue decomisionado (docs/auditoria/20_...md): Metas y Comisiones usa solo estadística pura.
- **API (prefijo `/api/v1`):** `/auth`, `/users`, `/roles`, `/analytics` (Gerencia), `/analytics/bodega`, `/analytics/ventas`, `/analytics/admin`, `/admin/modelos` (MLOps), `/gerencia/goals`. Salud en `/health`; Swagger en `/docs`. El módulo Bodega (docs/auditoria/23_modulo_bodega.md, extensión en docs/auditoria/24_prediccion_categoria_paginacion.md) expone bajo `/analytics/bodega`: `/filtros`, `/kpis`, `/salidas-forecast`, `/prediccion-compras-mes`, `/rotacion-matriz`, `/top-productos`, `/salidas-categoria`, `/stock-reorden`, `/necesidad-compra`, `/inventario-matriz`, `/transferencias-sugeridas`, `/notificaciones`, `/reportes/{tipo}[/excel]` — todo estadística sobre el EDW salvo el forecast por producto (`/salidas-forecast?producto_cod=...`) y `/prediccion-compras-mes` (predicción de compras del mes siguiente por categoría, con drill-down a los top artículos), que reutilizan `demand_rf` (sin modelos ML nuevos); umbrales configurables `BODEGA_*` en `backend/app/core/config.py` (reglas RN-B1..B7 en `docs/auditoria/02_reglas_negocio_validadas.md` §16). Paginación genérica reutilizable (`Page[T]`/`PaginationParams`, `backend/app/schemas/pagination.py`, espejo en `frontend/src/types/pagination.ts` + `components/ui/Pagination.tsx` + `hooks/usePagination.ts`) aplicada a `/stock-reorden`, `/necesidad-compra` (solo `recomendados`), `/inventario-matriz` y `/transferencias-sugeridas`. El módulo de Venta Cruzada (docs/auditoria/25_modulo_cross_selling.md) expone bajo `/analytics/ventas/cross-selling`: `POST /sugerencias` (asistente de canasta simulada), `POST /eventos` (telemetría mostrada/aceptada/rechazada, RN-CS2), `GET /kpis` (tasa de conversión) y `GET /productos` (autocompletar); reutiliza el modelo `association` (sin modelo nuevo); umbrales `CROSS_SELL_*` en `backend/app/core/config.py` (reglas RN-CS1/RN-CS2 en `docs/auditoria/02_reglas_negocio_validadas.md` §17). El endpoint original por-cliente (`GET /analytics/ventas/recommendations`) se conserva sin cambios de contrato, solo actualizado internamente para leer `score` en vez de `lift`. En el frontend, el Asistente de Venta Cruzada vive en una página propia (`/ventas/cross-selling`, `VentasCrossSelling.tsx`, nav propio en el Sidebar) -- mismo patrón que Metas y Comisiones (`/ventas/metas`), no una sección embebida en `DashboardVentas.tsx`.

## Dependencias

- **Externas:** SAP SQL Anywhere 17 (ERP; en Docker se conecta con FreeTDS/TDS 5.0 instalado en la imagen del ETL, en el host puede usarse el driver ODBC nativo — ver `docs/auditoria/06_auditoria_driver_sap_docker.md`), Docker/Docker Compose. Paquetes en `etl/requirements.txt`, `backend/requirements.txt`, `ml/requirements.txt`, `frontend/package.json`.
- **Internas (orden de dependencia):** EDW ← ETL ← ERP; ML entrena desde el EDW y publica `.pkl` que el backend consume vía volumen; el frontend depende de los contratos de la API; los DDL `edw/01..09` deben ejecutarse en orden.
- **Acoplamientos a tener en cuenta:** los `.pkl` acoplan versiones de librerías ML entre `ml/` y `backend/`; `publish_models.py` depende de Docker Compose en el host; el backend crea las tablas `public.*` con `Base.metadata.create_all` además del DDL de `edw/07`.

## Riesgos técnicos (observados, no corregidos)

- **`etl/loaders/` está borrado del working tree** (`dim_loader.py`, `fact_loader.py` figuran como eliminados sin commit) pero `orchestrator.py` los importa: **el ETL no puede ejecutarse en el estado actual del árbol de trabajo**. Están en git (`git ls-files` los rastrea); verificar si el borrado fue intencional.
- Scripts ad-hoc de diagnóstico en `etl/` (`query_diag_db.py`, `query_nc.py`, `query_notas_credito.py`, `test_sap.py` duplicado en `etl/` y `etl/connectors/`, `inspect_formapago.py`): código exploratorio mezclado con el pipeline.
- `etl/truncate_edw.py`: script destructivo sin salvaguardas, junto al pipeline.
- Duplicación de artefactos ML: `ml/models/`, `backend/ml_models/` y `models/` (raíz) contienen `.pkl`; `catboost_info/` en la raíz y en `ml/` son residuos de entrenamiento.
- `docs/credenciales_sistema.md` versionado en el repo: riesgo de exposición de credenciales.
- CORS por defecto `"*"` en el backend (solo aceptable en dev; restringir en producción vía `CORS_ORIGINS`).
- Defaults inseguros conocidos (JWT, password de BD) tolerados fuera de `ENV=production`.
- Frontend con `src/services/mocks/`: verificar que ningún dashboard consuma mocks en producción.
- Deuda documentada: `es_feriado` con workaround hardcodeado en ML, `dim_geografia` y `fact_metas_comerciales` vacías, cabeceras de extractor huérfanas ya eliminadas en auditoría 04.

## Observaciones (inconsistencias código ↔ documentación)

- **Crítico:** `docs/auditoria/04_auditoria_pipeline_python.md` describe correcciones aplicadas a `etl/loaders/*`, pero esos archivos están actualmente borrados del working tree (cambio sin commitear). El estado en disco contradice la auditoría y rompe el ETL.
- `docs/auditoria/00_planificacion.md` referencia rutas antiguas del backend (`backend/app/api/v1/endpoints/`); la estructura actual es `backend/app/api/routes/` (los endpoints v1 antiguos figuran como eliminados en git).
- Los reportes de auditoría mencionan una carpeta `prompts/` (prompts de fases 00–08) que no existe en el repositorio.
- `.agent/workflows/ejecutar-etl.md` referencia la ruta `c:\Tesis` como raíz de trabajo; la raíz real es `c:\Proyect_BI`.
- `docs/matriz_trazabilidad.md` lista rutas de endpoints (`/api/v1/kpis/gerencia/forecast`, etc.) que no coinciden con los prefijos reales de `backend/app/api/routes/api.py` (`/analytics/...`, `/gerencia/goals`); tomar el código como fuente de verdad.
- ~~Dos convenciones de variables de conexión al ERP (`SQLANY_*` vs `DB_*`)~~ — resuelto 2026-07-08: `.env.example` ahora usa las variables `DB_*` que realmente lee `etl/config/settings.py` (auditoría 06).
- `docs/auditoria/00_planificacion.md` indica "No existe README raíz": sigue siendo cierto; este CLAUDE.md actúa como documento principal de contexto.
- Pendiente de documentar: ventanas de carga/calendarización del ETL (hoy la ejecución es manual; el crontab está planificado en la Fase 6 de `docs/hoja_de_ruta_ejecucion.md`).
