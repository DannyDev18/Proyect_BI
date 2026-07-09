# Auditoría 09 — Revisión técnica de `etl/orchestrator.py` (lógica de orquestación)

- **Fecha:** 2026-07-09
- **Alcance:** únicamente la lógica de orquestación en `etl/orchestrator.py` (orden de ejecución,
  dependencias, manejo de errores/transacciones, logging, validaciones pre/post carga,
  idempotencia, modularidad, acoplamiento). No se tocan `etl/extractors/*.sql` (ya validados),
  el EDW (ya auditado en 07) ni `etl/transformers/*.py` (ya auditados/corregidos en 08).
- **Método:** revisión estática de código Python. No se ejecutó el pipeline, no se escribió en
  Producción ni en el EDW. Se contrastó contra `etl/config/settings.py`,
  `etl/connectors/postgres_connector.py` y el estado real de `etl/loaders/` (confirmado con
  listado de archivos) para verificar cada hallazgo con evidencia, no por suposición.
- **No se modificó ni se reescribió `orchestrator.py`** — este documento es auditoría previa,
  según el flujo de trabajo esperado para agentes de IA del proyecto.

## Hallazgos

### CRÍTICO — H1 Import de `etl/loaders/` inexistente: el orchestrator no puede ejecutarse
- **Función:** módulo (imports de cabecera), líneas 28-29.
- **Problema:** `from loaders.dim_loader import load_dimension, load_dim_scd2` y
  `from loaders.fact_loader import load_facts_append_only`. Se verificó con `Glob` sobre
  `etl/loaders/*.py`: no existe ningún archivo. Estos módulos figuran como eliminados del
  working tree (ya señalado como riesgo abierto en `CLAUDE.md`, sección "Riesgos técnicos").
- **Riesgo:** el archivo falla en tiempo de importación (`ModuleNotFoundError`) antes de que
  `run_etl()` llegue a ejecutar una sola línea. No es un riesgo de orquestación en sentido
  estricto, pero bloquea absolutamente cualquier ejecución del pipeline.
- **Impacto:** total — el ETL completo (dimensiones y hechos) está inoperante en el estado
  actual del árbol de trabajo.
- **Prioridad:** Alta (bloqueante).
- **Recomendación:** restaurar `etl/loaders/dim_loader.py` y `etl/loaders/fact_loader.py` desde
  git (`git log --diff-filter=D -- etl/loaders/`) antes de intentar ejecutar o seguir auditando
  el comportamiento en caliente del orchestrator. Confirmar con el usuario si el borrado fue
  intencional (parte de un refactor en curso) o accidental.

### CRÍTICO — H2 `asegurar_registros_desconocidos()` inserta en una tabla que ya no existe (`dim_geografia`) dentro de una única transacción con el resto de dimensiones
- **Función:** `asegurar_registros_desconocidos`, líneas 111-212 (INSERT problemático en
  200-206); invocada desde `run_etl` en la línea 398, **antes** del bucle de `PIPELINE_CONFIG`.
- **Problema:** la lista `inserts` contiene un `INSERT INTO {schema}.dim_geografia ...`. Según
  la auditoría 07 (H4) y la propia auditoría 08 (comentario ya agregado en la línea 217-218 de
  este mismo archivo), `Dim_Geografia` fue retirada del EDW — la tabla no existe. Todos los
  `INSERT` de la lista se ejecutan dentro de un único `with engine.begin() as conn:` (líneas
  209-212): si el `INSERT` a `dim_geografia` falla (tabla inexistente), **la transacción
  completa hace rollback**, incluyendo los centinelas `-1` de `dim_fecha`, `dim_sucursal`,
  `dim_almacen`, `dim_producto`, `dim_cliente`, etc., que sí son válidos.
- **Riesgo:** la excepción se propaga fuera de `asegurar_registros_desconocidos()` (no tiene su
  propio `try/except`) y sube hasta el `try` general de `run_etl` (línea 395), que la captura en
  el bloque de la línea 505 como "Falla crítica", registra `PIPELINE_GENERAL` como `FAIL` y
  **re-lanza la excepción** (`raise` en la línea 508) — abortando el pipeline completo antes de
  generar `Dim_Fecha` o procesar una sola tabla de `PIPELINE_CONFIG`.
- **Impacto:** bloqueo total del pipeline en cada ejecución (no es intermitente: la tabla nunca
  va a existir mientras el DDL actual de `edw/02_dimensiones.sql` esté vigente).
- **Prioridad:** Alta (bloqueante, y además es una regresión directa del cambio aplicado en la
  auditoría 08/07 que retiró `Dim_Geografia` sin propagar el cambio a esta función).
- **Recomendación:** eliminar el bloque `INSERT INTO {schema}.dim_geografia` de la lista
  `inserts` (mismo criterio que ya se aplicó al remover `transformar_geografia` y su entrada en
  `PIPELINE_CONFIG` en la auditoría 08, F11). Adicionalmente, considerar envolver cada `INSERT`
  centinela en su propio `try/except` (o ejecutar cada uno en su propia transacción) para que un
  futuro drift de esquema en una sola dimensión no bloquee el resto de los centinelas.

### CRÍTICO — H3 Los hechos no verifican si su(s) dimensión(es) de dependencia falló(aron) en la misma corrida
- **Función:** `run_etl`, bucle principal líneas 407-501 (contador `tablas_fail` en línea 501,
  variable `tablas_ok/tablas_fail` nunca consultada antes de procesar un hecho).
- **Problema:** el aislamiento de errores por tabla (línea 415 y comentario "P10") es correcto
  en el sentido de que una tabla que falla no aborta el pipeline — pero el diseño no registra
  **cuáles** dimensiones fallaron en la corrida actual, ni usa esa información para decidir si
  procesar los hechos que dependen de ellas. Si, por ejemplo, `dim_producto` (SCD2, línea 227)
  falla en una corrida (excepción capturada en la línea 496, `continue`), el bucle sigue
  normalmente hacia `fact_ventas_detalle` (línea 233) y lo procesa igual, resolviendo
  `producto_sk` contra una tabla `dim_producto` que puede estar vacía, sin la última versión
  SCD2, o en un estado inconsistente de esa misma corrida.
- **Riesgo:** `resolver_llaves_hecho()` sí protege contra nulos rellenando con el centinela `-1`
  cuando existe (líneas 329-362), así que el síntoma no sería un `NOT NULL` roto, sino una
  degradación silenciosa: filas de venta que deberían apuntar a un producto real terminan
  apuntando al producto "Desconocido" (`-1`) simplemente porque la dimensión no se refrescó en
  esta corrida, no porque la llave de negocio no exista realmente en el ERP. Esto es
  indistinguible en los logs de un caso legítimo de código huérfano.
- **Impacto:** pérdida silenciosa de trazabilidad producto-venta (o cliente-venta, etc.) en
  corridas donde una dimensión falla pero sus hechos dependientes "aparentan" éxito.
- **Prioridad:** Alta.
- **Recomendación:** llevar un registro de qué tablas de `PIPELINE_CONFIG` fallaron en la
  corrida (ya se tiene `cfg['tabla']` disponible); declarar explícitamente en `PIPELINE_CONFIG`
  de qué dimensiones depende cada hecho (o inferirlo de las columnas de llave que usa
  `resolver_llaves_hecho`) y, si una dependencia falló en esta misma corrida, marcar el hecho
  dependiente como `SKIPPED` (no `FAIL` ni `SUCCESS` silencioso) con un mensaje explícito en
  `edw.etl_control`.

### CRÍTICO — H4 `DELETE` + recarga por chunks no es atómico: ventana de datos incompletos si falla un chunk intermedio
- **Función:** `run_etl`, bloque de idempotencia líneas 430-453 (`DELETE`) seguido del bucle de
  chunks líneas 458-488 (`load_data_chunk`).
- **Problema:** el `DELETE` del rango a recargar se ejecuta y **comitea** en su propio
  `with pg.connect().begin() as conn:` (líneas 441-443 para snapshot, 451-453 para
  incremental), separado del bucle que carga los chunks extraídos de SAP. Cada llamada a
  `load_data_chunk` (línea 486) invoca, según el loader, `load_dimension`/`load_dim_scd2`/
  `load_facts_append_only` — funciones no disponibles para inspección (H1), pero a juzgar por
  el patrón usado en `PostgresConnector.load_dataframe` (cada llamada abre y cierra su propio
  `engine.begin()`), cada chunk comitea independientemente. Si un chunk N de M falla (por
  ejemplo, un error de red con SAP a mitad de `sa.yield_query_chunks`, o una excepción de tipo
  de dato en un chunk tardío), la excepción es capturada por el `except Exception as e_tbl`
  de la línea 496, pero los chunks 1..N-1 **ya fueron insertados y comiteados**, y el rango
  completo ya fue borrado por el `DELETE` previo.
- **Riesgo:** la tabla queda con datos parciales (rango borrado + solo una fracción recargada)
  desde el momento del fallo hasta la próxima ejecución exitosa del pipeline para esa tabla.
  Como `registrar_control_etl` solo escribe `SUCCESS` al final del bucle completo (línea
  491-492), la siguiente corrida recalculará `fecha_desde` desde el mismo `last_date` anterior
  al intento fallido (vía `get_last_etl_date`), así que el **siguiente run se autocorrige**
  (vuelve a borrar el rango parcial y lo recarga completo) — pero cualquier consumidor
  (dashboard, modelo ML, `EXPLAIN`/consulta ad-hoc) que lea la tabla en esa ventana ve datos
  incompletos sin ningún indicador de "carga en progreso/fallida" visible fuera de los logs y
  de `edw.etl_control`.
- **Impacto:** ventana de inconsistencia real y silenciosa para consumidores del EDW en cada
  fallo a mitad de carga de una tabla de hechos grande (`fact_ventas_detalle`,
  `fact_movimientos_inventario`, con cientos de miles de filas — más chunks, más probabilidad
  de fallo a mitad de carga).
- **Prioridad:** Alta.
- **Recomendación:** envolver el `DELETE` + todos los chunks de una misma tabla en una única
  transacción (un solo `engine.begin()` que se pase a `load_data_chunk`/loaders, o ejecutar
  todo dentro del mismo bloque `with`), de forma que un fallo a mitad de carga revierta también
  el `DELETE` — dejando la tabla en su estado anterior (consistente) hasta el próximo intento
  exitoso, en vez de en un estado a medias.

## Hallazgos — Recomendados

### ALTA — H5 Sin validación de orden/dependencias en `PIPELINE_CONFIG`: el orden correcto depende enteramente de que un humano mantenga la lista bien ordenada
- **Función:** `PIPELINE_CONFIG`, líneas 215-241; consumida secuencialmente en el bucle de la
  línea 407.
- **Problema:** el orden dimensiones-antes-que-hechos es correcto hoy (verificado línea por
  línea: 9 dimensiones en 219-227, 10 hechos en 231-240) y `Dim_Fecha` se genera aparte, antes
  del bucle (líneas 400-404) — eso está bien. Pero no existe ninguna validación programática
  (ni un grafo de dependencias, ni un simple `assert`) que impida que alguien agregue una nueva
  entrada de hecho antes de su dimensión en una futura edición de la lista. La única defensa es
  la disciplina de quien edite el archivo.
- **Riesgo:** un futuro cambio (agregar un extractor nuevo, reordenar por error al hacer un
  merge) puede introducir silenciosamente un hecho que se ejecute antes de que su dimensión
  exista o esté poblada, sin que nada lo detecte hasta que aparezcan centinelas `-1` en
  producción.
- **Impacto:** mantenibilidad y riesgo de regresión futura, no un bug actual.
- **Prioridad:** Media.
- **Recomendación:** declarar explícitamente en cada entrada de `PIPELINE_CONFIG` de qué
  dimensiones depende (p.ej. `'depende_de': ['dim_producto', 'dim_cliente', ...]`) y, al inicio
  de `run_etl`, hacer un `assert`/orden topológico simple que separe automáticamente
  dimensiones de hechos y garantice el orden — en vez de confiar en la posición en la lista.

### ALTA — H6 Excepciones swallowed en `get_last_etl_date` y `registrar_control_etl` pueden ocultar problemas de infraestructura sin detener el pipeline
- **Función:** `get_last_etl_date`, líneas 40-56 (try/except líneas 47-55);
  `registrar_control_etl`, líneas 58-71 (try/except líneas 63-71).
- **Problema:** ambas funciones capturan `Exception` genérica, loguean con `logger.error(...,
  exc_info=True)` y continúan sin re-lanzar. Si `edw.etl_control` tiene un problema real
  (permisos revocados, columna renombrada, disco lleno), `get_last_etl_date` devuelve
  silenciosamente `date(1900, 1, 1)` — lo cual fuerza modo `FULL` para **todas** las tablas de
  ahí en adelante — y `registrar_control_etl` simplemente no deja rastro de que la corrida
  "exitosa" en realidad no quedó registrada en absoluto.
- **Riesgo:** el pipeline puede seguir "funcionando" (cargando datos) mientras la trazabilidad
  operativa (`edw.etl_control`) queda rota indefinidamente sin que nadie lo note vía una falla
  visible del pipeline — solo aparecería en logs, que pueden no monitorearse activamente.
  También implica reprocesar el historial completo de cada tabla en cada corrida (impacto en
  duración/carga sobre el ERP de solo lectura) sin que se distinga de una primera ejecución
  legítima.
- **Impacto:** operacional/observabilidad; puede derivar en cargas `FULL` repetidas e
  innecesarias contra Producción.
- **Prioridad:** Media-Alta.
- **Recomendación:** distinguir explícitamente "tabla de control no existe todavía" (caso
  legítimo, ya cubierto en la línea 43) de "la consulta/escritura falló" (línea 52/70): este
  segundo caso debería, como mínimo, incrementar un contador de "fallas de control" que se
  reporte en el resumen final del pipeline (línea 503), para que sea visible sin tener que leer
  logs línea por línea.

### MEDIA — H7 `resolver_llaves_hecho()` es una función monolítica fuertemente acoplada a nombres de columna de todos los hechos
- **Función:** `resolver_llaves_hecho`, líneas 243-369 (127 líneas, 9 bloques `if <col> in
  df.columns` para 9 dimensiones distintas, más el bloque de defaults 329-362).
- **Problema:** cada dimensión nueva que deba resolverse contra un hecho requiere editar esta
  función central (acoplamiento alto), en vez de que `PIPELINE_CONFIG` declare qué columnas de
  llave debe resolver cada hecho y que la función itere sobre esa declaración. Además, el mapeo
  `sk_col -> nombre de tabla` (líneas 340-350) está hardcodeado con una cadena de `elif`
  duplicando en la práctica el mismo mapeo que ya existe implícitamente en las secciones 1-10
  de arriba.
- **Riesgo:** bajo en el corto plazo (funciona), pero alto en mantenibilidad: agregar una
  dimensión nueva (p.ej. si se repobla `dim_geografia` en el futuro) implica tocar esta función
  en dos lugares distintos (el bloque de merge y el mapeo de defaults), con riesgo de que
  queden desincronizados.
- **Impacto:** mantenibilidad y velocidad de futuras extensiones del modelo.
- **Prioridad:** Media.
- **Recomendación:** extraer una tabla de configuración única
  `{sk_col: {'tabla': ..., 'llave_negocio': [...]}}` y hacer que tanto el merge como el
  relleno de defaults iteren sobre esa misma estructura, eliminando la duplicación.

### MEDIA — H8 No hay forma de ejecutar una sola dimensión o un solo hecho de manera aislada
- **Función:** `run_etl`, líneas 380-513; `__main__`, líneas 515-518.
- **Problema:** `run_etl(config)` siempre recorre `PIPELINE_CONFIG` completo. No hay parámetro
  (CLI arg, variable de entorno, o argumento de función) para indicar "solo correr
  `dim_producto`" o "solo correr `fact_compras`" — necesario para depurar o re-ejecutar una
  tabla puntual tras corregir un problema, sin reprocesar las 18 tablas restantes.
- **Riesgo:** operacional — para reprocesar una sola tabla hoy habría que comentar/editar
  manualmente `PIPELINE_CONFIG` y revertir el cambio después, con riesgo de dejarlo mal editado.
- **Impacto:** velocidad operativa y riesgo de error humano al depurar en producción.
- **Prioridad:** Media.
- **Recomendación:** agregar un parámetro opcional (p.ej. `tablas_incluir: list[str] = None`) a
  `run_etl` que filtre `PIPELINE_CONFIG` por `cfg['tabla']`, expuesto como argumento de línea de
  comandos en el bloque `__main__`.

### MEDIA — H9 Sin bloqueo de concurrencia: dos ejecuciones simultáneas del orchestrator pueden interferir entre sí
- **Función:** `run_etl`, líneas 380-513 (ninguna sección adquiere un lock).
- **Problema:** no hay ningún mecanismo (advisory lock de PostgreSQL, archivo de lock, chequeo
  de proceso en ejecución) que impida correr `orchestrator.py` dos veces en paralelo (manual +
  cron, o dos operadores distintos).
- **Riesgo:** dos corridas concurrentes podrían pisarse el `DELETE`+recarga de la misma tabla
  (una borra lo que la otra está por insertar, o ambas insertan duplicados si el `DELETE` de
  una corre después del `INSERT` de la otra), además de condiciones de carrera sobre
  `edw.etl_control`.
- **Impacto:** bajo probabilidad si la operación es manual y disciplinada, pero alto impacto si
  ocurre (duplicados o pérdida de datos).
- **Prioridad:** Media.
- **Recomendación:** adquirir un `pg_advisory_lock` al inicio de `run_etl` (liberarlo en el
  `finally` junto con `pg.disconnect()`) para garantizar una sola ejecución activa a la vez.

### MEDIA — H10 Sin reconciliación post-carga entre filas extraídas y filas efectivamente cargadas
- **Función:** `run_etl`, bucle de chunks líneas 458-488; resumen por tabla líneas 490-494.
- **Problema:** `total_loaded` acumula el valor de retorno de `load_data_chunk` (línea 486-487),
  pero no se compara contra la cantidad de filas efectivamente extraídas de SAP por chunk
  (`len(df_chunk)` antes de las transformaciones/PII/resolución de llaves). Si
  `resolver_llaves_hecho` o el loader descartaran filas silenciosamente (más allá de los
  `WARNING` ya agregados en la auditoría 08 para los `_sk` nulos), el resumen final ("tablas OK
  / tablas con fallo", línea 503) no lo reflejaría — se reportaría como éxito total.
- **Riesgo:** una pérdida de filas entre extracción y carga (fuera de los casos ya cubiertos por
  `WARNING` de `_sk` nulo) pasaría desapercibida en el resumen de alto nivel.
- **Impacto:** calidad de datos — es exactamente el tipo de diferencia EDW-vs-Producción que
  este proyecto está tratando de erradicar.
- **Prioridad:** Media.
- **Recomendación:** acumular también `total_extraido` (suma de `len(df_chunk)` antes de
  transformar) y loguear/registrar en `edw.etl_control` ambos números; si difieren más allá de
  un umbral esperado (filtros de negocio conocidos), emitir un `WARNING` explícito de
  reconciliación en el resumen de la tabla.

## Mejoras futuras

### BAJA — H11 Las dimensiones siempre se extraen en modo `FULL` (`FECHA_HISTORICA`), nunca incremental
- **Función:** `run_etl`, línea 422: `incremental = config.MODO_INCREMENTAL and es_hecho and
  last_date.year > 1900` — `es_hecho` excluye a toda dimensión del modo incremental por diseño.
- **Problema/Riesgo:** para dimensiones grandes (`dim_cliente`, `dim_producto`, ambas SCD2), cada
  corrida reextrae el universo completo de SAP en vez de solo los cambios desde la última
  corrida exitosa.
- **Impacto:** rendimiento/carga sobre el ERP de solo lectura, no corrección de datos.
- **Prioridad:** Baja.
- **Recomendación:** evaluar (con evidencia de volumen real de `clientes`/`articulos` en SAP) si
  conviene extender el modo incremental a dimensiones SCD2 usando `fecult` como piso, ya que el
  extractor de clientes ya expone esa columna (`delta_col: 'fecult'` en la línea 221).

### BAJA — H12 Orden de hechos sin relación de precedencia documentada entre sí
- **Función:** `PIPELINE_CONFIG`, líneas 230-240.
- **Problema:** `fact_inventario_snapshot` (existencias, snapshot del día) se procesa antes que
  `fact_movimientos_inventario` (kardex). No hay una dependencia de integridad referencial entre
  hechos en este modelo (cada hecho referencia solo dimensiones), así que esto no es un riesgo
  de datos, pero tampoco está documentado por qué ese orden específico es el elegido.
- **Riesgo:** ninguno funcional; posible confusión futura al reordenar sin saber si importa.
- **Impacto:** documentación/claridad.
- **Prioridad:** Baja.
- **Recomendación:** agregar un comentario breve confirmando explícitamente que el orden entre
  hechos es irrelevante (no hay FK hecho→hecho), para que futuras ediciones no asuman una
  dependencia inexistente.

## Resumen por severidad

**Críticos (deben corregirse antes de ejecutar el ETL)**
- H1 — `etl/loaders/` no existe; el módulo no importa. Bloqueante absoluto.
- H2 — `asegurar_registros_desconocidos()` intenta insertar en `dim_geografia` (tabla
  inexistente) dentro de la misma transacción que los demás centinelas válidos; hace fallar y
  abortar el pipeline completo en toda corrida.
- H3 — un hecho se procesa igual aunque su dimensión de dependencia haya fallado en la misma
  corrida — riesgo de atribución silenciosa al centinela `-1` sin que sea un caso real de llave
  huérfana.
- H4 — `DELETE` + recarga por chunks no es atómico; un fallo a mitad de carga deja la tabla en
  un estado parcial hasta la siguiente corrida exitosa.

**Recomendados**
- H5 — sin validación programática de orden/dependencias en `PIPELINE_CONFIG`.
- H6 — excepciones swallowed en `get_last_etl_date`/`registrar_control_etl` pueden ocultar
  problemas de infraestructura y forzar recargas `FULL` repetidas sin visibilidad.
- H7 — `resolver_llaves_hecho()` monolítica y con mapeo de tablas duplicado.
- H8 — no se puede ejecutar una sola dimensión/hecho de forma aislada.
- H9 — sin lock de concurrencia entre corridas simultáneas.
- H10 — sin reconciliación post-carga entre filas extraídas y cargadas en el resumen del
  pipeline.

**Mejoras futuras**
- H11 — dimensiones siempre en modo `FULL`, nunca incremental.
- H12 — orden entre hechos sin documentar explícitamente que es irrelevante.

Ningún hallazgo de esta auditoría requirió modificar `etl/extractors/`, el EDW ni
`etl/transformers/*.py`. No se aplicó ninguna corrección — este reporte es previo a cualquier
cambio de código, según lo solicitado.

## Correcciones aplicadas (2026-07-09)

Validado con `py_compile` sobre `etl/orchestrator.py`, `etl/connectors/postgres_connector.py`,
`etl/loaders/dim_loader.py`, `etl/loaders/fact_loader.py`, y con una importación real del
módulo (`import orchestrator`) que ejecuta `validar_orden_pipeline()` sin errores. No se
ejecutó el pipeline completo contra SAP/EDW (fuera de alcance de esta corrección).

- **H1** — se restauraron `etl/loaders/dim_loader.py` y `etl/loaders/fact_loader.py` con
  `git checkout` (estaban borrados del working tree pero seguían rastreados en git como
  deleción no comiteada; se verificó con `git ls-files`/`git status` antes de restaurar).
- **H2** — se eliminó el `INSERT INTO {schema}.dim_geografia` de
  `asegurar_registros_desconocidos()`; ya no rompe la transacción de centinelas.
- **H3** — se agregó `dims_fallidas: set` en `run_etl` y la clave `'depende_de'` por cada
  entrada de hecho en `PIPELINE_CONFIG` (inferida de las columnas de negocio de cada
  extractor). Si una dimensión falla, los hechos que dependen de ella se marcan `SKIPPED` en
  `edw.etl_control` y no se procesan en esa corrida.
- **H4** — `PostgresConnector.load_dataframe()` y los loaders (`load_dimension`,
  `load_dim_scd2`, `load_facts_append_only`/`load_facts_incremental`/`load_facts_full`)
  aceptan ahora un parámetro `conn` opcional. El orchestrator abre una única
  `with pg.connect().begin() as conn_tabla:` por tabla que envuelve el `DELETE` de
  idempotencia y todos sus chunks; un fallo a mitad de carga revierte también el `DELETE`.
- **H5** — nueva `validar_orden_pipeline()`, invocada al inicio de `run_etl`, que revisa que
  cada `'depende_de'` de un hecho ya haya aparecido como dimensión antes en la lista; lanza
  `AssertionError` si no. Verificado en caliente (ver método arriba): pasa con el
  `PIPELINE_CONFIG` actual (19 entradas).
- **H6** — `_STATS_CONTROL['fallas']` cuenta las excepciones reales en
  `get_last_etl_date`/`registrar_control_etl` (distintas de "la tabla no existe todavía") y se
  reporta en el resumen final del pipeline.
- **H7** — se extrajo `DIM_TABLE_BY_SK` (mapeo único `sk_col -> tabla`) y se eliminó la cadena
  de `elif` duplicada en `resolver_llaves_hecho()`.
- **H8** — `run_etl(config, tablas_incluir=None)` filtra `PIPELINE_CONFIG` por nombre de tabla
  destino; expuesto como `--tablas` en el bloque `__main__` (`argparse`).
- **H9** — `pg_try_advisory_lock`/`pg_advisory_unlock` (id fijo `823141`) al inicio/fin de
  `run_etl`, sobre una conexión dedicada que se mantiene abierta toda la corrida; si no se
  obtiene el lock, el pipeline aborta de inmediato en vez de arriesgar una corrida concurrente.
- **H10** — se acumula `total_extraido` (antes de transformar) junto a `total_loaded`; si
  difieren, se loguea un `WARNING` de reconciliación (y queda también en el mensaje de
  `edw.etl_control`).
- **H12** — se agregó el comentario confirmando que el orden entre hechos es irrelevante (no
  hay FK hecho→hecho).
- **H11** — sin cambios: requiere evidencia de volumen real de `clientes`/`articulos` en SAP
  (no disponible en esta sesión) antes de decidir si vale la pena incrementalizar dimensiones
  SCD2; queda **pendiente de evaluar**, como se documentó arriba.

**Nota sobre el alcance de H4:** la intercepción PII (`cliente_lookup` en `public`) se
mantiene fuera de la transacción atómica por tabla — es una tabla y esquema distintos, y
mezclarla con el `search_path`/transacción de `edw.dim_cliente` habría añadido riesgo
desproporcionado al alcance de este hallazgo; sigue comiteando aparte, igual que antes.
