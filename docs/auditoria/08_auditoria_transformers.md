# Auditoría 08 — Revisión técnica de `etl/transformers/` (pre-corrección)

- **Fecha:** 2026-07-09
- **Alcance:** `etl/transformers/dim_tiempo.py`, `etl/transformers/dim_transformer.py`,
  `etl/transformers/fact_transformer.py`. Contrastado contra `etl/extractors/*.sql` (no
  modificados), contra el EDW ya corregido en `docs/auditoria/07_revision_diseno_edw.md`, y contra
  `docs/auditoria/02_reglas_negocio_validadas.md`.
- **Método:** Revisión estática de código Python (no se ejecutó contra Producción ni contra el
  EDW). Ningún hallazgo aquí requiere `SELECT` de validación porque son defectos de lógica de
  transformación, no de datos; donde la corrección depende de una regla de negocio no confirmada
  (F13, F14), se marca explícitamente **"Pendiente de validar"**.
- Aún no se corrige código — este documento es la auditoría previa a la corrección, según el
  flujo de trabajo esperado para agentes de IA del proyecto.

## Hallazgos

### `dim_tiempo.py`

#### F1 — `normalizar_fechas()` (línea 41): corte arbitrario de fechas sin base documentada
- **Función:** `normalizar_fechas`, línea 41.
- **Problema:** `df.loc[df[col] < pd.Timestamp('2000-01-01'), col] = pd.NaT` — cualquier fecha
  anterior al año 2000 se convierte en NULL, sin regla de negocio que lo respalde.
- **Riesgo:** `Dim_Fecha` se genera solo desde 2010 (`generar_dim_tiempo` default
  `fecha_inicio='2010-01-01'`), así que fechas reales entre 2000 y 2010 pasan este filtro pero
  igual fallarían el lookup contra `Dim_Fecha` — validación desalineada con el rango real del
  EDW. Fechas legítimas anteriores a 2000 (p.ej. `fecha_ingreso` de un empleado antiguo) se anulan
  silenciosamente.
- **Ejemplo:** empleado con `fecha_ingreso = '1998-03-01'` queda con `NaT`, perdiendo el dato real
  sin advertencia.
- **Recomendación:** alinear el corte al rango real de `Dim_Fecha` (parametrizar, no
  hardcodear `2000-01-01`) y registrar cuántas filas se anulan por esta regla.
- **Prioridad:** Media.

#### F2 — `normalizar_numericos()` (línea 48): `fillna(0.0)` cambia el significado del dato
- **Función:** `normalizar_numericos`, línea 48.
- **Problema:** `pd.to_numeric(..., errors='coerce').fillna(0.0)` trata "valor ausente/no
  parseable" igual que "valor es cero". Se usa para `costo_unitario`, `precio_oficial`,
  `limite_credito`, `sueldo_base`, etc.
- **Riesgo:** si `costo_promedio` de un artículo viene NULL desde SAP (sin costeo aún), se
  convierte en `0.0`, y en `transformar_ventas_detalle` eso generaría
  `margen_bruto = precio_venta - 0`, **inflando el margen al 100%** sin que nadie lo note.
- **Ejemplo:** artículo nuevo con `costo_promedio = NULL` → tras esta función, `0.0` → márgenes
  reportados a Gerencia sobreestimados.
- **Recomendación:** distinguir "ausente" de "cero" para campos que alimentan cálculos derivados
  (costos, precios); no aplicar `fillna(0.0)` ciegamente o loguear cuántas filas se rellenaron.
- **Prioridad:** Alta.

#### F3 — `normalizar_numericos()` (línea 48-49): DECIMAL → FLOAT
- **Función:** `normalizar_numericos`, línea 48-49.
- **Problema:** `pd.to_numeric` produce `float64` a partir de valores `DECIMAL/NUMERIC` exactos
  del origen; se redondea con `.round(4)` antes de insertar en columnas `NUMERIC(15,4)`.
- **Riesgo:** para campos financieros, la conversión binaria puede introducir diferencias de
  centésimas de centavo tras operaciones encadenadas, que no calzan exactamente con un cálculo en
  `DECIMAL`. Bajo para magnitudes típicas de venta; relevante si se cuadra el total contra SAP
  centavo a centavo.
- **Ejemplo:** `0.1 + 0.2` en float64 no es exactamente `0.3`; en un acumulado de 500k líneas el
  error puede notarse a nivel de reporte agregado.
- **Recomendación:** aceptable para KPIs agregados; documentar la tolerancia esperada si Gerencia
  necesita cuadre exacto.
- **Prioridad:** Media.

#### F4 — `normalizar_strings()` (línea 56): sin protección contra pérdida de ceros a la izquierda
- **Función:** `normalizar_strings`, línea 56.
- **Problema:** `df[col].astype(str).str.strip().str.upper()` — si la columna llega desde
  pyodbc/pandas como `int64` (posible si el driver infiere tipo numérico de una columna SAP
  `VARCHAR` con contenido solo numérico: `codalm`, `establ`, `codemp`), `astype(str)` sobre un
  entero produce `'1'`, no `'01'`. La pérdida ya ocurrió antes de esta línea, pero esta función es
  el único punto de defensa disponible y no la aplica.
- **Riesgo:** **crítico** — el modelo entero usa `codemp='01'` (`VARCHAR(2)`), `establ` de 3
  dígitos, etc. Si un extractor de dimensión entrega el código como numérico, esa dimensión nunca
  hará match con el resto del modelo (incluida la fila centinela `-1` de la auditoría 07/H6), y la
  carga fallaría silenciosamente al centinela o violaría los `UNIQUE`/`NOT NULL` agregados.
- **Ejemplo:** `Dim_Almacen.codalm` llega como `5` (int) en vez de `'005'`; no calza con
  `kardex.codalm='005'` en `Fact_Movimientos_Inventario`, perdiendo la relación.
- **Recomendación:** verificar/forzar que las columnas de código de negocio se traten siempre
  como texto desde la extracción, o normalizar con `zfill(n)` conocido por columna antes de
  `astype(str)`.
- **Prioridad:** Alta.

### `dim_transformer.py`

#### F6 — `normalizar_estado()` (línea 10): NULL se convierte silenciosamente en "Activo"
- **Función:** `normalizar_estado`, línea 10.
- **Problema:** `.astype(str).str.strip().str.upper().map(ESTADO_MAP).fillna('A')`. Si el valor
  original es `NaN`, `astype(str)` lo convierte en `'NAN'`, no está en `ESTADO_MAP`, `.map()`
  devuelve `NaN`, y `.fillna('A')` lo convierte en **'A' (Activo)**.
- **Riesgo:** un cliente/producto/proveedor con `estado` realmente desconocido (NULL en SAP)
  queda marcado Activo por defecto, inflando el conteo de activos en dashboards.
- **Ejemplo:** proveedor con `estado = NULL` → tras esta función, `'A'` → aparece activo en
  reportes de compras sin serlo necesariamente.
- **Recomendación:** distinguir "no vino estado" de "vino un código no mapeado"; loguear cuántas
  filas cayeron en el fallback en vez de asumir Activo silenciosamente.
- **Prioridad:** Alta.

#### F7 — Mismo patrón sin protección de ceros en `normalizar_estado`/`normalizar_tipo_id` (líneas 10, 17)
- **Función:** `normalizar_estado` (línea 10), `normalizar_tipo_id` (línea 17).
- **Problema:** igual que F4 — si `tipo_id`/`estado` llegan como numérico, se pierde cualquier
  cero a la izquierda antes del mapeo (`TIPO_ID_MAP` usa claves `'04'`, `'05'`, etc.; si llega `4`
  en vez de `'04'`, no matchea y cae a `'OTRO'` silenciosamente).
- **Riesgo:** todos los clientes con `tipo_id` numérico sin cero a la izquierda se reclasifican
  como `'OTRO'` en vez de `'RUC'`/`'CEDULA'`, perdiendo esa segmentación.
- **Recomendación:** mismo que F4 — asegurar tipo string con padding antes del mapeo.
- **Prioridad:** Alta.

#### F8 — `deduplicar()` (líneas 20-25): función definida pero **nunca invocada**
- **Función:** `deduplicar`, líneas 20-25; no se llama desde `transformar_clientes`,
  `transformar_productos` ni ninguna otra función del archivo.
- **Problema:** existe lógica de deduplicación por clave natural, pero ningún transformer de
  dimensión la usa.
- **Riesgo:** si el extractor de clientes/productos trae dos filas para el mismo
  `(codemp, codcli)`, ambas llegarían al loader como candidatas a versión SCD2 "vigente" — con el
  índice único parcial de la auditoría 07 (H1), esto **haría fallar la carga completa** en vez de
  solo generar una inconsistencia silenciosa (mejor que antes, pero el problema no está resuelto
  en el transformer).
- **Ejemplo:** dos filas para `codcli='000123'` con `fecult` distintas → sin dedup, el loader
  intenta insertar dos filas vigentes → violación del índice único de H1 → ETL se detiene.
- **Recomendación:** invocar `deduplicar(df, clave_natural=['codemp','codcli'])` (y análogo para
  productos) dentro de `transformar_clientes`/`transformar_productos` antes de retornar.
- **Prioridad:** Alta.

#### F9 — `deduplicar()` (líneas 22-24): desempate no determinista si `fecult` es nulo o repetido
- **Función:** `deduplicar`, líneas 22-24.
- **Problema:** `sort_values('fecult', ascending=False)` + `drop_duplicates(keep='first')`. Si
  varias filas duplicadas tienen `fecult` idéntico (o todas `NaT`), el desempate depende del orden
  de llegada del extractor, no de una regla explícita.
- **Riesgo:** no determinismo — dos corridas del mismo extractor podrían quedarse con una versión
  distinta del "duplicado" cada vez.
- **Recomendación:** agregar una clave de desempate secundaria estable (la propia clave natural)
  al `sort_values`, igual que se hizo en `almacenes_extractor.sql` con `ORDER BY ... ASC`.
- **Prioridad:** Baja.

#### F10 — Parseo de booleanos `activa`/`activo` sensible a representación numérica (líneas 66, 85, 95)
- **Función:** `transformar_sucursales` (línea 66), `transformar_vendedores` (línea 85),
  `transformar_empleados` (línea 95).
- **Problema:** `.astype(str).str.strip().str.upper().isin(['1','T','TRUE','A','ACTIVO','S'])`.
  Si la columna llega como `float64` (`1.0` en vez de `1`), `astype(str)` produce `'1.0'`, que
  **no está** en la lista de valores aceptados.
- **Riesgo:** un vendedor/sucursal/empleado realmente activo queda marcado `activo=False` sin
  aviso — filtra registros activos de los dashboards.
- **Ejemplo:** `vendedorescob.estado` llega como `1.0` (float) → `'1.0'` no está en la lista →
  `activo=False` para un vendedor activo.
- **Recomendación:** normalizar primero a numérico cuando sea posible
  (`pd.to_numeric(..., errors='coerce')`) y comparar contra `1`/`0`, o ampliar el `isin()` para
  cubrir representaciones flotantes, antes de convertir a string.
- **Prioridad:** Alta.

#### F11 — `transformar_geografia()` (líneas 109-111): función huérfana tras la auditoría del EDW
- **Función:** `transformar_geografia`, líneas 109-111.
- **Problema:** transforma datos para `Dim_Geografia`, tabla retirada del EDW en la auditoría 07
  (H4, aplicado en `edw/02_dimensiones.sql`).
- **Riesgo:** si esta función se invoca desde el orchestrator, el loader intentaría insertar en
  una tabla que ya no existe → error de carga.
- **Recomendación:** eliminar esta función (o documentar explícitamente que ya no tiene tabla
  destino), coordinado con que el orchestrator no la invoque.
- **Prioridad:** Baja.

### `fact_transformer.py`

#### F12 — `transformar_ventas_detalle()` (líneas 21, 24-25): **incompatible con el EDW ya corregido**
- **Función:** `transformar_ventas_detalle`, líneas 21 (`es_devolucion`) y 24-25
  (`estado_factura`).
- **Problema:** sigue generando `es_devolucion` y `estado_factura` como columnas sueltas para
  escribir directo en `Fact_Ventas_Detalle`, y no genera `tipo_documento`. Tras la auditoría 07
  (H9), `Fact_Ventas_Detalle` ya no tiene esas columnas — tiene
  `estado_documento_sk NOT NULL REFERENCES edw.Dim_Estado_Documento`.
- **Riesgo:** **el loader fallará por completo** al insertar columnas que ya no existen en la
  tabla destino, y le faltará el `estado_documento_sk` obligatorio. Hallazgo de mayor severidad:
  bloquea cualquier carga de la fact principal.
- **Ejemplo:** `INSERT INTO edw.Fact_Ventas_Detalle (..., es_devolucion, estado_factura) VALUES
  (...)` → error de columna inexistente.
- **Recomendación:** producir `tipo_documento`, `es_devolucion`, `estado_factura` como atributos
  intermedios y resolverlos contra `Dim_Estado_Documento` para obtener `estado_documento_sk`
  antes de entregar el DataFrame al loader (o verificar que el loader hace ese lookup con los
  nombres de columna que este transformer expone).
- **Prioridad:** Crítica.

#### F13 — `transformar_ventas_detalle()` (línea 21): heurística `cantidad < 0` sin validar contra Producción
- **Función:** `transformar_ventas_detalle`, línea 21.
- **Problema:** `df['es_devolucion'] = df['cantidad'] < 0`, asumiendo que una cantidad negativa
  en `renglonesfacturas.cantid` indica devolución. No hay evidencia en
  `docs/auditoria/02_reglas_negocio_validadas.md` que confirme que este campo puede ser negativo.
- **Riesgo:** si `cantid` nunca es negativo en Producción (las devoluciones viven en
  `renglonesdevoluciones`, tabla separada), la columna sería siempre `False` (inofensiva pero
  inútil); si puede serlo por otro motivo (ajuste, error de digitación), se clasificarían mal
  esas filas como devoluciones.
- **Recomendación:** **Pendiente de validar** —
  `SELECT MIN(cantid) FROM renglonesfacturas WHERE codemp='01'` (SELECT puro sobre SAP) antes de
  confiar en esta heurística.
- **Prioridad:** Media.

#### F14 — `transformar_ventas_detalle()` (línea 22, comentario): cambio de convención no documentado
- **Función:** `transformar_ventas_detalle`, línea 22.
- **Problema:** el comentario `# Removido: df['cantidad'] = df['cantidad'].abs() para que sumen
  negativamente` indica que se permite `cantidad` negativa en la fact deliberadamente. Contradice
  el patrón de `Fact_Movimientos_Inventario.cantidad_movimiento`, que sí se fuerza a magnitud
  positiva (línea 60 del mismo archivo).
- **Riesgo:** inconsistencia de convención entre facts hermanas sin documentar en el DDL ni en
  las reglas de negocio — cualquier consumidor que asuma `cantidad >= 0` en ventas (válido en
  movimientos) tendrá resultados incorrectos.
- **Recomendación:** documentar explícitamente esta convención de signo en el DDL de
  `Fact_Ventas_Detalle.cantidad` (mismo patrón que H8 con `pct_margen`).
- **Prioridad:** Media.

#### F15 — `transformar_movimientos_inventario()` (líneas 56-58): fallback reintroduce el bug crítico ya corregido
- **Función:** `transformar_movimientos_inventario`, líneas 55-58.
- **Problema:** el comentario (líneas 47-50) documenta correctamente que `cantidad_movimiento`
  siempre es positivo y la dirección la da `tipdoc`, citando la corrección de un bug donde "el
  código anterior marcaba todo como entrada". El `else` de fallback (si `'tipdoc' not in
  df.columns`) usa `cantidad_movimiento > 0` para `es_entrada` — exactamente la misma lógica rota.
- **Riesgo:** dado que `cantidad_movimiento` nunca es negativa, si `tipdoc` faltara (renombre
  accidental en el extractor), **todas** las filas caerían en este fallback marcadas como entrada,
  reintroduciendo silenciosamente el bug que la auditoría 04 ya había corregido.
- **Ejemplo:** si `kardex_extractor.sql` cambiara el alias de `tipdoc` sin actualizar este
  transformer, todo el inventario de salidas se contabilizaría como entrada.
- **Recomendación:** el fallback no debería ser "silenciosamente funcional" — si `tipdoc` no está
  presente, fallar explícitamente (`raise ValueError`) en vez de aplicar una heurística que se
  sabe incorrecta.
- **Prioridad:** Crítica.

#### F16 — `transformar_movimientos_inventario()`: no gestiona `codcli`/`codven` que el EDW ahora sí acepta (H5)
- **Función:** `transformar_movimientos_inventario`, líneas 43-61 (todo el cuerpo).
- **Problema:** tras la auditoría 07 (H5), `Fact_Movimientos_Inventario` ganó `cliente_sk`/
  `vendedor_sk` (nullable) para aprovechar `codcli`/`codven` del kardex. Esta función no
  normaliza ni preserva esas columnas.
- **Riesgo:** si el loader espera columnas normalizadas (`strip`/`upper`) para el lookup contra
  `Dim_Cliente`/`Dim_Vendedor` (que sí se normalizan en `dim_transformer.py`), un `codcli`/
  `codven` sin normalizar no calzará con la dimensión y cada movimiento `'FAC'` quedará con
  `cliente_sk`/`vendedor_sk` = centinela `-1`, perdiendo la información que H5 buscaba preservar.
- **Recomendación:** agregar `normalizar_strings(df, ['codcli', 'codven'])` en esta función.
- **Prioridad:** Alta.

#### F17 — Ausencia general de normalización de llaves de negocio en `fact_transformer.py`
- **Función:** todas (`transformar_ventas_detalle`, `transformar_compras`,
  `transformar_cobros_cxc`, `transformar_pagos_cxp`, `transformar_devoluciones`, etc.).
- **Problema:** ninguna normaliza (`strip`/`upper`) las columnas de código natural usadas para
  resolver surrogate keys (`codart`, `codcli`, `codalm`, `codven`, `codemp`, `codpro`,
  `codforpag`) — solo se normalizan explícitamente los identificadores degenerados (`num_factura`,
  `num_transaccion`, `num_caja`, `num_nota_credito`, `tipo_movimiento`, `num_documento`).
- **Riesgo:** inconsistencia entre cómo se normalizan las mismas llaves en `dim_transformer.py`
  (siempre `strip().upper()`) y cómo llegan sin normalizar desde `fact_transformer.py` — cualquier
  diferencia de espacios/mayúsculas hace que el lookup no resuelva y la fila caiga al centinela
  `-1`, perdiendo silenciosamente la relación real.
- **Recomendación:** aplicar `normalizar_strings()` a las columnas de llave natural en cada
  función, antes de que el loader resuelva los surrogate keys.
- **Prioridad:** Alta.

#### F18 — `transformar_cobros_cxc()`/`transformar_pagos_cxp()` (líneas 70, 79): regla implícita en `dias_vencimiento`
- **Función:** `transformar_cobros_cxc` (línea 70), `transformar_pagos_cxp` (línea 79).
- **Problema:** `dias_vencimiento` ausente se convierte en `0`, y de ahí
  `esta_vencido = dias_vencimiento > 0` (línea 74) resulta `False` — "no sé cuántos días de
  vencimiento tiene" se interpreta como "no está vencido".
- **Riesgo:** bajo pero real — una cuenta con vencimiento desconocido se reporta como "al día",
  ocultando cartera vencida real de Gerencia/Ventas.
- **Recomendación:** documentar esta regla explícitamente (mismo patrón que H8) o dejar
  `esta_vencido` como no determinable en ese caso.
- **Prioridad:** Media.

## Resumen por severidad

**Crítico / bloqueante para la próxima carga**
- F12 — `Fact_Ventas_Detalle` ya no acepta `es_devolucion`/`estado_factura`/`tipo_documento` sueltos.
- F15 — fallback de `es_entrada`/`es_salida` reintroduce el bug ya corregido si falta `tipdoc`.
- F4 / F7 — riesgo de pérdida de ceros a la izquierda en llaves de negocio.

**Alto (corrompe datos silenciosamente sin detener la carga)**
- F2 — `fillna(0.0)` en costos/precios infla márgenes.
- F6 — NULL en `estado` se vuelve "Activo" por defecto.
- F10 — booleanos flotantes mal parseados → activos marcados inactivos.
- F16 / F17 — llaves de negocio sin normalizar → lookups fallidos hacia el centinela `-1`.
- F8 — deduplicación no invocada.

**Medio**
- F1 — corte de fechas arbitrario y desalineado con el rango de `Dim_Fecha`.
- F13 / F14 — heurística de devolución/signo de `cantidad` sin validar y sin documentar.
- F18 — regla implícita de "vencimiento desconocido = no vencido".
- F3 — DECIMAL → FLOAT, riesgo bajo pero presente.

**Bajo**
- F9 — desempate no determinista en `deduplicar`.
- F11 — código muerto de `Dim_Geografia`.

Ningún hallazgo de esta auditoría requirió tocar `etl/extractors/`. F11 sí requirió coordinar con
`etl/orchestrator.py` (ver "Correcciones aplicadas").

## Correcciones aplicadas (2026-07-09)

Validado con `py_compile` sobre los tres transformers y `etl/orchestrator.py` (sin ejecución
contra Producción ni contra el EDW — ningún hallazgo de esta auditoría requería un `SELECT` de
validación).

- **F1** — `normalizar_fechas` ahora usa `fecha_minima` parametrizable (default alineado a
  `generar_dim_tiempo`, 2010-01-01) y loguea cuántas filas anula por estar fuera de rango.
- **F2** — `normalizar_numericos` acepta `permitir_nulos`; en `transformar_ventas_detalle`,
  `costo_unitario`/`costo_total` conservan `NaN` en vez de `0.0`, y el resto de columnas loguea
  cuántas filas rellenó.
- **F4** — `normalizar_strings` loguea un `WARNING` cuando la columna llega con dtype numérico
  (riesgo de pérdida de ceros a la izquierda); no se puede reconstruir el ancho original en el
  transformer, así que la corrección de fondo queda pendiente en extractor/conector.
- **F6** — `normalizar_estado` distingue NULL real de código no mapeado y loguea ambos casos
  por separado antes de aplicar el fallback a `'A'`.
- **F7** — `normalizar_tipo_id` aplica `zfill(2)` cuando la columna es numérica, alineado al
  ancho de las claves de `TIPO_ID_MAP`.
- **F8** — `deduplicar()` ahora se invoca desde `transformar_clientes`
  (`['codemp','codcli']`) y `transformar_productos` (`['codemp','codart']`).
- **F9** — `deduplicar()` agrega la propia clave natural como desempate secundario estable en
  el `sort_values`.
- **F10** — nueva `normalizar_booleano_activo()` normaliza a numérico antes de comparar,
  cubriendo representaciones flotantes (`1.0`); usada en `transformar_sucursales`,
  `transformar_vendedores`, `transformar_empleados`.
- **F11** — se eliminó `transformar_geografia` (código huérfano) y su entrada en
  `PIPELINE_CONFIG`/import de `etl/orchestrator.py`, ya que `Dim_Geografia` no existe en el EDW
  desde la auditoría 07 (H4); sin este cambio el pipeline habría fallado al intentar cargarla.
- **F12** — `transformar_ventas_detalle` ahora expone `tipo_documento`, `es_devolucion` y
  `estado_factura` (renombrando `estado` del extractor) con los nombres exactos de los atributos
  de `Dim_Estado_Documento`, para que el loader resuelva `estado_documento_sk` en vez de escribir
  columnas que ya no existen en `Fact_Ventas_Detalle`.
- **F15** — el fallback de `transformar_movimientos_inventario` cuando falta `tipdoc` ahora
  levanta `ValueError` explícito en vez de aplicar la heurística `cantidad_movimiento > 0` que
  reintroducía el bug ya corregido en la auditoría 04.
- **F16 / F17** — se agregó `normalizar_strings()` sobre las llaves de negocio
  (`codemp`, `codart`, `codalm`, `codcli`, `codven`, `codpro`, `codforpag`) en
  `transformar_movimientos_inventario`, `transformar_ventas_detalle`, `transformar_compras`,
  `transformar_cobros_cxc`, `transformar_pagos_cxp` y `transformar_devoluciones`.
- **F18** — documentado inline en `transformar_cobros_cxc` (regla implícita, no corregida: el
  modelo `esta_vencido` es `BOOLEAN` y no admite un estado "no determinable").
- **F3, F13, F14** — sin cambios de código. F3 es un riesgo aceptado (documentado). F13/F14
  siguen **Pendientes de validar** contra Producción (`SELECT MIN(cantid) FROM
  renglonesfacturas WHERE codemp='01'`) antes de decidir si la heurística de `es_devolucion` y
  la convención de signo de `cantidad` son correctas; no se asumió nada sin esa evidencia.
- **F9** (bajo) y **F3** (medio) fueron los únicos hallazgos de severidad Baja/Media aplicados
  sin requerir validación adicional; el resto de hallazgos Medios pendientes de decisión de
  negocio se dejó igual.
