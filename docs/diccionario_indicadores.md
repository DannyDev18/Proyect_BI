# Diccionario de Indicadores

> **Propósito:** fuente única de verdad de *qué significa* cada métrica de la plataforma —
> fórmula, tablas y columnas del EDW, filtros obligatorios, grano, dueño y pantallas que la
> consumen. Cierra G-02 de `docs/features/plan_madurez_bi_toma_decisiones.md`
> (*"la misma métrica se define en 7 lugares"*).
> **Creado:** 2026-07-27 · **Auditoría de respaldo:** `docs/auditoria/39_madurez_bi_toma_decisiones.md`
> **Reglas de negocio:** `docs/auditoria/02_reglas_negocio_validadas.md`

## Cómo usar este documento

1. **Antes de crear un KPI nuevo**, buscar aquí si la métrica ya existe. Si existe, se
   consume su punto único de cálculo; no se reimplementa.
2. **Antes de cambiar una fórmula**, actualizar primero esta tabla y la regla de negocio
   correspondiente; el código va después.
3. Los indicadores marcados **⚠ sin punto único** todavía se calculan en más de un lugar.
   Son deuda conocida, listada explícitamente para que no se olvide.

### Filtros obligatorios (aplican salvo que se indique lo contrario)

| # | Regla | Implementación |
|---|---|---|
| 1 | `estado_factura = 'P'` (Procesada); `'A'` es anulada | `FILTRO_ESTADO_VALIDO`, parametrizado con `ESTADO_DOCUMENTO_VALIDO` |
| 2 | `codemp = '01'` | Aplicado en el ETL (token `{CODEMP}`), no re-filtrado en el backend |
| 12 | Excluir la fila centinela `-1` de toda dimensión | `FILTRO_ESTADO_VALIDO` y equivalentes por dimensión |

---

## 1. Venta Neta ✅ punto único

| Campo | Valor |
|---|---|
| **Nombre de negocio** | Venta Neta |
| **Fórmula** | `SUM(subtotal_neto WHERE subtotal_neto > 0) − SUM(total_linea_devolucion)` |
| **Fuente** | `edw.fact_ventas_detalle` + `edw.fact_devoluciones` |
| **Grano** | Línea de factura; agregable a vendedor / sucursal / categoría / período |
| **Filtros obligatorios** | Reglas 1 y 12 |
| **Punto único** | `backend/app/services/metricas/venta_neta.py` (`SQL_VENTA_BRUTA`, `FILTRO_ESTADO_VALIDO`) |
| **Consumidores** | KPIs de Gerencia (`ingresos_totales`), Metas, Comisiones plana y variable, Cumplimiento, panel del vendedor |
| **Guardia** | `backend/tests/integration/test_venta_neta_consistencia.py` |
| **Regla de negocio** | 13 (grano vendedor), RN-G2, RN-BI3 |

**Precisiones que evitan errores frecuentes:**

- `subtotal_neto` **ya viene post-descuento**. SAP lo calcula en `renglonesfacturas.totren` y
  el ETL lo copia tal cual (auditoría 10). No volver a restar `valor_descuento`.
- **No** se filtra por `desinv` ni `es_linea_servicio`: la regla 5 condiciona el **costo** de
  inventario, no el ingreso. Una línea de servicio es venta real.
- **No** se excluye ninguna clase de producto (ver §2: la exclusión aplica solo a margen/ROI).
- Las devoluciones se restan **completas**: `fact_devoluciones` no tiene grano de clase de
  producto, así que no son atribuibles a una categoría.
- Solo se suman líneas de importe **positivo**. Medición sobre el EDW: **0 líneas negativas en
  522.477** del histórico, así que hoy es indistinto; se conserva como defensa porque
  `fact_transformer` declara *"Pendiente de validar"* el supuesto de que una cantidad negativa
  signifique devolución (auditoría 08, F13/F14) — si entraran, se contarían dos veces.

---

## 2. Universo costeable (margen y ROI) ✅ punto único

| Campo | Valor |
|---|---|
| **Definición** | Venta Neta **excluyendo** las clases de `ANALYTICS_CLASES_EXCLUIDAS_MARGEN` (default `Z-999`) |
| **Por qué existe** | El costo de línea se deriva como `cantidad × articulos.ultcos`, con `ultcos` en unidad de **compra** y `cantidad` en unidad de **venta**. Cuando difieren, el costo no tiene sentido económico. |
| **Caso confirmado** | `Z-9001` (BATERIAS CHATARRAS, unidad `KL`): se compra por batería, se vende por kilo. Ratio costo/precio **308×**; sus 95 líneas concentran el **94,9%** del costo de mercadería de todo el EDW. |
| **Punto único** | `ANALYTICS_CLASES_EXCLUIDAS_MARGEN` en `backend/app/core/config.py`, aplicado en `AnalyticsRepository` |
| **Regla de negocio** | RN-BI1 |

**Este universo NO aplica a los ingresos.** Vender chatarra es ingreso real; lo que no es real
es su costo derivado. Por eso `ingresos_totales` usa el universo completo (§1) y
`margen_utilidad_neta`/`roi_real` usan el costeable.

**Deuda abierta:** `fact_ventas_detalle.margen_bruto` conserva el valor derivado a nivel de
línea, y lo consume Comisiones Variables (regla 13). Pendiente de validar la unidad de
`ultcos` contra Producción antes de corregir el ETL (auditoría 39, H-01 recomendación 2).

---

## 3. Margen de Utilidad ✅ punto único

| Campo | Valor |
|---|---|
| **Fórmula** | `(venta_neta_costeable − costo_mercaderia_vendida) / venta_neta_costeable × 100` |
| **Fuente** | `edw.fact_ventas_detalle.costo_total` sobre el universo costeable (§2) |
| **Grano** | Agregado del recorte consultado (no por línea) |
| **Unidad** | Porcentaje |
| **Punto único** | `AnalyticsRepository.get_management_kpis` |
| **Consumidores** | `GPKPIGerencia.margen_utilidad_neta`, resumen ejecutivo del reporte de Gerencia |
| **Valor de referencia** | **9,59%** en el histórico completo (era −1.563% antes de RN-BI1) |

---

## 4. ROI — retorno sobre costo de mercadería vendida ✅ punto único

| Campo | Valor |
|---|---|
| **Fórmula** | `(venta_neta_costeable − costo_mercaderia_vendida) / costo_mercaderia_vendida × 100` |
| **Lectura de negocio** | Por cada $1 invertido en mercadería que efectivamente se vendió, cuánto retorna en utilidad bruta |
| **Grano / Unidad** | Agregado del recorte; porcentaje |
| **Nulo** | `NULL` cuando el período no tiene costo de mercadería. Se muestra como *"sin base de cálculo"*, **nunca** como `0%` |
| **Umbral de semáforo** | `ANALYTICS_ROI_UMBRAL_SANO` (default 10,0) |
| **Punto único** | `AnalyticsRepository.get_management_kpis` |
| **Valor de referencia** | **10,61%** en el histórico completo |
| **Regla de negocio** | RN-BI2 |

**Historia:** reemplaza a `roi_estimado = margen × 1,15`, una constante sin regla de negocio
aplicada además sobre un valor que ya era un porcentaje (auditoría 39, H-02). El campo viejo
ya no existe en el contrato y hay un test que lo verifica.

**Alternativa evaluada y descartada:** *retorno sobre inventario promedio* cruzando con
`fact_inventario_snapshot` — esa tabla tiene solo **7 días** de histórico (2026-07-10 a
2026-07-16), insuficiente para cualquier promedio significativo.

---

## 5. Ticket Promedio (Factura Promedio) ✅ punto único

| Campo | Valor |
|---|---|
| **Fórmula** | `venta_neta / COUNT(DISTINCT num_factura)` |
| **Fuente** | `edw.fact_ventas_detalle` |
| **Grano** | Factura |
| **Punto único** | `AnalyticsRepository.get_management_kpis` |
| **Consumidores** | `GPKPIGerencia.ticket_promedio` |

**Precisión:** el denominador cuenta facturas **distintas con al menos una línea positiva** en
el recorte filtrado. Al filtrar por categoría, una factura con líneas de varias categorías
cuenta entera en cada una — el ticket por categoría no es aditivo hacia el total.

---

## 6. Cumplimiento de Meta ⚠ sin punto único

| Campo | Valor |
|---|---|
| **Fórmula** | `venta_neta_del_vendedor / monto_meta × 100` |
| **Fuente** | Venta Neta (§1) + `public.metas_comerciales_operativas` |
| **Grano** | `(anio, mes, id_vendedor_origen)` — **no** por sucursal (regla 10) |
| **Se calcula en** | `GoalRepository.get_commission_report`, `CommissionService`, `AnalyticsRepository.get_sales_performance` |
| **Regla de negocio** | 10, 13 |

El numerador **sí** tiene punto único desde G-02 (§1). El cociente y la clasificación de
estado (`en_ritmo` / `en_riesgo` / `alta_probabilidad`) siguen replicados. Deuda abierta.

---

## 7. Comisión ⚠ sin punto único (por diseño)

Dos esquemas conviven, seleccionados por `COMISION_MODO` (`plana` default / `sombra` / `variable`).
El rollback es cambiar esa variable de entorno.

| Esquema | Base de cálculo | Motor |
|---|---|---|
| **Plana** | Venta Neta (§1) por tramos | `commission_engine.calcular_comision` |
| **Variable** | `margen_bruto` de la línea, ponderado por categoría A/B/C/S/X, plazo de crédito y tipo de vendedor | `commission_engine.calcular_comision_variable` |

La duplicación aquí **es intencional** (dos reglas de negocio distintas conviviendo durante un
piloto), no deriva. Regla de negocio 13, RN-CM1..CM7.

> **⚠ Advertencia activa:** el esquema variable comisiona sobre `margen_bruto`, afectado por
> la deuda de §2. Medido: 24 líneas de clase `Z-999` en 2025-2026 arrastran **−$115 millones**
> sobre un solo código de vendedor. Con `COMISION_MODO=plana` no hay pago incorrecto, pero
> `POST /commission-simulation` sí lee ese campo.

---

## 8. Indicadores de Bodega

Documentados en detalle en `docs/auditoria/02_reglas_negocio_validadas.md` §16 (RN-B1..B9).
Umbrales en `BODEGA_*` (`backend/app/core/config.py`). Punto único: `WarehouseService`.

| Indicador | Fórmula resumida | Umbral |
|---|---|---|
| Punto de reorden | `demanda_diaria × (BODEGA_LEAD_TIME_DIAS + BODEGA_STOCK_SEGURIDAD_DIAS)` | — |
| Estado de stock | `< reorden` crítico · `≤ reorden × BODEGA_FACTOR_CERCA_REORDEN` cerca · resto seguro | `BODEGA_FACTOR_CERCA_REORDEN` (1,5) |
| Rotación | `costo_vendido / inventario_promedio` | `BODEGA_ROTACION_BUENA` / `_REGULAR` |
| Días de inventario | `stock_actual / demanda_diaria` | `BODEGA_DIAS_EXCESO` / `_EXCEDENTE` |

---

## 9. Bandas de incertidumbre de forecast (supuestos, no reglas de negocio)

Se declaran aquí explícitamente porque **no** están validadas contra el negocio: son supuestos
de ingeniería usados solo como respaldo cuando el sidecar `.meta.json` del modelo no trae MAE.

| Uso | Variable | Default |
|---|---|---|
| Forecast de ventas | `FORECAST_BANDA_FALLBACK_VENTAS_PCT` | 0,15 |
| Forecast de demanda | `FORECAST_BANDA_FALLBACK_DEMANDA_PCT` | 0,20 |

Cuando el MAE **sí** está disponible (caso normal), la banda es `MAE × √n_días` en ventas y
`MAE` en demanda, y estas variables no intervienen.

---

## 10. Indicadores retirados

| Indicador | Estado | Motivo |
|---|---|---|
| `roi_estimado` | **Retirado** 2026-07-27 | `margen × 1,15`: constante sin regla de negocio, sobre un valor que ya era porcentaje. Reemplazado por §4. Auditoría 39, H-02 |
| `roi_estimado_tendencia_pct` | **Retirado** 2026-07-27 | Era algebraicamente idéntico a la tendencia del margen (misma constante en numerador y denominador). Reemplazado por `roi_real_tendencia_pct` |
| `goals_rf` (modelo ML de metas) | Decomisionado | `docs/auditoria/20_decomision_goals_rf.md`. Metas usa estadística pura (IQR + tendencia) |

---

## Deuda conocida de esta capa

1. **Cumplimiento de Meta** (§6) y la clasificación de estado siguen replicados en 3 lugares.
2. **`margen_bruto` a nivel de línea** (§2) sigue con el costo derivado sin validar unidad.
3. El filtro de estado de la regla 1 se explicitó en `AnalyticsRepository`; en
   `GoalRepository` conviven aún ~15 consultas con `estado_documento_sk <> -1` a secas.
   Hoy es equivalente (verificado: `dim_estado_documento` tiene 2 filas y la centinela es la
   única con `'A'`), pero es la misma fragilidad de RN-BI3.
