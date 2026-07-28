# Auditoría 39 — Madurez BI y soporte a la toma de decisiones (Fase 0)

- **Fecha:** 2026-07-27
- **Alcance:** validación previa a la implementación de `docs/features/plan_madurez_bi_toma_decisiones.md`.
  Objetos revisados: `backend/app/services/analytics_service.py`,
  `backend/app/repositories/analytics_repository.py`, `etl/extractors/facturas_detalle_extractor.sql`,
  `etl/transformers/fact_transformer.py`, y las tablas `edw.fact_ventas_detalle`,
  `edw.fact_devoluciones`, `edw.dim_producto`, `edw.dim_estado_documento`, `edw.dim_fecha`,
  `edw.fact_cobros_cxc`, `edw.fact_pagos_cxp`, `edw.fact_movimientos_caja`,
  `edw.fact_inventario_snapshot`, `edw.fact_metas_comerciales`, `edw.etl_control`.
- **Método:** revisión estática del código y consultas `SELECT` contra el EDW PostgreSQL
  (`docker exec bi_postgres_edw psql -U etl_user -d edw`). **No se ejecutó ninguna escritura**
  sobre el EDW ni ninguna consulta contra Producción (SAP) — la conectividad al ERP no estaba
  disponible en esta sesión, lo que deja marcados como *Pendiente de validar* los puntos que
  requieren contrastar contra `articulos`/`renglonesfacturas` en origen.
- **Decisiones de negocio recibidas del usuario antes de auditar:** G-01 se resuelve por la
  opción 2 del plan (sustituir `roi_estimado` por un ROI real definido sobre el EDW); G-05
  (alcance financiero CxC/CxP/caja) queda **sin decidir** y por lo tanto fuera del alcance de
  implementación, solo documentado aquí.

---

## Hallazgos

### CRÍTICO — H-01 · El costo de mercadería del EDW está dominado en un 94,9% por un solo artículo con unidad de medida incompatible

Este hallazgo **no estaba en el plan** y aparece al intentar construir el "ROI real" que pide
G-01. Es más grave que G-01 mismo: el KPI que G-01 quería reemplazar es falso, pero el KPI
`margen_utilidad_neta` que se daba por bueno **también lo es**.

**Evidencia 1 — el KPI de margen que hoy se publica en Gerencia:**

reproduciendo exactamente el SQL de `AnalyticsRepository.get_management_kpis`
(`backend/app/repositories/analytics_repository.py:30-64`) sin filtros de UI:

```sql
WITH ventas_agg AS (
  SELECT SUM(CASE WHEN f.subtotal_neto>0 THEN f.subtotal_neto ELSE 0 END) net_sales,
         SUM(CASE WHEN f.subtotal_neto>0 THEN f.costo_total ELSE 0 END) net_cost
  FROM edw.fact_ventas_detalle f
  JOIN edw.dim_estado_documento ed ON f.estado_documento_sk=ed.estado_documento_sk
  WHERE ed.estado_documento_sk <> -1),
dev AS (SELECT COALESCE(SUM(total_linea_devolucion),0) devol FROM edw.fact_devoluciones)
SELECT ROUND((net_sales-devol)::numeric,0) venta_neta,
       ROUND(net_cost::numeric,0) costo,
       ROUND((((net_sales-devol)-net_cost)/(net_sales-devol)*100)::numeric,2) margen_pct
FROM ventas_agg CROSS JOIN dev;
```

| venta_neta | costo | margen_pct |
|---|---|---|
| 26.701.901 | 444.098.311 | **−1.563,17** |

El costo de mercadería es **16,6× la venta neta**. La tarjeta "Margen de Utilidad" del dashboard
de Gerencia muestra hoy un margen de −1.563%.

**Evidencia 2 — concentración del costo:**

```sql
SELECT SUM(costo_total) costo_total_global,
  SUM(costo_total) FILTER (WHERE costo_unitario>precio_unitario) AS costo_lineas_desajustadas,
  ROUND(100.0*SUM(costo_total) FILTER (WHERE costo_unitario>precio_unitario)/SUM(costo_total),2) pct
FROM edw.fact_ventas_detalle WHERE subtotal_neto>0 AND costo_unitario IS NOT NULL;
```

| costo_total_global | costo_lineas_desajustadas | pct |
|---|---|---|
| 444.098.311 | 421.463.662 | **94,90** |

Solo 2.667 líneas (**0,58%** de 458.407) tienen `costo_unitario > precio_unitario`, pero
concentran el 94,9% del costo agregado.

**Evidencia 3 — el causante es un único artículo:**

```sql
SELECT p.codart, LEFT(p.nombre_articulo,32) articulo, p.unidad, p.clase,
  COUNT(*) lineas, ROUND(AVG(f.precio_unitario),4) precio_prom,
  ROUND(AVG(f.costo_unitario),2) costo_prom,
  ROUND(AVG(f.costo_unitario/NULLIF(f.precio_unitario,0)),0) ratio,
  ROUND(SUM(f.costo_total)::numeric,0) costo_acum
FROM edw.fact_ventas_detalle f JOIN edw.dim_producto p ON f.producto_sk=p.producto_sk
WHERE f.subtotal_neto>0 AND f.costo_unitario>f.precio_unitario AND f.precio_unitario>0
GROUP BY 1,2,3,4 ORDER BY costo_acum DESC LIMIT 5;
```

| codart | articulo | unidad | clase | lineas | precio_prom | costo_prom | ratio | costo_acum |
|---|---|---|---|---|---|---|---|---|
| **Z-9001** | BATERIAS CHATARRAS | **KL** | **Z-999** | 95 | 0,7538 | 230,92 | **308** | **421.432.117** |
| 0 250 202 065 | DS BUJIA BOSCH INCANDESCENTE | UND | REP | 69 | 19,999 | 22,28 | 1 | 6.504 |
| FIX 7677 | MULTIMETRO BOSCH PROFESSIONAL | UNI | EQU | 84 | 32,648 | 45,69 | 1 | 4.478 |
| 0 684 400 590 | KTS 590 SCANNER AUTOMOTRIZ | UNI | EQU | 1 | 4232,51 | 4392,00 | 1 | 4.392 |
| 0 242 236 577 | BUJIA BOSCH FR7NI332S | UND | REP | 52 | 4,2306 | 7,90 | 2 | 2.108 |

`Z-9001` solo aporta **421,4M de 444,1M** (94,9%). Los otros 81 artículos tienen ratio 1-2×, que
es venta ocasional a/bajo costo — comportamiento comercial normal, **no** un defecto de datos.

**Mecanismo (causa raíz).** `etl/transformers/fact_transformer.py:47-50` deriva el costo así:

```python
costo_unitario_bruto = pd.to_numeric(df.get('ultcos'), errors='coerce')
df['costo_unitario'] = costo_unitario_bruto.where(aplica_costo)
df['costo_total'] = (df['cantidad'] * costo_unitario_bruto).where(aplica_costo)
df['margen_bruto'] = np.where(aplica_costo, df['subtotal_neto'] - df['costo_total'], np.nan)
```

El propio comentario del transformer (líneas 29-30) ya declara la limitación: *"costo_total/
margen_bruto no existen en SAP a nivel de línea (`ultcos` es por artículo); se derivan aquí"*.
La aritmética es correcta (`costo_total = cantidad × costo_unitario` coincide en 463.116/463.116
filas verificadas), pero multiplica un costo expresado en **una unidad de medida** por una
cantidad expresada en **otra**. `Z-9001` es chatarra de baterías: se **compra por batería** y se
**vende por kilo** (`dim_producto.unidad = 'KL'`). `articulos.ultcos = 230,92` no es comparable
con un precio de venta de $0,75/kg; de ahí el ratio de 308×.

*Pendiente de validar contra Producción:* confirmar con `SELECT` sobre `articulos` que `ultcos`
de `Z-9001` está en unidad de compra y no es simplemente un dato erróneo del maestro. La
corrección difiere según el caso (factor de conversión vs. exclusión).

**Evidencia 4 — el margen real, aislando la clase de chatarra:**

```sql
-- (consulta completa con CTE `base` filtrando ed.estado_documento_sk<>-1 y subtotal_neto>0)
SELECT ... FROM base WHERE clase IS DISTINCT FROM 'Z-999';
```

| escenario | venta_neta | costo | margen_pct | roi_real_pct |
|---|---|---|---|---|
| CON Z-999 (lo que muestra hoy el dashboard) | 26.701.901 | 444.098.311 | −1.563,17 | −93,99 |
| **SIN clase Z-999 (chatarra)** | 24.950.469 | 22.557.666 | **9,59** | **10,61** |

Excluida la chatarra, el margen es **9,59%** y el retorno sobre costo de mercadería vendida
**10,61%** — ambos plausibles para un distribuidor de repuestos automotrices, y ambos calculables
íntegramente desde el EDW.

**Impacto.**

1. **Gerencia:** `margen_utilidad_neta` (−1.563% en vez de ~9,6%) y, por derivación,
   `roi_estimado` y las cuatro tendencias `*_tendencia_pct` del mismo endpoint.
2. **Comisiones Variables (regla 13, dinero real):** el esquema comisiona sobre `margen_bruto`
   de la línea. Exposición medida:

   ```sql
   SELECT v.nombre_vendedor, d.anio, COUNT(*) lineas,
     ROUND(SUM(f.subtotal_neto)::numeric,2) venta,
     ROUND(SUM(f.margen_bruto)::numeric,0) margen_bruto_acum
   FROM edw.fact_ventas_detalle f
   JOIN edw.dim_producto p ON f.producto_sk=p.producto_sk
   JOIN edw.dim_vendedor v ON f.vendedor_sk=v.vendedor_sk
   JOIN edw.dim_fecha d ON f.fecha_sk=d.fecha_sk
   WHERE p.clase='Z-999' AND d.anio>=2025 GROUP BY 1,2 ORDER BY 2 DESC;
   ```

   | nombre_vendedor | anio | lineas | venta | margen_bruto_acum |
   |---|---|---|---|---|
   | ALMACEN ATAHUALPA | 2026 | 8 | 137.583,20 | **−44.165.573** |
   | ALMACEN ATAHUALPA | 2025 | 16 | 221.938,33 | **−70.782.336** |

   24 líneas arrastran **−$115 millones** de margen sobre un solo código de vendedor. Con
   `COMISION_MODO=plana` (default actual) no se paga sobre margen, así que **no hay pago
   incorrecto hoy**; pero el panel `POST /commission-simulation` — el argumento con el que
   Gerencia decide si activar el esquema variable — sí consume `margen_bruto` y quedaría
   envenenado por esas 24 líneas.
3. **`pct_margen` saturado:** 11.916 líneas quedan en el tope `-9999.9999` del `clip` de
   `fact_transformer.py:90`, perdiendo información.

**Riesgos.**

- *De no corregir:* el primer KPI que un gerente mira es un −1.563%; se pierde la credibilidad
  de todo el tablero (exactamente el argumento del §0 del plan). Y si en algún momento se activa
  `COMISION_MODO=variable` sin corregir esto, se paga sobre un margen falso.
- *De corregir mal:* excluir la clase `Z-999` en el backend es un filtro de presentación que
  arregla los KPIs pero **no** arregla `margen_bruto` a nivel de línea, que es lo que consume
  Comisiones Variables. Corregir solo en el ETL requiere una re-carga histórica. Las dos capas
  necesitan tratamiento, y con criterios distintos.

**Recomendación.** Tres acciones, en este orden:

1. **Inmediata (backend, sin re-carga):** excluir la clase de chatarra de los KPIs de margen/ROI
   de Gerencia mediante un umbral configurable por env var (patrón `BODEGA_*`/`NOTIF_*`), p. ej.
   `ANALYTICS_CLASES_EXCLUIDAS_MARGEN=Z-999`. **Precedente ya establecido en el proyecto:** el
   pipeline ML de demanda ya excluye `Z-999` con esta misma justificación de negocio
   ("chatarra, no es un artículo de reposición", Fase 2 de `plan_mejora_pipeline_ml.md`) — se
   trata de aplicar en analytics un criterio ya validado y en producción en otro módulo.
2. **Estructural (ETL):** que `fact_transformer.build_fact_ventas_detalle` no derive
   `costo_total` cuando la unidad del artículo es incompatible con la unidad de venta, dejando
   `NULL` (la ruta ya soportada — `permitir_nulos`, salvaguarda 2 de comisiones) en vez de un
   número falso. Requiere validar antes contra Producción qué campo de `articulos` expresa la
   unidad de `ultcos`.
3. **Guardia:** test que falle si el margen agregado del EDW cae fuera de un rango plausible
   (p. ej. −50%..+90%), para que un caso así no vuelva a pasar inadvertido.

---

### CRÍTICO — H-02 · `roi_estimado` es un porcentaje multiplicado por una constante (G-01 confirmado)

**Evidencia:** `backend/app/services/analytics_service.py:42`

```python
roi_estimado = round(data["margen"] * 1.15, 2)  # Simulación adaptada de ROI de campaña
```

`data["margen"]` proviene de `margen_promedio` (`analytics_repository.py:58-61`), que **ya es un
porcentaje**. El KPI publicado como "Proyección ROI" es, literalmente, un porcentaje de margen
multiplicado por 1,15. Además `analytics_service.py:66` calcula `roi_prev` con la misma constante
para producir `roi_estimado_tendencia_pct` — es decir, se calcula la variación porcentual de una
constante por el margen, que matemáticamente **es idéntica a la variación del margen**.

**Impacto:** el valor se publica en `GPKPIGerencia.roi_estimado`, se pinta con semáforo
positivo/negativo y se incluye en el resumen ejecutivo del reporte Excel de Gerencia
(`analytics_service.py:127`, umbral mágico adicional `>= 10`).

**Recomendación (decisión de negocio ya tomada — opción 2 del plan):** sustituir por el **ROI
real** validado en H-01 evidencia 4:

> **Retorno sobre costo de mercadería vendida** =
> `(venta_neta − costo_mercaderia_vendida) / costo_mercaderia_vendida × 100`

Con el universo saneado (H-01 recomendación 1) da **10,61%** en el histórico completo. Se
documenta como regla de negocio nueva en `docs/auditoria/02_reglas_negocio_validadas.md`.
Depende de H-01: calcularlo sobre el costo actual daría −93,99%.

---

### ALTO — H-03 · `dim_geografia` no existe (el plan y la auditoría 05 la daban por "vacía")

**Evidencia:**

```sql
SELECT COUNT(*) FROM edw.dim_geografia;
-- ERROR:  relation "edw.dim_geografia" does not exist
```

`\dt edw.*` devuelve **24 tablas**: 10 dimensiones (no 11) y 13 hechos. `dim_geografia` no está
creada, pese a que `etl/extractors/geografia_extractor.sql` existe.

**Impacto:** G-12 del plan describe el análisis territorial como "trabajo de ETL sobre una
dimensión vacía"; en realidad requiere además el DDL. Corrige el inventario declarado en
`CLAUDE.md` ("Dimensiones (11)") y en la auditoría 05.

**Observación adicional:** existe `edw.fact_transferencias`, que no figura en la lista de 11
hechos de `CLAUDE.md`.

**Recomendación:** actualizar el inventario de objetos en `CLAUDE.md` y tratar G-12 (geografía)
como trabajo de DDL + ETL, no solo de carga.

---

### MEDIA — H-04 · Verificación de los supuestos del plan sobre hechos financieros y huecos dimensionales

Ejecutado sin hallazgos contradictorios; se reporta porque la ausencia de problemas también es
evidencia (G-05 y G-12 del plan).

```sql
SELECT 'fact_cobros_cxc' t, COUNT(*) n, MIN(d.fecha_completa)::text, MAX(d.fecha_completa)::text
FROM edw.fact_cobros_cxc f JOIN edw.dim_fecha d ON f.fecha_sk=d.fecha_sk
UNION ALL ... ;
```

| tabla | filas | desde | hasta | comentario |
|---|---|---|---|---|
| `fact_cobros_cxc` | 212.686 | 2013-01-16 | 2026-07-16 | Cargada y con histórico profundo. Sin consumidores (G-05 confirmado). |
| `fact_pagos_cxp` | 113.972 | 2016-02-24 | 2026-07-16 | Íd. La corrección de duplicación 6× de la auditoría 31 sigue aplicada. |
| `fact_movimientos_caja` | 254.236 | 2018-01-02 | 2026-07-16 | Íd. |
| `fact_inventario_snapshot` | 456.372 | **2026-07-10** | 2026-07-16 | Confirma el hueco: **7 días** de histórico, no "<1% pre-2026". |
| `fact_metas_comerciales` | 0 | — | — | Vacía, confirmado. |
| `dim_fecha.es_feriado = true` | 0 | — | — | Nunca poblado, confirmado. |

**Conclusión para G-05:** el dato financiero está cargado, es profundo y está limpio. La brecha
es exclusivamente de capa de presentación, tal como afirma el plan. **Sin acción en esta sesión**
por decisión del usuario (la razón del retiro del módulo sigue sin definirse).

**Conclusión para G-12:** `fact_inventario_snapshot` es más limitada de lo documentado — con 7
días no hay ninguna posibilidad de rotación histórica ni de evolución de inventario, lo que
descarta de raíz el escenario "retorno sobre inventario promedio" como definición alternativa de
ROI para H-02.

---

### MEDIA — H-05 · El filtro de estado de documento no aplica la regla 1 por su semántica

**Evidencia:** `analytics_repository.py:256` — el único filtro base es
`ed.estado_documento_sk <> -1`, un filtro sobre la **surrogate key centinela**, no sobre el
estado de negocio.

```sql
SELECT * FROM edw.dim_estado_documento;
```

| estado_documento_sk | tipo_documento | es_devolucion | estado_factura |
|---|---|---|---|
| −1 | −1 | f | **A** |
| 1 | F | f | **P** |

**Impacto:** hoy el resultado es **correcto por coincidencia** — solo existen dos filas y la
centinela es justamente la única con `estado_factura='A'`, así que excluir la centinela equivale
a aplicar la regla 1 (`estado='P'`). Pero es una equivalencia frágil: en cuanto el ETL cargue un
estado adicional, el filtro dejará de significar lo que su comentario supone, en silencio.

**Riesgo:** clásico de deriva. No produce datos incorrectos hoy; los producirá sin aviso ante un
cambio de catálogo.

**Recomendación:** filtrar explícitamente por `ed.estado_factura = 'P'` (regla 1,
parametrizada), conservando la exclusión de la centinela. Encaja de forma natural en el punto
único de cálculo que propone G-02.

---

### MEDIA — H-06 · Frescura del dato: última carga ETL hace 11 días (G-08 confirmado)

**Evidencia:**

```sql
SELECT tabla_destino, ultimo_etl_ok, registros_carg, estado FROM edw.etl_control ORDER BY id DESC LIMIT 8;
```

Las 8 cargas más recientes son todas `SUCCESS`, todas con fecha **2026-07-16 16:20**, modo
incremental desde 2026-07-14. A la fecha de esta auditoría (2026-07-27) el EDW acumula
**11 días de desfase** y ninguna pantalla lo comunica.

**Impacto:** confirma G-08 con evidencia concreta y cuantificada. Todo KPI mostrado hoy describe
un negocio de hace once días sin decirlo.

**Recomendación:** la del plan (sello de frescura visible por dominio + alerta de carga atrasada
al rol administrador reutilizando el módulo de notificaciones). `edw.etl_control` ya tiene todo
lo necesario; no requiere ETL nuevo.

---

## Verificaciones automáticas mínimas

| # | Verificación | Resultado |
|---|---|---|
| 1 | Pérdida de registros origen vs destino | **No ejecutable** — sin conectividad a SAP en esta sesión. *Pendiente de validar.* |
| 2 | Duplicados por llave de negocio | Sin hallazgos nuevos en `fact_ventas_detalle`; la duplicación 6× de `fact_pagos_cxp` (auditoría 31) sigue corregida (H-04). |
| 3 | Cambios de volumen entre cargas | `edw.etl_control`: 8 últimas cargas `SUCCESS`, volúmenes incrementales coherentes (21-740 filas). Ver H-06 por el desfase. |
| 4 | Cambios de granularidad | `costo_total = cantidad × costo_unitario` en 463.116/463.116 filas — grano de línea intacto. Sin hallazgos. |
| 5 | Llaves huérfanas / centinela | `dim_estado_documento`: 2 filas, una centinela. Ver H-05. Resto sin medir (*pendiente*). |
| 6 | Fechas fuera de rango | Máximos coherentes con la última carga (2026-07-16) en los 4 hechos revisados. Sin hallazgos. |
| 7 | Códigos inexistentes | Sin hallazgos en el recorte revisado. |
| 8 | Integridad dimensiones↔hechos (SCD2) | No re-ejecutado; fuera del alcance de esta fase. *Pendiente de validar.* |

---

## Resumen de recomendaciones por prioridad

| Prioridad | ID | Acción | Estado |
|---|---|---|---|
| **Alta** | H-01 | Excluir clase de chatarra de los KPIs de margen/ROI por env var; dejar `costo_total` en NULL en el ETL cuando la unidad es incompatible; test de guardia de margen plausible | **Requiere decisión** (ver abajo) |
| **Alta** | H-02 | Sustituir `roi_estimado` por retorno sobre costo de mercadería vendida; retirar la constante 1,15 y el umbral mágico `>= 10` | Bloqueado por H-01 |
| **Alta** | H-03 | Crear DDL de `dim_geografia`; corregir el inventario de objetos de `CLAUDE.md` | Pendiente |
| Media | H-05 | Filtrar por `estado_factura='P'` explícito dentro del punto único de cálculo (G-02) | Pendiente |
| Media | H-06 | Sello de frescura visible + alerta de carga atrasada (G-08) | Pendiente |
| — | H-04 | Sin acción; evidencia de soporte para G-05 (diferido) y G-12 | Cerrado |

### Decisión requerida antes de codificar H-01/H-02

La corrección de H-01 tiene dos capas con criterios distintos (presentación vs. dato de línea) y
la elección cambia el alcance:

- **Solo backend (rápido, sin re-carga):** corrige los KPIs de Gerencia; deja `margen_bruto`
  falso a nivel de línea, y con él la simulación de Comisiones Variables.
- **Backend + ETL (correcto, requiere re-carga histórica de `fact_ventas_detalle`):** corrige
  ambas capas, pero necesita antes una validación `SELECT` contra `articulos` en Producción para
  determinar la unidad de `ultcos`, hoy no disponible.

---

## Alineación con el plan

| Brecha del plan | Estado tras esta auditoría |
|---|---|
| G-01 | Confirmada (H-02) y **agravada**: el KPI de reemplazo (`margen`) también estaba roto (H-01) |
| G-05 | Datos validados y limpios (H-04); diferido por decisión del usuario |
| G-08 | Confirmada con evidencia cuantificada: 11 días de desfase (H-06) |
| G-12 | Corregida al alza: `dim_geografia` no existe (H-03); `fact_inventario_snapshot` tiene 7 días, no "<1% pre-2026" (H-04) |
| G-02 | Insumo nuevo: la regla 1 no se aplica por semántica (H-05); debe resolverse en el punto único de cálculo |
| G-03, G-04, G-06, G-07, G-09, G-10, G-11 | Sin validación de datos requerida en esta fase |

---

## Estado de aplicación (actualizado 2026-07-27)

### Etapa 1 — Higiene de confianza · APLICADA

**H-01 (capa backend, aplicada).** Nueva `ANALYTICS_CLASES_EXCLUIDAS_MARGEN` (default
`Z-999`) en `backend/app/core/config.py`. `AnalyticsRepository.get_management_kpis` calcula
ahora dos universos: el completo para **ingresos** y el costeable para **margen/ROI**.
Validado extremo a extremo contra la API real (`GET /api/v1/analytics/gerencia/kpis`):

| KPI | Antes | Después |
|---|---|---|
| `margen_utilidad_neta` | **−1.563,17%** | **9,59%** |
| `roi_real` | (no existía) | **10,61%** |
| `ingresos_totales` | 26.701.900,87 | 26.701.900,87 *(sin cambio, correcto)* |
| `costo_mercaderia` | (no expuesto) | 22.557.666,14 |

Coincide exactamente con las consultas `SELECT` de la evidencia 4.

**H-01 (capa ETL, NO aplicada).** Requiere validar contra Producción la unidad de `ultcos`;
sin conectividad al ERP en esta sesión. `fact_ventas_detalle.margen_bruto` sigue con el valor
derivado y Comisiones Variables lo consume. Documentado en RN-BI1 y en el diccionario §2/§7.

**H-02 (aplicada).** `roi_estimado` retirado del contrato. `analytics_service.py` ya no
contiene la constante `1.15` ni el umbral literal `>= 10` (ahora
`ANALYTICS_ROI_UMBRAL_SANO`). Contrato nuevo: `roi_real` (nullable) + `costo_mercaderia`;
`roi_estimado_tendencia_pct` → `roi_real_tendencia_pct`. Propagado a
`backend/app/schemas/analytics.py`, `frontend/src/types/gerencia.ts` y
`frontend/src/pages/DashboardGerencia.tsx` (tarjeta renombrada a *"ROI sobre costo de
mercadería"*, con estado *"Sin base"* cuando el valor es `NULL`).

**Barrido de constantes mágicas (completado).** Además de H-02 se encontraron y
parametrizaron 3 literales más: `prediction_service.py` (`val * 0.15`),
`warehouse_service.py` (`valor * 0.2` y `reorden * 1.5`) →
`FORECAST_BANDA_FALLBACK_VENTAS_PCT`, `FORECAST_BANDA_FALLBACK_DEMANDA_PCT`,
`BODEGA_FACTOR_CERCA_REORDEN`. Las dos primeras son bandas de **respaldo** (solo se usan si
el `.meta.json` del modelo no trae MAE) y se documentan como supuestos de ingeniería, no como
reglas de negocio — diccionario §9.

**G-10 (ya estaba cerrado).** Verificado: `frontend/src/services/mocks/` **no existe** y
`DashboardAdmin.tsx` consume hooks reales (`useAuditLogs`, `useModelsStatus`,
`useSystemHealth`, `useAnomalyDetector`, `useAnomaliaRevisiones`). Barrido sin resultados de
`from.*mocks|MOCK_|AUDIT_ENTRIES|MODEL_STATUS|PROVENANCE_FACTS` en todo `frontend/src/`.
M-02 de `plan_mejoras_proyecto.md` y la mención de mocks en §Riesgos técnicos de `CLAUDE.md`
están **obsoletas**.

**Guardias nuevas** en `backend/tests/integration/test_gerencia_actualizacion.py`:
`test_margen_y_roi_estan_en_rango_plausible` (margen dentro de −50%..90%, ROI dentro de
−100%..500%, y costo de mercadería nunca mayor que los ingresos — el síntoma exacto de H-01)
y `test_roi_ya_no_es_el_margen_por_una_constante`.

**Falla preexistente corregida de paso:**
`tests/unit/test_analytics_service.py::test_get_management_kpis_propaga_filtros_al_repositorio`
usaba `assert_called_once_with`, pero con fechas explícitas el servicio consulta el
repositorio **dos** veces a propósito (período pedido + anterior, para `*_tendencia_pct`).
Verificado que ya fallaba antes de esta sesión (`git stash` + `pytest`).

### Etapa 2 — Una sola verdad (G-02) · APLICADA

**Hallazgo nuevo H-07 (divergencia latente de Venta Neta).** Los dos caminos principales
trataban distinto las líneas de importe negativo:

| Consumidor | Fragmento |
|---|---|
| Gerencia (`analytics_repository`) | `SUM(CASE WHEN subtotal_neto > 0 THEN subtotal_neto ELSE 0 END)` |
| Metas/Comisiones (`goal_repository`) | `SUM(subtotal_neto)` |

```sql
SELECT COUNT(*) FILTER (WHERE subtotal_neto<0) AS negativas, COUNT(*) AS total
FROM edw.fact_ventas_detalle f
JOIN edw.dim_estado_documento ed ON f.estado_documento_sk=ed.estado_documento_sk
WHERE ed.estado_documento_sk<>-1;
-- negativas=0, total=522477
```

**0 líneas negativas en 522.477**: la divergencia era **latente, no activa** — ambos caminos
daban hoy el mismo número. Se unificó igualmente, porque nada garantizaba que siguiera así y
`fact_transformer` declara como *"Pendiente de validar"* el supuesto de que una cantidad
negativa signifique devolución (auditoría 08, F13/F14).

**Aplicado:**

- Paquete nuevo `backend/app/services/metricas/` con `venta_neta.py` como definición canónica
  (`SQL_VENTA_BRUTA`, `SQL_DEVOLUCIONES_MONTO`, `FILTRO_ESTADO_VALIDO`, `definicion_venta_neta`).
- `AnalyticsRepository` y `GoalRepository` (`get_commission_report`,
  `get_vendor_net_sales_period`) ensamblan ese fragmento en vez de repetir la fórmula.
- `docs/diccionario_indicadores.md` (nuevo): 10 secciones, con los indicadores marcados
  ✅ *punto único* / ⚠ *sin punto único*, los indicadores retirados y la deuda abierta.
- **H-05 aplicado**: `FILTRO_ESTADO_VALIDO` explicita `estado_factura = 'P'` (regla 1) además
  de excluir la centinela, parametrizado con `ESTADO_DOCUMENTO_VALIDO`.
- Guardia nueva `backend/tests/integration/test_venta_neta_consistencia.py` (3 tests,
  criterio de aceptación de G-02: la venta neta de Gerencia y la de Metas/Comisiones coinciden
  para un `(anio, mes, vendedor)` real de la BD). Fixture `db_session` agregada al conftest
  de integración.

**Deuda declarada, no cerrada:** el cociente de Cumplimiento de Meta sigue replicado en 3
lugares, y ~15 consultas de `GoalRepository` conservan `estado_documento_sk <> -1` a secas
(equivalente hoy, frágil mañana). Ambas quedan listadas en el diccionario.

### Reglas de negocio documentadas

`docs/auditoria/02_reglas_negocio_validadas.md` §23: **RN-BI1** (universo costeable),
**RN-BI2** (ROI = retorno sobre costo de mercadería vendida), **RN-BI3** (regla 1 aplicada
por su semántica).
