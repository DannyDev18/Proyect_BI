# Reglas de Negocio Validadas contra Producción (SAP SQL Anywhere)

- **Fecha:** 2026-07-08
- **Método:** consultas `SELECT` de solo lectura contra la BD origen (`DB_SERVER=xp_plus`, `db_microplus`, `172.16.50.5:4016`, empresa `codemp='01'`). No se ejecutó ninguna escritura.
- **Propósito:** documentar las reglas de negocio que antes estaban implícitas o hardcodeadas sin explicación (requisito CLAUDE.md: *toda regla de negocio debe estar documentada*). Estas reglas sustentan las correcciones de los extractores.

---

## 1. Estado de documentos (`estado`)

`encabezadofacturas.estado`:

| estado | registros | significado |
|---|---|---|
| `P` | 234 886 | **Procesada / válida** |
| `A` | 8 | **Anulada** |

**Regla:** filtrar `estado = 'P'` es correcto para excluir documentos anulados. Se mantiene, pero ahora **documentado y parametrizable** (`ESTADO_VALIDO`).

## 2. Empresa (`codemp`)

Toda la operación validada corresponde a `codemp = '01'`. Se **parametriza** vía `config.CODEMP` (token `{CODEMP}` en los extractores) para no dejarlo hardcodeado y permitir multi-empresa futura.

## 3. Tipos de movimiento de Kardex (`kardex.tiporg`)

| tiporg | registros | significado | dirección |
|---|---|---|---|
| `FAC` | 461 466 | Venta / facturación | Salida |
| `TRA` | 330 754 | Transferencia entre bodegas | Entrada+Salida (par) |
| `CPA` | 129 349 | Compra | Entrada |
| `DEV` | 8 429 | Devolución (nota de crédito) | Entrada |
| `BOD` | 7 545 | Ajuste de bodega / inventario | Entrada (mayoría) |
| `EGR` | 5 143 | Egreso | Salida |
| `ING` | 3 979 | Ingreso | Entrada |
| `DEC` | 1 167 | Ajuste / decremento | Salida (mayoría) |

## 4. Dirección del movimiento (`kardex.tipdoc`) — HALLAZGO CLAVE

`cantot` **siempre es positivo** (magnitud, no lleva signo). La dirección se determina por `tipdoc`:

| tipdoc | significado | tiporg asociados |
|---|---|---|
| `EN` | **Entrada** | CPA, DEV, ING, BOD, TRA (destino) |
| `SA` | **Salida** | FAC, EGR, DEC, TRA (origen) |
| `AC` | Ajuste (+) | BOD |
| `AD` | Ajuste (−) | DEC |

**Regla derivada para el DW:**
- `entrada = cantot` cuando `tipdoc IN ('EN','AC')`, si no `0`.
- `salida  = cantot` cuando `tipdoc IN ('SA','AD')`, si no `0`.

## 5. Transferencias (`tiporg = 'TRA'`) — estructura

Cada ítem transferido (`numdoc` + `numren`) genera **exactamente 2 filas** con la misma `cantot`:
- La fila con `tipdoc = 'SA'` → **bodega origen** (`codalm`).
- La fila con `tipdoc = 'EN'` → **bodega destino** (`codalm`).

Balance validado: `TRA` = 165 377 filas `EN` + 165 377 filas `SA` (perfectamente pareado).

**Regla derivada:** una transferencia se reconstruye agrupando por `(codemp, numdoc, numren, codart)` y pivotando `codalm` según `tipdoc` (SA=origen, EN=destino), con `cantidad_enviada = cantot`.
**Limitación [PENDIENTE ERP]:** el kardex no expone *cantidad solicitada* ni *estado* de la transferencia; solo la cantidad efectivamente movida.

## 6. Descarga de inventario (`renglonesfacturas.desinv`)

| desinv | registros | significado |
|---|---|---|
| `S` | 519 517 | La línea **sí** descarga inventario (afecta costo/stock) |
| `N` | 915 | La línea **no** descarga inventario (servicio/no inventariable) |

**Regla:** el costo de inventario solo aplica cuando `desinv = 'S'`. Documentado.

## 7. Existencias / stock — fuente confirmada

Existe la vista **`vi_mv_existencias`** con columnas: `codemp, codalm, codart, existe (stock), nomalm`.
- Provee **stock por bodega** directamente.
- **No** incluye costo → el costo/valor de inventario se obtiene de `articulos.ultcos` (último costo).
- Es la fuente para el nuevo `existencias_extractor.sql` (snapshot de inventario).

## 8. Integridad de claves (validado)

- `encabezadofacturas (codemp, numfac)`: **0 duplicados** → los JOIN cabecera↔detalle no multiplican filas.
- `articulos (codemp, codart)`: **0 duplicados** → el `LEFT JOIN articulos` no duplica renglones.

Esto **descarta** el riesgo de duplicación por JOIN señalado como *[VALIDAR]* en `01_auditoria_extractores.md` (§4.1/§4.2).

## 9. Costo de artículo (`articulos.ultcos`)

`ultcos` = **último costo** (no promedio). El alias `costo_promedio` del extractor es incorrecto y se renombra a `ultimo_costo`.

## 13. Venta Neta por vendedor (Metas y Comisiones)

**Regla:** `Venta Neta = SUM(fact_ventas_detalle.subtotal_neto) - SUM(fact_devoluciones.total_linea_devolucion)`, agregada por vendedor/mes (ver regla 15 — NO por sucursal). `fact_ventas_detalle` se filtra por `dim_estado_documento.estado_documento_sk <> -1`; `fact_devoluciones` no tiene columna de estado de documento (no aplica ese filtro). Es la base del motor estadístico de propuesta de metas (`IQRGoalCalculationEngine`, ver `docs/auditoria/16_venta_neta_y_propuesta_meta_siguiente_mes.md`), que es el generador OFICIAL de la meta persistida y el ÚNICO motor de Metas y Comisiones: el modelo `goals_rf` fue decomisionado (`docs/auditoria/20_decomision_goals_rf.md`), el módulo no usa ningún modelo ML.

## 14. Tramos de comisión (Metas y Comisiones)

**Regla:** el cumplimiento se mide como `Venta Neta del período / monto_meta`. Cuatro tramos (docs/modulo_metas.md "PROPUESTA IA" Fase 4, prioridad sobre la nota informal del mismo documento que se contradice en el tramo 80-89%): Lejos (<80%) no comisiona; Cerca (80-89%) comisiona `comision_base_pct * 5/7` sin bono; Meta (90-99%) comisiona `comision_base_pct` completo; Excelente (>=100%) comisiona `comision_base_pct + 2pp` más el bono fijo `bono_sobrecumplimiento`. `comision_base_pct`/`bono_sobrecumplimiento` son campos ya existentes y editables por vendedor/meta en `public.metas_comerciales_operativas` (no hardcodeados). Implementado en `backend/app/services/commission_engine.py`, ver `docs/auditoria/17_comisiones_liquidacion.md`.

## 15. Grano de Metas y Comisiones: vendedor, NO vendedor×sucursal

**Regla:** `public.metas_comerciales_operativas` tiene grano `(anio, mes, id_vendedor_origen)`. `edw.dim_vendedor` no tiene una sucursal propia asociada — un vendedor transacciona en múltiples sucursales físicas dentro de `fact_ventas_detalle` (verificado contra el EDW real: `VEN13` transacciona en las 7 sucursales, varios otros vendedores en 5-6). Agrupar por `(vendedor, sucursal)` generaba hasta 7 metas/comisiones duplicadas por vendedor por mes. Toda consulta de `GoalRepository` relacionada con metas/comisiones agrega Venta Neta/ventas de TODAS las sucursales del vendedor. Ver `docs/auditoria/19_grano_vendedor_metas_y_meta_futura_razonable.md`.

## 16. Módulo Bodega: abastecimiento y transferencias (RN-B1..B6)

Reglas del módulo de Bodega (`docs/features/modulo_bodega.md`, auditoría 23 — `docs/auditoria/23_modulo_bodega.md`). Umbrales parametrizados por env (`BODEGA_*` en `backend/app/core/config.py`), no hardcodeados:

- **RN-B1 (punto de reorden efectivo):** el configurado en `fact_inventario_snapshot.punto_reorden` si es > 0; si no, `(salida_prom_diaria_30d × lead_time) + (salida_prom_diaria_30d × días_seguridad)` (defaults 7 y 5 días).
- **RN-B2 (estado de stock):** Crítico si `stock < reorden`; Cerca si `reorden ≤ stock ≤ reorden×1.5`; Seguro si `stock > reorden×1.5`; Exceso si días de inventario > 90.
- **RN-B3 (transferir antes de comprar):** sugerir transferencia si el origen tiene >60 días de inventario y el destino <15; cantidad = la necesaria para llevar el destino a 30 días sin dejar al origen bajo 60. Prioridad Alta si el destino está en Crítico.
- **RN-B4 (cantidad a comprar):** si días de inventario < 20 → `(salida_prom_diaria × horizonte) − stock_actual`; horizonte 30 días (necesidad inmediata) o 45 (plan de fin de mes).
- **RN-B5 (rotación):** `costo_de_ventas / inventario_promedio` del período; anualizada: >4 buena, 2–4 regular, <2 mala.
- **RN-B6 (salidas):** toda salida se mide con `fact_movimientos_inventario.es_salida = TRUE` (dirección por `tipdoc`, regla 3) — nunca por signo de cantidad. El "inventario actual" es SIEMPRE el último snapshot de `fact_inventario_snapshot` (sumar el histórico duplica conteos).
- **RN-B7 (predicción de compras del próximo mes por categoría, `docs/auditoria/24_prediccion_categoria_paginacion.md`):** dado un filtro de categoría, se toman los `BODEGA_TOP_ARTICULOS_PREDICCION` (default 20) artículos con más ventas reales del período (`fact_ventas_detalle`, no kardex) y se corre `demand_rf` (walk-forward) por artículo para el mes calendario siguiente; `compra_sugerida = max(0, predicción_mes − stock_actual)`. El método se declara por artículo y a nivel agregado (`ml_demand_rf` si al menos uno usó el modelo, `estadistico` si todos degradaron). Las bandas de confianza de la serie agregada son la suma directa de las N bandas individuales — una aproximación conservadora, no una banda estadísticamente rigurosa.

**Actualización 2026-07-15 (`docs/features/plan_actualizacion_modulo_bodega.md`, `docs/auditoria/32_actualizacion_modulo_bodega.md`):**

- **RN-B8 (montos condicionados al tipo de movimiento):** `edw.fact_movimientos_inventario.valor_venta`/`.costo_total` vienen pobladas a nivel de movimiento (heredadas de `kardex.totven`/`costot`, verificado con `SELECT` real contra el EDW: `FAC` trae `valor_venta` real ≈ $28.0M sobre 462.577 filas, `CPA` trae `costo_total` real ≈ $20.3M sobre 129.595 filas), pero solo esos 2 tipos representan dinero real de venta/compra. `/top-productos` y `/salidas-categoria` exponen `monto_ventas` (mapa cerrado `TIPOS_MOVIMIENTO_CON_MONTO = {"FAC": "venta", "CPA": "compra"}` en `warehouse_repository.py`) únicamente cuando el filtro `tipo_movimiento` activo es `FAC` o `CPA`; en cualquier otro caso (sin filtro u otro tipo del catálogo) el campo es `null`, aunque la columna SQL tenga valor heredado del kardex genérico. **Reconciliado 2026-07-15 con `SELECT` de solo lectura directamente contra Producción** (SAP SQL Anywhere, tabla `kardex`, `WHERE codemp='01' GROUP BY tiporg`): los 8 tipos coinciden con el EDW dentro de <0.1% (ej. `BOD`: 7.545 filas y `SUM(totven)=$0.00` idénticos en ambos lados; `FAC`: SAP 462.798 filas/$28.02M vs EDW 462.577 filas/$28.01M, diferencia explicada por el lag normal entre la última corrida del ETL y el estado actual de Producción, que tenía datos hasta el mismo día de la reconciliación).
- **RN-B9 (justificación estadística de transferencias):** una sugerencia de transferencia (`/transferencias-sugeridas`) solo se emite si `beneficio_neto_estimado > 0` (`ahorro_estimado − costo_logístico_estimado`, este último `cantidad × costo_unitario × BODEGA_COSTO_LOGISTICO_PCT/100`, default 5%) y `meses_con_venta_destino ≥ BODEGA_MIN_MESES_VENTA` (default 2, sobre una ventana de 6 meses) — nunca se sugiere mover inventario a una bodega sin historial real de venta del artículo. Las métricas de evidencia (`demanda_media_destino`, `demanda_mediana_destino`, `coeficiente_variacion_destino`, `tendencia_destino_pct`, `venta_monetaria_destino_90d`) se calculan sobre una serie diaria de 90 días con calendario completo (ceros en días sin movimiento, no solo días con actividad) para que el coeficiente de variación sea representativo de la demanda real. La confianza (`alta` si `CV < BODEGA_CV_ALTA` y `meses_con_venta ≥ BODEGA_MESES_CONFIANZA_ALTA`; `media` si `CV < BODEGA_CV_MEDIA` y `meses_con_venta ≥ BODEGA_MIN_MESES_VENTA`; `baja` en cualquier otro caso) se muestra siempre — incluida la confianza baja, marcada "revisar manualmente" — nunca oculta en silencio. **Umbrales calibrados contra datos reales, no contra un estándar genérico de libro** (docs/auditoria/32 H32-5): la demanda de repuestos de este negocio es intermitente por naturaleza (mediana real de CV ≈ 2.6 sobre 200 sugerencias verificadas del EDW), por lo que `BODEGA_CV_ALTA=1.2`/`BODEGA_CV_MEDIA=2.5`/`BODEGA_MESES_CONFIANZA_ALTA=5` (vs. los `0.5`/`1.0` "de libro" que dejaban 199/200 sugerencias en "baja", una señal inútil). El campo `motivo` (string) se conserva por compatibilidad con consumidores existentes.

**Actualización 2026-07-29 (`docs/features/plan_correcciones_integrales_sistema.md` Fase 1, `docs/auditoria/42_correcciones_integrales_sistema.md`):**

- **RN-B10 (RLS por bodega):** un usuario con rol `bodega` solo puede leer/exportar datos de los almacenes que el administrador le asignó (`public.usuario_almacenes`, relación N:N -- un usuario puede tener una, varias o ninguna bodega asignada), o de todos los almacenes si se marcó `usuarios.todos_los_almacenes = TRUE`. El parámetro `almacen` que el usuario elige en la barra de filtros se **intersecta** con esa restricción (`al.codalm IN (...)`, nunca `al.nombre_almacen`, que es un dominio distinto) — nunca la amplía; una bodega sin ninguna asignación no ve ningún dato (no "todos" por omisión). Cierra H-1 (docs/auditoria/42): antes cualquier usuario `bodega` podía leer/exportar cualquier almacén cambiando `?almacen=<otro>` en la URL, sin restricción alguna -- fuga análoga a la corregida para el rol `ventas` en RN-V4 (docs/auditoria/34), pero no cubierta entonces porque el módulo Bodega quedó fuera de esa auditoría. **Extensión a la UI (2026-07-29, petición explícita del usuario):** el mismo criterio aplica al catálogo de `GET /analytics/bodega/filtros` -- el selector de almacén de `BodegaFilterBar.tsx` solo lista las bodegas asignadas al usuario (o el catálogo completo si `todos_los_almacenes = TRUE`), no solo los datos que puede consultar.

## 17. Módulo Venta Cruzada (Cross-Selling): formato de sugerencia y telemetría (RN-CS1, RN-CS2, RN-CS3)

Reglas del módulo de Venta Cruzada (`docs/features/plan_modulo_cross_selling.md`, auditoría 25 — `docs/auditoria/25_modulo_cross_selling.md`). Umbrales parametrizados por env (`CROSS_SELL_*` en `backend/app/core/config.py`):

- **RN-CS1 (formato de sugerencia):** dado un conjunto de `codart` en la canasta simulada (y opcionalmente un `cliente_id`), se devuelven hasta `CROSS_SELL_TOP_N` (default 5) sugerencias con `codart`, `nombre`, `precio` (`dim_producto.precio_oficial` vigente), `categoria` (`clase`), `score` y `motivo`. Se excluyen productos ya en la canasta y, si hay `cliente_id`, los ya comprados por ese cliente. El umbral `CROSS_SELL_MIN_LIFT` solo se aplica a fuentes en escala de lift (`coocurrencia`/`apriori`, >1 = afinidad real); el modelo publicado (`item_item`, similitud coseno en `[0,1]`) NO se filtra por ese umbral -- aplicárselo rechazaría siempre todas las filas (bug real encontrado y corregido en la verificación end-to-end de la auditoría 25, Fase 4). Si el artefacto no devuelve ninguna sugerencia para la canasta, se usa el fallback por popularidad de categoría (producto más vendido de la misma `clase` que no esté ya en la canasta). El factor de margen (`CROSS_SELL_PESO_MARGEN`) solo se aplica cuando `dim_producto.costo_promedio` es no nulo y > 0 (≈92% del catálogo vigente, auditoría 25 §1); si no, se ordena solo por score.
- **RN-CS2 (telemetría y conversión):** cada sugerencia mostrada al vendedor registra un evento `mostrada` en `public.recomendaciones_eventos`; el clic en "Agregar" registra `aceptada`. La tasa de conversión de un período = `count(aceptada) / count(mostrada)`. La "aceptación" es un registro en la plataforma BI, no una línea de factura en SAP (el ERP no se toca, regla de solo-lectura de Producción).
- **RN-CS3 (diversidad entre categorías, hallazgo de uso real 2026-07-13):** máximo `CROSS_SELL_MAX_POR_CATEGORIA` (default 2) sugerencias de una misma categoría entre las `CROSS_SELL_TOP_N` finales. El artefacto item-item entrena solo los top-20 vecinos por producto, y para algunos productos (p.ej. baterías) los 20 vecinos son TODOS de su misma categoría -- sin señal cruzada real disponible. Cuando la selección final queda concentrada en una sola categoría, se reemplazan hasta 2 sugerencias por los productos más vendidos de OTRAS categorías (`fuente: popularidad_otra_categoria`), para que el asistente siempre ofrezca opciones de venta cruzada real entre categorías, no solo variantes del mismo producto.

**Actualización 2026-07-28 (Fase 1 de `docs/features/plan_refactor_venta_cruzada_ia.md`, auditoría previa `docs/auditoria/40_refactor_venta_cruzada.md`):**

- **RN-CS4 (CLV histórico, decisión de negocio 2026-07-28):** el "valor del cliente" que expone el perfil 360 del asistente (`GET /cross-selling/clientes/{id}/perfil`) es `SUM(subtotal_neto)` de TODA la historia de facturas válidas del cliente (`Cartera360Repository.get_perfil_cliente`) -- **histórico, no predictivo** (se descartó BG/NBD + Gamma-Gamma por requerir un modelo nuevo sin justificación de negocio todavía). A diferencia de `valor_historico` de la cartera de UN vendedor (`get_lista_trabajo`, RN-V1, ventana de 12 meses), este es TODA la historia del cliente sin filtrar por vendedor ni ventana -- un cliente puede haber comprado a más de un vendedor a lo largo del tiempo, y el perfil 360 responde "¿cuánto vale este cliente para la empresa?", no "¿cuánto le ha comprado a MI cartera este año?".
- **RN-CS5 (estado vacío real para "sin historial", no ceros):** cuando un cliente no tiene ninguna venta válida en el EDW, el perfil devuelve `tiene_historial: false` y todos los campos agregados en `null` (`num_compras`, `valor_historico`, `ticket_promedio`, etc.) -- nunca `0`, que en la UI se leería como "cliente sin valor" en vez de "sin datos todavía". Confirmado con evidencia real en la auditoría 40 (A0-3): 57.8% de la cartera tiene una sola compra registrada y 77.1% menos de 3 meses de historial -- el caso "historial escaso" es el típico, no el raro, y el diseño (incluida la Fase 2 del plan, el ranker) debe tratarlo como tal.
- **`probabilidad_recompra` es `100 - probabilidad_abandono` de `churn_rf`, no un modelo aparte** (decisión de negocio 2026-07-28): mostrar la misma cifra de churn reexpresada como "probabilidad de recompra" en el perfil 360, documentado así en el schema (`PerfilClienteResponse`) para no sugerir un tercer modelo independiente donde solo hay uno.
- **RLS obligatoria en el nuevo endpoint** (decisión §3 punto 6 del plan): `GET /cross-selling/clientes/{id}/perfil` aplica el mismo `_verificar_pertenencia_cartera` que `/churn-risk`/`/recommendations`/`/clientes/{id}/segmento` (auditoría 34, H-V2) -- un cliente ajeno a la cartera del vendedor autenticado responde 403, verificado con test de integración (`backend/tests/integration/test_cross_selling_fase1.py`).

**Actualización 2026-07-28 (Fase 2-3 del mismo plan):**

- **RN-CS6 (ranker no promovido, sin cambio de serving):** el modelo `cross_sell_ranker`
  (7º modelo, Fase 2) se entrenó y evaluó con datos reales del EDW pero NO superó la línea
  base del motor item-item vigente en el backtest (Precision@5=0.0369 vs. 0.0782 fresco,
  mismo protocolo de la auditoría 25) -- por la regla de decisión fijada de antemano (§2.4
  del plan), no se promueve. `registry.json` y el serving del backend quedan sin cambios;
  el contrato `cross_sell_ranker` permanece en `status: draft`. Detalle completo, incluida
  la hipótesis de por qué falló (sesgo de distribución train/serving en el muestreo de
  negativos), en `docs/auditoria/40_refactor_venta_cruzada.md` §Fase 2 aplicada.
- **RN-CS7 (simulación de canasta, solo cifras reales):** `POST /cross-selling/simular`
  (Fase 3) nunca predice -- `ticket_estimado`/`margen_estimado` son sumas reales de
  `dim_producto.precio_oficial`/`costo_promedio` vigente (`margen_estimado` es `None`
  cuando falta el costo de CUALQUIER producto de la canasta, nunca una suma parcial
  engañosa); `incremento_vs_ticket_promedio_cliente` y `probabilidad_recompra` reutilizan
  el perfil de cliente de la Fase 1 (CLV histórico y `churn_rf`) sin cálculo nuevo. No
  expone "probabilidad de cierre de venta" (el EDW no tiene ventas perdidas, decisión de
  negocio confirmada) ni "probabilidad de compra por producto" (dependía del ranker de la
  Fase 2, no promovido). RLS obligatoria cuando se pasa `cliente_id` (mismo criterio de
  H-V2).

**Actualización 2026-07-28 (Fases 4-6 del mismo plan, bajo la restricción explícita del usuario "esto no debe contener ninguna simulacion, todos con datos reales"):**

- **RN-CS8 (combos inteligentes, 4 estrategias sin campos inventados):** `GET /cross-selling/combos` (Fase 4) expone 4 estrategias -- Oferta Estrella (coocurrencia real de facturas, `get_top_combinaciones`), Mayor Rentabilidad (`get_top_margen_relativo`, top-1 por categoría con costo y venta reales), Cliente Frecuente (solo con `cliente_id`, `popularidad` = % real del gasto histórico del cliente sobre sus productos favoritos) y Protección Total (`get_top_productos_diversos`). "Ideal para Flotas" queda fuera por decisión de negocio ya tomada (sin definición de "cliente de flota/corporativo" derivable del EDW, §8.4 del plan). Los campos `confianza`/`incremento_esperado` del diseño original del plan se OMITEN del contrato (`CombinacionInteligente`) en vez de rellenarse con `None`/placeholders, porque ninguna de las 4 estrategias tiene una base real para calcularlos sin el ranker de la Fase 2 (no promovido). `margen_esperado` es `None` si falta el costo de cualquier producto del combo (mismo criterio agregado que RN-CS7).
- **RN-CS9 (decomposición del score, dos medidores, no una barra apilada):** `GET /cross-selling/sugerencias` (Fase 5) expone `factor_margen` (siempre real, `1.0` neutro) junto al `score` existente. Como el orden final de sugerencias resulta de **multiplicar** `score × factor_margen`, no de sumarlos, el frontend (`ScoreDecompositionBar.tsx`) los renderiza como dos medidores independientes normalizados contra el máximo de la lista visible -- una barra apilada aditiva sería una representación visual falsa de cómo se compone el ranking real.
- **RN-CS10 (explicabilidad real vía SHAP, etiquetado explícito, R-3 del plan):** `GET /cross-selling/clientes/{id}/explicacion-churn` (Fase 6) expone la contribución real de cada feature de `churn_rf` (`recency`, `frequency`, `monetary_value`, `average_ticket`) al riesgo de abandono del cliente, calculada con `shap.TreeExplainer` sobre el modelo ya entrenado -- sin modelo nuevo, sin texto generado. El panel se etiqueta explícitamente **"Explicación del modelo (SHAP)"** (`WhyExplanationPanel.tsx`), nunca "IA" ni lenguaje que sugiera generación de contenido, cumpliendo R-3 del plan (no fingir IA generativa donde hay un cálculo determinista/estadístico real). RLS obligatoria (mismo criterio de H-V2); consulta bajo demanda (solo al expandir el panel), no en cada carga del perfil, por el costo real de calcular SHAP.

## 18. Comisiones Variables por Margen/Categoría (RN-CM1..RN-CM4)

Reglas del sistema de Comisiones Variables (`docs/features/plan_integracion_comisiones_variables.md`, auditoría 30 — `docs/auditoria/30_comisiones_variables.md`). Convive con el esquema plano existente (regla 15/`commission_engine.calcular_comision`), activado por `COMISION_MODO` (`plana` default, `sombra`, `variable`) en `backend/app/core/config.py`.

- **RN-CM1 (base comisionable):** la comisión variable se calcula sobre `edw.fact_ventas_detalle.margen_bruto` de la línea (grupos A/B/C de `comision_matriz_categorias`) o sobre `subtotal_neto` (grupo S — servicios, y líneas sin costo registrado bajo la tasa mínima de la salvaguarda 2). Líneas con `|subtotal_neto| < COMISION_UMBRAL_SUBTOTAL_X` (default 1.0) se reclasifican a grupo X (tasa 0%) — cortesías/redondeos, mismo espíritu que la convención de `pct_margen=0` de la auditoría 07 H8.
- **RN-CM2 (clasificación por código, no por nombre):** la matriz de categorías indexa por `dim_producto.clase`/`subclase` (código SAP), nunca por `nombre_clase` — verificado 100% vacío en el catálogo vigente al momento de la auditoría 30 (H2). El match más específico gana: `(clase, subclase)` exacto > `(clase, NULL)` > comodín `('*', NULL)`.
- **RN-CM3 (perfil de margen agregado, no por línea):** el perfil de margen por categoría (`GoalRepository.get_margin_profile_by_category`, insumo de la clasificación A/B/C/S/X) se calcula como `SUM(margen_bruto)/SUM(subtotal_neto)` agregado — nunca `AVG(margen_bruto/subtotal_neto)` por línea, que se distorsiona por las líneas de subtotal casi nulo (H3, hasta -20.699× de ratio en líneas individuales).
- **RN-CM4 (factor de crédito, cobertura de datos limitada):** el factor de ajuste por plazo se resuelve por `dim_formapago.dias_plazo` de la línea (`comision_factores_credito`, tabla completa de 7 tramos 0–90+ días). En el EDW actual solo hay tráfico real en 0 y 30 días (H4) — los tramos > 30 días son configuración latente sin historial que la respalde todavía; se documenta explícitamente en la simulación para no sobre-prometer a gerencia un ajuste fino que el ERP no soporta hoy.
- **Factor por tipo de vendedor (brecha B1):** `edw.dim_vendedor` no distingue externo/interno ni tiene fecha de ingreso — se gestiona en `public.comision_config_vendedor` (mantenida por gerencia), con default `externo`/factor 1.0 para cualquier vendedor sin fila explícita (nunca se penaliza por omisión).
- **Rollback:** `COMISION_MODO=plana` (default) dejar el comportamiento de la regla 15 sin cambios; el motor variable (`commission_engine.calcular_comision_variable`) es una función pura adicional, nunca reemplaza `calcular_comision`.

**Actualización 2026-07-15 (`docs/features/plan_actualizacion_modulo_metas_comisiones.md`, `docs/auditoria/35_actualizacion_modulo_metas.md`):**

- **RN-CM5 (configuración vigente AL CIERRE del período, no "hoy"):** tanto el cálculo real (`CommissionService._calcular_variable`, usado por `/commissions` y `/mi-comision`) como la simulación retroactiva (`CommissionSimulationService.simular`) resuelven la matriz de categorías y los factores de crédito vigentes a `commission_engine.fecha_referencia_periodo(anio, mes)` (el último día de ESE mes, acotado a "hoy" si el período está en curso) — nunca a la fecha de la consulta. Antes el cálculo real no pasaba fecha y siempre usaba la configuración vigente hoy sin importar qué período se consultaba (el fix de la auditoría 34 H-8 solo se había aplicado a la simulación).
- **RN-CM6 (inmutabilidad real de liquidaciones "oficiales"):** una vez que existe un snapshot en `public.comision_liquidaciones` con `modo='oficial'` (dinero real, `COMISION_MODO=variable`) para un período ya cerrado, `CommissionService._calcular_variable` lo devuelve tal cual — nunca lo recalcula ni lo reescribe, incluso si la matriz de categorías o los factores de crédito cambiaron después. Antes cada vista de un período cerrado (`GET /commissions`, `GET /mi-comision`) recalculaba con la configuración vigente en ese momento y sobrescribía (`UPSERT`) el snapshot existente, contradiciendo el propio docstring del modelo ("snapshot congelado", salvaguarda 6) y el `UniqueConstraint(anio, mes, id_vendedor_origen, esquema, modo)` de la tabla. El modo `sombra` (piloto, no paga) sigue refrescándose en cada consulta a propósito — solo `oficial` es inmutable.
- **RN-CM7 (paridad de bonos entre simulación y liquidación real):** `CommissionSimulationService.simular` calcula los 3 bonos complementarios (venta cruzada aceptada, cliente nuevo/reactivado, cobranza sana) con la misma función pura `calcular_bonos_periodo` (`app/services/commission_bonus.py`, extraída de `CommissionService`) que usa el cálculo real, en el mismo patrón de dos pasadas (pre-bonos → bonos reales → comisión final). Antes la simulación siempre pasaba `bonos_total=0.0`, subestimando sistemáticamente el costo del esquema variable frente al panel que gerencia usa como "argumento decisivo" para activarlo.
- **Brecha conocida, no corregida (RN-CM6/H4 de la auditoría 35):** `comision_config_vendedor` (tipo externo/interno, factor) no tiene vigencia histórica — un cambio de tipo de vendedor se aplicaría retroactivamente si se recalcula un período cerrado que aún no se ha congelado por primera vez. El impacto queda acotado por RN-CM6 a la primera congelación; requiere agregar vigencia a esa tabla para cerrarse del todo (cambio de esquema, fuera de alcance de esta sesión).

**Actualización 2026-07-30 (Comisión sobre Cobros, `docs/features/plan_comisiones_sobre_cobros.md`, `docs/auditoria/44_comisiones_sobre_cobros.md`, RN-CM8..RN-CM13):**

La regla que realmente rige la comisión en la empresa hoy no es sobre venta facturada sino sobre **cobranza efectiva**, con tasa por tramo de días de cobro; se incorpora como configuración adicional del esquema Variable (fórmula `cobranza`, `public.comision_formula`), sin tocar el motor por margen/categoría ni el esquema plano (`COMISION_MODO` intacto como rollback).

- **RN-CM8 (devengo por fecha de efectivización, no por recepción del cheque):** `edw.fact_cobros_cuotas.fecha_sk` = `fp_cxc_cuotas.banfec` (cuándo el dinero se hace efectivo), NUNCA `fectra` (cuándo se registró el cobro). Verificado contra Producción: 47,4% de los cobros con cheque postfechado (`tiptra='CP'`) cruzan de mes entre ambas fechas (desfase promedio 35,5 días; $366.688 de $839.412 en ene-2025..jul-2026).
- **RN-CM9 (tramos de días de cobro por perfil):** `dias_cobro = banfec - fecemi` (piso en 0 por 12 filas históricas con `banfec` anterior a `fecemi`, mínimo -25 días), materializado en el ETL. `public.comision_tramos_cobranza` resuelve la tasa por el primer tramo (`dias_hasta` ascendente) que cubre `dias_cobro`; perfiles `externo`/`interno` (2,00/1,75/0,75/0,50/0,00% a 21/60/90/120/365 días) y `jefe_agencia` (1,00% en el primer tramo, resto igual) — semilla exacta del cuadro de negocio, reproducida en `commission_engine.calcular_comision_cobranza` y validada contra la verdad de campo de feb-2026 (VEN13: $963,00).
- **RN-CM10 (instrumento de pago como dimensión degenerada):** `edw.fact_cobros_cuotas.tipo_instrumento` (`EF`/`CP`/`DP`/`CH`/`TA`/`ND`/`NC`) es un varchar en el hecho, no una FK a `dim_formapago` — esa dimensión proviene de un extractor estático de 3 filas y deja el 100% de `fact_cobros_cxc` en el centinela `-1`; repetir ese patrón habría reintroducido el mismo defecto.
- **RN-CM11 (contado/crédito por `conpag`, contraintuitivo):** el componente "1% de ventas de contado de la agencia" (perfil `jefe_agencia`) filtra `dim_formapago.codforpag = 'E'` = CONTADO y `'C'` = CRÉDITO — verificado contra Producción (786/786 facturas `'C'` generan CxC, 0/1493 `'E'` lo hacen). Nunca asumir por la inicial.
- **RN-CM12 (notas de débito excluidas):** cobros con `numcco` de prefijo `ND` (`es_nota_debito`) se excluyen de la base comisionable, replicando el filtro del reporte del ERP (`substring(numcco,1,2)<>'ND'`).
- **RN-CM13 (fórmula como configuración, no código):** `public.comision_formula`/`comision_formula_componente` modelan la comisión como una tubería ORDENADA de componentes de un catálogo cerrado (`base_lineas_venta`, `base_cobranza`, `contado_agencia`, `factor_tipo_vendedor`, `multiplicador_cumplimiento`, `devoluciones`, `bonos`) con operador `sumar`/`restar`/`multiplicar` por paso (`commission_engine.evaluar_formula`) — nunca evaluación de expresiones arbitrarias.

**Corrección de diseño 2026-07-30 (petición explícita del usuario tras revisar la Fase 4 -- migración `0009_formula_unica_unificada`):** la primera versión de RN-CM13 modelaba `base_lineas_venta` y `base_cobranza+contado_agencia` como DOS fórmulas alternativas ("actual"/"cobranza") entre las que gerencia "activaba" una u otra -- el usuario corrigió que esto es conceptualmente erróneo: **"las comisiones variables son un todo"**, un solo total por vendedor que SUMA margen/categoría + cobranza + contado de agencia, nunca un esquema que reemplaza al otro. Corregido: **una sola fórmula** (`clave='variable'`, sin concepto de "activar" -- se eliminó el endpoint `/formula/{id}/activar` y el selector de fórmulas del panel) con los 7 componentes combinados: las 3 bases se SUMAN, el total se multiplica por `factor_tipo_vendedor` y `multiplicador_cumplimiento`, y al final se resta `devoluciones` y se suma `bonos`. **RN-CM14 (un solo motor para cálculo real y simulación):** se extrajo `commission_variable_engine.calcular_comision_variable_completa` (usado por `CommissionService` y por las 3 rutas de `CommissionSimulationService` -- `simular`, `reconstruir_mes_especifico`, `proyectar_comision_variable`) para que el simulador de gerencia deje de subestimar el costo real: antes llamaba directo a `commission_engine.calcular_comision_variable` (solo líneas de venta) y nunca reflejaba la cobranza ni el contado de agencia, aunque ambas configuraciones ya existieran en el panel. Validado en vivo contra el EDW real: VEN13/feb-2026 pasa de `comision_base=200,82` (solo líneas) a `comision_base=1.163,42` (líneas + cobranza sumadas) tras activar la fórmula unificada.

**Actualización 2026-07-31 (Sobrecumplimiento, umbral de pago al 90% y desglose del simulador, `docs/features/plan_comisiones_sobrecumplimiento_umbral_y_desglose.md`, auditoría 45 — `docs/auditoria/45_sobrecumplimiento_umbral_y_desglose.md`, RN-CM15/RN-CM16):**

- **RN-CM15 (multiplicador de cumplimiento configurable, reemplaza los tramos fijos):** el multiplicador del componente `multiplicador_cumplimiento` de la fórmula variable deja de resolverse desde constantes de módulo (`UMBRAL_EXCELENTE/META/CERCA` + `COMISION_MULT_EXCELENTE/CERCA`+`COMISION_PISO_LEJOS`) y pasa a una tabla con vigencia, `public.comision_tramos_cumplimiento` (migración `0012_tramos_cumplimiento`) — mismo patrón que `comision_tramos_cobranza`. `commission_engine.resolver_tramo_cumplimiento` (función pura) resuelve el tramo por el primer `[pct_desde, pct_hasta)` que cubre el % de cumplimiento; si la tabla queda sin filas vigentes, cae a `TRAMOS_CUMPLIMIENTO_FALLBACK` (`commission_variable_engine.py`), que reproduce byte a byte los 4 tramos previos a esta auditoría — red de seguridad, no una forma de reintroducirlos a propósito. El esquema plano legacy (`calcular_comision`, `COMISION_MODO='plana'`) **no se modifica** — conserva sus 4 tramos fijos (`UMBRAL_*`), decisión deliberada para no cambiar dos esquemas a la vez y poder atribuir cualquier diferencia observada durante el piloto en sombra.
- **RN-CM16 (semilla: sin comisión bajo 90%, escala de sobrecumplimiento sobre el escalón plano):** petición explícita del usuario -- (1) un vendedor comisiona solo desde el 90% de cumplimiento de su meta (el tramo 80-89%, que antes pagaba con multiplicador 0.7×, queda en 0.0×); (2) el sobrecumplimiento (>100%) deja de ser un único escalón plano (1.2× sin importar cuánto se exceda) y pasa a una escala: 1.20× (100-110%), 1.35× (110-125%), 1.50× (≥125%). `perfil` admite `NULL` (aplica a todos los perfiles, la semilla actual) o un perfil específico (externo/interno/jefe_agencia) para diferenciación futura sin migración nueva -- descartada explícitamente en esta pasada. Cada tramo tiene un `bono_fijo` opcional (sembrado en `$0`, activarlo es decisión de gerencia) que se suma al componente `bonos` de la fórmula -- el beneficio adicional al sobrecumplimiento pedido por el usuario, sin crear un componente nuevo en el catálogo cerrado (`COMPONENTES_FORMULA`). El multiplicador se aplica **antes** de restar devoluciones y sumar bonos (orden vigente de la fórmula unificada): un vendedor bajo el 90% recibe `$0` en el paso `multiplicador_cumplimiento`, pero los bonos (venta cruzada, cliente nuevo, cobranza sana) se siguen sumando después -- decisión deliberada (premian una conducta específica, no el cumplimiento de meta), visible en el desglose del simulador.
- **Desglose de la construcción de la comisión (sin regla de negocio nueva, solo transparencia):** el simulador (`POST /gerencia/goals/commission-simulation`, ambos modos -- reconstrucción de mes específico y proyección al próximo mes) expone `componentes: [{orden, componente, etiqueta, operador, monto, es_factor, acumulado_tras_paso}]`, la traza completa de `commission_engine.evaluar_formula` con etiquetas legibles (`ETIQUETAS_COMPONENTES_FORMULA`, fuente única). En la proyección (promedio de 3/6 meses), los componentes `sumar`/`restar` se promedian; los `multiplicar` (`factor_tipo_vendedor`, `multiplicador_cumplimiento`) no se promedian porque son constantes entre los meses históricos simulados (config vigente hoy, cumplimiento neutro forzado). Un componente inactivo en la fórmula vigente **no aparece** en el desglose -- nunca se muestra como `$0.00`, que sugeriría falsamente que aportó.
- **Hallazgo de auditoría, no una regla de negocio (H-5, documentado y NO corregido por decisión explícita del usuario):** el bono de cliente nuevo/reactivado (`COMISION_BONO_CLIENTE_NUEVO`, $50/cliente) no distingue vendedores de cartera de códigos de venta de mostrador con alta rotación de compradores ocasionales -- verificado contra el EDW real, un vendedor de mostrador (`VEN01`, "ALMACEN EL REY") generó $25.600 de este bono en un solo mes (512 de 677 clientes calificados como "nuevos"), muy por encima de su propia base comisionable de líneas+cobranza ($514,57). El usuario indicó explícitamente no tocar este comportamiento en esta sesión -- queda expuesto en el desglose del simulador (visible, no oculto) para que gerencia lo evalúe, ver `docs/auditoria/45_sobrecumplimiento_umbral_y_desglose.md` §1.2 y §4.

> **Nota (2026-07-14):** los módulos "Gerencia: Cartera y Flujo de Caja" y "Bodega: Compras y
> Proveedores" que documentaban las secciones 19 y 21 de esta lista se implementaron, se
> auditaron (auditorías 31 y 33) y luego se **retiraron del alcance por decisión de producto**
> (no por un problema de datos). Los fixes de ETL aplicados durante la auditoría 31
> (`fact_pagos_cxp` duplicándose 6x por corrida, `fact_cobros_cxc.sucursal_sk` sin resolver)
> **se mantienen** — son correcciones de datos válidas independientes del módulo. El código y las
> reglas de negocio específicas de ambos módulos se eliminaron de este documento y del código;
> los reportes de auditoría 31/33 se conservan como registro histórico en `docs/auditoria/`.

## 19. Módulo Ventas: Cartera de Clientes 360 (RN-V1..RN-V3)

Reglas del módulo de Cartera de Clientes 360 (`docs/features/propuesta_nuevos_modulos_roi.md` §4, auditoría 32 — `docs/auditoria/32_modulo_ventas_cartera_360.md`). Compone los 3 modelos ML ya servidos (`churn_rf`, `segmentation`, `association`) sin entrenar nada nuevo; umbrales parametrizados por env (`VENTAS360_*` en `backend/app/core/config.py`).

- **RN-V1 (priorización en dos etapas con churn real, mejora de verificación 2026-07-14):** la cartera de un `codven` puede tener hasta ~31,000 clientes (algunos códigos de vendedor son en realidad cuentas de sucursal, ej. "ALMACEN EL REY", no un individuo) — correr `churn_rf` sobre toda la cartera en cada request no es viable (auditoría 32 H1). La lista de trabajo diaria (`GET /analytics/ventas/cartera360/lista-trabajo`) resuelve esto en dos etapas: (1) shortlist barata de hasta `VENTAS360_CANDIDATOS_ENRIQUECER` (default 300) candidatos por `valor_histórico × factor_alerta_frecuencia` (una sola consulta SQL agregada, sin modelo); (2) el churn real de ESE shortlist se consulta en un solo lote (`PredictionService.get_churn_risk_batch` — una consulta SQL con `IN` + una inferencia vectorizada del modelo, no N round-trips), y el ranking final usa `prioridad = valor_histórico × (1 + probabilidad_abandono_real)`, truncado a `VENTAS360_MAX_CARTERA` (default 100). Verificado contra el EDW real: 0.51–0.57s incluso para la cartera de 31,000 clientes (VEN01). Todo cliente devuelto en la lista ya trae su `probabilidad_abandono` real — el detalle bajo demanda (`GET /.../clientes/{cliente_id}/detalle`) solo agrega lo que la lista no trae: segmento RFM y recomendaciones de venta cruzada.
- **RN-V2 (caída de frecuencia, sin ML):** un cliente tiene `alerta_caida_frecuencia = true` cuando `dias_sin_comprar > 2 × frecuencia_promedio_dias` (intervalo promedio histórico entre compras del propio cliente). Deriva directo de `fact_ventas_detalle`, sin ningún dato ni modelo nuevo.
- **RN-V3 (self-scope a la cartera propia, sin override):** a diferencia de `resolve_sucursal_filter` (que permite a gerencia/administrador ver todas las sucursales), este módulo no tiene "ver todos los vendedores" — cada usuario, incluido gerencia/administrador, queda acotado a `current_user.id_vendedor_origen` (mismo patrón `_requerir_vendedor` de `sales.py`). El panel del supervisor (`GET /analytics/ventas/cartera360/tasa-recuperacion`) es la única excepción: gerencia/administrador ven la tasa agregada de todos los vendedores, un `ventas` ve solo la suya.
- **Registro de gestión (`public.gestion_cartera_eventos`):** mismo espíritu que la telemetría de Venta Cruzada (`public.recomendaciones_eventos`, RN-CS2) — el vendedor marca el resultado de cada contacto (`contactado`/`recompro`/`perdido`) con 1 clic, creando el dato de efectividad que antes no existía. Nombres reales de cliente vía `public.cliente_lookup` (regla de negocio 8), acotados siempre por la cartera propia del vendedor (RN-V3) — extiende el precedente ya existente de `catalog_repository.search_clientes()` (autocompletar de Venta Cruzada, ya accesible al rol `ventas`) a la cartera completa, no un mecanismo nuevo de exposición de PII.

**Actualización 2026-07-15 (`docs/features/plan_actualizacion_modulo_ventas.md`, `docs/auditoria/34_actualizacion_modulo_ventas.md`):**

- **RN-V4 (RLS de cartera para churn/recomendaciones/segmento, cierra una fuga real):** `GET /analytics/ventas/churn-risk`, `/recommendations`, `/clientes/{cod}/segmento` y `GET .../cartera360/clientes/{id}/detalle` restringen el `cliente_id` consultado a la cartera propia del vendedor autenticado (`CatalogRepository.cliente_pertenece_a_vendedor`: al menos una venta histórica real con ese vendedor; `PermissionDeniedError` → 403 si no pertenece). `gerencia`/`administrador` no tienen esta restricción (mismo criterio de privilegio que `resolve_sucursal_filter`). Antes cualquier `ventas` autenticado podía consultar cualquier cliente del sistema, incluido el docstring de `cartera360.py` que afirmaba una restricción que el código no aplicaba.
- **RN-V5 (grano de `metas_comerciales_operativas` sin sucursal, aplicado a `/analytics/ventas/goals`):** `AnalyticsRepository.get_sales_performance` restringe las metas a los vendedores que vendieron en la sucursal consultada durante el período (subconsulta contra `fact_ventas_detalle`), nunca por una columna `sucursal` en la tabla de metas — esa columna no existe (regla 10: grano `(anio, mes, id_vendedor_origen)`). Antes el filtro roto (`m.sucursal = :sucursal`) hacía que este endpoint —el KPI principal del dashboard de Ventas— devolviera 500 en el 100% de los requests de un usuario `ventas` real, porque `resolve_sucursal_filter(allow_override=False)` siempre fuerza su propia sucursal. `query_ranking` del mismo método gana el filtro de sucursal que le faltaba (antes mostraba el ranking global de la empresa incluso con un filtro de sucursal activo).
- **Deduplicación de doble-click en Cartera 360:** `POST .../cartera360/gestion` ignora un segundo submit idéntico (mismo usuario/cliente/evento) dentro de `CARTERA360_DEDUPE_DOBLE_CLICK_SEGUNDOS` (default 10s), devolviendo el registro ya creado en vez de duplicarlo — protege `tasa_recuperacion` (KPI del supervisor) de inflarse por clics accidentales, sin imponer una regla de "una gestión por día".
- **Umbral de churn "riesgo alto" configurable:** `settings.CHURN_UMBRAL_RIESGO_ALTO` (default 0.5) reemplaza el literal hardcodeado en `get_churn_risk`/`get_churn_risk_batch`. Distinto de `NOTIF_CHURN_UMBRAL` (0.7, cuándo notificar proactivamente) a propósito — propósitos distintos, mismo nombre de dominio.
- **Selector de sucursal retirado del dashboard de Ventas:** `/analytics/ventas/*` nunca honra un override de sucursal para ningún rol (gerencia/administrador ven siempre el consolidado global, `ventas` siempre su propia sucursal) — se eliminó el selector de UI (`GlobalBranchSelector`) que aparentaba filtrar sin efecto real. El selector de período (`GET /gerencia/goals/periods`, RBAC ampliado a `ventas` por no exponer datos sensibles) sí es funcional y propaga `anio`/`mes` a `/analytics/ventas/goals`.

## 20. Módulo de Notificaciones Inteligentes Segmentadas por Rol (RN-N1..RN-N4)

Reglas del módulo de Notificaciones (`docs/features/plan_modulo_notificaciones.md`, auditoría 31 — `docs/auditoria/31_modulo_notificaciones.md`). Generaliza el patrón ya validado de notificaciones de Bodega (`warehouse_service.get_notificaciones`) a los 4 roles, agregando persistencia + estado de lectura para eventos puntuales. Sin modelos ML nuevos (reutiliza `demand_rf`, `churn_rf`, `isolation_forest`, `sales_rf`); umbrales parametrizados por env (`NOTIF_*` en `backend/app/core/config.py`).

- **RN-N1 (segmentación por rol y RLS):** toda notificación tiene `rol_destino` (catálogo cerrado de `public.roles`) y opcionalmente `usuario_id` (NULL = visible a todo el rol). Ventas filtra estrictamente por `id_vendedor_origen` del token; Bodega por `codalm`/`todos_los_almacenes`, replicando el mismo criterio RLS que ya usan sus endpoints de analítica (mismo patrón de `warehouse.py`/`sales.py`). Un usuario nunca ve notificaciones fuera de su alcance de datos, aunque comparta rol con otro usuario.
- **RN-N2 (calculadas vs. persistidas):** las notificaciones **calculadas** (stock, forecast, churn) se generan al vuelo en cada `GET /notificaciones`, sin estado de lectura ni fila en base de datos. Las **persistidas** (metas generadas, liquidaciones, anomalías) se insertan una única vez vía `notification_service.emitir(...)`, con deduplicación de `(tipo_evento, contexto)` en una ventana de `NOTIF_DEDUPE_HORAS` (default 24h) para no repetir el mismo evento en cada polling.

## 21. Módulo Administrador: usuarios, auditoría y MLOps (RN-A1..RN-A4)

Reglas de la actualización del módulo Administrador (`docs/features/plan_actualizacion_modulo_admin.md`, auditoría 36 — `docs/auditoria/36_actualizacion_modulo_admin.md`). `GET /analytics/admin/anomalies` **no es un listado con ventana temporal**: es una consulta puntual del modelo `anomaly` sobre un `transaccion_id` dado, sin nada que paginar.

- **RN-A1 (ventana por defecto del log de auditoría):** `GET /analytics/admin/audit-logs` filtra por `fecha_desde`/`fecha_hasta`/`usuario`(codusu)/`modulo` y pagina con el contrato `Page[T]` ya usado en Bodega. Sin `fecha_desde` explícito, se acota a los últimos `ADMIN_AUDIT_LOGS_VENTANA_DIAS` (default 30) en vez de todo el histórico de `edw.Fact_Logs_Auditoria`.
- **RN-A2 (política de contraseña, fuente única de verdad):** `PASSWORD_MIN_LENGTH`/`PASSWORD_REGEX` en `backend/app/core/config.py` (default: 8+ caracteres, mayúscula+minúscula+dígito+carácter especial) se validan en los 3 puntos de entrada de contraseña (`UserCreate`, `UserUpdate`, `UserChangePassword`, `schemas/user.py`). El `pattern` HTML del formulario de `UsersManagement.tsx` queda como ayuda de UX, no como control de seguridad — un request directo a la API sin pasar por el frontend queda sujeto a la misma regla.
- **RN-A3 (colisión de email/vendedor en edición):** `UserService.update()` valida que el nuevo `email` o `id_vendedor_origen` no pertenezcan ya a otro usuario antes de persistir (`ConflictError` → 409), igual que `create()`. Antes solo `create()` validaba esto; editar con un valor duplicado dejaba que la restricción `UNIQUE` de Postgres fallara como `IntegrityError` no capturada (500 genérico).
- **RN-A4 (retrain síncrono-antes-de-encolar):** `POST /admin/modelos/retrain` valida la existencia de `settings.ML_SOURCE_DIR` de forma síncrona en el router, antes de encolar el `BackgroundTask` de `TrainingService`. En un entorno sin el código de `ml/` montado (prod-like), responde `400` con mensaje explícito en vez de un `200 "iniciado"` que fallaría en silencio (el fallo real solo quedaba antes en `GET /admin/modelos/status`, que ningún dashboard consulta).
- **Verificaciones que NO requirieron cambio (confirmadas en la auditoría 36):** el catálogo de roles ya es estable por orden de seed (`1=gerencia, 2=administrador, 3=ventas, 4=bodega`, `edw/08_seed_roles_usuarios.sql`) — el riesgo real no era el id sino que el formulario de creación preseleccionaba `administrador` por defecto (corregido en el frontend seleccionando por nombre de rol, no por id fijo); `get_current_user` (`core/deps.py`) ya rechaza cada request de un usuario con `es_activo=false`, incluso con JWT vigente — no solo en el siguiente login; `GET /admin/modelos/models` ya reporta `NO_CARGADO` por modelo faltante/corrupto sin 500 (`model_loader.is_loaded`).

## 22. Módulo Gerencia: KPIs, forecast y procedencia de datos (RN-G1..RN-G3)

Reglas de la actualización del módulo Gerencia (`docs/features/plan_actualizacion_modulo_gerencia.md`, auditoría 33 — `docs/auditoria/33_actualizacion_modulo_gerencia.md`).

- **RN-G1 (alcance real de filtros del forecast de ventas):** `GET /gerencia/sales-prediction` (modelo `sales_rf`) solo respeta `sucursal` (RLS)/`vendedor`/`almacen`. `categoria` **no existe como columna** en el dataset de entrenamiento del modelo (`ml/src/data/make_dataset.py::fetch_daily_sales` no la referencia) y `start_date`/`end_date` tampoco aplican: el walk-forward usa una ventana continua fija de `limit_days=730` días hacia atrás porque las features de lag/rolling requieren historial ininterrumpido — un rango arbitrario del usuario rompería esas features. Los KPIs (`/gerencia/kpis`) y el desglose por categoría (`/gerencia/revenue-by-category`) sí soportan los 6 filtros completos (`sucursal, start_date, end_date, categoria, vendedor, almacen`) hasta el SQL — la asimetría es intencional y documentada en la UI (aviso junto al panel de forecast en `DashboardGerencia.tsx`), no un bug de propagación.
- **RN-G2 (ingresos totales calculados en backend):** `GPKPIGerencia.ingresos_totales` = `SUM(subtotal_neto) − SUM(total_linea_devolucion)` calculado en SQL por `AnalyticsRepository.get_management_kpis` (misma definición de Venta Neta de la regla 13). Antes el servicio descartaba ese valor y el frontend lo reconstruía sumando `ventas_por_sucursal`, un mapa que excluye sucursales con neto exactamente `0` y podía divergir del total real en casos borde.
- **RN-G3 (procedencia de datos real, sin mocks en producción):** `GET /system/provenance` (cualquier usuario autenticado, sin restricción de rol — la barra de procedencia se muestra en los 4 roles) expone `ultima_carga_dw` (`MAX(edw.etl_control.ultimo_etl_ok)` con `estado='SUCCESS'`) y el estado real de los 6 modelos (`algoritmo`/`entrenado_en`/`activo` desde `ModelLoader`, mismo mapa de nombres de negocio `MODEL_DISPLAY_NAMES` que usa el panel MLOps de Administrador). Reemplaza el mock estático `PROVENANCE_FACTS` (`services/mocks/provenance.mock.ts`, eliminado) que `ProvenanceRail` mostraba como si fuera el estado real en cada página autenticada de la plataforma.
- **RN-N3 (estado de lectura por rol destino):** cuando `usuario_id IS NULL` (notificación a todo el rol), `leida_por` acumula los ids de cada usuario que la marcó leída; la notificación deja de considerarse "no leída" para ese usuario específico sin afectar a los demás miembros del rol.
- **RN-N4 (degradación con gracia):** cada generador (calculado o disparador de emisión persistida) se ejecuta envuelto en `try/except Exception as e: logger.error(...)`, devolviendo lista vacía en caso de fallo — un generador caído nunca debe tumbar el resto de la campana ni el request completo, siguiendo el mismo patrón ya validado en `prediction_service.py`.


## 23. Madurez BI: universo costeable, margen y ROI (RN-BI1..RN-BI3)

Reglas de la Etapa 1 de `docs/features/plan_madurez_bi_toma_decisiones.md` (auditoría 39 —
`docs/auditoria/39_madurez_bi_toma_decisiones.md`, hallazgos H-01/H-02/H-05). Validadas con
`SELECT` contra el EDW; **no hubo escrituras a Producción**.

- **RN-BI1 (universo costeable del margen):** el costo de línea de `edw.fact_ventas_detalle`
  se deriva en el ETL como `cantidad × articulos.ultcos` (`etl/transformers/fact_transformer.py`),
  donde `ultcos` es un costo **por artículo en unidad de compra** y `cantidad` está en la unidad
  de **venta**. Cuando ambas unidades difieren, el costo resultante no tiene sentido económico.
  Caso confirmado: `Z-9001` (BATERIAS CHATARRAS, clase `Z-999`, `dim_producto.unidad='KL'`) se
  compra por batería y se vende por kilo — ratio costo/precio de **308×**; sus 95 líneas
  concentran el **94,9%** del costo de mercadería de todo el EDW y llevaban el margen publicado
  en Gerencia a **−1.563%**. Por eso las clases listadas en `ANALYTICS_CLASES_EXCLUIDAS_MARGEN`
  (default `Z-999`) quedan fuera del universo de **margen y ROI**, pero **no** del de
  **ingresos** — vender chatarra es ingreso real; lo que no es real es su costo derivado.
  Es el mismo criterio de negocio ya aplicado en el pipeline ML de demanda ("chatarra, no es un
  artículo de reposición", Fase 2 de `docs/features/plan_mejora_pipeline_ml.md`).
  **Alcance de la corrección:** capa de presentación (KPIs de Gerencia). El campo
  `fact_ventas_detalle.margen_bruto` conserva el valor derivado y lo consume Comisiones
  Variables (regla 13) — **pendiente de validar** la unidad de `ultcos` contra Producción antes
  de corregir el ETL (auditoría 39, H-01 recomendación 2). Exposición medida: 24 líneas de
  clase `Z-999` en 2025-2026 arrastran −$115 millones de `margen_bruto` sobre un solo código de
  vendedor; con `COMISION_MODO=plana` (default) no hay pago incorrecto, pero
  `POST /commission-simulation` sí lee ese campo.
- **RN-BI2 (ROI = retorno sobre costo de mercadería vendida):** sustituye al antiguo
  `roi_estimado = margen × 1,15` (una constante sin regla de negocio, aplicada además sobre un
  valor que ya era un porcentaje). Definición vigente, calculada en SQL sobre el EDW:

  > `ROI = (venta_neta − costo_mercaderia_vendida) / costo_mercaderia_vendida × 100`

  sobre el universo costeable de RN-BI1. Valor de referencia medido en el histórico completo:
  **10,61%** (margen **9,59%**). Es `NULL` — y se comunica como *"sin base de cálculo"*, nunca
  como `0%` — cuando el período no tiene costo de mercadería con el que comparar. El umbral del
  semáforo es `ANALYTICS_ROI_UMBRAL_SANO` (default 10,0), antes un `>= 10` literal.
- **RN-BI3 (regla 1 aplicada por su semántica, no por la centinela):** los filtros de analytics
  aplican `dim_estado_documento.estado_factura = ESTADO_DOCUMENTO_VALIDO` ('P', regla 1) además
  de excluir la fila centinela `-1`. Hoy ambos filtros son equivalentes porque
  `dim_estado_documento` tiene solo 2 filas y la centinela es justamente la única con
  `estado_factura='A'`; la equivalencia es una coincidencia del catálogo actual y se romperá en
  silencio en cuanto el ETL cargue un estado adicional.

## 24. Motor de Metas Comerciales v2: fórmula configurable y trazabilidad real (RN-MT1..RN-MT6)

Reglas de `docs/features/plan_motor_metas_configurable.md` (auditoría 46 —
`docs/auditoria/46_motor_metas_configurable.md`). Petición explícita del usuario: revisar
exactamente la fórmula de meta, hacerla editable por el gerente, usar el mismo mes de años
anteriores además de meses recientes, evitar que un mes atípico infle la meta futura, y
fundamentar el método con literatura de gestión de fuerzas de venta (requisito de tesis).

Auditoría previa (solo `SELECT` + ejecución en modo lectura del motor real dentro de
`bi_backend`) cuantificó el problema con un caso real, no una hipótesis: recalculando hoy la
meta de agosto-2026 de `VEN13` con el motor v1, el resultado es **$76.941,13** — un 58% menos
que la meta persistida ($121.359,95) para el mismo vendedor/período, sin forma de reconstruir
la diferencia porque el motor v1 no guardaba ninguna traza del cálculo (H-5). La mediana de
cumplimiento del único mes cerrado disponible (julio-2026, 9 vendedores) es 95,7%, con 33% de
vendedores bajo el 90% de pago (auditoría 45) — no es una ruptura agregada catastrófica, pero
sí confirma mecanismos concretos de sobre-ajuste (H-3: ningún techo posterior a los factores de
negocio; H-4: un mes atípico reciente se filtraba sin atenuar a la tendencia). Ver la auditoría
46 para el detalle completo con cifras reales.

- **RN-MT1 (fórmula v2 — nivel × estacionalidad × tendencia, con banda de alcanzabilidad
  final):** `IQRGoalCalculationEngine.calcular` (`backend/app/services/goal_calculation_engine.py`)
  reemplaza el diseño anterior ("promedio del mismo mes de años previos" + "promedio de los
  últimos 4 meses", combinados 50/50 sin ningún tope posterior) por la descomposición clásica de
  series de tiempo — nivel robusto (media ponderada tras excluir outliers de Tukey y atenuar
  meses atípicos de ML) × índice estacional ratio-to-moving-average (normalizado, calculado
  **sobre la serie ya desestacionalizada**) × factor de tendencia reciente (mismo mecanismo del
  motor v1: mediana de razones intermensuales, acotada y atenuada por coeficiente de
  variación) — acotada por una **banda de alcanzabilidad sobre la meta FINAL**, después de
  aplicar presión comercial y factor de tipo de vendedor (antes el único guardarraíl se aplicaba
  ANTES de esos factores de negocio, dejando la meta final sin ningún tope real). Fundamentación:
  quota setting bottom-up basado en histórico (Zoltners, Sinha & Lorimer, *The Complete Guide to
  Sales Force Incentive Compensation*) combinado con la descomposición nivel-estacionalidad-
  tendencia de Hyndman & Athanasopoulos (*Forecasting: Principles and Practice*).
- **RN-MT2 (índice estacional propio del vendedor, con respaldo de empresa mes a mes):** el
  índice estacional se calcula **por mes calendario individual** (no todo-o-nada por vendedor):
  un mes con `>= min_anios_estacional` (default 2) años distintos de historia usa el promedio de
  ese vendedor, normalizado a media 1.0 sobre los meses con señal propia; un mes sin suficientes
  años cae al índice agregado de toda la empresa (`GoalRepository.get_indice_estacional_empresa`,
  resuelto UNA VEZ por lote de generación, no por vendedor); sin ningún índice disponible, el
  factor es neutro (1.0). Auditoría 46 (A-0.3): con la ventana de 36 meses, el 80,6% de los
  pares (vendedor, mes-calendario) de la fuerza de ventas activa ya tienen ≥2 años del mismo mes
  — el índice propio es viable para la mayoría, no la excepción.
- **RN-MT3 (banda de alcanzabilidad, corrige H-3):** la meta final se acota a
  `[banda_alcanzabilidad_min, banda_alcanzabilidad_max] × referencia_alcanzable`, donde
  `referencia_alcanzable` = mediana desestacionalizada de los últimos `meses_referencia_alcanzable`
  meses × índice estacional del mes objetivo — "lo que este vendedor realmente vende en un mes
  como este", calculada sin ponderar por señales de ML (una referencia de alcanzabilidad debe
  ser conservadora, nunca artificialmente reducida). Semilla: `[0.85, 1.20]`.
- **RN-MT4 (período objetivo explícito, corrige H-1):** el mes/año objetivo del cálculo es
  **siempre el que pide el llamador** (`GoalMLService.generate_proposals(anio, mes)` pasa ambos
  al motor) — nunca se infiere como "el mes siguiente al último dato disponible" (comportamiento
  legado, conservado solo como valor por defecto de la función pura para comparación/pruebas). La
  ventana de histórico usa exclusivamente meses **estrictamente anteriores** al objetivo.
- **RN-MT5 (escalera de degradación explícita, corrige H-6):** el `metodo` persistido distingue
  4 niveles según el respaldo estadístico real disponible para el mes objetivo puntual —
  `estacional_propio_v2` (≥2 años del mismo mes), `estacional_empresa_v2` (histórico propio
  insuficiente, índice de empresa), `tendencia_robusta_v2` (sin ningún índice estacional, ≥4
  meses), `equipo_prorrateado_v2` (<4 meses: se usa la **mediana** — no el promedio, que un
  vendedor de volumen atípico distorsiona — del monto y de las unidades del resto del equipo del
  período). Un vendedor sin ningún mes de historia no recibe meta propuesta automáticamente.
- **RN-MT6 (trazabilidad real persistida, corrige H-5):** `metas_comerciales_operativas` gana
  `trazabilidad_calculo` (JSONB) con la traza completa del cálculo que produjo `monto_meta`
  (histórico usado, método, índice estacional aplicado y su fuente, factor de tendencia, banda
  de alcanzabilidad y si actuó, meta antes/después de cada guardarraíl). El endpoint
  `GET /gerencia/goals/meta-sugerida?anio=&mes=` devuelve esa traza EXACTA cuando la meta ya fue
  generada para ese período (`es_trazabilidad_persistida=true`) — nunca un recálculo con el
  histórico o la configuración vigentes HOY; solo recalcula en vivo (etiquetado como tal) para
  metas anteriores a esta migración o períodos sin meta generada todavía. Regenerar
  (`generate_proposals`) siempre fuerza un recálculo fresco, nunca reutiliza una traza vieja.
  **Configuración editable (requisito 2):** `public.metas_config_parametros` (13 parámetros,
  fila viva por clave — sin vigencia histórica, a diferencia de `comision_tramos_cumplimiento`:
  una meta ya generada guarda su propia trazabilidad completa, así que un cambio de parámetro
  solo afecta a las metas que se generen desde ese momento) + bitácora en
  `comision_config_auditoria` (reutilizada) + pestaña "Fórmula de metas" en el panel de Gerencia.
  **Comisión variable siempre visible (requisito 9, H-8):** `CommissionService.get_commission_tracking`
  calcula la comisión variable de cada vendedor SIEMPRE (antes solo si `COMISION_MODO` en
  `sombra`/`variable`, dejando el panel "Comisiones devengadas" sin ninguna referencia del
  esquema variable mientras la empresa opera en `plana`, el 100% del tiempo hasta ahora);
  `COMISION_MODO` sigue controlando exclusivamente si el cálculo se persiste como snapshot
  oficial, nunca si se muestra. La tabla expone además el tramo/% de cumplimiento real de la
  auditoría 45 (no los 4 tramos fijos del esquema plano legacy), resolviendo fórmula/matriz/
  crédito/tramos UNA vez por período (mismo patrón de pre-resolución que
  `CommissionSimulationService`).

## 25. Reabastecimiento Inteligente: stock de seguridad, punto de reorden y priorización por riesgo (RN-RB1..RN-RB5)

Reglas del nuevo módulo `/bodega/reabastecimiento` (`docs/features/plan_reabastecimiento_inteligente.md`, auditoría `docs/auditoria/50_reabastecimiento_inteligente.md`; F0-F10 de un plan de 12 fases completados, solo F6 diferida -- ver el cierre de esta sección). Convive con el motor determinista existente de RN-B1/RN-B4 (`/bodega/necesidad-compra`) sin reemplazarlo — prioriza por **riesgo real de quiebre**, no por volumen de ventas.

- **RN-RB1 (stock de seguridad estocástico, degradación explícita):** `SS = z(nivel_servicio) × σ_demanda_diaria × √lead_time_dias` (Silver/Pyke/Peterson; Chopra & Meindl) cuando hay ≥`MESES_MINIMOS_ESTOCASTICO` (6) meses con venta en la ventana de 36 meses; con 1-5 meses degrada a un método "determinista" (`dias_seguridad_fallback × demanda_diaria_media`, mismo criterio de RN-B1); sin ningún mes con venta, `metodo_stock_seguridad="sin_historia"` y `SS=0` — nunca se inventa una varianza que los datos no sostienen. La demanda mensual (`fact_movimientos_inventario`, dirección por `tipdoc`, RN-3) se convierte a diaria dividiendo por `365.25/12`; `σ_diaria = σ_mensual / √(365.25/12)`.
- **RN-RB2 (punto de reorden y riesgo):** `ROP = demanda_diaria_media × lead_time_dias + SS`; `cobertura_dias = stock_actual / demanda_diaria_media`. Riesgo `critico` si la cobertura es menor a la mitad del lead time, `alto` si es menor al lead time completo, `medio`/`bajo` según margen sobre el ROP, `sin_demanda` si no hay ventas medibles en la ventana — clasificación explícita en vez de dejar como "Seguro" (mismo defecto ya corregido en Bodega §16 con el estado "Inmovilizado") cualquier artículo sin señal de demanda.
- **RN-RB3 (clasificación ABC/XYZ, umbrales propios calibrados contra datos reales):** ABC por Pareto de `valor_consumo` (venta neta 12 meses) con cortes 80%/95% (excluye `Z-9001`/`Z-999`, chatarra, mismo criterio que `demand_rf`); XYZ por terciles del coeficiente de variación de la demanda mensual — `CORTE_XYZ_X=0.39`/`CORTE_XYZ_Y=0.61`, calculados con `percentile_cont` sobre el catálogo real de este negocio (auditoría 50, A-0.4). **Deliberadamente NO reutiliza** `BODEGA_CV_ALTA`/`BODEGA_CV_MEDIA` (RN-B9): esos umbrales están calibrados para decidir transferencias entre bodegas, un caso de uso distinto, y aplicados aquí dejaban al 96,6% del catálogo en una sola clase (inútil para priorizar).
- **RN-RB4 (lead time, resolución por especificidad, sin origen real derivable del EDW hoy):** el EDW no tiene fecha de orden de compra (`Fact_Compras` solo trae `fecha_sk` de la factura recibida) ni de solicitud de transferencia (`Fact_Transferencias` solo tiene un `fecha_sk`) — confirmado con `SELECT` real (auditoría 50, A-0.1/A-0.2), sin conectividad a SAP disponible para verificar `encabezadoordcom`/`renglonesordcom` como fuente futura. El lead time se resuelve de una tabla de configuración editable por gerencia/administrador (`public.reabastecimiento_lead_time`, migración `0016_reabastecimiento`), con especificidad producto > categoría > proveedor > `settings.BODEGA_LEAD_TIME_DIAS` (default global, nunca sembrado como fila — se pasa explícitamente como parámetro). `lead_time_origen` en la respuesta declara cuál de los 4 niveles resolvió el valor, para que la UI nunca presente un dato configurado como si fuera medido.
- **RN-RB5 (nivel de servicio por clase ABC, editable):** `public.reabastecimiento_politica` (semilla: A=97,5%, B=95%, C=90%, mismo patrón de "más servicio a los artículos de mayor valor" que la literatura de quota/inventory management) resuelve el `z` de la tabla normal estándar usado en RN-RB1; editable vía `PUT /analytics/bodega/reabastecimiento/politica/{clase_abc}` (solo gerencia/administrador), sin bitácora dedicada en esta fase (columnas `actualizado_por`/`actualizado_en` en la fila, trazabilidad básica; no se integró con `comision_config_auditoria` porque su `CHECK` de nombres de tabla no incluye las tablas nuevas — documentado como recorte de alcance, no descuido).

**RN-RB6 (explicabilidad por artículo, F5):** `GET /reabastecimiento/lista/{codart}/explicacion` devuelve el mismo `ItemReabastecimiento` que produciría la lista completa para ese `codart`, reutilizando `get_lista_reabastecimiento` con los filtros de alcance (almacén/categoría/proveedor/tipo_movimiento/horizonte) pero **sin propagar los post-filtros de riesgo/ABC/XYZ** de la lista (`solo_criticos`/`riesgo`/`clase_abc`/`clase_xyz` se ignoran a propósito) — la clase ABC de un artículo depende de la curva de Pareto de TODO el catálogo filtrado, así que calcularla en aislamiento para un solo `codart` le daría una clase distinta a la que ese mismo artículo tiene en la lista, rompiendo la invariante de que la lista y el detalle cuentan la misma historia. `404` explícito si el `codart` no existe en el alcance de filtros actual.

**RN-RB7 (alertas inteligentes, extienden sin duplicar, F7):** `GET /reabastecimiento/alertas` (`ReplenishmentService.get_alertas`) cubre solo 2 señales nuevas -- `detectar_cambio_brusco` (demanda del último mes fuera de `media ± 2σ` del histórico, control estadístico de proceso clásico, exige ≥`MESES_MINIMOS_ALERTA`=3 meses de historia y `σ>0`) y `detectar_tendencia_decreciente` (3 meses consecutivos estrictamente decrecientes, sin empates). El riesgo de quiebre (🔴 del plan) y el sobrestock (🟠) **NO se repiten aquí** -- son el mismo evento real que `stock_critico`/`prediccion_agotamiento`/"Inmovilizado" del generador de Bodega ya existente (`WarehouseService.get_notificaciones`), solo calculado con una fórmula distinta; mostrar ambos por el mismo artículo en la misma campana confundiría sin agregar información. `NotificationService._generar_bodega` (RN-N del §20) se extiende con estas 2 señales nuevas -- `ReplenishmentService` se inyecta como una dependencia más, sin tocar el generador existente.
**RN-RB8 (simulador what-if, solo lectura, F8):** `POST /reabastecimiento/simular` recalcula el resumen bajo `niveles_servicio`/`lead_time_default_dias` hipotéticos -- **nunca escribe** en `reabastecimiento_politica`/`_lead_time` (verificado con un test que aserta que ningún método de escritura del repositorio de configuración se invoca durante la simulación); devuelve `resumen_actual` (config real vigente) junto a `resumen_simulado`, para que la UI compare directamente sin que el usuario tenga que recordar el estado "antes". Cambiar la política real sigue siendo exclusivamente `PUT /politica`/`PUT /lead-times` (gerencia/administrador).
**RN-RB9 (propuestas de compra persistidas, snapshot congelado, F9):** `public.propuesta_compra`/`propuesta_compra_linea` (migración `0017_propuesta_compra`) -- `POST /propuestas` congela un snapshot de la Lista Inteligente vigente (solo líneas con `cantidad_sugerida > 0`) en el momento de crearla, incluida la justificación completa por línea (mismo criterio que `comision_liquidaciones`: una propuesta ya creada no se recalcula al mirarla, para que aprobar/rechazar sea sobre lo que el usuario realmente vio). Máquina de estados cerrada: `borrador -> aprobada` o `borrador -> rechazada` únicamente -- una propuesta ya decidida no admite una segunda decisión (`ValidationError` explícito), para que el estado persistido siga siendo la decisión real tomada una sola vez. `transferencia_decision` (cierre de H-5, hoy `useState` efímero en `BodegaAlmacenes.tsx`) **queda fuera de esta migración** -- pertenece a un router/página distintos (`warehouse.py`, no `replenishment.py`) y se documenta como trabajo de seguimiento explícito, no una omisión silenciosa.
**RN-RB10 (limpieza del dashboard de Bodega, F10):** `DashboardBodega.tsx` retira 3 de los 6 gráficos originales del módulo (§7.2 del plan): G2 "Matriz de Rotación y Rentabilidad" (scatter rotación×margen) se elimina sin reemplazo directo en este dashboard -- era análisis financiero puro que duplicaba el Dashboard Ejecutivo (H-10); su sustituto real, la clasificación ABC/XYZ que sí define una política de inventario accionable, ya vive en `/bodega/reabastecimiento` (un enlace directo reemplaza el gráfico). G3 "Top 20 Productos con Mayor Salida" se elimina -- ordenaba por volumen de ventas, exactamente lo opuesto de priorizar por riesgo de quiebre; el hook `useTopProductos` se conserva únicamente porque alimenta el selector de producto de G1 (histórico + predicción), no para renderizar el gráfico retirado. G4 "Distribución de Salidas por Categoría" (pie) se elimina -- descriptivo puro, ninguna acción se derivaba de él. **Deliberadamente NO se decomisionan** los endpoints backend `/rotacion-matriz`/`/salidas-categoria`/`/top-productos` (siguen sirviendo `WarehouseService.get_reporte_justificacion`, el reporte de Gerencia, y el selector de G1) ni `/necesidad-compra` (RN-B1/RN-B4) -- A-0.7 de la auditoría 50 ya había cuantificado que el cambio de fórmula altera el estado de más de la mitad del catálogo evaluado, una decisión de política de negocio que le corresponde a gerencia tomar explícitamente, no a un refactor de UI.

Con RN-RB1..RN-RB10, el corte F0-F10 del plan de 12 fases queda cerrado. **Pendiente, explícitamente diferido (F6, no descuido):** `metodo_demanda` sigue siendo siempre `"estadistico"`/`"sin_historia"` -- conectar `demand_rf` como fuente de demanda para la Lista Inteligente exigiría, primero, un backtest por SKU (A-0.8 de la auditoría 50, nunca completado por falta de conectividad al contenedor `ml`/SAP en este entorno) que demuestre que el modelo gana al baseline estadístico en el grano `(producto, almacén)` -- y, aun si lo hiciera, correr walk-forward de `demand_rf` para las ~8.150 filas del catálogo completo en cada request de `/lista` sería computacionalmente impracticable (miles de inferencias por request, frente al costo casi nulo de la estadística agregada ya usada); conectarlo solo al endpoint de un artículo individual (`/explicacion`) evita el problema de volumen pero no resuelve la falta del backtest que lo justifique. Forzar el modelo sin esa evidencia repetiría exactamente el error que ya llevó a decomisionar `goals_rf`/`sales_rf` (docs/auditoria/20_.../49_...md) -- se deja fuera de esta sesión hasta que exista el backtest real.
