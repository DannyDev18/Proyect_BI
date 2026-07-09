# Auditoría Técnica del Extractor ETL — Ventas, Inventario y Logística

- **Proyecto:** Plataforma Inteligente de Analítica Empresarial (`c:\Proyect_BI`)
- **Alcance:** capa `etl/extractors/` (22 SQL) + núcleo Python del pipeline (`orchestrator.py`, connectors, transformers, loaders, settings).
- **Fecha:** 2026-07-08
- **Modo:** SOLO LECTURA. No se ejecutó SQL contra Producción ni se modificó ningún archivo del proyecto (regla CLAUDE.md: *auditar antes de modificar*).
- **Objetivo:** entender el ETL actual, detectar problemas técnicos y de negocio, y proponer mejoras **sin rehacer el ETL desde cero**. Este documento es el **entregable de la Octava fase** (documento técnico) y precede a cualquier cambio de código.

> **Validación pendiente contra Producción (solo `SELECT`):** varios hallazgos dependen de la estructura real del ERP SAP SQL Anywhere (unicidad de claves, significado de códigos de estado y de `tiporg`, existencia de tabla de existencias). Se marcan como **[VALIDAR]**.

---

## 1. Estructura actual del extractor

```
etl/
├── orchestrator.py            Orquestador secuencial (lee .sql, transforma, resuelve SKs, carga)
├── config/settings.py         ETLConfig (dataclass leída de .env)
├── connectors/
│   ├── sqlany_connector.py    Origen SAP SQL Anywhere (pyodbc; streaming por chunks)
│   └── postgres_connector.py  Destino EDW PostgreSQL (append / truncate / upsert + staging _stg_)
├── transformers/
│   ├── dim_transformer.py     Limpieza/normalización de dimensiones
│   ├── fact_transformer.py    Limpieza/cálculo de hechos
│   └── dim_tiempo.py          Genera Dim_Fecha algorítmicamente + normalizadores
├── loaders/
│   ├── dim_loader.py          load_dimension (upsert) + load_dim_scd2 (SCD Tipo 2)
│   └── fact_loader.py         load_facts_append_only (usado) + full/incremental (código muerto)
└── extractors/               22 SELECT contra SAP (10 dimensiones + 12 hechos)
```

---

## 2. Explicación de cada componente

### 2.1 Extractores SQL (`etl/extractors/*.sql`)
Consultas `SELECT` contra SAP SQL Anywhere. Cada archivo produce el "raw" de una dimensión o hecho. **Todos** filtran por empresa con el literal `codemp = '01'` y **ninguno** trae filtro de fecha propio (el filtro incremental lo inyecta el orquestador; ver §4).

### 2.2 `orchestrator.py`
Punto de entrada `run_etl(config)`. Genera primero `Dim_Fecha` en memoria y luego itera `PIPELINE_CONFIG` (10 dimensiones → 12 hechos). Por cada entrada: lee el `.sql`, inyecta filtro incremental, extrae por chunks de 10 000, aplica el `transform`, resuelve llaves subrogadas (SK) contra las dimensiones y carga con el `loader` indicado. Controla incremental/idempotencia vía `edw.etl_control` y aplica hashing PII (HMAC-SHA256) al cliente.

### 2.3 `config/settings.py`
`ETLConfig` lee credenciales SAP/PostgreSQL, `PII_SALT`, `BATCH_SIZE`, `FECHA_DESDE`, `MODO_INCREMENTAL` desde `.env`. **Nota:** `BATCH_SIZE`, `FECHA_DESDE`, `MODO_INCREMENTAL` y `CODEMP` existen pero **no se usan** en el pipeline.

### 2.4 Connectors
- `sqlany_connector.py`: conexión pyodbc a SAP; `yield_query_chunks` (streaming). Usa dialecto `mssql+pyodbc` como *hack* de SQLAlchemy pero opera con la conexión raw.
- `postgres_connector.py`: `load_dataframe(modo=append|truncate|upsert)`. El `upsert` escribe a staging temporal `edw._stg_<tabla>` y hace `INSERT ... ON CONFLICT (claves) DO UPDATE`.

### 2.5 Transformers / Loaders
- Transformers: normalizan fechas/números/strings y calculan métricas.
- Loaders: `dim` (upsert), `scd2` (SCD Tipo 2 para `dim_cliente` y `dim_producto`), `fact_inc` (que en la práctica llama a `load_facts_append_only`, un INSERT puro).

---

## 3. Flujo ETL actual (mapa)

```
SAP SQL Anywhere (solo lectura)
        │  SELECT (codemp='01', sin fecha propia)
        ▼
extractors/*.sql ──lee──> orchestrator.py
        │  inyecta " AND <delta_col> >= 'fecha' " reemplazando ';'
        │  extrae por chunks (10.000)
        ▼
transformers/*  (normaliza, calcula, hashea PII cliente)
        ▼
resolver_llaves_hecho  (merge contra dim_* para códigos → SK)
        ▼
loaders/*  (dim=upsert | scd2 | fact_inc=append)
        ▼
EDW PostgreSQL (edw.Dim_*, edw.Fact_*)  +  edw.etl_control (trazabilidad)
```

**Mapa extractor → tabla DW (de `PIPELINE_CONFIG`):**

| # | Extractor | Tabla DW | Loader | delta_col |
|---|---|---|---|---|
| Dim | geografia / sucursales / almacenes / clientes / proveedores / vendedores / empleados / usuarios / formapago / articulos | dim_geografia … dim_producto | dim / **scd2** (cliente, producto) | fecult (algunos) |
| Hecho | kardex_extractor | fact_movimientos_inventario | fact_inc | fecdoc |
| Hecho | facturas_detalle_extractor | fact_ventas_detalle | fact_inc | e.fecfac |
| Hecho | compras_detalle_extractor | fact_compras | fact_inc | e.fecfac |
| Hecho | cobros_cxc / pagos_cxp | fact_cobros_cxc / fact_pagos_cxp | fact_inc | fecemi |
| Hecho | nomina / movimientos_caja / metas_comerciales | fact_nomina / fact_movimientos_caja / fact_metas_comerciales | fact_inc | fecdoc / fecape / fecmes |
| Hecho | devoluciones_detalle | fact_devoluciones | fact_inc | e.fecfac |

> Nota: los extractores de **cabecera** (`facturas_cabecera`, `compras_cabecera`, `devoluciones_cabecera`) **no están en `PIPELINE_CONFIG`** → no se cargan (código/consultas huérfanas).

---

## 4. Problemas encontrados

### 4.1 CRÍTICOS (correctitud — generan datos erróneos)

**C1 · Idempotencia rota → duplicación de hechos en cada corrida incremental.**
`Dim_Fecha.fecha_sk` es `SERIAL PRIMARY KEY` ([edw/02_dimensiones.sql:7](../../edw/02_dimensiones.sql#L7)) y los hechos obtienen su `fecha_sk` por merge sobre `fecha_completa` ([orchestrator.py:111-114](../../etl/orchestrator.py#L111-L114)), es decir reciben un serial pequeño (1, 2, 3…). Pero el DELETE de idempotencia compara `fecha_sk >= YYYYMMDD` (p.ej. `>= 20260703`) ([orchestrator.py:260-261](../../etl/orchestrator.py#L260-L261)). Ese umbral **nunca** se alcanza → borra 0 filas → como el loader es `load_facts_append_only` (INSERT puro), **cada ejecución incremental vuelve a insertar los mismos hechos** (duplicados). El propio código lo admite en comentarios (líneas 255-259: *"¿es Integer o DATE? ... ASUMIMOS..."*).

**C2 · Filtro incremental incompleto en SQL con `UNION ALL`.**
El filtro se inyecta con `sql_query.replace(';', " AND <delta_col> >= '...';")` ([orchestrator.py:270](../../etl/orchestrator.py#L270)). En `facturas_detalle_extractor.sql` (dos SELECT unidos por `UNION ALL`, con un único `;` final) el `AND e.fecfac >= ...` se añade **solo a la segunda rama** (notas de crédito); la primera rama (facturas) **re-extrae todo el histórico** cada corrida. Combinado con C1, multiplica los duplicados. Afecta a los extractores con `UNION ALL`.

**C3 · Inconsistencia de signo en devoluciones (doble conteo).**
Las devoluciones aparecen **negadas** (`* -1`) en la rama NC de `facturas_detalle_extractor.sql`, pero **positivas** en `devoluciones_detalle_extractor.sql`. Ambos alimentan hechos distintos (`fact_ventas_detalle` y `fact_devoluciones`); si el consumo aguas abajo suma ambos, hay riesgo de doble contabilización o cancelación errónea. Falta una única fuente de verdad para devoluciones. **[VALIDAR]** consumo en `analytics_service`.

**C4 · `estado = 'P'` y `codemp = '01'` como reglas de negocio no documentadas y hardcodeadas.**
El significado de `'P'` (¿procesada/pagada?) no está documentado (viola CLAUDE.md). `codemp='01'` está fijo en los 22 extractores e impide multi-empresa; `config.CODEMP` existe pero no se usa.

### 4.2 ALTOS (calidad de datos / negocio)

**A1 · Dimensiones con datos inventados o placeholders NULL.**
- `formapago_extractor.sql`: dimensión **100% estática** desde una tabla `dummy` (3 filas fijas). Cualquier `codforpag` real fuera de esas 3 quedará huérfano en los hechos.
- `movimientos_caja_extractor.sql`: `monto_apertura = 0.0`, `monto_egreso = 0.0`, e **`ingreso` y `cierre` mapeados a la misma columna `valor`**. Modelo de arqueo esencialmente inventado.
- `pagos_cxp_extractor.sql`: `'C' AS codforpag` forzado; regla binaria `saldo = 0 si cerrado, si no total` que **ignora pagos parciales**.
- `clientes_extractor.sql`: `tipo_id='05'`, `sexo='U'`, `dias_credito=30`, `nombre_clase=NULL`, `nombre_zona=NULL`.
- `geografia_extractor.sql`: `pais='Ecuador'` fijo, `parroquia=NULL`, JOIN a `zona` deshabilitado; filtra geografía por `codemp` (cuestionable).
- `usuarios_extractor.sql`: `estado='A'` fijo. `proveedores`/`metas`: `dias_credito=30` fijo.

**A2 · Alias semánticamente engañosos (riesgo de interpretación).**
- `devoluciones_cabecera`: `totfac AS costo_total_devolucion` — es **valor de venta**, no costo.
- `articulos`: `ultcos AS costo_promedio` — `ultcos` es *último costo*, no promedio (impacta costeo de inventario y reposición).
- `nomina`: `totegr AS descuento_seguro` — agrupa todos los egresos bajo "IESS".
- `pagos_cxp`: `valcob AS valor_pagado` — es valor del documento, no lo pagado.

**A3 · `COALESCE(a.ultcos, 0.0)` enmascara costos faltantes** en detalle de facturas y devoluciones → `margen_bruto` y `costo_total` inflados cuando falta el costo del artículo.

**A4 · Dimensión `dim_almacen` derivada por heurística inestable.**
`almacenes_extractor.sql` deriva `establ` por *moda* (`TOP 1 ... ORDER BY COUNT(*) DESC` sobre `kardex`) y formatea con `RIGHT('000'+codalm,3)`. No determinista ante empates y puede cambiar entre cargas, pese a que `establecimientos` (en `sucursales_extractor`) es el maestro real.

**A5 · SCD2 parcial y frágil.**
`load_dim_scd2` solo versiona ante cambio de **una** columna (`desc_col`: `clase_cliente` / `nombre_articulo`); cambios en crédito, precio, estado, etc. **no** generan versión. Expira fila por fila en un loop Python (ineficiente) y el `append` de la nueva versión puede chocar si la unicidad del destino es sobre la clave natural. **[VALIDAR]** constraint real en DDL.

### 4.3 MEDIOS (rendimiento / mantenibilidad / trazabilidad)

**M1 · Relectura de dimensiones completas por cada chunk.** `resolver_llaves_hecho` hace `pd.read_sql` de `dim_fecha`, `dim_producto`, `dim_cliente`, etc. **completas en cada chunk** de 10 000 filas ([orchestrator.py:111+](../../etl/orchestrator.py#L111)) → O(chunks × tamaño_dim). Deberían cachearse una vez.

**M2 · Config quemada.** `PG_SCHEMA='edw'` en el dataclass; `chunksize=10000` literal (ignora `BATCH_SIZE`); `date(1900,1,1)`, rango `2010-2030` y umbral `2000-01-01` literales. `PII_SALT` con **default hardcodeado** `"s3cr3t_s4lt_v3ry_s3cur3"` ([settings.py:32](../../etl/config/settings.py#L32)) → hashes PII predecibles si falta la variable de entorno.

**M3 · Sin aislamiento de errores por tabla.** El bucle de `PIPELINE_CONFIG` no tiene `try/except` propio: si un extractor falla, **aborta todo el pipeline**; una tabla que falla a mitad no deja registro `FAIL` individual, y la próxima corrida la trata como "primera ejecución" (→ 1900 → recarga completa). Transaccionalidad fragmentada (DELETE e INSERT en transacciones separadas).

**M4 · Trazabilidad incompleta en `edw.etl_control`.** Registra tabla, fecha, nº registros, estado, duración y error, pero **no** registra fuente/origen, usuario ejecutor ni la ventana de fechas procesada; `registros_carg` no distingue insertados de duplicados.

**M5 · Logs solo a consola** (sin archivo ni rotación) y **código muerto** (`load_facts_full`, `load_facts_incremental`, `transformar_inventario_snapshot`, `transformar_logs_auditoria`, `query_to_dataframe` no se usan).

**M6 · Privacidad:** se crea `public.cliente_lookup` (hash → `id_cliente_transaccional` + `nombre_cliente`), una **tabla de re-identificación reversible** que debe evaluarse contra el protocolo de anonimización (`docs/tesis/04_protocolo_anonimizacion.md`).

---

## 5. Riesgos identificados

| ID | Riesgo | Impacto | Prob. |
|---|---|---|---|
| C1 | Duplicación de hechos por idempotencia rota | KPIs, ventas, inventario y ML entrenados con datos inflados | Alta |
| C2 | Histórico re-extraído en ramas UNION | Duplicados + carga innecesaria sobre Producción | Alta |
| C3 | Doble conteo de devoluciones | Ventas netas / márgenes incorrectos | Media |
| A1 | Dimensiones inventadas / huérfanas | Hechos sin dimensión válida; análisis sesgado | Alta |
| A3 | Costos = 0 enmascarados | Márgenes y valor de inventario erróneos | Media |
| A4 | `dim_almacen` no determinista | Bodega mal atribuida; reposición errónea | Media |
| — | Ausencia de stock/existencias y transferencias | No se puede calcular reposición ni rotación reales | Alta |

---

## 6. Análisis funcional del negocio (inventario / kardex / transferencias)

**Ventas:** ✅ `facturas_detalle_extractor.sql` cubre el grano Artículo+Bodega+Fecha (tiene `codart`, `codalm`, `fecfac`, cantidad, valor, cliente, vendedor, `tipo_documento`). Es el extractor más sólido.

**Compras:** ✅ `compras_detalle_extractor.sql` tiene artículo, bodega, cantidad, costo y fecha (útil para reposición). La cabecera no aporta artículo/cantidad y no se carga.

**Kardex:** ⚠️ `kardex_extractor.sql` trae `tiporg` (tipo movimiento), `codart`, `codalm`, `fecdoc`, `cantot`, `cosuni`, `costot`, `totven`, pero **NO** distingue/normaliza tipo (FAC/TRA/CPA/DEV), **NO** separa entrada/salida/saldo, **NO** trae motivo, **NO** trae `establ` (que sí lee `almacenes_extractor`), y el **signo de `cantot` no está documentado**. **[VALIDAR]** catálogo de `tiporg` en SAP.

**Inventario / existencias:** ❌ **AUSENTE**. No hay extractor de stock/existencias ni snapshot; `kardex` no expone saldo corriente. Sin esto no se calcula stock por bodega, cobertura ni valor de inventario reales.

**Transferencias:** ❌ **AUSENTE** como extractor dedicado. Derivables parcialmente del kardex (filtrando el `tiporg` de transferencia y auto-uniendo por `numdoc`: salida=origen, entrada=destino), pero el modelo actual **no** expone cantidad solicitada vs. enviada ni estado.

**Artículos sin movimiento:** ⚠️ parcial. `articulos.fecult` permite "fecha último movimiento"; falta calcular *días sin movimiento* contra una fecha de corte y cruzar con ventas/salidas.

---

## 7. Mejoras propuestas (a aplicar tras aprobación)

> Cambios acotados que **respetan la arquitectura existente** (no se rehace el ETL). Ordenados por prioridad.

**P1 — Corregir idempotencia de hechos (C1).** En `orchestrator.py`, borrar por fecha real, no por serial. Dos opciones: (a) hacer el DELETE por rango de `fecha_sk` **resuelto** desde `dim_fecha` para `fecha_completa >= last_date`; o (b) usar la ya existente `load_facts_incremental` (que borra por rango de fecha correctamente) en lugar de `append_only`. Preferible (a)+(b) combinadas.

**P2 — Corregir inyección incremental (C2).** Reemplazar el `str.replace(';', ...)` por un mecanismo robusto: envolver cada extractor como subconsulta (`SELECT * FROM (<sql>) q WHERE q.fecha >= :fecha_desde`) o parametrizar con placeholder explícito `{FILTRO_FECHA}` en cada `.sql`. Usar consulta parametrizada, no interpolación de string.

**P3 — Parametrizar `codemp` y documentar `estado='P'` (C4).** Sustituir literales por `:codemp` (desde `config.CODEMP`) y documentar el catálogo de estados en este directorio de auditoría.

**P4 — Unificar tratamiento de devoluciones (C3).** Elegir una sola fuente (recomendado: `devoluciones_detalle` → `fact_devoluciones` con signo positivo y bandera) y quitar la rama NC negada de `facturas_detalle`, o viceversa. Documentar la convención de signo.

**P5 — Nuevos extractores faltantes (crítico para reposición):**
- `existencias_extractor.sql` → snapshot de stock por (artículo, bodega, fecha) con costo. **[VALIDAR]** tabla origen real de existencias en SAP.
- `transferencias_extractor.sql` → origen/destino/fecha/artículo/cantidad, derivado del kardex por `numdoc` o de la tabla de transferencias de SAP si existe.

**P6 — Enriquecer kardex.** Exponer `establ`, motivo/concepto, y normalizar `tiporg` a categorías de negocio (FAC/TRA/CPA/DEV/AJU) con entrada/salida derivadas del signo; documentar la regla.

**P7 — Corregir alias y costos (A2, A3):** renombrar alias engañosos (`ultcos`→`ultimo_costo`, etc.) y sustituir `COALESCE(ultcos,0.0)` por marca de "costo faltante" (o NULL controlado) para no inflar márgenes.

**P8 — Estabilizar `dim_almacen` (A4):** obtener `establ` desde el maestro (`establecimientos`) en vez de la moda del kardex.

**P9 — Rendimiento (M1) y config (M2):** cachear dimensiones una sola vez en `resolver_llaves_hecho`; propagar `BATCH_SIZE`; volver obligatorio `PII_SALT` (sin default).

**P10 — Robustez y trazabilidad (M3, M4):** `try/except` por tabla con registro `FAIL` individual; añadir a `etl_control` columnas de fuente, usuario y ventana `fecha_desde/hasta`; logging a archivo.

---

## 8. Nuevos campos / extractores propuestos

- **`existencias_extractor.sql`** (nuevo): `codemp, codart, codalm, fecha_snapshot, stock, costo_unitario, valor_inventario`.
- **`transferencias_extractor.sql`** (nuevo): `codemp, numdoc, fecha, codart, codalm_origen, codalm_destino, cantidad_enviada[, cantidad_solicitada, estado]`.
- **`kardex_extractor.sql`** (ampliar): `+ establ, + motivo, + entrada, + salida, + tipo_movimiento_norm`.
- **`articulos_extractor.sql`** (resolver): `nombre_clase`, `subclase`, `nombre_unidad`, `grupo`, `marca`, `proveedor` (hoy NULL); renombrar `ultcos`.
- **`clientes`/`geografia`/`usuarios`** (resolver): lookups reales para `nombre_clase`, `nombre_zona`, `parroquia`, `estado`, `sexo`, `tipo_id`.

---

## 9. Consultas optimizadas (lineamientos)

- Añadir `{FILTRO_FECHA}` explícito en cada extractor de hecho para carga incremental segura (compatible con `UNION ALL`).
- Evitar subconsultas correlacionadas en `almacenes_extractor` (reemplazar por JOIN a maestro).
- Añadir `COALESCE`/normalización a `poriva` y montos para no propagar NULL a IVA/total.
- Homogeneizar la fórmula de `valor_descuento` entre ramas F y NC.

---

## 10. Recomendaciones para integración con el DW

1. **Bloquear reprocesos hasta corregir C1/C2** (o purgar duplicados existentes en `edw.Fact_*` con `SELECT` de verificación previo).
2. **Definir el contrato de `fecha_sk`**: mantener serial y borrar por join a `dim_fecha`, o migrar a smart-key `YYYYMMDD` (cambio de DDL — fuera del alcance del extractor).
3. **Priorizar existencias + transferencias**: sin ellas, los modelos de reposición (grano Artículo+Bodega+Periodo) no son alimentables con datos reales.
4. **Documentar todas las reglas de negocio** detectadas (estado `'P'`, `tiporg`, signo de `cantot`, `desinv='S'`, excepciones Pelileo/Salcedo) en `docs/auditoria/`.
5. **Validar contra Producción con `SELECT`**: unicidad de `(codemp, numfac)` y `(codemp, codart)`, catálogo de `tiporg`, existencia de tabla de existencias.

---

## 11. Estado y próximos pasos

Auditoría completada **sin modificar código**. Los hallazgos C1 y C2 fueron **verificados directamente en el código fuente** (no solo inferidos). Las mejoras del §7 están **propuestas, no aplicadas**: requieren aprobación y, en varios casos, validación con `SELECT` contra Producción y/o confirmación de reglas de negocio.

**Pendiente de decisión del usuario:** alcance y orden de los cambios a implementar (ver siguiente interacción).
