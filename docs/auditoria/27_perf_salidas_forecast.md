# 27. Performance: gráfico "Histórico y Predicción de Salidas" (Bodega G1) lento

**Fecha:** 2026-07-13
**Alcance:** `backend/app/repositories/warehouse_repository.py` (`get_salidas_serie_diaria`),
`edw/04_indices.sql`.

## Síntoma

El usuario reportó que el gráfico G1 del dashboard de Bodega ("Histórico y Predicción de
Salidas", `GET /analytics/bodega/salidas-forecast`) es el más lento del dashboard.

## Medición

Con la app corriendo en Docker (`bi_backend`, `bi_postgres_edw`), se midió el tiempo de
respuesta de los endpoints del dashboard de Bodega con las mismas condiciones (usuario
`bodega_quito`, sin filtros adicionales):

| Endpoint | Tiempo (antes) |
|---|---|
| `/kpis` | ~104 ms |
| `/salidas-forecast` | **~330-400 ms** |
| `/rotacion-matriz` | ~27 ms |
| `/top-productos` | ~10 ms |
| `/salidas-categoria` | ~12 ms |
| `/stock-reorden` | ~49 ms |
| `/necesidad-compra` | ~44 ms |

`salidas-forecast` es 3-40× más lento que sus pares.

## Causa raíz

`WarehouseRepository.get_salidas_serie_diaria` (usada para el modo "Top 10 productos
(agregado)", `producto_cod=None`) construye dos consultas contra
`edw.fact_movimientos_inventario` (~949 369 filas): una subconsulta para hallar los 10
artículos con más salidas del rango, y la consulta externa para la serie diaria de esos
10 artículos. Ambas incluían **siempre** `JOIN edw.dim_almacen al` y `JOIN edw.dim_sucursal su`,
aunque no hubiera filtro de almacén/sucursal activo (esos alias solo se referencian en el
`WHERE` cuando `_filtros_snapshot` recibe esos parámetros).

Con `EXPLAIN (ANALYZE, BUFFERS)` contra el EDW real:
- Con los JOIN innecesarios: **63 ms**, plan con `Parallel Seq Scan` completo de
  `fact_movimientos_inventario` filtrando `es_salida` en memoria (no hay índice que lo
  soporte bien combinado con esos JOIN adicionales).
- Quitando los JOIN innecesarios (mismo resultado, sin filtro de almacén/sucursal): **6.8 ms**,
  el planner usa un `Index Only Scan` sobre un nuevo índice parcial.

Los JOIN de más no cambian el resultado (son `INNER JOIN` sobre FKs que siempre resuelven),
pero desvían al optimizador hacia un plan mucho más caro.

## Fix aplicado

1. **Índice parcial nuevo** — `edw/04_indices.sql`:
   ```sql
   CREATE INDEX idx_fmi_salidas_fecha_prod ON edw.Fact_Movimientos_Inventario (fecha_sk, producto_sk)
       INCLUDE (cantidad_movimiento) WHERE es_salida;
   ```
   Cubre exactamente el patrón de esta consulta (filtrar `es_salida`, agrupar por
   `producto_sk` dentro de un rango de `fecha_sk`), permitiendo Index Only Scan.
   Aplicado también en caliente sobre el EDW de desarrollo (los DDL de `edw/` solo
   corren en volumen nuevo — regla del proyecto — así que en cualquier otro ambiente
   existente hay que aplicarlo manualmente igual que se hizo aquí).

2. **JOIN condicionales** — `get_salidas_serie_diaria` ahora solo une `dim_almacen`/
   `dim_sucursal` cuando `almacen`/`sucursal` vienen seteados, tanto en la subconsulta
   del top-N como en la consulta externa.

## Alcance no cubierto

El mismo patrón de JOIN incondicionales a `dim_almacen`/`dim_sucursal` vía
`_filtros_snapshot` existe en el resto de `WarehouseRepository` (KPIs, rotación, stock
por almacén, etc.). No se tocó ese código en esta pasada porque esos endpoints ya miden
por debajo de 50-100 ms (ver tabla de medición); si alguno se vuelve un cuello de botella
más adelante, el mismo patrón de fix (JOIN condicional + índice parcial dirigido) aplica.
