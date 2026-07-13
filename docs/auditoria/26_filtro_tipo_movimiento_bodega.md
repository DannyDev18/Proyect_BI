# 26. Módulo Bodega: reemplazo del filtro "Buscar artículo" por "Tipo de movimiento" (Kardex)

**Fecha:** 2026-07-13
**Alcance:** `backend/app/repositories/warehouse_repository.py`, `backend/app/services/warehouse_service.py`,
`backend/app/api/routes/warehouse.py`, `backend/app/schemas/warehouse.py`,
`frontend/src/components/bodega/BodegaFilterBar.tsx`, `frontend/src/store/bodegaFiltersStore.ts`,
`frontend/src/services/bodega.ts`, `frontend/src/types/bodega.ts`, `docs/features/modulo_bodega.md`.

## Motivo del cambio

Solicitud explícita del usuario: el filtro global de texto libre "Buscar artículo" (§1.1 del dashboard de
Bodega, `ILIKE` sobre `codart`/`nombre_articulo`) se reemplaza por un filtro de **tipo de movimiento de
Kardex**, que restringe los artículos mostrados a los que tienen al menos un movimiento del tipo
seleccionado en `edw.fact_movimientos_inventario.tipo_movimiento` (columna que refleja `kardex.tiporg`).

## Catálogo (regla de negocio §3, `docs/auditoria/02_reglas_negocio_validadas.md`)

| código | etiqueta |
|---|---|
| FAC | Ventas (facturas) |
| TRA | Transferencias entre bodegas |
| EGR | Egresos |
| CPA | Compras |
| DEV | Devoluciones |
| ING | Ingresos |
| BOD | Ajustes de bodega |
| DEC | Ajustes / decrementos |

Catálogo cerrado, expuesto como constante `TIPOS_MOVIMIENTO` en `warehouse_repository.py` (mismo patrón
que otros catálogos fijos del proyecto, p.ej. `public.roles`) y servido en `GET /analytics/bodega/filtros`
como `tipos_movimiento: [{codigo, etiqueta}]`.

## Cambios aplicados

- **Backend:** el parámetro `busqueda` se renombró a `tipo_movimiento` en todo el módulo Bodega
  (repositorio, servicio, rutas — mismo alcance que el filtro que reemplaza: KPIs, gráficos G1-G6, matriz
  de inventario, transferencias sugeridas). En `WarehouseRepository._filtros_snapshot` el fragmento SQL
  cambió de `(p.codart ILIKE :x OR p.nombre_articulo ILIKE :x)` a un `IN (SELECT ... FROM
  edw.fact_movimientos_inventario ...)` filtrando por `tipo_movimiento`, mismo patrón que el filtro de
  `proveedor` (subconsulta a otra tabla de hechos vía `dim_producto`).
- **Frontend:** `BodegaFilterBar.tsx` reemplaza el `<input>` de búsqueda por un `<Select>` poblado desde
  `catalogos.tipos_movimiento`; el store (`bodegaFiltersStore.ts`) cambió `busqueda: string` (vacío por
  defecto) por `tipoMovimiento: string | null`; `services/bodega.ts` y `types/bodega.ts` siguen el mismo
  renombre.

## Impacto

- Los usuarios ya no pueden buscar un artículo por código/nombre en el dashboard de Bodega. No se detectó
  otro punto de la UI que ofrezca esa búsqueda (el `producto_cod` de `/salidas-forecast` y
  `/prediccion-compras-mes` se alimenta del drill-down de las tablas, no de un buscador de texto).
- No se requirió migración de datos ni cambios de esquema del EDW: `tipo_movimiento` ya existía en
  `edw.Fact_Movimientos_Inventario` (poblado por `kardex_extractor.sql`, regla de negocio §3).
