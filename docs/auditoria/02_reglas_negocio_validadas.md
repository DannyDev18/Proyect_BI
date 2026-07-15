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

## 17. Módulo Venta Cruzada (Cross-Selling): formato de sugerencia y telemetría (RN-CS1, RN-CS2, RN-CS3)

Reglas del módulo de Venta Cruzada (`docs/features/plan_modulo_cross_selling.md`, auditoría 25 — `docs/auditoria/25_modulo_cross_selling.md`). Umbrales parametrizados por env (`CROSS_SELL_*` en `backend/app/core/config.py`):

- **RN-CS1 (formato de sugerencia):** dado un conjunto de `codart` en la canasta simulada (y opcionalmente un `cliente_id`), se devuelven hasta `CROSS_SELL_TOP_N` (default 5) sugerencias con `codart`, `nombre`, `precio` (`dim_producto.precio_oficial` vigente), `categoria` (`clase`), `score` y `motivo`. Se excluyen productos ya en la canasta y, si hay `cliente_id`, los ya comprados por ese cliente. El umbral `CROSS_SELL_MIN_LIFT` solo se aplica a fuentes en escala de lift (`coocurrencia`/`apriori`, >1 = afinidad real); el modelo publicado (`item_item`, similitud coseno en `[0,1]`) NO se filtra por ese umbral -- aplicárselo rechazaría siempre todas las filas (bug real encontrado y corregido en la verificación end-to-end de la auditoría 25, Fase 4). Si el artefacto no devuelve ninguna sugerencia para la canasta, se usa el fallback por popularidad de categoría (producto más vendido de la misma `clase` que no esté ya en la canasta). El factor de margen (`CROSS_SELL_PESO_MARGEN`) solo se aplica cuando `dim_producto.costo_promedio` es no nulo y > 0 (≈92% del catálogo vigente, auditoría 25 §1); si no, se ordena solo por score.
- **RN-CS2 (telemetría y conversión):** cada sugerencia mostrada al vendedor registra un evento `mostrada` en `public.recomendaciones_eventos`; el clic en "Agregar" registra `aceptada`. La tasa de conversión de un período = `count(aceptada) / count(mostrada)`. La "aceptación" es un registro en la plataforma BI, no una línea de factura en SAP (el ERP no se toca, regla de solo-lectura de Producción).
- **RN-CS3 (diversidad entre categorías, hallazgo de uso real 2026-07-13):** máximo `CROSS_SELL_MAX_POR_CATEGORIA` (default 2) sugerencias de una misma categoría entre las `CROSS_SELL_TOP_N` finales. El artefacto item-item entrena solo los top-20 vecinos por producto, y para algunos productos (p.ej. baterías) los 20 vecinos son TODOS de su misma categoría -- sin señal cruzada real disponible. Cuando la selección final queda concentrada en una sola categoría, se reemplazan hasta 2 sugerencias por los productos más vendidos de OTRAS categorías (`fuente: popularidad_otra_categoria`), para que el asistente siempre ofrezca opciones de venta cruzada real entre categorías, no solo variantes del mismo producto.

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

