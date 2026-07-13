# Plan de Ejecución: Módulo Bodega (Dashboard de Inventario y Abastecimiento)

> Generado por la skill `module-requirements-analyzer` a partir de `docs/features/modulo_bodega.md`.
> Fecha: 2026-07-10. Auditoría asociada: `docs/auditoria/23_modulo_bodega.md`.

## 1. Análisis de Requerimientos

- **Objetivo:** que el encargado de bodega decida *qué, cuándo y cuánto* comprar o transferir, con base en histórico del EDW + predicción de demanda ML, priorizando transferencias entre bodegas antes de comprar.
- **Componentes identificados:** dashboard (6 filtros, 6 KPIs, 6 gráficos), panel de inventario por almacén, matriz de transferencias inteligentes, plan de compras (proyección 45 días), sistema de notificaciones, 3 reportes para gerencia con export.
- **Roles afectados:** `bodega` (usuario principal, filtrado por su sucursal), `gerencia` y `administrador` (vista consolidada). El checker existente `bodeguero_checker` en `backend/app/api/routes/warehouse.py` ya cubre exactamente estos roles.

## 2. Descomposición Técnica

### 2.1 Capa de Datos (EDW) — SIN cambios de DDL ni ETL

Decisión clave (ver auditoría 23): **todos los datos requeridos ya existen en el EDW**; no se crean tablas nuevas ni se toca `etl/` (que además está roto en el working tree: `etl/loaders/` borrado sin commit — riesgo documentado en CLAUDE.md).

| Requerimiento del .md | Fuente real en el EDW |
|---|---|
| Inventario actual (`fact_inventario_actual`) | `edw.fact_inventario_snapshot` (última `fecha_sk`), con `stock_actual`, `valor_inventario`, `punto_reorden`, alertas |
| Salidas históricas | `edw.fact_movimientos_inventario` con `es_salida = TRUE` (regla de negocio 3: dirección por `tipdoc`, nunca por signo) |
| Punto de reorden (`dim_producto.punto_reorden` — NO existe) | `fact_inventario_snapshot.punto_reorden`; si es 0, se calcula dinámico: `salidas_diarias × lead_time + stock_seguridad` (fórmulas sección 6.3 del .md, parámetros configurables) |
| Costo (`dim_producto.ultcos` — NO existe con ese nombre) | `dim_producto.costo_promedio` y `fact_inventario_snapshot.costo_promedio` |
| Transferencias (`fact_transferencias` nueva — NO se crea) | Ya existen en `edw.fact_movimientos_inventario` como pares SA/EN (regla de negocio 4, `tiporg='TRA'`); las *sugerencias* se calculan al vuelo, no se persisten |
| Categoría | `dim_producto.clase` / `nombre_clase` |
| Proveedor por artículo | `edw.fact_compras` JOIN `dim_proveedor` (último proveedor que suministró el artículo) |

Limitación conocida (auditoría 05): `fact_inventario_snapshot` solo está poblada "hacia adelante" (<1% pre-2026) → las tendencias "vs mes anterior" de KPIs de inventario usan el snapshot más antiguo disponible dentro de la ventana y se degradan con gracia a `null` si no hay mes anterior.

### 2.2 Pipeline ETL — sin tareas

No se requieren extractores/transformers/loaders nuevos. Nada que tocar en `etl/`.

### 2.3 Modelos de ML — reutilización, sin entrenar modelos nuevos

El .md pide 4 "modelos"; se mapean así (mismo precedente que Metas: estadística determinística donde un modelo no aporta — auditoría 20):

| Modelo pedido | Implementación |
|---|---|
| Predicción de salidas | **Reutiliza `demand_rf_model` existente** vía `walk_forward_forecast` (mismo patrón que ventas en `PredictionService.get_sales_forecast`), por producto, con banda de confianza basada en MAE real del sidecar |
| Predicción de agotamiento | Derivada: `días_hasta_reorden = (stock − punto_reorden) / salida_diaria_prevista` usando el forecast del modelo de demanda |
| Clasificación de rotación | Estadística pura: `rotación = costo_ventas / inventario_promedio`, umbrales del .md (>4 buena, 2–4 regular, <2 mala) |
| Sugerencia de transferencia | Regla determinística del propio .md (§3.2): excedente >60 días en origen, déficit <15 días en destino, cantidad para llevar destino a 30 días sin exceder excedente |

No hay `.pkl` nuevos → no se toca `ml/` ni los contratos.

### 2.4 Backend (FastAPI) — el grueso del trabajo

Nuevos archivos (patrón routes → services → repositories, excepciones de dominio):

- `backend/app/repositories/warehouse_repository.py` — todo el SQL (filtros con bind params, exclusión de centinelas `-1`).
- `backend/app/services/warehouse_service.py` — fórmulas (§6.3), semáforos, prioridades (§8.3), lógica comprar-vs-transferir (§8.1/8.2), generación de notificaciones (§4.2), armado de reportes (§2).
- `backend/app/schemas/warehouse.py` — contratos Pydantic.
- Extensión de `backend/app/api/routes/warehouse.py` (prefijo real `/api/v1/analytics/bodega`):

| Endpoint | Requerimiento |
|---|---|
| `GET /kpis` | §1.2 — 6 KPIs con filtros globales |
| `GET /filters` | §1.1 — catálogo de almacenes/categorías/proveedores |
| `GET /salidas-forecast` | §1.3 G1 — histórico + predicción ML por producto o top-10 |
| `GET /rotacion-matriz` | §1.3 G2 — scatter rotación × margen |
| `GET /top-productos` | §1.3 G3 — top 20 salidas con stock y tendencia |
| `GET /salidas-categoria` | §1.3 G4 — distribución por categoría con comparativa |
| `GET /stock-reorden` | §1.3 G5 — estado vs punto de reorden (Crítico/Cerca/Seguro) |
| `GET /necesidad-compra` | §1.3 G6 y §3.3 — proyección de compra (horizonte 30/45 días) |
| `GET /inventario-matriz` | §3.1 — stock por producto × almacén (pivot) |
| `GET /transferencias-sugeridas` | §3.2 — matriz de transferencias con prioridad y ahorro |
| `GET /notificaciones` | §4 — alertas calculadas al vuelo (sin persistencia) |
| `GET /reportes/justificacion` | §2.1 — JSON completo del reporte |
| `GET /reportes/transferencias` | §2.2 |
| `GET /reportes/analisis-mensual` | §2.3 |
| `GET /reportes/{tipo}/excel` | §2.1 — export XLSX (openpyxl, nueva dependencia) |

- **Export PDF:** se resuelve en el frontend con vista imprimible (print CSS) — evita dependencias pesadas de render server-side; el Excel sí es server-side (openpyxl).
- **RBAC:** `bodeguero_checker` + `resolve_sucursal_filter(allow_override=False)` existentes (bodega ve solo su sucursal; gerencia/admin consolidan).
- **Parámetros de negocio configurables** en `app/core/config.py` (no hardcodes): lead time (7d), días stock de seguridad (5d), umbrales 15/20/30/45/60/90 días, umbrales de rotación 2/3/4.

### 2.5 Frontend (React 19 + Vite)

- `src/types/bodega.ts` — tipos de los contratos nuevos.
- `src/services/bodegaService.ts` — cliente Axios de los endpoints (elimina el uso de `mocks/bodega.mock`).
- `src/hooks/bodega/` — hooks TanStack Query por endpoint, con clave dependiente de filtros.
- `src/store/bodegaFiltersStore.ts` — Zustand con `persist` (sessionStorage) para los 6 filtros globales (§1.1 "persistir en la sesión").
- `src/pages/DashboardBodega.tsx` — reescritura: fila de 6 KPIs + 6 gráficos (Recharts: ComposedChart con banda de confianza, ScatterChart de burbujas, BarChart horizontales, PieChart, tablas con barras de progreso).
- `src/pages/BodegaInventarioAlmacen.tsx` — panel §3 (matriz por almacén + transferencias sugeridas con aprobar/rechazar local + plan de compras).
- `src/pages/BodegaReportes.tsx` — reportes §2 con export Excel (descarga) y PDF (print).
- `src/components/bodega/NotificationBell.tsx` — campana en el header con las notificaciones del endpoint.
- Rutas nuevas en `src/router/AppRouter.tsx` + permisos en `src/constants/permissions.ts`.

## 3. Orden de Ejecución (Fases)

1. **Auditoría previa** — `docs/auditoria/23_modulo_bodega.md` (antes de tocar código). ✔ requisito CLAUDE.md
2. **Backend repositorio** — SQL sobre `fact_movimientos_inventario` + `fact_inventario_snapshot` + `fact_compras`.
3. **Backend servicio + schemas + rutas** — fórmulas, notificaciones, reportes (cargar skill `backend-ml-serving` antes: los endpoints exponen predicciones del modelo de demanda).
4. **Backend export Excel** — openpyxl en `requirements.txt`.
5. **Frontend datos** — tipos, servicio, store de filtros, hooks.
6. **Frontend UI** — dashboard, panel por almacén, reportes, campana de notificaciones, rutas.
7. **Validación** — `pytest backend/tests`, `py_compile`, build/lint del frontend, actualización de docs.

## 4. Dependencias y Secuencia

`Auditoría 23 → warehouse_repository → warehouse_service → schemas → routes → (frontend types → service → hooks → páginas)`. El frontend no puede empezar antes de fijar los contratos Pydantic. ML/ETL/EDW: sin dependencias (no se modifican).

## 5. Checklist de Auditoría (CLAUDE.md)

- [x] Sin PII nueva (solo productos/almacenes, sin clientes)
- [x] Sin cambios SCD2 (solo lectura de `dim_producto` con `es_vigente = TRUE`)
- [x] Sin extractores nuevos (no aplica tokenización)
- [ ] Sin hardcodes: umbrales de días/rotación en `config.py` con env vars
- [x] Sin cambios de ETL/idempotencia (no aplica)
- [ ] Centinelas `-1` excluidos de catálogos y agregados
- [ ] Contratos API en `app/schemas/warehouse.py`
- [ ] RBAC: `bodega` filtrado por sucursal, `gerencia`/`administrador` consolidado
- [x] Sin secretos nuevos
- [ ] Reglas nuevas documentadas en auditoría 23 y `02_reglas_negocio_validadas.md`

## 6. Riesgos y Mitigaciones

| Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|
| `fact_inventario_snapshot` sin histórico pre-2026 → tendencias "vs mes anterior" vacías | Alta | Medio | Degradar a `null`; el frontend muestra "—" en la tendencia |
| `punto_reorden` del snapshot en 0 para muchos SKU | Media | Alto | Cálculo dinámico con fórmula §6.3 cuando el configurado sea 0 |
| Forecast por producto lento para "Top 10" (10 walk-forwards) | Media | Medio | Horizonte corto (30 días), forecast solo del producto seleccionado; top-10 usa proyección estadística (media móvil) |
| BD no disponible en el entorno de desarrollo actual | Media | Bajo | Validación por tests unitarios con SQL revisado + `py_compile`; queda pendiente validación contra EDW vivo |
| Volumen de `fact_movimientos_inventario` (~948k) en queries de matriz | Media | Medio | Agregaciones con ventana de 30/90 días vía `dim_fecha`, límites y paginación |

## 7. Hitos

| Hito | Validación |
|---|---|
| Auditoría 23 creada | Documento en `docs/auditoria/` |
| Backend completo | `pytest backend/tests` verde + `py_compile` |
| Frontend completo | `npm run build` + oxlint sin errores |
| Documentación | CLAUDE.md/auditoría 23 actualizados |

## 8. Documentación Requerida

- `docs/auditoria/23_modulo_bodega.md` (antes y después de implementar)
- Reglas nuevas (umbrales de abastecimiento) en `docs/auditoria/02_reglas_negocio_validadas.md`
- Actualizar sección API de `CLAUDE.md` si cambia el mapa de endpoints

## 9. Calidad de Datos

- Todas las queries excluyen centinelas `-1` en catálogos y usan `es_vigente = TRUE` en `dim_producto`.
- Salidas SIEMPRE por `es_salida = TRUE` (nunca signo de cantidad — regla 3).
- Snapshot: siempre "última fecha disponible", nunca suma de histórico (duplicaría conteos — patrón ya validado en `get_inventory_alerts`).

## 10. Notas

- El .md de requerimientos nombra columnas/tablas que no existen (`dim_producto.punto_reorden`, `ultcos`, `fact_transferencias`, `fact_inventario_actual`); este plan las mapea a los objetos reales sin inventar esquema nuevo.
- "Informe semanal 5 días antes de fin de mes": se implementa como endpoint on-demand + notificación calculada por fecha (sin scheduler; el crontab del proyecto está planificado para Fase 6 de la hoja de ruta).
- Aprobar/rechazar transferencias: al no existir flujo transaccional hacia el ERP (solo lectura), la aprobación marca la sugerencia en la UI y la incluye/excluye del reporte; no escribe en SAP.
