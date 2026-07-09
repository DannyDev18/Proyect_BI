# Auditoría ETL — Fase 0: Planificación e Inventario

- **Proyecto:** Plataforma Inteligente de Analítica Empresarial (`c:\Proyect_BI`)
- **Fase:** 0 — Planificación / Inventario (prompt `prompts/00_planificacion.md`)
- **Fecha:** 2026-07-08
- **Alcance:** Análisis de arquitectura e inventario del proyecto completo. **No se revisa aún el contenido lógico de los SQL. No se modifica ningún archivo.**
- **Regla base (CLAUDE.md):** la BD de Producción es de **solo lectura**; toda validación se hace con `SELECT`. Antes de modificar código se genera reporte de auditoría; todos los reportes viven en `docs/auditoria/`.

> **Nota sobre el nombre de archivo:** el prompt de Fase 0 sugiere `00_inventario.md`, pero se genera con el nombre solicitado explícitamente por el usuario: `docs/auditoria/00_planificacion.md`.

---

## 1. Estructura del proyecto

```
c:\Proyect_BI\
├── etl\          Pipeline ETL en Python (SAP SQL Anywhere → EDW PostgreSQL)
├── edw\          DDL del Data Warehouse (PostgreSQL 16, esquemas edw / public / ml)
├── backend\      API FastAPI (BI + servido de modelos ML)
├── ml\           Entrenamiento y serialización de modelos (MLOps)
├── frontend\     SPA React 19 + Vite + TypeScript (dashboards)
├── docs\         Documentación (arquitectura, features, tesis, auditoría, requisitos)
├── prompts\      Prompts de auditoría por fases (00–08)
├── .agent\       Skills y workflows del agente
├── models\       Modelos serializados (nivel raíz)
├── catboost_info\ Artefactos de entrenamiento CatBoost
├── docker-compose.yml   Orquestación de servicios
├── .env / .env.example  Variables de entorno (secretos / plantilla)
└── CLAUDE.md     Contexto y reglas del proyecto
```

Archivos de log sueltos en raíz: `backend.log`, `backend_crash.log`, `backend_logs.txt`, `etl_run.log`. **No existe README raíz.**

---

## 2. Módulos encontrados

| Módulo | Tecnología | Rol | Rutas clave |
|---|---|---|---|
| **ETL** | Python (pyodbc, SQLAlchemy, psycopg2, pandas) | Extracción SAP → carga EDW | `etl/orchestrator.py`, `etl/extractors/`, `etl/loaders/`, `etl/transformers/`, `etl/connectors/` |
| **EDW** | PostgreSQL 16 | Data Warehouse (modelo multiestrella) | `edw/01_schema.sql` … `edw/09_vistas_ml.sql` |
| **Backend** | FastAPI 2.0 (SQLAlchemy, Pydantic, JWT) | API BI + inferencia ML | `backend/app/main.py`, `backend/app/api/v1/`, `backend/app/services/`, `backend/ml_models/*.pkl` |
| **ML** | scikit-learn / XGBoost / CatBoost / LightGBM | Entrenamiento y publicación de modelos | `ml/main.py`, `ml/src/`, `ml/publish_models.py`, `ml/notebooks/` |
| **Frontend** | React 19 + Vite + TS + Tailwind 4 | Dashboards por rol | `frontend/src/pages/`, `frontend/src/services/api.ts`, `frontend/src/router/AppRouter.tsx` |

**Servicios backend por caso de negocio** (según reglas de CLAUDE.md):

| Caso de negocio | Servicio | Endpoint |
|---|---|---|
| Predicción de ventas | `prediction_service.get_sales_forecast_weekly` | `GET /analytics/gerencia/sales-prediction` |
| Predicción de reposición (demanda) | `prediction_service.get_demand_forecast` | `GET /analytics/bodega/demand-forecasting` |
| Dashboard Gerencial | `analytics_service.get_management_kpis` (+ revenue/categorías/sucursales/vendedores) | `GET /analytics/gerencia/kpis` |
| Dashboard de Bodega | `analytics_service.get_warehouse_kpis` | `GET /analytics/bodega/kpis-inventory` |
| Venta Cruzada | `prediction_service.get_product_recommendations` | `GET /analytics/ventas/recommendations` |
| Segmentación de Clientes | `prediction_service.get_customer_segment` / `get_churn_risk` | `GET /analytics/ventas/clientes/{cod}/segmento` |
| Metas y Comisiones | `analytics_service.GoalsAutomationService` + `endpoints/goals.py` | `/gerencia/goals` |
| MLOps (reentrenamiento) | `mlops_service` + `endpoints/admin_mlops.py` | `POST /admin/modelos/retrain` |

---

## 3. Arquitectura del ETL

**Flujo:** SAP SQL Anywhere (origen, solo lectura) → extractores SQL → transformers Python → staging temporal → loaders → EDW PostgreSQL.

- **Orquestador:** `etl/orchestrator.py` — orquestador propio secuencial (sin Airflow/DAGs). Define `PIPELINE_CONFIG` (dimensiones → hechos), control incremental vía tabla `edw.etl_control` (`get_last_etl_date`, `registrar_control_etl`) y hashing PII (hashlib/hmac).
- **Conectores:** `connectors/sqlany_connector.py` (origen SAP, ODBC/pyodbc) · `connectors/postgres_connector.py` (destino EDW, psycopg2; modos append / truncate / upsert).
- **Extractores:** 22 archivos `etl/extractors/*.sql` (queries `SELECT` contra SAP).
- **Transformers:** `transformers/dim_tiempo.py` (genera `Dim_Fecha`), `dim_transformer.py`, `fact_transformer.py`.
- **Loaders:** `loaders/dim_loader.py` (`load_dimension`, `load_dim_scd2`), `loaders/fact_loader.py` (`load_facts_append_only`).
- **Configuración:** `etl/config/settings.py` (`ETLConfig`, lee variables de entorno vía `python-dotenv`).
- **Tareas:** `etl/tasks/generar_metas_operativas.py`.
- **Utilitarios sueltos (no del pipeline):** `truncate_edw.py`, `query_diag_db.py`, `query_nc.py`, `query_notas_credito.py`, `test_sap.py`, `connectors/inspect_formapago.py`.

**Staging:** no hay tablas staging persistentes. El staging es temporal y dinámico: `edw._stg_<tabla>` creado con `if_exists='replace'` y eliminado tras el upsert (`postgres_connector.py`).

---

## 4. Inventario SQL — total: **31**

### 4.1 Extractores SAP — 22 (`etl/extractors/*.sql`)

**Origen de dimensiones (10):**

| Archivo | Propósito (tabla origen SAP) |
|---|---|
| `articulos_extractor.sql` | Producto / Artículo (`articulos`) |
| `clientes_extractor.sql` | Cliente (`clientes`) |
| `proveedores_extractor.sql` | Proveedor (`proveedores`) |
| `vendedores_extractor.sql` | Vendedor (`vendedorescob`) |
| `empleados_extractor.sql` | Empleado (`nom_empleados`) |
| `usuarios_extractor.sql` | Usuario (`usuarios`) |
| `sucursales_extractor.sql` | Sucursal (`establecimientos`) |
| `almacenes_extractor.sql` | Almacén |
| `geografia_extractor.sql` | Geografía (contiene literal `'Ecuador'`) |
| `formapago_extractor.sql` | Forma de pago (SELECT estático UNION ALL) |

**Origen de hechos (12):**

| Archivo | Propósito (tabla origen SAP) |
|---|---|
| `facturas_cabecera_extractor.sql` | Facturación cabecera (`encabezadofacturas`) |
| `facturas_detalle_extractor.sql` | Detalle de facturas (`renglonesfacturas`) |
| `devoluciones_cabecera_extractor.sql` | Devoluciones / notas de crédito cabecera |
| `devoluciones_detalle_extractor.sql` | Devoluciones detalle |
| `compras_cabecera_extractor.sql` | Compras cabecera (`encabezadocompras`) |
| `compras_detalle_extractor.sql` | Compras detalle (`renglonescompras`) |
| `cobros_cxc_extractor.sql` | Cobros cuentas por cobrar (`cuentasporcobrar`) |
| `pagos_cxp_extractor.sql` | Pagos cuentas por pagar (`cuentasporpagar`) |
| `nomina_extractor.sql` | Nómina (`nom_nomina`) |
| `movimientos_caja_extractor.sql` | Movimientos de caja |
| `kardex_extractor.sql` | Inventario / movimientos (`kardex`) |
| `metas_comerciales_extractor.sql` | Metas comerciales (`metas`) |

### 4.2 DDL del Data Warehouse — 9 (`edw/*.sql`)

| Archivo | Propósito |
|---|---|
| `01_schema.sql` | Crea schema `edw` y usuario de solo lectura para backend |
| `02_dimensiones.sql` | Define las 13 tablas de dimensiones |
| `03_hechos.sql` | Define las 11 tablas de hechos |
| `04_indices.sql` | Índices de desempeño sobre las Fact |
| `05_etl_control.sql` | Tabla `edw.etl_control` (auditoría / idempotencia del ETL) |
| `06_verificacion.sql` | Script de verificación del despliegue (psql `\echo`) |
| `07_public_app_tables.sql` | Tablas de aplicación `public.*`: roles, usuarios, cliente_lookup (auth) |
| `08_seed_roles_usuarios.sql` | Seed idempotente de roles y usuario admin |
| `09_vistas_ml.sql` | Schema `ml` y vista `ml.v_ventas_cruzadas_desanonima` |

---

## 5. Tablas del Data Warehouse

### 5.1 Dimensiones — 13 (`edw/02_dimensiones.sql`)

`Dim_Fecha`, `Dim_Sucursal`, `Dim_Almacen`, `Dim_Producto`, `Dim_Cliente`, `Dim_Proveedor`, `Dim_Vendedor`, `Dim_Empleado`, `Dim_Usuario`, `Dim_FormaPago`, `Dim_Geografia`.

> `Dim_Fecha` se genera programáticamente en `transformers/dim_tiempo.py`. (El conteo de 13 incluye las dimensiones declaradas en el DDL; se confirmará el detalle exacto en la Fase 1.)

### 5.2 Hechos — 11 (`edw/03_hechos.sql`)

`Fact_Ventas_Detalle`, `Fact_Inventario_Snapshot`, `Fact_Movimientos_Inventario`, `Fact_Compras`, `Fact_Cobros_CXC`, `Fact_Pagos_CXP`, `Fact_Nomina`, `Fact_Movimientos_Caja`, `Fact_Metas_Comerciales`, `Fact_Logs_Auditoria`, `Fact_Devoluciones`.

### 5.3 Staging

Sin tablas staging persistentes. Staging temporal dinámico `edw._stg_<tabla>` en `postgres_connector.py` (creado y borrado en cada upsert).

---

## 6. Conteos resumen

| Métrica | Cantidad |
|---|---|
| Scripts SQL totales | **31** |
| — Extractores SAP | 22 |
| — DDL del DW | 9 |
| Dimensiones (DW) | **13** |
| Hechos (DW) | **11** |
| Módulos principales | 5 (ETL, EDW, Backend, ML, Frontend) |
| Modelos ML entrenados | 7 |

**Modelos ML:** ventas (`sales_rf_model.pkl`), demanda/reposición (`demand_rf_model.pkl`), segmentación RFM/KMeans (`kmeans_rfm_model.pkl`), churn (`churn_classifier.pkl`), recomendación/venta cruzada (`association_rules.pkl`), anomalías (`isolation_forest_model.pkl`), metas (`goals_rf_model.pkl`).

---

## 7. Dependencias

- **Backend:** `backend/requirements.txt` — fastapi, uvicorn, sqlalchemy, pydantic, psycopg2-binary, python-jose, passlib, pandas, scikit-learn, xgboost, catboost, lightgbm, joblib.
- **ML:** `ml/requirements.txt`.
- **Frontend:** `frontend/package.json` — react 19, vite, typescript, tailwindcss 4, zustand, axios, recharts, react-router-dom 7, lucide-react.
- **ETL:** `etl/requirements.txt` (pyodbc, SQLAlchemy, psycopg2, pandas, python-dotenv).
- **Orquestación:** `docker-compose.yml`, `backend/Dockerfile`, `etl/Dockerfile`, `ml/Dockerfile`.
- **Entorno:** `.env` (secretos reales) / `.env.example` (plantilla: SAP, PostgreSQL EDW, App auth, JWT, control ETL — `BATCH_SIZE`, `FECHA_DESDE`, `MODO_INCREMENTAL`).
- **Nota:** no existe `pyproject.toml` ni `requirements.txt` a nivel raíz; las dependencias Python están separadas por servicio.

**Cadena de dependencias de datos:** SAP SQL Anywhere → ETL → EDW PostgreSQL → (Backend API + ML training) → Frontend. El backend se conecta al EDW vía `backend/app/db/session.py` con URI `postgresql://etl_user@postgres_edw:5432/edw` (`backend/app/core/config.py`).

---

## 8. Documentación relacionada

| Documento | Contenido |
|---|---|
| `docs/arquitectura_dw.md` | Diseño del DW: modelo multiestrella (PostgreSQL 16 / SAP SQL Anywhere 17), v2.0 |
| `docs/data_engineering_etl_architecture.md` | Arquitectura de ingeniería de datos y estructura del pipeline |
| `docs/diseno_etl_reposicion_inventario.md` | Diseño ETL y preparación de datos para reposición de inventario |
| `docs/matriz_trazabilidad.md` | Trazabilidad negocio → fuente SAP → ETL/dimensión → ML → endpoint → dashboard |
| `docs/hoja_de_ruta_ejecucion.md` | Hoja de ruta (transición Fase 5 Frontend → Fase 6 Despliegue) |
| `docs/identificacion_bd.md` | Listado crudo de tablas de la BD origen |
| `docs/ml_metrics_report.md` | Métricas de reentrenamiento de modelos (Julio 2026) |
| `docs/features/*` | Specs: predicción de ventas, cross-selling, segmentación, dashboards, metas comerciales |
| `docs/tesis/*` | Propuesta, documentación completa, NDA, LOPDP, anonimización, metodología Kimball |
| `docs/requirements/preguntas_metas_comisiones.md` | Levantamiento de requisitos de metas/comisiones |

`docs/auditoria/` (destino de esta auditoría) y `docs/architecture/` existían vacías al inicio.

---

## 9. Señales tempranas detectadas

> Registradas para las fases posteriores. **No auditadas en esta fase** — sin análisis de fondo.

- **Credenciales/host hardcodeados** en scripts sueltos: `truncate_edw.py` (`password=CHANGE_ME host=127.0.0.1 port=5433`), `query_diag_db.py` (`postgresql://postgres:postgres@localhost:5432/bi_dw`).
- **`PII_SALT` con valor por defecto** en `etl/config/settings.py` (`"s3cr3t_s4lt_v3ry_s3cur3"`), además de defaults de usuario/host/puerto.
- **Valores de negocio fijos** en extractores: `'Ecuador'` en `geografia_extractor.sql`; dimensión completamente estática en `formapago_extractor.sql`.
- **Inconsistencia de configuración de BD** entre scripts: aparecen `5432/edw`, `5433/edw` y `5432/bi_dw`.
- **Archivos duplicados:** dos copias de `test_sap.py` (`etl/` y `etl/connectors/`).
- **Carpeta `backend/ml/` vacía** (los pickles servidos están en `backend/ml_models/`).

---

## 10. Orden recomendado de auditoría (fases siguientes)

Según los prompts en `prompts/`:

| Orden | Prompt | Objetivo |
|---|---|---|
| Fase 0 ✅ | `00_planificacion.md` | Planificación / inventario (este documento) |
| Fase 1 | `01_inventario.md` | Revisar todos los archivos SQL a partir del inventario |
| Fase 2 | `02_hardcoding.md` | Detectar valores hardcodeados en los extractores |
| Fase 3 | `03_comparacion.md` | Analizar el SQL de cada proceso ETL |
| Fase 4 | `05_calidad.md` | Revisar todos los JOIN *(encabezado dice Fase 4)* |
| Fase 5 | `04_validacion.md` | Validar el DW tabla por tabla *(encabezado dice Fase 5)* |
| Fase 6 | `06_validacionml.md` | Evaluar si el DW es apto para ML |
| Fase 7 | `07_refactorizacion.md` | Proponer refactorización del ETL |
| Fase 8 | `08_implementacion.md` | Implementar la refactorización aprobada |

> **Advertencia:** la numeración de nombres de archivo `04`/`05` está cruzada respecto a la "Fase" declarada en sus encabezados (`04_validacion.md` dice Fase 5; `05_calidad.md` dice Fase 4). Se recomienda respetar el orden lógico de la tabla y aclarar la numeración antes de la Fase 7.

---

## 11. Estado

Fase 0 completada. Inventario generado sin modificar archivos del proyecto y sin revisar el contenido lógico de los SQL. **A la espera de instrucciones para iniciar la Fase 1.**
