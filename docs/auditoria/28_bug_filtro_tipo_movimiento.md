# 28. Bug: filtro "Tipo de movimiento" tumbaba KPIs y varios gráficos de Bodega (500)

**Fecha:** 2026-07-13
**Alcance:** `backend/app/repositories/warehouse_repository.py` (`_filtros_snapshot`),
`edw/04_indices.sql`.

## Síntoma

Al filtrar el dashboard de Bodega por "Tipo de movimiento" (filtro agregado en la sesión
anterior, ver `docs/auditoria/26_filtro_tipo_movimiento_bodega.md`), `GET
/analytics/bodega/kpis` y `GET /analytics/bodega/stock-reorden` respondían `500 Internal
Server Error`. Otros gráficos que no reutilizan las mismas CTEs (top-productos,
salidas-categoria, rotación) seguían funcionando.

## Causa raíz

El fragmento SQL del filtro (`_filtros_snapshot`, agregado en la sesión anterior) era:

```sql
p.codart IN (
    SELECT p2.codart FROM edw.fact_movimientos_inventario fmi
    JOIN edw.dim_producto p2 ON fmi.producto_sk = p2.producto_sk
    WHERE fmi.tipo_movimiento = :tipo_movimiento
)
```

Dos problemas se combinaron:

1. **Baja selectividad + sin índice.** `tipo_movimiento = 'FAC'` matchea ~462 000 de las
   ~949 000 filas del hecho (casi todo el catálogo se ha vendido alguna vez), y no había
   ningún índice sobre esa columna. Postgres tenía que unir esas 462k filas contra
   `dim_producto` ANTES de poder deduplicar por `codart` (~113ms medidos con
   `EXPLAIN ANALYZE` contra el EDW real).
2. **El fragmento se repite varias veces por request.** `_filtros_snapshot` se inyecta en
   más de una CTE dentro de la misma consulta (p.ej. `get_inventario_productos` lo usa en
   la CTE `snap` y en la CTE `salidas`; `get_kpis_periodo` lo usa en `costo_ventas` y en
   `inv_por_dia`), así que un solo `GET /kpis` con `tipo_movimiento` activo ejecutaba esa
   subconsulta de ~113ms **varias veces**, varias con plan paralelo (`Gather`/`Parallel
   Seq Scan`). Con `/dev/shm` en el default de Docker (64MB), la suma de memoria
   compartida pedida por los workers paralelos superaba el límite:

   ```
   psycopg2.errors.DiskFull: could not resize shared memory segment
   "/PostgreSQL.xxxxx" to 8388608 bytes: No space left on device
   ```

   que el handler global tradujo en `500 Internal Server Error`.

## Fix aplicado

1. **Índice nuevo** `idx_fmi_tipo_prod (tipo_movimiento, producto_sk)` en
   `edw/04_indices.sql` (aplicado también en caliente sobre el EDW de desarrollo).
2. **Subconsulta reescrita** para que el filtrado por `producto_sk` (la columna indexada,
   PK de `dim_producto`) ocurra ANTES de traer `codart`, permitiendo un semi-join que se
   detiene en el primer movimiento por producto en vez de materializar las 462k filas:

   ```sql
   p.codart IN (
       SELECT p2.codart FROM edw.dim_producto p2
       WHERE p2.producto_sk IN (
           SELECT fmi.producto_sk FROM edw.fact_movimientos_inventario fmi
           WHERE fmi.tipo_movimiento = :tipo_movimiento
       )
   )
   ```

   Medido contra el EDW real: **113ms → 12ms** por ocurrencia, plan sin `Gather`/paralelo
   (deja de competir por `/dev/shm`).

## Validación

Los 7 endpoints de Bodega que aceptan `tipo_movimiento`, probados con los 8 valores del
catálogo (FAC, TRA, EGR, CPA, DEV, ING, BOD, DEC): todos `200 OK`, todos por debajo de
115ms. Sin errores en los logs del backend tras el fix.

## Observación relacionada (no corregida aquí)

El `DiskFull` fue el síntoma visible, pero la causa de fondo -- `/dev/shm` de Docker en su
default de 64MB -- puede repetirse con cualquier consulta futura que dispare varios
`Parallel Seq Scan` concurrentes contra las tablas de hechos de ~1M filas. Subir
`shm_size` del servicio `postgres_edw` en `docker-compose.yml` (p.ej. a 256MB) es una
mejora defensiva razonable, pero requiere recrear el contenedor (`docker compose up -d
--force-recreate postgres_edw`) y no se aplicó en esta sesión por ser un cambio de
infraestructura fuera del alcance del bug reportado.
