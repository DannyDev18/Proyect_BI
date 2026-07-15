# Plan de Actualización — Módulo Bodega (filtros, valores monetarios, transferencias, reportes)

> **Fecha:** 2026-07-14
> **Estado:** Propuesta (requiere auditoría previa `docs/auditoria/32_actualizacion_modulo_bodega.md` según flujo de `CLAUDE.md`)
> **Base:** módulo Bodega existente (auditorías 23 y 24, reglas RN-B1..B7). Sin modelos ML nuevos; se reutiliza `demand_rf` donde aplique.

## 0. Diagnóstico verificado en código (no supuesto)

| # | Reclamo del usuario | Causa raíz confirmada |
|---|---|---|
| D1 | "Los filtros no funcionan en reportes/Excel" | **Bug real:** `GET /analytics/bodega/reportes/{tipo}` y `/reportes/{tipo}/excel` (`warehouse.py:351-380`) solo reciben `almacen, categoria, proveedor`. El frontend envía `tipo_movimiento`, `fecha_desde`, `fecha_hasta` (`toQueryFilters`, `bodegaFiltersStore.ts:44`) pero el backend los descarta. Los servicios `get_reporte_*` (`warehouse_service.py:1013+`) tampoco los aceptan. |
| D2 | "Los filtros no funcionan en los gráficos" | Cobertura desigual: algunos endpoints aceptan los 6 filtros (`/kpis`, `/top-productos`, `/salidas-categoria`), otros no (`/rotacion-matriz` sin `tipo_movimiento` en fechas, `/stock-reorden` y `/necesidad-compra` sin fechas — el stock es una foto actual, pero las **salidas** que alimentan `salida_diaria` sí deberían respetar el rango). Falta una matriz endpoint × filtro con decisión explícita de qué aplica y qué no (un filtro de fecha sobre una foto de stock actual NO tiene sentido — hay que documentarlo y deshabilitarlo en la UI, no ignorarlo en silencio). |
| D3 | "Mostrar dinero además de unidades, solo cuando el tipo de movimiento involucra dinero" | Los gráficos G1/G3/G4 y KPIs solo exponen `unidades`. El EDW sí tiene el dato: `fact_ventas_detalle` (venta neta) y costo (`articulos.ultcos` → `costo_unitario` ya usado en rotación). Regla 3 del proyecto: la dirección/tipo la da `tipdoc` — los tipos que involucran dinero de venta son las salidas por facturación; entradas por compra involucran costo. |
| D4 | "Eliminar Estado de Stock vs Punto de Reorden del dashboard" | Tabla G5 en `DashboardBodega.tsx:350-376` (`useStockReorden`). Nota: el endpoint `/stock-reorden` NO se elimina — lo consume también la campana de notificaciones y potencialmente gerencia; solo se quita la tabla del dashboard. |
| D5 | "Mover Predicción de Necesidad de Compra a Status Almacén" | Sección G6 en `DashboardBodega.tsx:381-413` → mover a `BodegaAlmacenes.tsx`. Endpoint `/necesidad-compra` sin cambios de contrato. |
| D6 | "El motivo de transferencias no tiene fundamento estadístico" | `_transferencias_completo` (`warehouse_service.py:914-919`) genera un string plano con solo 2 datos (días de stock y salida diaria promedio). No expone: variabilidad de la demanda, tendencia, histórico monetario en destino, costo logístico vs beneficio, ni confianza de la estimación. |
| D7 | "Los reportes no son intuitivos" | `BodegaReportes.tsx:44-96` renderiza el JSON crudo recursivamente (claves `snake_case` "titulizadas", sin jerarquía visual ni resumen ejecutivo). `warehouse_export.py:61` hace lo mismo hacia Excel (volcado genérico sin formato). |

## 1. Fase 1 — Filtros consistentes de punta a punta (D1, D2)

**Objetivo:** los 6 filtros globales (`almacen`, `categoria`, `proveedor`, `tipo_movimiento`, `fecha_desde`, `fecha_hasta`) se aplican en TODO el módulo o se deshabilitan visiblemente donde no tienen sentido.

1. **Matriz endpoint × filtro** (entregable de la auditoría 32): para cada uno de los 13 endpoints de `/analytics/bodega`, documentar qué filtros aplica hoy, cuáles debe aplicar y cuáles no aplican conceptualmente (ej.: `fecha_desde/hasta` sobre stock actual = N/A; sobre salidas/rotación = SÍ).
2. **Backend:**
   - `/reportes/{tipo}` y `/reportes/{tipo}/excel`: agregar `tipo_movimiento`, `fecha_desde`, `fecha_hasta` como query params y propagarlos por `_generar_reporte` → `get_reporte_justificacion/transferencias/analisis_mensual` → repository. Los filtros aplicados deben quedar **impresos en el propio reporte** (sección "Filtros aplicados" en JSON y Excel) para que el usuario vea con qué se generó.
   - `/rotacion-matriz` y cualquier otro endpoint de la matriz con gaps: completar la propagación hasta el SQL del repository (verificar que `get_stock_por_almacen` / `get_salidas_*` realmente usan el parámetro y no solo lo reciben).
   - Validación de `tipo_movimiento` contra el catálogo cerrado (entrada `EN/AC`, salida `SA/AD`, transferencia `TRA` — regla de negocio 3/4), nunca texto libre.
3. **Frontend:**
   - `BodegaFilterBar`: deshabilitar (con tooltip explicativo) los filtros que no aplican a la vista actual según la matriz — nunca mostrar un filtro activo que se ignora en silencio (esa es la causa de la percepción "no funcionan").
   - Verificar que TODOS los hooks de `hooks/bodega.ts` incluyan los filtros en su `queryKey` (si un filtro no está en la key, TanStack Query sirve caché vieja y el gráfico "no reacciona" — sospechoso principal de D2).
4. **Tests:** integración por endpoint: misma consulta con y sin cada filtro debe producir resultados distintos sobre datos seed; test explícito de que el Excel respeta los filtros (generar con filtro, verificar contenido).

## 2. Fase 2 — Valores monetarios condicionados al tipo de movimiento (D3)

**Regla de negocio nueva (RN-B8, a validar contra el EDW antes de implementar):** los montos solo se muestran cuando el `tipo_movimiento` filtrado involucra dinero:
- **Salidas por venta** → monto = venta neta desde `fact_ventas_detalle` (fuente oficial de ventas; NO multiplicar unidades del kardex por precio — los movimientos de kardex no llevan precio de venta).
- **Entradas por compra** → monto = costo desde `fact_compras` / `costo_unitario`.
- **Transferencias (`TRA`) y ajustes** → sin monto de venta (mover cajas no es vender); mostrar solo valorización a costo si se decide en auditoría.

Implementación:
1. **Backend:** los schemas de `/kpis`, `/top-productos`, `/salidas-categoria`, `/salidas-forecast` ganan campos opcionales `monto_ventas: float | None` (y `moneda` implícita USD) — **aditivo, sin romper contrato**, poblados solo cuando el filtro `tipo_movimiento` corresponde a un tipo monetario; `None` en caso contrario. El servicio decide con un mapa `TIPOS_MONETARIOS` en `config.py` (no hardcodear en el servicio).
2. **Repository:** las consultas de salidas que hoy solo agregan `SUM(cantidad)` del kardex ganan un `LEFT JOIN`/subconsulta a `fact_ventas_detalle` por `(codart, fecha, almacén/sucursal)` para traer venta neta — cuidado con el grano: validar contra el EDW que el join no duplique (auditoría 32, método SELECT).
3. **Frontend:** los gráficos muestran un toggle o doble eje "Unidades / USD" que solo aparece cuando la respuesta trae `monto_ventas != null`; tooltips muestran ambos. Sin filtro monetario activo, la UI queda exactamente como hoy.

## 3. Fase 3 — Reorganización del dashboard (D4, D5)

1. Eliminar la tabla "Estado de Stock vs Punto de Reorden" de `DashboardBodega.tsx` (G5, líneas 350-376) junto con su estado local (`soloCriticos`, `stockPagination`, `useStockReorden`). El endpoint `/stock-reorden` se conserva (lo consumen las notificaciones y sigue disponible para otras vistas).
2. Mover "Predicción de Necesidad de Compra" (G6 + `useNecesidadCompra` + `compraColumns`) de `DashboardBodega.tsx` a `BodegaAlmacenes.tsx` (página "Status por Almacén"), respetando los filtros globales compartidos vía `bodegaFiltersStore` (ya es sessionStorage compartido — el movimiento es gratis en estado).
3. Revisar que el dashboard resultante mantenga una narrativa coherente: KPIs → forecast → rotación/categorías → top productos → predicción de compras del mes (`PrediccionComprasChart` se queda).

## 4. Fase 4 — Motivo de transferencias con fundamento estadístico (D6)

**Principio:** una transferencia gasta logística; la sugerencia debe demostrar que el destino SÍ venderá el artículo. Reemplazar el string plano por un objeto `justificacion` estructurado + score.

1. **Nuevas métricas por par (producto, origen, destino)** — todas calculables del EDW, sin ML nuevo (y donde exista, reutilizar `demand_rf` vía `prediction_service`, patrón del forecast por producto):
   - `demanda_destino`: media y **mediana** diaria de salidas en destino (ventana 90 días), con **coeficiente de variación** (CV) — demanda errática (CV alto) baja la confianza.
   - `tendencia_destino_pct`: tendencia de salidas del destino últimos 30 vs 90 días.
   - `venta_monetaria_destino`: venta neta del artículo en el destino últimos 90 días (desde `fact_ventas_detalle`) — el argumento en dinero que pide el usuario.
   - `dias_cobertura_origen_post` y `dias_cobertura_destino_post`: cobertura de ambos lados después de la transferencia (el origen no debe quedar desabastecido — salvaguarda).
   - `meses_con_venta_destino`: en cuántos de los últimos 6 meses el destino registró ventas del artículo (persistencia de la demanda, evita picos aislados).
   - `beneficio_neto_estimado`: `ahorro_por_no_comprar − costo_logistico_estimado`, con `BODEGA_COSTO_LOGISTICO_*` configurable en `config.py` (por defecto un % del valor transferido; parametrizable por env var, nunca hardcode).
   - `confianza`: alta/media/baja derivada de (CV, meses_con_venta, volumen de historia). **Sugerencias de confianza baja se muestran pero marcadas "revisar manualmente"** — nunca ocultas en silencio.
2. **Contrato:** `TransferenciaSugerida` gana campos opcionales (`justificacion: JustificacionTransferencia`, `confianza`, `beneficio_neto_estimado`) — aditivo; `motivo` (string) se conserva por compatibilidad, ahora generado desde la justificación.
3. **Umbral de emisión:** solo sugerir si `beneficio_neto_estimado > 0` y `meses_con_venta_destino >= BODEGA_MIN_MESES_VENTA` (nuevo setting, default 2) — esto responde directamente al reclamo "gastar dinero moviendo artículos que no se van a vender".
4. **Frontend (`BodegaAlmacenes.tsx`):** fila expandible con la justificación completa: mini-tabla de evidencia (demanda, tendencia, venta $ 90d, cobertura post, beneficio neto) + badge de confianza. La notificación de la campana (§4.2) incluye el beneficio neto.
5. **Documentar RN-B9** (criterios estadísticos de transferencia) en `02_reglas_negocio_validadas.md`, validando los cálculos contra el EDW con SELECT.

## 5. Fase 5 — Rediseño de reportes (D7) — el módulo de trabajo intensivo

**Principio:** cada reporte responde UNA pregunta de negocio en la primera pantalla; el detalle va después. Se abandona el render recursivo genérico.

1. **Backend — contrato tipado por reporte** (en vez de `dict` libre):
   - Cada reporte devuelve: `resumen_ejecutivo` (3-5 KPIs con etiqueta de negocio + interpretación en una frase: "Se recomienda comprar 42 artículos por $12.400; 8 son críticos"), `filtros_aplicados` (eco de los filtros, fase 1), `secciones` tipadas con columnas definidas (nombre de negocio, tipo, formato), y `generado_en`.
   - Schemas Pydantic por tipo de reporte en `schemas/warehouse.py` (reemplaza `ReporteBodegaResponse` genérico — cambio de contrato coordinado con el frontend en el mismo PR).
2. **Excel (`warehouse_export.py`):** una hoja "Resumen" (KPIs + filtros + fecha) y una hoja por sección con: encabezados de negocio en español, formato de moneda/porcentaje, anchos de columna, filas de prioridad Alta resaltadas, y autofiltro de Excel. Ya no un volcado del JSON.
3. **Frontend (`BodegaReportes.tsx`):**
   - Selector de reporte con tarjetas que explican **qué decisión soporta cada reporte** ("¿Qué comprar este mes y por qué?" / "¿Qué mover entre bodegas?" / "¿Cómo cerró el mes el inventario?").
   - Vista: banda de KPIs del resumen ejecutivo arriba → interpretación en lenguaje natural → tablas con columnas fijas diseñadas (no derivadas de claves JSON), ordenables, con prioridades destacadas.
   - Los filtros aplicados visibles en un chip-bar dentro del reporte (y en la impresión), para que nunca haya duda de qué datos incluye.
   - Mantener export PDF vía `window.print` con hoja de estilos de impresión revisada.
4. **Sesión de validación con usuario final** (criterio de aceptación explícito): el usuario debe poder decir qué le dice cada reporte en <30 segundos sin explicación.

## 6. Orden de ejecución, validación y entregables

| Fase | Riesgo | Validación |
|---|---|---|
| 0. Auditoría `docs/auditoria/32_actualizacion_modulo_bodega.md` + matriz endpoint × filtro + validación RN-B8/B9 contra EDW (solo SELECT) | — | Revisión doc |
| 1. Filtros E2E | Bajo (aditivo) | `pytest backend/tests/integration/` con casos por filtro; Excel con filtro verificado |
| 2. Montos condicionales | Medio (joins nuevos — riesgo de duplicación por grano) | Reconciliación SELECT: `SUM(monto)` del endpoint vs `fact_ventas_detalle` directo, mismos filtros |
| 3. Reorganización dashboard | Bajo (solo frontend) | oxlint + revisión visual; `/stock-reorden` sigue vivo (test de humo) |
| 4. Justificación transferencias | Medio (lógica estadística nueva) | Tests unitarios del cálculo con datos sintéticos (CV alto/bajo, sin historia); validación de 5 sugerencias reales contra EDW a mano |
| 5. Reportes | Alto en frontend (cambio de contrato) | Backend y frontend en el mismo PR; sesión con usuario final |

**Reglas transversales (del proyecto):** routers thin (routes → services → repositories); excepciones de dominio, nunca `HTTPException` en servicios; umbrales nuevos como settings `BODEGA_*` en `config.py` con env vars (cero hardcodes); RBAC intacto (`bodeguero_checker`, rol bodega forzado a su sucursal); Producción SAP no se toca (todo sobre el EDW); si se reutiliza `demand_rf`, siempre vía `prediction_service` con degradación con gracia y `ModelLoader` inyectado (nunca instanciado en endpoint). Al cierre de cada fase: actualizar auditoría 32 y reglas nuevas en `02_reglas_negocio_validadas.md`.
