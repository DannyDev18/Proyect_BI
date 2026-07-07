# Documentación de Arquitectura de Ingeniería de Datos y ETL

## 1. Resumen Ejecutivo

Este documento describe la arquitectura, la estructura del código y las implementaciones técnicas construidas para la **Plataforma Inteligente de Análisis de Negocios** (Proyect_BI). El enfoque de esta documentación es la capa de Ingeniería de Datos, específicamente el pipeline ETL (Extracción, Transformación y Carga) que migra los datos desde el sistema transaccional SAP SQL Anywhere hacia el Data Warehouse Empresarial (EDW) en PostgreSQL.

## 2. Visión General de la Arquitectura

El pipeline ETL sigue una arquitectura modular, robusta y basada en scripts, administrada por un orquestador central en Python.

### Componentes Principales

- **Origen**: SAP SQL Anywhere (Base de Datos Transaccional).
- **Destino**: PostgreSQL 16 (Data Warehouse Dimensional).
- **Orquestación**: Python (`etl/orchestrator.py`) que utiliza archivos SQL para la extracción, Pandas para la transformación y SQLAlchemy para la ingesta de datos.

### Diagrama de Componentes (C4 Context)

```mermaid
graph TD
    SAP[(SAP SQL Anywhere\nOrigen)]
    PG[(PostgreSQL EDW\nDestino)]
    Orch[Orquestador Python\n'orchestrator.py']
    Ext[Extracción SQL\n'etl/extractors/*.sql']
    Trans[Transformaciones Pandas\n'etl/transformers/']
    Load[Cargadores Python\n'etl/loaders/*.py']

    Orch -->|Invoca| Ext
    Ext -->|Ejecuta Queries| SAP
    SAP -->|Data Bruta (DataFrames)| Orch
    Orch -->|Envía a| Trans
    Trans -->|Data Limpia| Orch
    Orch -->|Envía a| Load
    Load -->|Inserta/Actualiza| PG
```

## 3. Capa de Extracción de Datos (Extractores)

El proceso de extracción ha sido completamente modularizado para aislar las consultas monolíticas del código en Python. Se crearon archivos `.sql` dedicados en el directorio `etl/extractors/` para cada tabla especificada en el diseño del EDW.

**Scripts Clave Creados:**

- **Dimensiones**: `clientes_extractor.sql`, `articulos_extractor.sql`, `vendedores_extractor.sql`, `sucursales_extractor.sql`, `almacenes_extractor.sql`, `proveedores_extractor.sql`, `empleados_extractor.sql`, `usuarios_extractor.sql`, `formapago_extractor.sql`, `geografia_extractor.sql`.
- **Hechos (Facts)**: `facturas_cabecera_extractor.sql`, `facturas_detalle_extractor.sql`, `kardex_extractor.sql`, `compras_cabecera_extractor.sql`, `compras_detalle_extractor.sql`, `cobros_cxc_extractor.sql`, `pagos_cxp_extractor.sql`, `nomina_extractor.sql`, `movimientos_caja_extractor.sql`, `metas_comerciales_extractor.sql`, `devoluciones_cabecera_extractor.sql`, `devoluciones_detalle_extractor.sql`.

## 4. Capa de Carga de Datos (Loaders)

El componente de ingesta de datos maneja la complejidad de sincronizar los DataFrames transformados hacia PostgreSQL, garantizando la integridad de los datos, el seguimiento histórico y evitando duplicidades.

### `etl/loaders/dim_loader.py`

Maneja todas las tablas Dimensionales.

- **`load_dimension(pg, df, tabla, claves_negocio)`**: Carga UPSERT estándar. Realiza un `INSERT ... ON CONFLICT DO UPDATE`, asegurando que cualquier cambio en SAP se refleje en el EDW sin crear registros duplicados.
- **`load_dim_scd2(pg, df_new, tabla, claves_negocio, desc_col)`**: Implementa la lógica de **Dimensiones Lentamente Cambiantes Tipo 2 (SCD2)**. Lee los registros actualmente activos (`es_vigente = TRUE`), los compara con el nuevo lote de extracción de forma nativa en Pandas, marca los registros antiguos como expirados estableciendo `es_vigente = FALSE` y `fecha_fin_vigencia = CURRENT_DATE` en la base de datos, e inserta las nuevas filas. Se utiliza para `Dim_Producto` y `Dim_Cliente` con el fin de rastrear el historial de precios o zonificación.

### `etl/loaders/fact_loader.py`

Maneja todas las tablas de Hechos (Transaccionales).

- **`load_facts_full(pg, df, tabla)`**: Ejecuta un `TRUNCATE` seguido de un `BULK INSERT`. Ideal para tablas de estado/fotografía no aditivas (ej. `Fact_Inventario_Snapshot`).
- **`load_facts_incremental(pg, df, tabla, date_col, dt_start, dt_end)`**: Aplica una estrategia de carga **Idempotente**. Primero ejecuta un `DELETE` en el rango de partición definido por `dt_start` y `dt_end`, y luego anexa (append) los datos. Esto garantiza que volver a ejecutar el ETL tras una falla diaria no duplicará los hechos transaccionales.
- **`load_facts_append_only(pg, df, tabla)`**: Inserción simple hacia adelante para logs donde solo se agregan datos nuevos.

## 5. Automatización y Ejecución (Orquestador)

El módulo `orchestrator.py` integra estas capas secuencialmente:

1. Valida los parámetros de conexión hacia SAP y hacia el PostgreSQL interno (`config.settings`).
2. Genera dimensiones estáticas (Dimensión Tiempo).
3. Ejecuta los comandos de lectura analizando los archivos SQL de manera secuencial.
4. Limpia strings, normaliza IDs y aplica conversiones de tipos a través de `dim_transformer.py` y `fact_transformer.py`.
5. Llama a las funciones compartidas en `dim_loader` y `fact_loader` inyectando el contexto procesado hacia las estructuras de esquema de PostgreSQL.
6. Escribe los resultados de éxito/falla y el conteo de filas afectadas procesadas de carga en la tabla central de auditoría `edw.etl_control`.

## 6. Instrucciones de Ejecución

Este módulo es completamente 'plug-and-play'. Si los servicios de Docker están activos (mediante `/configurar-entorno`), ejecuta el pipeline lanzando el siguiente comando:

```bash
cd backend/etl
python orchestrator.py
```
