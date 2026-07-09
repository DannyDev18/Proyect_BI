# Auditoría 10 — Cálculo de subtotales/IVA/margen en Fact_Ventas_Detalle

- **Fecha:** 2026-07-09
- **Alcance:** `etl/extractors/facturas_detalle_extractor.sql`, `etl/transformers/fact_transformer.py::transformar_ventas_detalle`, tablas SAP `renglonesfacturas`, `encabezadofacturas`, `iva`.
- **Método:** SELECT de solo lectura contra Producción (vía `tsql`/FreeTDS, sin escrituras), revisión estática del extractor y el transformer. Contexto: primera carga real de `fact_ventas_detalle` desde que se corrigió el cuelgue de conexión SAP (ver commit del fix de `sqlany_connector.py`); nunca se había ejecutado de punta a punta contra datos reales.

## Hallazgos

### Alta — H1: `transformar_ventas_detalle` esperaba columnas que el extractor nunca produce
- **Evidencia:** `etl/transformers/fact_transformer.py:24-29` referencia `df['subtotal_neto']`, pero `facturas_detalle_extractor.sql` no selecciona esa columna (ni `subtotal_bruto`, `valor_iva`, `total_linea`, `costo_total`, `margen_bruto`). Falla con `KeyError: 'subtotal_neto'` en la primera corrida real (log `etl_run5.log`, 2026-07-09 16:45:38).
- **Impacto:** `fact_ventas_detalle` (tabla principal, ~539k filas esperadas) no puede cargar en absoluto.
- **Causa raíz:** el transformer nunca se había ejecutado contra datos reales (el pipeline se colgaba antes por el bug de conexión SAP corregido en el mismo día), así que este desajuste extractor↔transformer nunca se detectó.

### Alta — H2: `encabezadofacturas.poriva` no es un porcentaje, es (probablemente) un código de tarifa
- **Evidencia:**
  - `SELECT * FROM renglonesfacturas WHERE 1=0` confirma que existe `r.porceiva` (nivel línea).
  - Muestra real de 15 líneas (`renglonesfacturas` join `encabezadofacturas`, `codemp='01'`, `estado='P'`): `r.porceiva = 0.15` en el 100% de las filas muestreadas — coincide con el patrón de una tasa vigente única (IVA Ecuador 15%).
  - Tabla `iva` (catálogo `codiva → poriva`): `codiva=3 → poriva=15.00`. La muestra de `encabezadofacturas` mostró `poriva=1` en el encabezado — no coincide con ningún `poriva` real de la tabla `iva` (que va de 0 a 99, pero como *porcentaje*, no como código plano de 1 dígito salvo por coincidencia con `codiva`); es consistente con que `encabezadofacturas.poriva` almacene el `codiva` (FK), no la tasa.
  - **Pendiente de validar de forma concluyente:** no se confirmó con un `JOIN` directo `encabezadofacturas.poriva = iva.codiva` sobre una muestra grande porque se priorizó no demorar más la carga; se marca aquí como hallazgo de alta confianza pero no 100% confirmado.
- **Impacto:** el extractor actual usa `e.poriva` (posible código, no tasa) para calcular IVA — de haberse usado tal cual, el IVA y por tanto `total_linea`/`margen_bruto` habrían quedado mal calculados en silencio (p.ej. `poriva=1` interpretado como 1% en vez de resolver a 12-15% real).
- **Recomendación:** usar `r.porceiva` (ya resuelto como fracción decimal a nivel de línea) para el cálculo de IVA, no `e.poriva`. No requiere JOIN a la tabla `iva`.

### Media — H3: `desren` es un porcentaje de descuento, no un valor absoluto
- **Evidencia:** en la misma muestra de 15 líneas, `cantid * preuni * (1 - desren/100) ≈ totext ≈ totren` en el 100% de los casos (diferencias solo por redondeo a 2 decimales). Ejemplo: `preuni=122.67, cantid=1, desren=30.24 → 122.67*(1-0.3024)=85.57`, que coincide exactamente con `totext=85.57` y `totren=85.570000`.
- **Impacto:** de haberse tratado `desren` como valor absoluto en dólares (interpretación más intuitiva del nombre "valor_descuento"), el cálculo de `subtotal_bruto`/`valor_descuento` habría quedado mal.
- **Recomendación:** `valor_descuento` (dólares) se deriva como `subtotal_bruto - totren`, no se usa `desren` directamente como monto.

### Media — H4: `costo_total` y `margen_bruto` no existen como columnas en SAP
- **Evidencia:** columnas completas de `renglonesfacturas` (dump `SELECT * WHERE 1=0`) no incluyen costo ni margen a nivel de línea; solo `articulos.ultcos` (costo unitario del artículo, ya extraído como `a.ultcos`) permite derivar el costo de línea.
- **Impacto:** ninguno — es esperado que un ERP transaccional no almacene margen (es una métrica analítica). Se documenta para que quede explícito que `costo_total`/`margen_bruto` son cálculos DW, no un "dato ya calculado en la BD origen" como podría asumirse.
- **Recomendación:** `costo_total = cantid * ultcos`, `margen_bruto = subtotal_neto - costo_total` (fórmula ya presente en el DDL como comentario, `edw/03_hechos.sql:30-32`, y ya implementada correctamente en `transformar_ventas_detalle` para `pct_margen`).

## Fórmula validada a aplicar (evidencia: muestra real de 15 filas, `codemp='01'`, `estado='P'`)

```
subtotal_bruto  = cantid * preuni
valor_descuento = subtotal_bruto - totren
subtotal_neto   = totren                          -- ya calculado en SAP, no se deriva
valor_iva       = subtotal_neto * porceiva         -- porceiva de renglonesfacturas (línea), NO e.poriva (encabezado)
total_linea     = subtotal_neto + valor_iva
costo_unitario  = ultcos                           -- ya extraído (articulos.ultcos)
costo_total     = cantid * ultcos
margen_bruto    = subtotal_neto - costo_total
pct_margen      = margen_bruto / subtotal_neto * 100 si subtotal_neto != 0, si no 0.0  -- ya implementado
```

### Media — H5: `renglonesfacturas.porceiva` no está poblado para facturas anteriores a 2024
- **Evidencia:** tras la carga completa (520,760 filas), `valor_iva > 0` en 0-2 filas/año entre 2018-2023, y en 47k-79k filas/año (~99%+ de cobertura) desde 2024. Consistente con que `porceiva` sea una columna agregada al esquema de `renglonesfacturas` en algún punto de 2024, sin backfill retroactivo.
- **Impacto:** `valor_iva`/`total_linea` están subestimados (sin IVA) para ventas 2018-2023 en el EDW — afecta análisis financieros que agreguen `total_linea` en ese rango histórico.
- **Recomendación:** no se asume una tasa histórica (sin evidencia de cuál aplicaba línea a línea en ese rango). Marcar como **pendiente de validar**: confirmar con el área contable si existe una tasa histórica única aplicable, y si corresponde, correr un backfill dirigido solo a ese rango de fechas.

### Alta — H6: `fact_pagos_cxp`, `fact_devoluciones`, `fact_movimientos_caja` — mismo patrón de alias/columna faltante que H1/H2
- **`fact_pagos_cxp`:** `pagos_cxp_extractor.sql` renombra `fecemi AS fecha_emision`; `resolver_llaves_hecho()` busca el nombre crudo `fecemi` en una lista fija para resolver `fecha_sk`. Sin ese nombre exacto, `fecha_sk` nunca resuelve → `NOT NULL` viola. Fix: `transformar_pagos_cxp` expone también `df['fecemi'] = df['fecha_emision']`.
- **`fact_devoluciones`:** `encabezadodevoluciones.codcli` existe en SAP (confirmado con `SELECT * WHERE 1=0`) pero `devoluciones_detalle_extractor.sql` no lo seleccionaba; `Fact_Devoluciones.cliente_sk` es `NOT NULL`. Fix: agregar `e.codcli` al extractor.
- **`fact_movimientos_caja`:** el extractor usaba `tipoorg` (columna inexistente — error SAP `-143 Column 'tipoorg' not found`); la columna real es `tiporg`. Además no seleccionaba `establ`, así que `sucursal_sk` caía siempre al centinela `-1` en vez de resolver la sucursal real. Fix: corregir el nombre y agregar `establ`.
- **Impacto:** las 3 tablas no podían cargar en absoluto antes de este fix.
- **Método de detección:** ejecución real contra Producción (primera vez que estas tablas corrían de punta a punta, igual que H1/H2) + `SELECT * FROM <tabla> WHERE 1=0` contra SAP para confirmar nombres reales de columna.

### Media — H7: `fact_transferencias` nunca se conectó a `PIPELINE_CONFIG`
- **Evidencia:** `transferencias_extractor.sql` ya traía un comentario propio indicando que estaba "validado y listo para conectarse a PIPELINE_CONFIG"; la tabla `edw.Fact_Transferencias` existe en el DDL desde antes de esta sesión, pero no había `transformar_transferencias()` ni entrada en `PIPELINE_CONFIG` — quedaba en 0 filas permanentemente, sin generar ningún error (por eso no apareció en los logs de las corridas anteriores).
- **Detalle técnico:** esta tabla resuelve **dos** llaves foráneas hacia `dim_almacen` (`almacen_origen_sk`, `almacen_destino_sk`), algo que `resolver_llaves_hecho()` no soportaba (solo resolvía una columna genérica `codalm`). Se agregó un bloque de resolución dual específico.
- **Resultado tras el fix:** 165,480 filas cargadas, 0 huérfanas en ningún FK (`almacen_origen_sk`, `almacen_destino_sk`, `sucursal_sk`, `producto_sk`).

## Resumen de recomendaciones por prioridad

- **Alta (H1):** implementar el cálculo faltante en `transformar_ventas_detalle` usando las columnas ya extraídas + `r.porceiva` (nueva).
- **Alta (H2):** agregar `r.porceiva` al `SELECT` de `facturas_detalle_extractor.sql` (cambio mínimo, una columna) y dejar de usar `e.poriva` para el cálculo de IVA.
- **Media (H3, H4):** ya cubiertas por la fórmula validada arriba; sin acción adicional.
- **Pendiente de validar:** confirmar con un `JOIN` masivo `encabezadofacturas.poriva = iva.codiva` que efectivamente es una FK (H2), en una auditoría posterior sin presión de tiempo de carga.
