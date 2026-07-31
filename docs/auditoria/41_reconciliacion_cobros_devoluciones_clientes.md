# Auditoría 41 — Reconciliación EDW vs Producción: `clientes`, `fact_cobros_cxc`, `fact_devoluciones`

> **Estado (2026-07-28, actualizado tras la recarga real):** H1, H2 y H3 fueron corregidos en
> código **y aplicados a los datos reales del EDW** (autorización explícita del usuario para
> escribir al EDW local de desarrollo, solo lectura contra SAP). En el proceso se encontraron y
> corrigieron **dos bugs adicionales del propio orquestador** (H6, H7) que no se habían manifestado
> antes porque nunca se había repetido una recarga histórica completa de estas tablas. Todo
> verificado con `SELECT` contra el EDW tras la recarga — ver §Aplicado y verificado.

- **Fecha:** 2026-07-28
- **Alcance:** `etl/extractors/clientes_extractor.sql`, `etl/extractors/cobros_cxc_extractor.sql`,
  `etl/extractors/devoluciones_cabecera_extractor.sql`, `etl/extractors/devoluciones_detalle_extractor.sql`,
  `etl/transformers/dim_transformer.py::transformar_clientes`, `etl/transformers/fact_transformer.py::transformar_cobros_cxc/transformar_devoluciones`,
  `etl/orchestrator.py::PIPELINE_CONFIG/resolver_llaves_hecho/_leer_dim_cacheada`,
  `edw.dim_cliente`, `edw.fact_cobros_cxc`, `edw.fact_devoluciones`. Motivado por la necesidad de
  usar estas tablas en el refactor de Cartera 360 (`docs/features/plan_refactor_cartera360_ruta_inteligente.md`)
  — se detectó en la planificación que el timeline propuesto asumía sobre `fact_cobros_cxc` un
  comportamiento (log de eventos) que la auditoría 31 ya había refutado (H3: es un snapshot de
  documento, no un evento), lo que motivó revisar también `clientes_extractor.sql` por sospecha
  del usuario de valores quemados en código.
- **Método:** `SELECT` puro contra Producción (SAP SQL Anywhere, `172.16.50.5:4016`, driver nativo
  `SQL Anywhere 12` desde el host Windows — el entorno sandbox de este agente no tiene ruta a esa
  red, se ejecutó vía PowerShell/pyodbc directo, ver scripts de evidencia en el scratchpad de la
  sesión) y `SELECT` contra el EDW (`docker exec bi_postgres_edw psql`). **No se ejecutó ninguna
  escritura contra Producción.** Se reprodujo el pipeline real (extractor con tokens sustituidos +
  función `transform*` real + hash `hmac` real) en un script Python aparte para aislar en qué etapa
  se origina cada diferencia, en vez de suponerla. No se modificó ningún dato del EDW en esta
  sesión — solo lectura en ambos lados.

## Hallazgos

### 🔴 Alta — H1: `clientes_extractor.sql` descarta 4-5 columnas reales y pobladas de SAP, reemplazándolas por constantes fijas para el 100% de los clientes

- **Evidencia (código):**
  ```sql
  -- etl/extractors/clientes_extractor.sql
  '05' AS tipo_id,
  codcla AS clase_cliente,
  NULL AS nombre_clase,
  codzona AS zona,
  NULL AS nombre_zona,
  ...
  30 AS dias_credito,
  ...
  'U' AS sexo,
  ```
- **Evidencia (Producción, `SELECT` real contra `clientes` codemp='01', 73.505 filas):**
  - `codcre` (crédito real por cliente) — **NO es 30 para todos**: `NULL`=72.362 (98.4%, sin
    plazo definido — típico de "consumidor final"/contado), `0`=677, `30`=331 (0.45%, los únicos
    que de verdad tienen 30 días), `60`=131, `90`=4.
  - `tiprucced` (tipo real de identificación) — **NO es '05'/CEDULA para todos**: `C`=46.476 (63.2%,
    cédula), `R`=26.997 (36.7%, RUC), `P`=30 (pasaporte), `F`=2.
  - `sexo` — columna real presente en `clientes` (no hace falta join): `NULL`=69.576 (personas
    jurídicas/consumidor final), `M`=3.082, `F`=847. El extractor la descarta y hardcodea `'U'`.
  - `clasesclientes` (tabla catálogo real, confirmada existente y poblada) resuelve
    `nomcla` a partir de `(codemp, codcla)` — ej. `codcla='GCL11' → 'CLIENTES CHATARRA'`,
    `codcla='GCLI5' → 'FLOTAS, COOP. DE TRANSPORTE'`. El extractor hardcodea `NULL AS nombre_clase`
    en vez de este join.
  - `zona` (tabla catálogo real, confirmada existente y poblada) resuelve `nomzona`/`dirzona`/`nomciu`
    (provincia/cantón/parroquia) a partir de `(codemp, codzona)` — jerarquía geográfica real. El
    extractor hardcodea `NULL AS nombre_zona`.
  - **Consultas utilizadas** (contra SAP, solo lectura):
    ```sql
    SELECT codcre, count(*) FROM clientes WHERE codemp='01' GROUP BY codcre ORDER BY count(*) DESC;
    SELECT tiprucced, count(*) FROM clientes WHERE codemp='01' GROUP BY tiprucced ORDER BY count(*) DESC;
    SELECT sexo, count(*) FROM clientes WHERE codemp='01' GROUP BY sexo ORDER BY count(*) DESC;
    SELECT TOP 10 * FROM clasesclientes;
    SELECT TOP 10 * FROM zona;
    ```
- **Confirmado que la corrupción ya está cargada en el EDW actual** (`SELECT DISTINCT` sobre
  `edw.dim_cliente WHERE es_vigente`): una única combinación `(dias_credito=30, tipo_id='CEDULA',
  sexo='U', nombre_clase=NULL, nombre_zona=NULL)` para las 73.502 filas vigentes, sin excepción.
- **Impacto:** hoy **no hay pérdida de decisión de negocio en producción** — se verificó que
  ningún servicio del backend ni del pipeline ML lee `dim_cliente.{tipo_id,sexo,dias_credito,
  nombre_zona}` (`grep` sobre `backend/` y `ml/`, sin resultados; `nombre_clase` que aparece en el
  código es el de `dim_producto`, una columna distinta, no relacionada). El riesgo es hacia
  adelante: el plan de refactor de Cartera 360 (y cualquier análisis de tesis) que use estos campos
  heredaría datos fabricados que parecen reales — en particular `dias_credito=30` es el más
  peligroso porque **tiene la forma de un dato válido** (a diferencia de un `NULL` explícito).
  También relevante para el propio plan de Cartera 360: la clase `'FLOTAS, COOP. DE TRANSPORTE'`
  SÍ existe como catálogo real vía `clasesclientes` — contradice la premisa previa del plan de que
  un perfil "flota" no era derivable del EDW (§4.5 de ese plan, a revisar).
- **Riesgos de no corregir:** cualquier feature de ML o regla de negocio que en el futuro use estos
  campos partiría de datos falsos sin ningún error visible (no hay NULL que alerte, hay un valor
  plausible). Riesgo de corregirlo: ninguno relevante — son campos hoy sin consumidores.
- **Recomendación:** seleccionar las columnas reales (`codcre AS dias_credito`, `tiprucced AS
  tipo_id`, `sexo` real) y agregar los dos `JOIN` a `clasesclientes`/`zona` para resolver los
  nombres. **Aplicado** (ver §Correcciones aplicadas).

### 🔴 Alta — H2: `fact_devoluciones.cliente_sk` queda en el registro centinela (`-1`) en el 92%-100% de las filas, pese a que el cliente real existe y está vigente en `dim_cliente`

- **Evidencia (EDW, antes de cualquier corrección):**
  ```sql
  SELECT count(*) FILTER (WHERE cliente_sk = -1), count(*) FROM edw.fact_devoluciones;
  -- 18373 / 18492  (99.4%)

  SELECT d.anio, count(*) total, count(*) FILTER (WHERE f.cliente_sk = -1) sin_cliente
  FROM edw.fact_devoluciones f JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
  GROUP BY d.anio ORDER BY d.anio;
  -- 2018..2025: 100% sin_cliente cada año. 2026 (año en curso): 92.1% sin_cliente (1389/1508).
  ```
- **Diagnóstico por etapas (se reprodujo el pipeline real para aislar la causa, no se supuso):**
  1. Se tomaron documentos reales de `fact_devoluciones` con `cliente_sk=-1` (p.ej. `DA003059`,
     `DA003060`, `DA003061`, con `codcli` reales `202145`, `136736`, `107518`).
  2. Se ejecutó el `SELECT` **real** de `devoluciones_detalle_extractor.sql` (tokens sustituidos)
     contra SAP: `codcli` llega como `str` limpio, sin artefactos de tipo.
  3. Se corrió `transformar_devoluciones` real sobre ese resultado: `codcli` normalizado
     correctamente (`'202145'`, `'136736'`, `'107518'`).
  4. Se calculó `hash_anonimo = hmac_sha256(PII_SALT, codcli)` con el mismo algoritmo exacto de
     `orchestrator.py::resolver_llaves_hecho`.
  5. **Se verificó que ese hash EXISTE en `edw.dim_cliente` con `es_vigente=true` y un
     `cliente_sk` válido** (ej. `codcli='202145' → hash a0cdb7...b26 → cliente_sk=40956,
     es_vigente=true`).
  6. Sin embargo, la fila real de `fact_devoluciones` para ese mismo documento (`DA003059`) tiene
     `cliente_sk=-1` en el EDW.
  7. Se descartó que sea un problema general del resolvedor: **`fact_cobros_cxc.cliente_sk` y
     `fact_ventas_detalle.cliente_sk` tienen 0% de filas centinela** (0/213.845 y 0/525.267
     respectivamente) usando exactamente la misma función `resolver_llaves_hecho`.
- **Causa raíz más probable (evidencia estructural, no solo circunstancial):** en
  `etl/orchestrator.py::PIPELINE_CONFIG`, la entrada de `fact_devoluciones` es la **única** de las
  tres tablas comparadas que **no declara `dim_cliente` en `depende_de`**:
  ```python
  # cobros_cxc (0% centinela):
  {'file': 'cobros_cxc_extractor.sql', ..., 'depende_de': ['dim_cliente', 'dim_vendedor', 'dim_formapago']},
  # ventas_detalle (0% centinela):
  {'file': 'facturas_detalle_extractor.sql', ..., 'depende_de': ['dim_producto', 'dim_cliente', 'dim_vendedor', 'dim_almacen', 'dim_sucursal']},
  # devoluciones_detalle (92-100% centinela):
  {'file': 'devoluciones_detalle_extractor.sql', ..., 'depende_de': ['dim_producto', 'dim_almacen', 'dim_sucursal', 'dim_vendedor']},  # falta 'dim_cliente'
  ```
  `orchestrator.py:560` usa `depende_de` para omitir el procesamiento de un hecho si alguna de sus
  dimensiones declaradas falló en la corrida (`dependencias_fallidas = set(cfg.get('depende_de',
  [])) & dims_fallidas`). Como `fact_devoluciones` no declara depender de `dim_cliente`, es la
  única de las tres que **no queda protegida** si la carga de `dim_cliente` falla o queda
  incompleta en una corrida — se procesa igual, resolviendo `cliente_sk` contra un estado de
  `dim_cliente` potencialmente vacío o parcial en ese momento (`_leer_dim_cacheada` cachea la
  dimensión una sola vez por proceso). Una vez cargada con `-1`, el borrado idempotente por rango
  de fecha (`fact_inc`) solo repite las ventanas de fecha reprocesadas incrementalmente — las filas
  antiguas nunca se vuelven a resolver, lo que explica por qué **2018-2025 están 100% afectados**
  mientras que **2026 (cargado ya con corridas recientes) baja a 92.1%**, la única mejora parcial
  observable. **No es posible reconstruir con certeza absoluta el incidente histórico exacto que
  dejó `dim_cliente` incompleta la primera vez** (fuera del alcance de un `SELECT`), pero el defecto
  estructural (la ausencia de `dim_cliente` en `depende_de`) es 100% verificable en el código y es
  la única diferencia real entre esta tabla y sus dos pares sin el problema.
- **Impacto:** `fact_devoluciones` es hoy **inutilizable para cualquier análisis por cliente**
  (18.373 de 18.492 filas no se pueden atribuir a un cliente real) — directamente relevante porque
  el plan de Cartera 360 proponía usar devoluciones en el timeline del cliente. Los análisis
  agregados (por producto, por sucursal) no están afectados por este hallazgo específico.
- **Riesgos:** ninguno de corregir la declaración `depende_de` (cambio de metadata, no de lógica).
  Corregir los datos ya cargados requiere un **reproceso completo de `fact_devoluciones`** (borrar y
  recargar contra SAP), una escritura al EDW que requiere autorización explícita — no se ejecutó en
  esta auditoría.
- **Recomendación:** (1) agregar `'dim_cliente'` a `depende_de` de `fact_devoluciones`. **Aplicado**
  (ver §Correcciones aplicadas). (2) Reprocesar `fact_devoluciones` completo contra SAP para
  resolver `cliente_sk` en las filas históricas — **pendiente de autorización del usuario** (escribe
  al EDW).

### 🔴 Alta — H3: `fact_cobros_cxc.saldo_documento` convierte `NULL` (55.5% de los documentos reales) en `0.0`, indistinguible de "documento pagado"

- **Evidencia (Producción, `cuentasporcobrar` codemp='01', 213.897 filas totales):**
  ```sql
  SELECT
    SUM(CASE WHEN saldodoc IS NULL THEN 1 ELSE 0 END) es_null,
    SUM(CASE WHEN saldodoc = 0 THEN 1 ELSE 0 END) es_cero,
    SUM(CASE WHEN saldodoc > 0 THEN 1 ELSE 0 END) es_positivo
  FROM cuentasporcobrar WHERE codemp='01';
  -- es_null=118749 (55.5%), es_cero=0, es_positivo=95138
  ```
  Es decir: en SAP, **ningún documento tiene `saldodoc` explícitamente en `0`** — o se conoce el
  saldo pendiente (`>0`, 95.138 filas) o se desconoce (`NULL`, 118.749 filas). No existe un
  "cerrado con saldo cero" real en la fuente.
- **Código responsable:**
  ```python
  # etl/transformers/fact_transformer.py::transformar_cobros_cxc
  df = normalizar_numericos(df, ['valor_cobrado', 'saldo_documento'])  # sin permitir_nulos
  ```
  `normalizar_numericos` (`etl/transformers/dim_tiempo.py`) hace `fillna(0.0)` para toda columna no
  incluida en `permitir_nulos` — documentado explícitamente en su propio docstring (auditoría 08,
  F2) como un riesgo a evitar para columnas donde "ausente" no es lo mismo que "cero", el mismo
  patrón que sí se aplicó correctamente a costos/precios en `transformar_productos`.
- **Confirmado que ya está cargado así en el EDW:**
  ```sql
  SELECT count(*) FILTER (WHERE saldo_documento = 0) FROM edw.fact_cobros_cxc;  -- 118716
  ```
  Coincide (con el desfase normal por timing entre ambas consultas) con los 118.749 `NULL` reales
  de SAP — confirma que el `fillna(0)` es la causa, no una coincidencia.
- **Impacto:** cualquier suma de "cartera pendiente" o "documentos abiertos" sobre esta tabla
  **subestima el riesgo real**, porque más de la mitad de los documentos con saldo desconocido se
  cuentan como pagados. Directamente relevante para cualquier panel de cobranza que el módulo de
  Cartera 360 quiera construir sobre esta tabla (auditoría 31 H3 ya advertía que es un snapshot de
  documento, no un log de eventos; este hallazgo agrega que ni siquiera el snapshot es confiable
  para más de la mitad de las filas).
- **Riesgos:** el destino `edw.fact_cobros_cxc.saldo_documento` está declarado `NOT NULL` en el DDL
  (`edw/01_schema.sql` / equivalente) — permitir `NULL` real requiere una migración de esquema
  `edw.*` (fuera del alcance de Alembic, que solo cubre `public.*`; los DDL de `edw/` solo se
  aplican automáticamente en un volumen nuevo — un cambio en una BD existente es manual, regla de
  Restricciones del `CLAUDE.md` raíz).
- **Recomendación:** (a) preferida — `ALTER TABLE edw.fact_cobros_cxc ALTER COLUMN saldo_documento
  DROP NOT NULL` + `permitir_nulos=['saldo_documento']` en el transformer, para representar el
  "desconocido" real como `NULL`; (b) alternativa sin tocar el esquema — agregar una columna
  booleana `saldo_desconocido` derivada de si `saldodoc` llegó nulo en origen. **No aplicado en
  esta auditoría** (requiere alterar el esquema `edw` de una BD existente, escritura fuera del
  alcance de solo-lectura de esta sesión) — **pendiente de autorización del usuario**.

### 🟢 Sin hallazgo — Reconciliación de volumen total EDW vs Producción (`fact_cobros_cxc`, `fact_devoluciones`)

- **Contexto:** una primera reconciliación con el filtro `fecemi/fecfac >= FECHA_DESDE
  ('2020-01-01')` mostró aparentes faltantes graves (SAP 171.580 vs EDW 213.845 en cobros; SAP
  14.460 vs EDW 18.492 en devoluciones). **Se investigó antes de reportarlo como hallazgo** (regla
  de este flujo: aislar la etapa, no quedarse en el síntoma).
- **Causa real:** el EDW contiene el **historial completo** desde 2013 (cobros) / 2018
  (devoluciones), no solo desde `FECHA_DESDE=2020-01-01` — evidencia de que la carga inicial se
  hizo con una ventana más amplia (o sin filtro) antes de fijar el valor actual de `FECHA_DESDE` en
  `.env`. Al reconciliar **sin** el filtro de fecha (`codemp='01'` solamente, igual que el volumen
  real que el EDW contiene), los totales coinciden dentro de un margen normal de desfase temporal
  entre ambas consultas:
  - `cuentasporcobrar`: SAP=213.897 vs EDW=213.845 (Δ=52, <0.03%).
  - `renglonesdevoluciones` (vía `encabezadodevoluciones`, estado='P'): SAP=18.499 vs EDW=18.492
    (Δ=7, <0.04%).
- **Veredicto:** sin pérdida ni duplicación de registros. El filtro `FECHA_DESDE` de `.env` solo
  aplica a la ventana incremental de corridas nuevas, no reduce lo ya cargado — comportamiento
  esperado del loader `fact_inc`, no un defecto.

### 🟡 Media — H4: código muerto con hardcodes propios en `devoluciones_cabecera_extractor.sql`

- **Evidencia:** el archivo no aparece en `PIPELINE_CONFIG` (`grep -n "devoluciones" etl/orchestrator.py`
  solo referencia `devoluciones_detalle_extractor.sql`, que ya trae `codcli`/`codven`/`fecfac` vía
  `JOIN encabezadodevoluciones e`) — cumple la definición de código muerto de este proyecto ("SQL no
  registrado en PIPELINE_CONFIG es código muerto"). Además tiene sus propios hardcodes
  (`codemp = '01'` literal en vez de `{CODEMP}`, `estado = 'P'` en vez de `{ESTADO}`, sin filtro
  incremental de fecha) inconsistentes con el resto del proyecto — sin impacto real porque nunca se
  ejecuta, pero confunde a cualquiera que lo lea creyendo que es parte del pipeline activo.
- **Impacto:** ninguno funcional (no se ejecuta). Riesgo de mantenimiento/confusión.
- **Recomendación:** eliminar el archivo. **Aplicado** (ver §Correcciones aplicadas).

### 🟡 Media — H5 (pendiente de caracterizar): `fact_devoluciones.producto_sk` centinela en 54% de las filas

- **Evidencia:** `10.012/18.492` filas con `producto_sk=-1`. A diferencia de H2, la muestra
  verificada (`DA003059`, `DA003061`) mostró `codart='\SR1'` — un código con formato atípico
  (prefijo `\`), consistente con un pseudo-artículo de servicio/nota interna, no necesariamente un
  código de catálogo real ausente por error. Otro documento de la misma muestra (`DA003060`,
  `codart` numérico real) sí resolvió correctamente (`producto_sk=425`).
- **Impacto:** no caracterizado con evidencia suficiente para concluir si es un hallazgo real
  (código de catálogo real descartado) o un comportamiento esperable (líneas de servicio sin
  artículo de inventario, coherente con `desinv`/`bienser` ya documentados en otras tablas). **No se
  investigó a fondo en esta sesión** por alcance — se prioriza H1/H2/H3 por su severidad e impacto
  directo en el plan de Cartera 360.
- **Recomendación:** repetir el método de H2 (tomar una muestra de `codart` con `producto_sk=-1`,
  verificar si existen en `articulos` con el mismo formato, y si el patrón `\SR1`-like es
  sistemático) en una auditoría de seguimiento antes de usar `fact_devoluciones` para cualquier
  análisis por producto. **Pendiente de validar.**

### 🔴 Alta — H6 (encontrado durante la recarga): una recarga histórica completa (`FULL`, sin corrida `SUCCESS` previa en `etl_control`) duplica los datos en vez de reemplazarlos

- **Evidencia:** `etl/orchestrator.py` solo tenía dos ramas de borrado antes de insertar:
  `if cfg.get('snapshot'): ...` y `elif incremental: ...` — **sin `else`**. Cuando una tabla se
  recarga en modo `FULL` (p.ej. tras resetear `etl_control` para aplicar H1/H2, o en la primera
  carga histórica de una tabla nueva que ya tuviera datos previos por otra vía), no se ejecutaba
  ningún `DELETE` antes del `INSERT`. Reproducido en vivo: dos recargas `FULL` consecutivas de
  `fact_cobros_cxc` (213.845 → 213.898 → 641.641, exactamente 213.845+213.898+213.898) y
  `fact_devoluciones` (18.492 → 18.499 → 55.490, exactamente 18.492+18.499+18.499) — coincide
  matemáticamente con "cada corrida se suma en vez de reemplazar".
- **Impacto:** cualquier recarga histórica repetida (reset de `etl_control`, recuperación tras un
  incidente, o simplemente una segunda ejecución de `--tablas X` en modo full) triplica/multiplica
  silenciosamente los hechos — sin ningún error, `[OK] FINALIZADO` en el log. Es el bug más
  peligroso de los encontrados en esta auditoría porque no depende de un dato de SAP: es
  100% reproducible con solo repetir una operación ya documentada como legítima (reset de
  `etl_control`, patrón usado en auditorías 30/31/34).
- **Recomendación:** agregar una rama `elif es_hecho:` que borre la tabla completa
  (`DELETE FROM {tabla}`) antes de insertar en modo `FULL`. **Aplicado y verificado** — ver
  §Aplicado y verificado.

### 🟡 Media — H7 (encontrado durante la recarga): el cambio SCD2 de `dim_cliente` solo se detecta si cambia `clase_cliente` — corregir el extractor no actualiza a los clientes ya vigentes

- **Evidencia:** `etl/loaders/dim_loader.py::load_dim_scd2` compara únicamente la columna
  `desc_col` (configurada como `'clase_cliente'` en `PIPELINE_CONFIG` para `dim_cliente`) contra
  el valor vigente en BD; si no cambió, la fila entera se descarta (`mask_sin_cambio`) sin
  actualizar ninguna otra columna. Tras corregir H1 y volver a extraer, **solo se generaron
  nuevas versiones para los clientes cuya `clase_cliente` cambió** — el resto (>99%) conservó
  `tipo_id`/`sexo`/`dias_credito`/`nombre_clase`/`nombre_zona` con los valores fabricados
  anteriores, pese a que el extractor ya traía los reales.
- **Impacto:** cualquier columna de `dim_cliente` fuera de `clase_cliente` puede quedar
  permanentemente desincronizada de SAP sin que ninguna corrida normal del ETL lo corrija — un
  riesgo estructural más allá de H1 (aplica a cualquier futuro cambio de columna en esta
  dimensión).
- **Recomendación (no aplicada, requiere decisión de diseño):** ampliar la detección de cambio a
  todas las columnas rastreadas (más costoso por corrida, a evaluar) o documentar explícitamente
  qué columnas de `dim_cliente` son "solo se corrigen con un `UPDATE` manual" vs. "versionadas por
  SCD2". **Para esta sesión**, se aplicó una corrección puntual de los datos ya cargados con un
  `UPDATE` directo (preserva `cliente_sk` y las FK existentes, no crea una versión SCD2 nueva —
  criterio: es la corrección de un valor mal extraído desde el origen, no un cambio real de
  negocio que amerite historial) — ver §Aplicado y verificado. **Pendiente de decisión:** si
  ampliar `load_dim_scd2` para detectar cambios en más columnas.

## Correcciones aplicadas en esta sesión

Solo cambios de **código** (extractor SQL + metadata de `PIPELINE_CONFIG`), sin escritura al EDW:

1. `etl/extractors/clientes_extractor.sql`: reemplazados los 5 hardcodes por las columnas/joins
   reales (`codcre`, `tiprucced`, `sexo`, `clasesclientes.nomcla`, `zona.nomzona`) — H1.
2. `etl/orchestrator.py::PIPELINE_CONFIG`: agregado `'dim_cliente'` a `depende_de` de
   `fact_devoluciones` — H2 (mitiga la recurrencia futura; no corrige las filas ya cargadas).
3. Eliminado `etl/extractors/devoluciones_cabecera_extractor.sql` (código muerto) — H4.

## Aplicado y verificado (autorización explícita del usuario, escritura al EDW local de desarrollo)

1. `ALTER TABLE edw.fact_cobros_cxc ALTER COLUMN saldo_documento DROP NOT NULL` (aplicado sobre
   `bi_postgres_edw` + actualizado `edw/03_hechos.sql` para que un volumen nuevo nazca ya
   corregido) + `permitir_nulos=['saldo_documento']` en `transformar_cobros_cxc` — H3.
2. `orchestrator.py`: agregada la rama `elif es_hecho:` que borra la tabla completa antes de una
   recarga `FULL` — H6. **Sin esta corrección la recarga de H1/H2/H3 habría triplicado los datos**
   (se reprodujo el problema en vivo antes de corregirlo — dos recargas `FULL` consecutivas
   duplicaron `fact_cobros_cxc` a 641.641 filas y `fact_devoluciones` a 55.490; se hizo `TRUNCATE`
   de ambas tablas — sin dependientes por FK, son hechos hoja — y se recargó limpio una vez
   corregido el bug).
3. Reset de `etl_control` + recarga completa de `fact_devoluciones` y `fact_cobros_cxc` contra SAP
   (`docker compose run etl python orchestrator.py --tablas fact_devoluciones fact_cobros_cxc`).
   **Verificado tras la recarga:**
   - `fact_devoluciones.cliente_sk`: **0 filas sin resolver** de 18.499 (antes 18.373/18.492,
     99.4%) — H2 confirmado corregido en los datos.
   - `fact_cobros_cxc.saldo_documento`: 118.750 `NULL` reales (antes 0, todos fillna(0)), 0 filas
     con `0` falso — H3 confirmado corregido en los datos. Coincide con el 55.5% real de SAP.
4. Reparación puntual de `dim_cliente`: dado que el loader SCD2 no propagó el fix de H1 a los
   clientes ya vigentes (H7), se extrajo `clientes` completo desde SAP (solo lectura) con el
   extractor corregido y se aplicó un `UPDATE` directo sobre las 73.507 filas vigentes de
   `edw.dim_cliente` (emparejado por `hash_anonimo`, preservando `cliente_sk` y todas las FK de
   `fact_*` que ya apuntan a él — sin tocar el historial SCD2, sin generar versiones nuevas).
   **Verificado tras la reparación** — distribución real (antes vs. después):
   | Campo | Antes (fabricado) | Después (real, verificado) |
   |---|---|---|
   | `tipo_id` | 100% `'CEDULA'` | `C`=46.477 (63.2%), `R`=26.997 (36.7%), `P`=30, `F`=2 |
   | `dias_credito` | 100% `30` | `NULL`=72.364 (98.4%), `0`=677, `30`=331, `60`=131, `90`=4 |
   | `sexo` | 100% `'U'` | `NULL`=69.578, `M`=3.082, `F`=847 |
   | `nombre_clase` | 100% `NULL` | 73.506/73.507 resueltos vía `clasesclientes` |
   | `nombre_zona` | 100% `NULL` | 73.499/73.507 resueltos vía `zona` |

## Pendiente (fuera de alcance de esta sesión)

| # | Acción | Motivo |
|---|---|---|
| 1 | Investigar H5 (`producto_sk` centinela en `fact_devoluciones`, 54%) con el mismo método que H2 | No caracterizado — muestra sugiere códigos de servicio (`\SR1`) legítimamente ausentes del catálogo, no necesariamente un bug |
| 2 | Decidir si ampliar `load_dim_scd2` para detectar cambios en más columnas (H7) | Decisión de diseño — más costoso por corrida, evaluar antes de cambiar |

## Resumen de recomendaciones por prioridad

- **Alta:** H1, H2, H3, H6 — **todas aplicadas y verificadas contra datos reales del EDW**.
- **Media:** H4 (aplicado), H7 (paliado con reparación puntual de datos; el cambio de diseño del
  loader queda pendiente), H5 (pendiente de investigar).
- **Sin hallazgo:** reconciliación de volumen EDW vs Producción para `fact_cobros_cxc`/
  `fact_devoluciones` previa a esta sesión (confirmado consistente, documentado para no reabrirse
  como duda futura).

## Relevancia directa para `docs/features/plan_refactor_cartera360_ruta_inteligente.md`

- Confirma y profundiza la limitación ya anticipada en la conversación previa sobre §4.6 (timeline):
  `fact_cobros_cxc` no solo es un snapshot (auditoría 31 H3), sino que además su campo de saldo es
  poco confiable para más de la mitad de los documentos (H3 de esta auditoría) — refuerza la
  recomendación de no presentarlo como evento cronológico ni sumarlo como "cartera pendiente" sin
  resolver antes el `NULL`.
  `fact_devoluciones` no puede usarse para el timeline por cliente hasta reprocesarse (H2) — el
  95%+ de sus filas hoy no tienen cliente resuelto.
- El catálogo real `clasesclientes` (H1) contiene una clase `'FLOTAS, COOP. DE TRANSPORTE'` — vale
  la pena revisar si esto reabre la decisión §4.5 de ese plan sobre perfiles "flota" no derivables.
