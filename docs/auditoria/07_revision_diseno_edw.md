# Auditoría 07 — Revisión técnica del diseño del EDW (pre-transformers)

- **Fecha:** 2026-07-09
- **Alcance:** `edw/01_schema.sql` … `edw/09_vistas_ml.sql` (modelo dimensional completo: 11
  dimensiones, 11 hechos, control ETL, tablas `public.*`, seed, vista ML). Contrastado contra los
  24 extractores en `etl/extractors/*.sql` (ya congelados, no se propone ningún cambio sobre
  ellos) y contra `docs/auditoria/02_reglas_negocio_validadas.md`.
- **Método:** Revisión estática de DDL + lectura de extractores para verificar compatibilidad de
  columnas/tipos/grain. **No se ejecutó ningún SQL contra Producción ni contra el EDW** (el EDW
  aún no tiene datos cargados porque `etl/loaders/` está borrado del working tree — ver
  Observaciones de `CLAUDE.md`); por tanto los hallazgos de volumen/integridad referencial real
  quedan marcados **"Pendiente de validar"** hasta que exista una carga real.

## Hallazgos

### Alta — H1: Sin constraint que impida más de una versión vigente en SCD2
- **Archivo/Tabla:** `edw/04_indices.sql` — `Dim_Producto`, `Dim_Cliente`.
- **Evidencia:** `idx_dp_vigente` e `idx_dc_vigente` son índices parciales **no únicos**
  (`CREATE INDEX ... WHERE es_vigente = TRUE`), no `CREATE UNIQUE INDEX`. Nada en el esquema
  impide dos filas con `es_vigente = TRUE` para el mismo `(codemp, codart)` / `hash_anonimo`.
- **Riesgo durante el ETL:** un loader SCD2 que reintente tras un fallo parcial (no cerrar la
  versión anterior antes de insertar la nueva) duplica la versión vigente sin que la base lo
  impida. Los hechos que se unan por vigencia (`JOIN ... WHERE es_vigente`) devolverían filas
  multiplicadas, inflando ventas/márgenes silenciosamente.
- **Recomendación:** reemplazar ambos índices por únicos:
  `CREATE UNIQUE INDEX ux_dim_producto_vigente ON edw.Dim_Producto(codemp, codart) WHERE es_vigente;`
  `CREATE UNIQUE INDEX ux_dim_cliente_vigente ON edw.Dim_Cliente(hash_anonimo) WHERE es_vigente;`
  Esto convierte el bug potencial del loader en un error de carga explícito en vez de un dato
  corrupto silencioso.
- **Prioridad:** Alta.

### Resuelto (no aplica) — H2: Comisión de vendedor sin historia (Tipo 1)
- **Archivo/Tabla:** `edw/02_dimensiones.sql` — `Dim_Vendedor.comision`.
- **Estado actualizado (2026-07-09):** el extractor `vendedores_extractor.sql` ya no selecciona
  `comision1` (columna eliminada del extractor antes de esta revisión). Al no existir la fuente,
  el riesgo original de "sobrescribir retroactivamente el % de comisión histórico" ya no aplica:
  no hay comisión que sobrescribir. Se deja constancia por trazabilidad; el diseño en el EDW
  conserva la columna `Dim_Vendedor.comision`, que en la práctica quedará permanentemente `NULL`
  con el extractor actual — no es un hallazgo bloqueante, pero si en el futuro se reactiva la
  fuente, revisar si conviene reintroducir este hallazgo.
- **Prioridad:** N/A (cerrado sin acción sobre el EDW).

### Alta — H3: `Fact_Ventas_Detalle.num_factura` con longitud menor que el resto del modelo
- **Archivo/Tabla:** `edw/03_hechos.sql` línea 14 — `Fact_Ventas_Detalle.num_factura VARCHAR(10)`.
- **Evidencia:** el mismo campo origen (`numfac`, tabla `encabezadofacturas`/`renglonesfacturas`)
  se modela en el resto del EDW con longitudes mayores: `Fact_Compras.num_factura VARCHAR(20)`,
  `Fact_Devoluciones.num_nota_credito VARCHAR(50)`, `Fact_Cobros_CXC/Fact_Pagos_CXP.num_transaccion
  VARCHAR(20)`. Solo la fact principal de ventas (~539k filas esperadas) usa `VARCHAR(10)`.
- **Riesgo durante el ETL:** si `numfac` en Producción excede 10 caracteres (algo ya asumido en
  el resto del modelo), la carga fallará por truncamiento/violación de longitud en la fact más
  grande y de mayor uso (Gerencia, todos los dashboards). Es inconsistente además para cruzar
  `num_factura` entre `Fact_Ventas_Detalle` y `Fact_Devoluciones`/`Fact_Cobros_CXC` en análisis de
  trazabilidad documento a documento.
- **Recomendación:** ampliar a `VARCHAR(20)` para alinear con `Fact_Compras` y evitar corte de
  datos. Confirmar la longitud real de `numfac` con
  `SELECT MAX(LENGTH(numfac)) FROM encabezadofacturas WHERE codemp='01'` (SELECT puro sobre SAP).
- **Prioridad:** Alta.

### Resuelto — H4: `Dim_Geografia` no está referenciada por ninguna dimensión ni hecho
- **Archivo/Tabla:** `edw/02_dimensiones.sql` — `Dim_Geografia`; no aparece como FK en
  `edw/03_hechos.sql` ni como columna en ninguna otra dimensión.
- **Evidencia:** `Dim_Cliente` ya trae `zona`/`nombre_zona`/`ciudad` desnormalizados directamente
  (correcto para modelo estrella), y ninguna tabla tiene `geografia_sk`. `Dim_Geografia` queda
  aislada: se puebla (`geografia_extractor.sql` existe y es válido) pero no hay camino de
  consumo. Esto coincide con el hallazgo abierto de la auditoría 05 ("`dim_geografia` vacía"),
  pero aquí se confirma que el problema es estructural, no solo de datos: aunque se cargue,
  ninguna fact/dim la referencia.
- **Riesgo:** dimensión muerta; cualquier análisis territorial (ventas por provincia/cantón más
  allá del campo plano `ciudad` de cliente) no es posible con el modelo actual pese a existir la
  tabla.
- **Recomendación:** decidir explícitamente uno de dos caminos antes de escribir los
  transformers: (a) agregar `geografia_sk` a `Dim_Sucursal` (rollup territorial de sucursales,
  el caso de uso más natural para "empresas multisucursal") y consumirla desde ahí, o (b)
  eliminar `Dim_Geografia` del alcance si no hay un caso de uso concreto de negocio que la
  necesite. Mantenerla sin FK es deuda de diseño, no una decisión.
- **Decisión (2026-07-09):** se eliminó `Dim_Geografia` del alcance del EDW (no había caso de
  uso de negocio que la necesitara). Se retiró la tabla de `edw/02_dimensiones.sql` y su entrada
  de `edw/06_verificacion.sql`. `geografia_extractor.sql` queda sin tabla destino en el EDW por
  decisión explícita (no se modificó el extractor ni el orchestrator).
- **Prioridad:** Alta → Cerrado.

### Resuelto — H5: `Fact_Movimientos_Inventario` descarta `codcli`/`codven` que el extractor sí trae
- **Archivo/Tabla:** `edw/03_hechos.sql` — `Fact_Movimientos_Inventario` vs
  `etl/extractors/kardex_extractor.sql`.
- **Evidencia:** el extractor de kardex expone `codcli` y `codven` (comentados como "Cliente/
  Vendedor asociado si aplica", útiles cuando `tiporg='FAC'`), pero `Fact_Movimientos_Inventario`
  no tiene columnas `cliente_sk` ni `vendedor_sk`. El transformer, al no poder modificar el
  extractor pero tampoco tener dónde escribir esas columnas en el DDL, forzosamente descarta esa
  información.
- **Riesgo:** se pierde la posibilidad de conciliar un movimiento de salida de inventario por
  venta con el cliente/vendedor que lo originó directamente desde la fact de inventario (hoy solo
  se puede vía `num_documento` cruzando manualmente con `Fact_Ventas_Detalle`, que no está
  garantizado como join limpio porque `num_documento` en movimientos no está tipado igual que
  `num_factura` en ventas — ver H3).
- **Recomendación:** si el negocio necesita este cruce (auditoría de bodega, detección de fraude
  en salidas por venta), agregar `cliente_sk INT REFERENCES edw.Dim_Cliente(cliente_sk)` y
  `vendedor_sk INT REFERENCES edw.Dim_Vendedor(vendedor_sk)` **nullable** (solo aplica a
  `tiporg IN ('FAC')`) a `Fact_Movimientos_Inventario`. Si no se necesita, documentar la decisión
  de descartarlos para que el transformer no lo trate como un bug pendiente.
- **Decisión (2026-07-09):** se agregaron `cliente_sk` y `vendedor_sk` (nullable, con FK a
  `Dim_Cliente`/`Dim_Vendedor`) a `Fact_Movimientos_Inventario` en `edw/03_hechos.sql`, con
  comentario documentando que solo aplican cuando `tipo_movimiento='FAC'`.
- **Prioridad:** Alta → Cerrado.

### Resuelto — H6: Ninguna fila centinela `-1` está seedeada en el DDL de `edw/`
- **Archivo/Tabla:** todas las dimensiones en `edw/02_dimensiones.sql`; `edw/08_seed_roles_usuarios.sql`
  solo siembra `public.roles`/`public.usuarios`.
- **Evidencia:** la regla de negocio #12 de `CLAUDE.md` exige un registro centinela `-1` por
  dimensión para llaves no resueltas, y todas las FK de las 11 facts son `NOT NULL`. No hay
  ningún `INSERT` en `edw/01..09` que cree esas filas `-1`.
- **Riesgo durante el ETL:** si la creación del centinela vive únicamente en el loader (Python,
  hoy borrado del working tree) y no en el DDL, la primera carga de hechos fallará por violación
  de FK `NOT NULL` en cualquier fila que no resuelva su dimensión, en vez de degradar
  correctamente al centinela — y si el loader se reescribe sin recordar esta convención, el
  requisito se pierde silenciosamente.
- **Recomendación:** asegurar que la creación de los 11 registros `-1` ("Desconocido") sea parte
  del propio DDL (agregarlos al final de `02_dimensiones.sql` con `INSERT ... ON CONFLICT DO
  NOTHING`, igual que se hizo con roles en `08_seed_roles_usuarios.sql`), de modo que el
  requisito no dependa de que el loader lo recuerde implementar.
- **Decisión (2026-07-09):** se agregó una sección "REGISTROS CENTINELA" al final de
  `edw/02_dimensiones.sql` con un `INSERT ... ON CONFLICT DO NOTHING` por cada una de las 10
  dimensiones vigentes (excluida `Dim_Geografia`, retirada en H4), sembrando la fila `-1`
  ("Desconocido") con valores válidos para los `NOT NULL`/`UNIQUE` de cada tabla.
- **Prioridad:** Alta → Cerrado.

### Resuelto — H7: `Dim_Sucursal.codigo_sucursal` único sin `codemp`, pese a ser multiempresa por diseño
- **Archivo/Tabla:** `edw/02_dimensiones.sql` línea 29 —
  `codigo_sucursal VARCHAR(5) NOT NULL UNIQUE` (no `UNIQUE(codemp, codigo_sucursal)`).
- **Evidencia:** `sucursales_extractor.sql` deriva `codigo_sucursal = establ` (código de 3
  caracteres del establecimiento), y `CLAUDE.md` documenta `codemp` como tokenizado explícitamente
  "para multi-empresa futura". Con una sola empresa (`codemp='01'`) no falla hoy, pero el diseño
  ya contempla más de una empresa.
  Contraste: `Dim_Almacen` sí usa `UNIQUE(codemp, codalm)` correctamente.
- **Riesgo:** si se activa una segunda empresa cuyo establecimiento coincide en código (p.ej.
  ambas tienen un `establ='001'`), la carga de `Dim_Sucursal` fallará por violación de unicidad,
  o peor, un ETL sin ese constraint bien puesto podría mezclar sucursales de dos empresas
  distintas bajo la misma SK.
- **Recomendación:** cambiar a `UNIQUE (codemp, codigo_sucursal)`, igual que se hizo en
  `Dim_Almacen`, `Dim_Proveedor`, `Dim_Vendedor`, etc.
- **Decisión (2026-07-09):** se cambió `codigo_sucursal VARCHAR(5) NOT NULL UNIQUE` por
  `codigo_sucursal VARCHAR(5) NOT NULL` + `UNIQUE (codemp, codigo_sucursal)` a nivel de tabla en
  `edw/02_dimensiones.sql`. Se ajustó también el `ON CONFLICT` de la fila centinela `-1` (H6)
  para referenciar el nuevo constraint compuesto.
- **Prioridad:** Media → Cerrado.

### Resuelto — H8: `pct_margen NOT NULL` sin protección explícita contra división por cero
- **Archivo/Tabla:** `edw/03_hechos.sql` — `Fact_Ventas_Detalle.pct_margen NUMERIC(8,4) NOT NULL`.
- **Evidencia:** `pct_margen` se deriva de `margen_bruto / subtotal_neto` (o similar). `precio_
  oficial` en `Dim_Producto` es nullable y el negocio incluye `es_servicio`/artículos con
  `precio_unitario = 0` (promociones, cortesías). La columna es `NOT NULL`, obligando al
  transformer a decidir un valor (0, NULL-safe fallback) sin que el DDL documente cuál.
- **Riesgo:** si el transformer no maneja el caso `subtotal_neto = 0` explícitamente, la carga de
  esa fila fallará completa en vez de degradar el campo no aditivo, deteniendo el ETL de la fact
  más importante del modelo por una sola línea con precio 0.
- **Recomendación:** documentar en el DDL (comentario) la regla de cálculo cuando el denominador
  es 0 (p.ej. `pct_margen = 0` por convención), o permitir `NULL` en la columna si "sin margen
  calculable" es semánticamente distinto de "margen 0%".
- **Decisión (2026-07-09):** se mantiene `pct_margen NOT NULL`; se documenta con
  `COMMENT ON COLUMN` en `edw/03_hechos.sql` la convención `pct_margen = 0` cuando
  `subtotal_neto = 0`, para que el transformer la implemente sin ambigüedad.
- **Prioridad:** Media → Cerrado.

### Resuelto — H9: Flags/códigos de baja cardinalidad dispersos en `Fact_Ventas_Detalle`
- **Archivo/Tabla:** `edw/03_hechos.sql` — `tipo_documento`, `es_devolucion`, `estado_factura`.
- **Evidencia:** tres columnas de baja cardinalidad viven sueltas en la fact en vez de una junk
  dimension.
- **Riesgo:** ninguno funcional; solo ancho de fila y falta de un catálogo único de combinaciones.
- **Recomendación:** opcional, considerar junk dimension `Dim_Estado_Documento` si el número de
  combinaciones crece. No urgente.
- **Decisión (2026-07-09):** se creó `Dim_Estado_Documento` (junk dimension) en
  `edw/02_dimensiones.sql` con `UNIQUE(tipo_documento, es_devolucion, estado_factura)` y su fila
  centinela `-1`. `Fact_Ventas_Detalle` reemplazó las tres columnas sueltas por
  `estado_documento_sk NOT NULL REFERENCES edw.Dim_Estado_Documento`. Se agregó el índice
  `idx_fvd_estado_doc` y la entrada en `edw/06_verificacion.sql`.
- **Prioridad:** Baja → Cerrado.

### Resuelto — H10: Ausencia de `Fact_Transferencias` (ya señalada por el propio extractor)
- **Archivo:** `etl/extractors/transferencias_extractor.sql` (comentario propio: "[PENDIENTE DDL]
  Aún no existe Fact_Transferencias en el DW").
- **Evidencia:** el extractor está validado y listo, pero no hay tabla en `edw/03_hechos.sql`
  que lo reciba. Hoy las transferencias solo se reflejarían como dos filas independientes en
  `Fact_Movimientos_Inventario` (`SA` origen / `EN` destino) sin relación explícita entre ellas.
- **Riesgo:** no se puede medir eficiencia/tiempo de tránsito de una transferencia (origen→destino)
  ni su estado, sin reconstruir el pareo `(numdoc, numren, codart)` en cada consulta analítica —
  lógica de negocio replicada en cada consumidor en vez de resuelta una sola vez en el modelo.
- **Recomendación:** decisión de producto/tesis: crear `Fact_Transferencias` (grain: transferencia
  por línea, con `codalm_origen_sk`, `codalm_destino_sk`, `cantidad_enviada`) o aceptar
  formalmente el modelo actual de dos filas en `Fact_Movimientos_Inventario` y documentarlo como
  decisión, no como pendiente.
- **Decisión (2026-07-09):** se creó `Fact_Transferencias` en `edw/03_hechos.sql` (grain:
  transferencia por línea, `UNIQUE(num_documento, num_renglon, producto_sk)`), con
  `almacen_origen_sk`/`almacen_destino_sk` como FKs de rol contra `Dim_Almacen`. Se agregaron sus
  índices en `edw/04_indices.sql` y su entrada en `edw/06_verificacion.sql`. Pendiente fuera de
  este alcance: activar `transferencias_extractor.sql` en `PIPELINE_CONFIG` (orchestrator, no
  tocado en esta sesión).
- **Prioridad:** Media → Cerrado.

## Verificaciones mínimas ejecutadas

1. **Pérdida de registros / duplicados / integridad referencial real:** no aplica todavía — el
   EDW no tiene datos cargados en este momento (loaders ausentes del working tree). Ninguna
   verificación de volumen es posible sin una carga; **marcado explícitamente como pendiente**,
   no como "sin hallazgos".
2. **Grain declarado vs grain real:** revisado por diseño (no por datos) para las 11 facts;
   ninguna mezcla evidente de granularidades en el DDL salvo lo señalado en H10.
3. **FKs físicas e indexadas:** confirmado — las 11 facts declaran `REFERENCES` y
   `edw/04_indices.sql` cubre las columnas de join más usadas. Sin hallazgos adicionales.
4. **SCD2 — una sola fila vigente por llave de negocio:** no verificable con datos (no hay carga
   aún); el **diseño** no lo garantiza (ver H1). Marcado como riesgo de diseño, no de datos.

## Resumen de recomendaciones por prioridad

**Alta**
- H1: Añadir índice único parcial `es_vigente` en `Dim_Producto` y `Dim_Cliente`. — **Aplicado.**
- H2: Cerrado, no aplica (extractor de vendedores ya no trae `comision1`).
- H3: Ampliar `Fact_Ventas_Detalle.num_factura` a `VARCHAR(20)`. — **Aplicado.**
- H4: Resolver el destino de `Dim_Geografia`. — **Aplicado (tabla retirada del alcance).**
- H5: Agregar `cliente_sk`/`vendedor_sk` a `Fact_Movimientos_Inventario`. — **Aplicado.**
- H6: Seedear las filas centinela `-1` en el propio DDL de `edw/`. — **Aplicado.**

**Media**
- H7: `UNIQUE (codemp, codigo_sucursal)` en `Dim_Sucursal`. — **Aplicado.**
- H8: Documentar/asegurar el manejo de división por cero en `pct_margen`. — **Aplicado.**
- H10: Crear `Fact_Transferencias`. — **Aplicado.**

**Baja**
- H9: Junk dimension `Dim_Estado_Documento` para flags de `Fact_Ventas_Detalle`. — **Aplicado.**

Ninguna de estas recomendaciones tocó `etl/extractors/`, `etl/transformers/` ni el orchestrator;
todos los cambios se hicieron sobre `edw/*.sql` (DDL). Todos los hallazgos (H1–H10) están
cerrados: H1, H3, H4, H5, H6, H7, H8, H9, H10 con cambios aplicados en el DDL; H2 cerrado sin
acción por cambio previo en el extractor.
