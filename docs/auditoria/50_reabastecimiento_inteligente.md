# Auditoría 50 — Reabastecimiento Inteligente (Fase 0)

**Fecha:** 2026-08-04
**Alcance:** Módulo Bodega (`/analytics/bodega/*`), previo a la refactorización hacia un Sistema de Apoyo a Decisiones descrita en `docs/features/plan_reabastecimiento_inteligente.md`.
**Método:** `SELECT` reales contra `bi_postgres_edw` (contenedor `bi_postgres_edw`, vivo); lectura de código real de `backend/app/services/warehouse_service.py`, `backend/app/repositories/warehouse_repository.py`, `edw/03_hechos.sql`, extractores ETL y catálogo de esquema SAP (`docs/identificacion_bd.md`). Sin escritura sobre SAP ni sobre el EDW en ningún momento.
**Limitación real de este entorno:** no hay conectividad en vivo al ERP SAP SQL Anywhere desde esta sesión (falla `Adaptive Server is unavailable` incluso dentro del contenedor `etl`) — mismo tipo de limitación ya documentado en auditorías previas del proyecto (p. ej. auditoría 04, "sin conectividad en vivo al ERP"). Lo relativo a SAP en este reporte se basa en el catálogo de esquema real ya extraído (`docs/identificacion_bd.md`), no en una consulta ejecutada hoy.

---

## Resultados por pregunta (A-0.1 .. A-0.7)

### A-0.1 — ¿Es derivable un lead time real?

**Hallazgo revisado respecto al plan.** El plan asumía que no había ninguna fuente. Es más matizado:

- `edw.Fact_Compras` (columnas confirmadas por `\d edw.fact_compras`) tiene **una sola fecha** (`fecha_sk`, la de la factura de compra `fecfac`). El extractor real (`etl/extractors/compras_cabecera_extractor.sql`) solo trae `fecfac`. **Desde este hecho, el lead time NO es derivable** — se confirma H-1 tal como estaba en el plan.
- Sin embargo, el catálogo de esquema real de SAP (`docs/identificacion_bd.md`) muestra que **sí existen tablas de orden de compra separadas de la factura**: `encabezadoordcom` / `renglonesordcom` (Orden de Compra), con columnas `fectra` (fecha de la orden), `numfac` (posible cruce con `encabezadocompras.numfac`), `codpro`, `estadow`, `descargado`, `aprobado`. Ninguna de las dos tablas está en `PIPELINE_CONFIG` del ETL hoy — no se extraen.
- **No se pudo confirmar en vivo** (sin conectividad a SAP en este entorno) si `numfac` efectivamente cruza `encabezadoordcom` con `encabezadocompras` fila a fila, ni la calidad del dato `fectra`, ni qué fracción de compras reales pasa por una orden formal antes de facturarse (compras urgentes de mostrador podrían no tener orden previa).

**Conclusión para D-1:** la opción (b) del plan ("extender el ETL para derivar lead time real") es **más viable de lo que el plan asumía** — hay una tabla candidata real, no hipotética — pero sigue sin poder validarse sin acceso a Producción. Se mantiene la recomendación del plan: **(a) tabla de configuración editable ahora**, y se añade un ítem concreto de trabajo futuro no genérico: *"verificar contra Producción si `encabezadoordcom.numfac = encabezadocompras.numfac` cruza de forma consistente, y si acaso, extraerlo como `Fact_Ordenes_Compra` con `fecha_orden`/`fecha_factura` para medir lead time real por proveedor"*.

### A-0.2 — ¿`Fact_Transferencias` permite medir lead time interno?

Confirmado con datos reales:

```
SELECT COUNT(*) FROM edw.fact_transferencias;              → 166,864 filas
SELECT MIN/MAX fecha_completa ...                            → 2018-01-02 .. 2026-07-30
```

**Hallazgo nuevo, no anticipado por el plan:** `edw.Fact_Transferencias` (igual que `Fact_Compras`) tiene **una sola columna de fecha** (`fecha_sk`), no un par salida-origen/entrada-destino. La documentación de `edw/03_hechos.sql` no distingue fecha de envío de fecha de recepción. El tiempo de tránsito entre bodegas **tampoco es medible** con el hecho actual, contra lo que H-15 del plan sugería como posible. Se retira esa expectativa; el patrón de "una sola fecha" resulta ser sistémico en `Fact_Compras` y `Fact_Transferencias`, no una excepción de compras.

### A-0.3 — Distribución ABC real (12 meses, valor de consumo)

Primera corrida (sin excluir nada): **95.81% del valor total** lo concentra un solo código, `Z-9001` "BATERIAS CHATARRAS" — el mismo SKU ya señalado como atípico en la auditoría 38 (modelo de demanda) por una razón distinta (unidad de chatarra, no de reposición). Confirma que la exclusión ya aplicada al entrenamiento de `demand_rf` (clase `Z-999`) es igualmente necesaria para cualquier clasificación de valor, no solo para el modelo.

Segunda corrida, excluyendo `Z-9001`/clase `Z-999`/centinela `-1`:

```
Clase A: 58 SKUs    (2.6%)
Clase B: 294 SKUs   (13.2%)
Clase C: 1,875 SKUs (84.2%)
Total:   2,227 SKUs con venta en 12 meses
```

Curva de Pareto real y razonable (80/20 clásico, sin distorsión). **Confirmado: ABC es viable y barato de calcular** (una sola consulta agregada sobre `Fact_Ventas_Detalle`), tal como anticipaba el plan §2.4.

### A-0.4 — Distribución XYZ real (coeficiente de variación mensual, 12 meses, ≥3 meses con venta)

```
Con los umbrales actuales (BODEGA_CV_ALTA=1.2, BODEGA_CV_MEDIA=2.5, hoy solo usados en transferencias):
  Clase X (CV≤1.2):  965 SKUs (96.6%)
  Clase Y (1.2-2.5):  34 SKUs (3.4%)
  Clase Z (>2.5):      0 SKUs (0.0%)
  CV promedio=0.52, mediana=0.49, percentil 90=0.92
```

**Hallazgo confirmado (H-4/A-0.4 del plan): los umbrales `BODEGA_CV_ALTA`/`BODEGA_CV_MEDIA` no discriminan nada para XYZ** — calibrados para otro propósito (transferencias), dejan prácticamente todo el catálogo en una sola clase. Con los mismos datos, los **terciles reales** son:

```
Corte X/Y: CV = 0.39
Corte Y/Z: CV = 0.61
```

**Acción para Fase 2:** el motor de reabastecimiento necesita su propio umbral XYZ (`REABASTECIMIENTO_XYZ_CORTE_X`, `REABASTECIMIENTO_XYZ_CORTE_Y`), sembrado con estos valores reales, **no reutilizar `BODEGA_CV_ALTA`/`MEDIA`**.

### A-0.5 — Cobertura de historia suficiente para ROP estocástico

```
SKUs con ≥6 meses activos (de 36 meses de ventana): 1,164
SKUs con al menos una venta en 36 meses:             3,621
→ 32.1% del catálogo con historia real califica para el método estocástico completo.
```

Confirma cuantitativamente lo que el plan anticipaba de forma cualitativa: **más de dos tercios del catálogo necesitará degradar** a un método más simple (demanda determinista simple, o benchmark de categoría) — el motor debe declarar el método usado por SKU (`metodo_demanda`), nunca fingir precisión estocástica sin historia.

### A-0.6 — ¿El filtro de fechas afecta `salida_diaria` en los endpoints de compra/reorden?

Confirmado por lectura directa de [warehouse_repository.py:204-217](backend/app/repositories/warehouse_repository.py#L204-L217): `get_inventario_productos` acepta `dias_salidas: int = 30` como parámetro, **pero ninguno de sus 7 llamadores** (`get_kpis`, `_forecast_ml_producto`-adjacent, `_prediccion_compras_mes_categoria`, `get_stock_reorden`/`_stock_reorden_filas`, `_necesidad_compra_completo`, `get_inventario_matriz`, `get_notificaciones`) lo sobreescribe con `fecha_desde`/`fecha_hasta`.

**H-9 del plan queda CONFIRMADO, no refutado**: el filtro de fechas de la barra global es decorativo para `/stock-reorden`, `/necesidad-compra`, `/inventario-matriz`, `/transferencias-sugeridas` y las notificaciones de Bodega — todos calculan `salida_diaria` sobre una ventana fija de 30 días sin importar lo que el usuario seleccione en el filtro. (Los endpoints de gráficos — `/kpis`, `/top-productos`, `/salidas-categoria` — sí respetan el filtro, porque pasan `fecha_desde`/`fecha_hasta` explícitos a sus propias consultas.)

### A-0.7 — Impacto de cambiar el ROP determinista por uno estocástico

Simulación con datos reales (30 días de movimientos, `z=1.65` → nivel de servicio 95%, `LT=7` días fijo — mismo lead time global que usa hoy el sistema, para aislar el efecto del cambio de fórmula):

```
Fórmula actual:      ROP = demanda_diaria × 12        (LT=7 + SS=5, ambos fijos)
Fórmula estocástica: ROP = demanda_diaria × 7 + 1.65 × σ_demanda × √7

SKUs con venta en 30 días evaluados: 779
Delta promedio:        -7.6 unidades (el ROP estocástico tiende a ser MENOR en promedio)
Suben de ROP:           49 SKUs (6.3%)
Bajan de ROP:          729 SKUs (93.6%)
Cambian >30%:          422 SKUs (54.2% del catálogo evaluado)
```

**Confirma la advertencia del plan (§9, salvaguarda F3):** no es un cambio cosmético. El actual "5 días de stock de seguridad fijo" resulta, para la mayoría del catálogo (demanda de baja variabilidad, CV mediana 0.49), **más conservador** que un cálculo estocástico correcto — pero para el 6.3% que sube, la fórmula actual estaba **subestimando** el riesgo real de quiebre porque ignora la variabilidad de esos SKUs específicos. Ambas direcciones del cambio son reales y deben presentarse a gerencia antes de activar el motor nuevo como predeterminado (F3 convive con el método viejo, no lo reemplaza de inmediato — según el plan de implementación).

### A-0.8 y A-0.9 — Diferidas explícitamente

- **A-0.8** (exactitud real de `demand_rf` por SKU vía `ml/scripts/backtest_demand_por_sku.py`) requiere levantar el contenedor `ml` con el pipeline de entrenamiento completo — se difiere a la Fase 6 del plan (que depende de este resultado), no bloquea F0-F4.
- **A-0.9** (latencia base de `/necesidad-compra`/`/inventario-matriz`) requiere autenticación JWT contra el backend real — se difiere a la validación de la Fase 3, momento en el que además hay una consulta nueva que medir junto con las existentes.

### A-0.10 — Recorrido UX actual

Confirmado por lectura de código (no requiere datos): desde "abrir Bodega" hasta "saber qué comprar" hoy son **mínimo 3 pasos** — (1) `DashboardBodega` muestra KPIs y gráficos pero ningún listado accionable; (2) clic en "Status por Almacén"; (3) scroll hasta la sección "Plan de Necesidad de Compra" dentro de `BodegaAlmacenes.tsx`, ordenada por prioridad pero mezclada en la misma página con la matriz de inventario y las transferencias. No hay una sola pantalla que responda "¿qué compro hoy?" de forma directa — confirma la premisa central del pedido del usuario.

---

## Clasificación de hallazgos

### Críticos
- **H-1** (revisado): lead time es una constante global sin fuente real derivable desde el EDW actual; existe una tabla candidata en SAP (`encabezadoordcom`) no verificada por falta de acceso a Producción.
- **H-2**: el motor de compra no usa `demand_rf`.
- **H-3**: sin nivel de servicio ni variabilidad en el ROP — **cuantificado en A-0.7**: cambia el estado de más de la mitad del catálogo evaluado.
- **H-4**: sin ABC/XYZ — **A-0.3/A-0.4 confirman que ambos son viables y baratos**, y que los umbrales XYZ existentes no sirven para este propósito.
- **H-5**: aprobación de transferencias no persistida (`useState` de React).
- **H-9**: filtro de fechas decorativo en 4 endpoints + notificaciones — **confirmado por lectura de código, A-0.6**.

### Importantes
- H-6 (KPIs calculados y descartados), H-7 (banda de confianza constante), H-8 (sin exactitud por SKU), H-10 (duplicación financiera), H-11 (horizonte no configurable por el usuario).
- **Nuevo, A-0.2:** `Fact_Transferencias` tampoco permite medir lead time interno (una sola fecha) — información adicional para descartar esa vía en el diseño del motor.

### Menores
- H-12, H-13, H-14 (sin cambios respecto al plan).

### Oportunidades confirmadas con datos reales
- ABC calculable con una sola consulta agregada sobre `Fact_Ventas_Detalle`, resultado de negocio razonable (2.6/13.2/84.2%).
- XYZ calculable, pero **necesita umbrales propios** (0.39/0.61), no los de transferencias.
- El patrón de exclusión de `Z-9001`/`Z-999` ya validado para ML debe aplicarse también en ABC/XYZ — mismo SKU, mismo motivo.

## Recomendaciones priorizadas

1. **Ejecutar F1-F4 del plan** (motor puro + ABC/XYZ + ROP estocástico + lista priorizada) usando los umbrales XYZ reales de esta auditoría, no los de `BODEGA_CV_*`.
2. **D-1 se resuelve como (a)** tabla de configuración editable de lead time, con el hallazgo de `encabezadoordcom` documentado como ítem de trabajo futuro concreto (requiere sesión con acceso a Producción para validar el cruce por `numfac`).
3. **F3 debe convivir con `/necesidad-compra`** (no reemplazarlo de inmediato): A-0.7 muestra que el cambio de fórmula altera el estado de más de la mitad del catálogo evaluado — es una decisión de política de negocio que gerencia debe ver antes de que sea la predeterminada.
4. **Corregir H-9 como parte de F3**, no como parche aislado: el motor nuevo debe aceptar la ventana de demanda como parámetro real (ligado al filtro de fechas o a la política configurada), no una constante de 30 días enterrada en la firma del repositorio.
5. A-0.8/A-0.9 quedan como trabajo explícito de la Fase 6/Fase 3 respectivamente — no bloquean el corte mínimo de valor F0→F4.
