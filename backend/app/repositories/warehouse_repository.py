# backend/app/repositories/warehouse_repository.py
"""SQL del módulo Bodega (docs/features/modulo_bodega.md, auditoría 23).

Fuentes (H23-1): el inventario actual es SIEMPRE el último snapshot disponible de
`edw.fact_inventario_snapshot` (sumar histórico duplicaría conteos — mismo patrón
validado en AnalyticsRepository.get_inventory_alerts); las salidas se miden con
`edw.fact_movimientos_inventario.es_salida = TRUE` (regla de negocio 3: dirección
por tipdoc, nunca por signo). El grano de producto es `codart` (colapsa versiones
SCD2 de dim_producto para no partir el stock de un mismo artículo en dos filas).

Mismo estilo que AnalyticsRepository: cláusulas WHERE construidas con f-strings de
fragmentos fijos del propio código y SIEMPRE bind params para los valores.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.utils.validators import sanitize_date_str

EXCLUIR_CODART = {"Z-9001"}

# Catálogo cerrado de kardex.tiporg (docs/auditoria/02_reglas_negocio_validadas.md §3):
# usado tanto para validar el filtro `tipo_movimiento` como para poblar el selector
# del frontend (WarehouseService.get_filtros).
TIPOS_MOVIMIENTO = [
    {"codigo": "FAC", "etiqueta": "Ventas (facturas)"},
    {"codigo": "TRA", "etiqueta": "Transferencias entre bodegas"},
    {"codigo": "EGR", "etiqueta": "Egresos"},
    {"codigo": "CPA", "etiqueta": "Compras"},
    {"codigo": "DEV", "etiqueta": "Devoluciones"},
    {"codigo": "ING", "etiqueta": "Ingresos"},
    {"codigo": "BOD", "etiqueta": "Ajustes de bodega"},
    {"codigo": "DEC", "etiqueta": "Ajustes / decrementos"},
]


class WarehouseRepository:
    def __init__(self, db: Session):
        self.db = db

    # ── Filtros comunes ─────────────────────────────────────────────────────
    @staticmethod
    def _filtros_snapshot(
        sucursal: str | None, almacen: str | None, categoria: str | None,
        proveedor: str | None, tipo_movimiento: str | None,
    ) -> tuple[str, dict[str, Any]]:
        """Filtros para queries basadas en el snapshot (alias fijos: su=dim_sucursal,
        al=dim_almacen, p=dim_producto)."""
        filtros: list[str] = []
        params: dict[str, Any] = {}

        if EXCLUIR_CODART:
        # Construir placeholders para los códigos a excluir
            placeholders = ", ".join([f":excl_{i}" for i in range(len(EXCLUIR_CODART))])
            for i, cod in enumerate(EXCLUIR_CODART):
                params[f"excl_{i}"] = cod
            filtros.append(f"p.codart NOT IN ({placeholders})")
        if sucursal:
            filtros.append("su.nombre_sucursal = :sucursal")
            params["sucursal"] = sucursal
        if almacen:
            filtros.append("al.nombre_almacen = :almacen")
            params["almacen"] = almacen
        if categoria:
            filtros.append("p.clase = :categoria")
            params["categoria"] = categoria
        if proveedor:
            # El ERP no guarda proveedor en el artículo: se infiere de fact_compras
            # (qué artículos se le compran a cada proveedor, requerimiento §1.1).
            filtros.append(
                "p.codart IN (SELECT p2.codart FROM edw.fact_compras fc "
                "JOIN edw.dim_producto p2 ON fc.producto_sk = p2.producto_sk "
                "JOIN edw.dim_proveedor pr ON fc.proveedor_sk = pr.proveedor_sk "
                "WHERE pr.nombre_proveedor = :proveedor)"
            )
            params["proveedor"] = proveedor
        if tipo_movimiento:
            # Filtro por tipo de movimiento de Kardex (kardex.tiporg, regla de negocio §3):
            # solo incluye artículos con AL MENOS UN movimiento de ese tipo (FAC=venta,
            # TRA=transferencia entre bodegas, EGR=egreso, CPA=compra, DEV=devolución,
            # BOD=ajuste de bodega, ING=ingreso, DEC=ajuste/decremento). FAC en particular
            # matchea ~462k de las ~949k filas del hecho (casi todo el catálogo alguna vez
            # se vendió) -- muy poco selectivo. El IN anidado por producto_sk (en vez de
            # unir primero a dim_producto por codart) deja que Postgres resuelva un Hash/
            # Nested Loop Semi Join que se detiene en el primer movimiento por producto,
            # en vez de materializar las 462k filas antes de deduplicar: medido 113ms →
            # 12ms contra el EDW real, evitando el `DiskFull` de /dev/shm (64MB) que
            # tumbaba /kpis y otros endpoints con varias CTEs que repiten este filtro
            # (docs/auditoria/28_bug_filtro_tipo_movimiento.md).
            filtros.append(
                "p.codart IN (SELECT p2.codart FROM edw.dim_producto p2 "
                "WHERE p2.producto_sk IN (SELECT fmi.producto_sk "
                "FROM edw.fact_movimientos_inventario fmi "
                "WHERE fmi.tipo_movimiento = :tipo_movimiento))"
            )
            params["tipo_movimiento"] = tipo_movimiento
        clausula = (" AND " + " AND ".join(filtros)) if filtros else ""
        return clausula, params

    @staticmethod
    def _rango_fechas(
        fecha_desde: str | None, fecha_hasta: str | None, params: dict[str, Any],
    ) -> str:
        """Fragmento de rango sobre dim_fecha (alias d) para hechos de movimiento/venta."""
        fecha_desde = sanitize_date_str(fecha_desde)
        fecha_hasta = sanitize_date_str(fecha_hasta)
        fragmentos = []
        if fecha_desde:
            fragmentos.append("d.fecha_completa >= :fecha_desde")
            params["fecha_desde"] = fecha_desde
        if fecha_hasta:
            fragmentos.append("d.fecha_completa <= :fecha_hasta")
            params["fecha_hasta"] = fecha_hasta
        return (" AND " + " AND ".join(fragmentos)) if fragmentos else ""

    # ── Surtido real por almacén (KPI "Artículos en Inventario") ────────────
    def get_skus_surtido(
        self, sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None, tipo_movimiento: str | None = None,
    ) -> int:
        """Tamaño real del surtido de un almacén/sucursal. `vi_mv_existencias` (SAP) no
        distingue "nunca asignado a este almacén" de "agotado temporalmente": siempre expone
        TODO el catálogo por almacén con existencia 0 donde nunca hubo stock, por lo que
        `COUNT(DISTINCT codart)` sobre el snapshot da el mismo número (tamaño del catálogo)
        sin importar el almacén filtrado. Se aproxima el surtido real contando los codart con
        AL MENOS UN movimiento histórico de kardex en el almacén (fact_movimientos_inventario,
        cualquier dirección -- regla de negocio 3); verificado que ningún codart con stock
        actual > 0 carece de movimiento histórico, así que nunca subcuenta lo realmente activo."""
        where_extra, params = self._filtros_snapshot(sucursal, almacen, categoria, proveedor, tipo_movimiento)
        query = f"""
            SELECT COUNT(DISTINCT p.codart)
            FROM edw.fact_movimientos_inventario m
            JOIN edw.dim_producto p ON m.producto_sk = p.producto_sk
            JOIN edw.dim_almacen  al ON m.almacen_sk = al.almacen_sk
            JOIN edw.dim_sucursal su ON m.sucursal_sk = su.sucursal_sk
            WHERE p.producto_sk <> -1 {where_extra}
        """
        return int(self.db.execute(text(query), params).scalar() or 0)

    # ── Catálogos para los filtros globales (§1.1) ──────────────────────────
    def get_proveedores(self) -> list[str]:
        # Centinela -1 fuera del catálogo (regla 12), mismo criterio que get_almacenes.
        res = self.db.execute(text(
            "SELECT DISTINCT nombre_proveedor FROM edw.dim_proveedor "
            "WHERE nombre_proveedor IS NOT NULL AND proveedor_sk <> -1 ORDER BY nombre_proveedor"
        )).fetchall()
        return [str(r[0]) for r in res]

    # ── Inventario maestro por producto (KPIs, G5, G6, plan de compras) ────
    def get_inventario_productos(
        self, sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None,
        tipo_movimiento: str | None = None, dias_salidas: int = 30,
    ) -> list[dict[str, Any]]:
        """Una fila por codart: stock/valor del último snapshot (sumado sobre los
        almacenes filtrados) + salidas de los últimos `dias_salidas` días + salidas del
        período previo equivalente (tendencia)."""
        where_extra, params = self._filtros_snapshot(sucursal, almacen, categoria, proveedor, tipo_movimiento)
        params["dias"] = dias_salidas

        query = f"""
            WITH ultimo AS (SELECT MAX(fecha_sk) AS fecha_sk FROM edw.fact_inventario_snapshot),
            snap AS (
                SELECT p.codart,
                       MAX(p.nombre_articulo)              AS nombre_articulo,
                       MAX(COALESCE(p.clase, 'SIN-CLASE')) AS categoria,
                       SUM(s.stock_actual)                 AS stock_actual,
                       SUM(s.valor_inventario)             AS valor_inventario,
                       MAX(s.costo_promedio)               AS costo_unitario,
                       SUM(s.punto_reorden)                AS punto_reorden_config
                FROM edw.fact_inventario_snapshot s
                JOIN ultimo u ON s.fecha_sk = u.fecha_sk
                JOIN edw.dim_producto p ON s.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON s.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON s.sucursal_sk = su.sucursal_sk
                WHERE p.producto_sk <> -1 {where_extra}
                GROUP BY p.codart
            ),
            salidas AS (
                SELECT p.codart,
                       SUM(m.cantidad_movimiento) FILTER (
                           WHERE d.fecha_completa >= CURRENT_DATE - (:dias * INTERVAL '1 day')
                       ) AS salidas_periodo,
                       SUM(m.cantidad_movimiento) FILTER (
                           WHERE d.fecha_completa <  CURRENT_DATE - (:dias * INTERVAL '1 day')
                       ) AS salidas_periodo_anterior
                FROM edw.fact_movimientos_inventario m
                JOIN edw.dim_fecha d ON m.fecha_sk = d.fecha_sk
                JOIN edw.dim_producto p ON m.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON m.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON m.sucursal_sk = su.sucursal_sk
                WHERE m.es_salida
                  AND d.fecha_completa >= CURRENT_DATE - (2 * :dias * INTERVAL '1 day')
                  {where_extra}
                GROUP BY p.codart
            )
            SELECT snap.codart, snap.nombre_articulo, snap.categoria,
                   snap.stock_actual, snap.valor_inventario, snap.costo_unitario,
                   snap.punto_reorden_config,
                   COALESCE(sal.salidas_periodo, 0)          AS salidas_periodo,
                   COALESCE(sal.salidas_periodo_anterior, 0) AS salidas_periodo_anterior
            FROM snap
            LEFT JOIN salidas sal ON sal.codart = snap.codart
            ORDER BY salidas_periodo DESC, snap.valor_inventario DESC
        """
        res = self.db.execute(text(query), params).fetchall()
        return [
            {
                "codart": str(r[0]),
                "nombre": str(r[1]),
                "categoria": str(r[2]),
                "stock_actual": float(r[3] or 0),
                "valor_inventario": float(r[4] or 0),
                "costo_unitario": float(r[5] or 0),
                "punto_reorden_config": float(r[6] or 0),
                "salidas_periodo": float(r[7] or 0),
                "salidas_periodo_anterior": float(r[8] or 0),
            }
            for r in res
        ]

    # ── KPIs de período (rotación, valor, stockouts, comparativa mensual) ──
    def get_kpis_periodo(
        self, fecha_desde: str | None, fecha_hasta: str | None,
        sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None,
        tipo_movimiento: str | None = None,
    ) -> dict[str, Any]:
        where_extra, params = self._filtros_snapshot(sucursal, almacen, categoria, proveedor, tipo_movimiento)
        rango = self._rango_fechas(fecha_desde, fecha_hasta, params)

        # Rotación (RN-B5): costo de ventas del período / inventario promedio del
        # período (promedio de los snapshots dentro del rango; si no hay ninguno,
        # el servicio degrada usando el valor del último snapshot).
        query = f"""
            WITH costo_ventas AS (
                SELECT COALESCE(SUM(f.costo_total), 0) AS costo,
                       COUNT(DISTINCT d.fecha_completa) AS dias_con_venta
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_producto p ON f.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON f.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON f.sucursal_sk = su.sucursal_sk
                JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                WHERE ed.estado_documento_sk <> -1 {where_extra} {rango}
            ),
            inv_por_dia AS (
                SELECT d.fecha_completa,
                       SUM(s.valor_inventario) AS valor_dia,
                       COUNT(*) FILTER (WHERE s.stock_actual <= 0) AS skus_sin_stock,
                       COUNT(*) AS skus_total
                FROM edw.fact_inventario_snapshot s
                JOIN edw.dim_fecha d ON s.fecha_sk = d.fecha_sk
                JOIN edw.dim_producto p ON s.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON s.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON s.sucursal_sk = su.sucursal_sk
                WHERE p.producto_sk <> -1 {where_extra} {rango}
                GROUP BY d.fecha_completa
            )
            SELECT cv.costo,
                   (SELECT AVG(valor_dia) FROM inv_por_dia),
                   (SELECT SUM(skus_sin_stock)::float / NULLIF(SUM(skus_total), 0) * 100 FROM inv_por_dia),
                   (SELECT COUNT(*) FROM inv_por_dia)
            FROM costo_ventas cv
        """
        r = self.db.execute(text(query), params).fetchone()
        return {
            "costo_ventas": float(r[0] or 0) if r else 0.0,
            "inventario_promedio": float(r[1]) if r and r[1] is not None else None,
            "tasa_stockout_pct": round(float(r[2]), 2) if r and r[2] is not None else None,
            "dias_snapshot_periodo": int(r[3] or 0) if r else 0,
        }

    def get_snapshot_total_a_fecha(
        self, fecha_corte: str | None, sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None, tipo_movimiento: str | None = None,
    ) -> dict[str, Any] | None:
        """Totales (SKUs, valor) del snapshot más reciente <= fecha_corte (o el último
        disponible si fecha_corte es None). Para la tendencia "vs mes anterior" (H23-2:
        si no existe snapshot previo devuelve None y el frontend muestra '—')."""
        where_extra, params = self._filtros_snapshot(sucursal, almacen, categoria, proveedor, tipo_movimiento)
        fecha_corte = sanitize_date_str(fecha_corte)
        corte = ""
        if fecha_corte:
            corte = "WHERE d.fecha_completa <= :fecha_corte"
            params["fecha_corte"] = fecha_corte

        query = f"""
            WITH corte AS (
                SELECT MAX(s.fecha_sk) AS fecha_sk
                FROM edw.fact_inventario_snapshot s
                JOIN edw.dim_fecha d ON s.fecha_sk = d.fecha_sk
                {corte}
            )
            SELECT COUNT(DISTINCT p.codart)                                  AS total_skus,
                   COUNT(DISTINCT p.codart) FILTER (WHERE s.stock_actual > 0) AS skus_activos,
                   COALESCE(SUM(s.valor_inventario), 0)                       AS valor_total,
                   COALESCE(SUM(s.stock_actual), 0)                          AS cantidad_total
            FROM edw.fact_inventario_snapshot s
            JOIN corte c ON s.fecha_sk = c.fecha_sk
            JOIN edw.dim_producto p ON s.producto_sk = p.producto_sk
            JOIN edw.dim_almacen  al ON s.almacen_sk = al.almacen_sk
            JOIN edw.dim_sucursal su ON s.sucursal_sk = su.sucursal_sk
            WHERE p.producto_sk <> -1 {where_extra}
        """
        r = self.db.execute(text(query), params).fetchone()
        if not r or not r[0]:
            return None
        return {
            "total_skus": int(r[0]),
            "skus_activos": int(r[1] or 0),
            "valor_total": float(r[2] or 0),
            "cantidad_total": float(r[3] or 0),
        }

    def get_valor_por_categoria(
        self, sucursal: str | None = None, almacen: str | None = None,
        proveedor: str | None = None, tipo_movimiento: str | None = None, limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Top categorías por valor de inventario del último snapshot (KPI 5)."""
        where_extra, params = self._filtros_snapshot(sucursal, almacen, None, proveedor, tipo_movimiento)
        params["limit"] = limit
        query = f"""
            WITH ultimo AS (SELECT MAX(fecha_sk) AS fecha_sk FROM edw.fact_inventario_snapshot)
            SELECT COALESCE(p.clase, 'SIN-CLASE') AS categoria, SUM(s.valor_inventario) AS valor
            FROM edw.fact_inventario_snapshot s
            JOIN ultimo u ON s.fecha_sk = u.fecha_sk
            JOIN edw.dim_producto p ON s.producto_sk = p.producto_sk
            JOIN edw.dim_almacen  al ON s.almacen_sk = al.almacen_sk
            JOIN edw.dim_sucursal su ON s.sucursal_sk = su.sucursal_sk
            WHERE p.producto_sk <> -1 {where_extra}
            GROUP BY COALESCE(p.clase, 'SIN-CLASE')
            ORDER BY valor DESC
            LIMIT :limit
        """
        res = self.db.execute(text(query), params).fetchall()
        return [{"categoria": str(r[0]), "valor": float(r[1] or 0)} for r in res]

    # ── Gráfico 1: serie diaria de salidas ──────────────────────────────────
    def get_salidas_serie_diaria(
        self, producto_cod: str | None, fecha_desde: str | None, fecha_hasta: str | None,
        sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None,
        top_n: int | None = None,
    ) -> list[dict[str, Any]]:
        """Serie diaria de unidades salidas. `producto_cod` restringe a un artículo;
        `top_n` restringe a los N artículos con más salida del rango (para "Top 10").

        Los JOIN a `dim_almacen`/`dim_sucursal` son condicionales: solo se agregan si el
        usuario realmente filtra por esa dimensión (`_filtros_snapshot` solo referencia
        los alias `al`/`su` en el WHERE cuando `almacen`/`sucursal` vienen seteados).
        Unirlos siempre -- aunque no filtren nada -- desvía al planner del índice parcial
        `idx_fmi_salidas_fecha_prod` (fecha_sk, producto_sk) WHERE es_salida hacia un Seq
        Scan completo de fact_movimientos_inventario (~950k filas): medido 63ms → 7ms al
        quitar los JOIN innecesarios en el caso sin filtro de almacén/sucursal (el caso
        del gráfico "Histórico y Predicción de Salidas" con "Top 10 productos")."""
        where_extra, params = self._filtros_snapshot(sucursal, almacen, categoria, proveedor, None)
        rango = self._rango_fechas(fecha_desde, fecha_hasta, params)
        join_al = "JOIN edw.dim_almacen  al ON {m}.almacen_sk = al.almacen_sk" if almacen else ""
        join_su = "JOIN edw.dim_sucursal su ON {m}.sucursal_sk = su.sucursal_sk" if sucursal else ""

        filtro_prod = ""
        if producto_cod:
            filtro_prod = "AND p.codart = :producto_cod"
            params["producto_cod"] = producto_cod
        filtro_top = ""
        if top_n and not producto_cod:
            filtro_top = f"""
                AND p.codart IN (
                    SELECT p2.codart
                    FROM edw.fact_movimientos_inventario m2
                    JOIN edw.dim_fecha d ON m2.fecha_sk = d.fecha_sk
                    JOIN edw.dim_producto p2 ON m2.producto_sk = p2.producto_sk
                    {join_al.format(m='m2')}
                    {join_su.format(m='m2')}
                    WHERE m2.es_salida {where_extra} {rango}
                    GROUP BY p2.codart
                    ORDER BY SUM(m2.cantidad_movimiento) DESC
                    LIMIT :top_n
                )
            """
            params["top_n"] = top_n

        query = f"""
            SELECT d.fecha_completa AS fecha, SUM(m.cantidad_movimiento) AS unidades
            FROM edw.fact_movimientos_inventario m
            JOIN edw.dim_fecha d ON m.fecha_sk = d.fecha_sk
            JOIN edw.dim_producto p ON m.producto_sk = p.producto_sk
            {join_al.format(m='m')}
            {join_su.format(m='m')}
            WHERE m.es_salida {where_extra} {rango} {filtro_prod} {filtro_top}
            GROUP BY d.fecha_completa
            ORDER BY d.fecha_completa
        """
        res = self.db.execute(text(query), params).fetchall()
        return [{"fecha": str(r[0]), "unidades": float(r[1] or 0)} for r in res]

    # ── Gráfico 2: rotación × margen por producto ───────────────────────────
    def get_rotacion_productos(
        self, fecha_desde: str | None, fecha_hasta: str | None,
        sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None,
        tipo_movimiento: str | None = None, limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Por producto: costo de ventas y margen del período (fact_ventas_detalle) +
        stock/valor del último snapshot. El servicio calcula rotación y cuadrantes."""
        where_extra, params = self._filtros_snapshot(sucursal, almacen, categoria, proveedor, tipo_movimiento)
        rango = self._rango_fechas(fecha_desde, fecha_hasta, params)
        params["limit"] = limit

        query = f"""
            WITH ultimo AS (SELECT MAX(fecha_sk) AS fecha_sk FROM edw.fact_inventario_snapshot),
            ventas AS (
                SELECT p.codart,
                       MAX(p.nombre_articulo)             AS nombre_articulo,
                       MAX(COALESCE(p.clase, 'SIN-CLASE')) AS categoria,
                       SUM(f.cantidad)                    AS unidades_vendidas,
                       SUM(f.costo_total)                 AS costo_ventas,
                       SUM(f.margen_bruto)                AS margen_total
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_producto p ON f.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON f.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON f.sucursal_sk = su.sucursal_sk
                JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                WHERE ed.estado_documento_sk <> -1 AND p.es_servicio = FALSE {where_extra} {rango}
                GROUP BY p.codart
            ),
            snap AS (
                SELECT p.codart,
                       SUM(s.stock_actual)     AS stock_actual,
                       SUM(s.valor_inventario) AS valor_inventario
                FROM edw.fact_inventario_snapshot s
                JOIN ultimo u ON s.fecha_sk = u.fecha_sk
                JOIN edw.dim_producto p ON s.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON s.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON s.sucursal_sk = su.sucursal_sk
                WHERE p.producto_sk <> -1 {where_extra}
                GROUP BY p.codart
            )
            SELECT v.codart, v.nombre_articulo, v.categoria, v.unidades_vendidas,
                   v.costo_ventas, v.margen_total,
                   COALESCE(sn.stock_actual, 0), COALESCE(sn.valor_inventario, 0)
            FROM ventas v
            LEFT JOIN snap sn ON sn.codart = v.codart
            ORDER BY v.costo_ventas DESC NULLS LAST
            LIMIT :limit
        """
        res = self.db.execute(text(query), params).fetchall()
        return [
            {
                "codart": str(r[0]),
                "nombre": str(r[1]),
                "categoria": str(r[2]),
                "unidades_vendidas": float(r[3] or 0),
                "costo_ventas": float(r[4] or 0),
                "margen_total": float(r[5] or 0),
                "stock_actual": float(r[6] or 0),
                "valor_inventario": float(r[7] or 0),
            }
            for r in res
        ]

    # ── Gráficos 3 y 4: top salidas y distribución por categoría ───────────
    def get_salidas_por_producto(
        self, fecha_desde: str | None, fecha_hasta: str | None,
        fecha_desde_prev: str | None, fecha_hasta_prev: str | None,
        sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None,
        tipo_movimiento: str | None = None, limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Top N productos por unidades salidas en el rango, con el rango previo
        (tendencia §1.3-G3) y stock del último snapshot."""
        where_extra, params = self._filtros_snapshot(sucursal, almacen, categoria, proveedor, tipo_movimiento)
        rango = self._rango_fechas(fecha_desde, fecha_hasta, params)
        params["limit"] = limit
        # Rango previo con parámetros propios (mismos filtros dimensionales).
        prev_params: dict[str, Any] = {}
        rango_prev = self._rango_fechas(fecha_desde_prev, fecha_hasta_prev, prev_params)
        params.update({f"prev_{k}": v for k, v in prev_params.items()})
        rango_prev = rango_prev.replace(":fecha_desde", ":prev_fecha_desde").replace(":fecha_hasta", ":prev_fecha_hasta")

        query = f"""
            WITH ultimo AS (SELECT MAX(fecha_sk) AS fecha_sk FROM edw.fact_inventario_snapshot),
            actual AS (
                SELECT p.codart, MAX(p.nombre_articulo) AS nombre,
                       MAX(COALESCE(p.clase, 'SIN-CLASE')) AS categoria,
                       SUM(m.cantidad_movimiento) AS unidades
                FROM edw.fact_movimientos_inventario m
                JOIN edw.dim_fecha d ON m.fecha_sk = d.fecha_sk
                JOIN edw.dim_producto p ON m.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON m.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON m.sucursal_sk = su.sucursal_sk
                WHERE m.es_salida {where_extra} {rango}
                GROUP BY p.codart
            ),
            previo AS (
                SELECT p.codart, SUM(m.cantidad_movimiento) AS unidades
                FROM edw.fact_movimientos_inventario m
                JOIN edw.dim_fecha d ON m.fecha_sk = d.fecha_sk
                JOIN edw.dim_producto p ON m.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON m.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON m.sucursal_sk = su.sucursal_sk
                WHERE m.es_salida {where_extra} {rango_prev}
                GROUP BY p.codart
            ),
            snap AS (
                SELECT p.codart, SUM(s.stock_actual) AS stock_actual
                FROM edw.fact_inventario_snapshot s
                JOIN ultimo u ON s.fecha_sk = u.fecha_sk
                JOIN edw.dim_producto p ON s.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON s.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON s.sucursal_sk = su.sucursal_sk
                WHERE p.producto_sk <> -1 {where_extra}
                GROUP BY p.codart
            )
            SELECT a.codart, a.nombre, a.categoria, a.unidades,
                   COALESCE(pr.unidades, 0) AS unidades_previo,
                   COALESCE(sn.stock_actual, 0) AS stock_actual
            FROM actual a
            LEFT JOIN previo pr ON pr.codart = a.codart
            LEFT JOIN snap   sn ON sn.codart = a.codart
            ORDER BY a.unidades DESC
            LIMIT :limit
        """
        res = self.db.execute(text(query), params).fetchall()
        return [
            {
                "codart": str(r[0]),
                "nombre": str(r[1]),
                "categoria": str(r[2]),
                "unidades": float(r[3] or 0),
                "unidades_previo": float(r[4] or 0),
                "stock_actual": float(r[5] or 0),
            }
            for r in res
        ]

    def get_salidas_por_categoria(
        self, fecha_desde: str | None, fecha_hasta: str | None,
        fecha_desde_prev: str | None, fecha_hasta_prev: str | None,
        sucursal: str | None = None, almacen: str | None = None,
        proveedor: str | None = None, tipo_movimiento: str | None = None,
    ) -> list[dict[str, Any]]:
        where_extra, params = self._filtros_snapshot(sucursal, almacen, None, proveedor, tipo_movimiento)
        rango = self._rango_fechas(fecha_desde, fecha_hasta, params)
        prev_params: dict[str, Any] = {}
        rango_prev = self._rango_fechas(fecha_desde_prev, fecha_hasta_prev, prev_params)
        params.update({f"prev_{k}": v for k, v in prev_params.items()})
        rango_prev = rango_prev.replace(":fecha_desde", ":prev_fecha_desde").replace(":fecha_hasta", ":prev_fecha_hasta")

        query = f"""
            WITH ultimo AS (SELECT MAX(fecha_sk) AS fecha_sk FROM edw.fact_inventario_snapshot),
            actual AS (
                SELECT COALESCE(p.clase, 'SIN-CLASE') AS categoria, SUM(m.cantidad_movimiento) AS unidades
                FROM edw.fact_movimientos_inventario m
                JOIN edw.dim_fecha d ON m.fecha_sk = d.fecha_sk
                JOIN edw.dim_producto p ON m.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON m.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON m.sucursal_sk = su.sucursal_sk
                WHERE m.es_salida {where_extra} {rango}
                GROUP BY COALESCE(p.clase, 'SIN-CLASE')
            ),
            previo AS (
                SELECT COALESCE(p.clase, 'SIN-CLASE') AS categoria, SUM(m.cantidad_movimiento) AS unidades
                FROM edw.fact_movimientos_inventario m
                JOIN edw.dim_fecha d ON m.fecha_sk = d.fecha_sk
                JOIN edw.dim_producto p ON m.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON m.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON m.sucursal_sk = su.sucursal_sk
                WHERE m.es_salida {where_extra} {rango_prev}
                GROUP BY COALESCE(p.clase, 'SIN-CLASE')
            ),
            stock AS (
                SELECT COALESCE(p.clase, 'SIN-CLASE') AS categoria, SUM(s.stock_actual) AS stock
                FROM edw.fact_inventario_snapshot s
                JOIN ultimo u ON s.fecha_sk = u.fecha_sk
                JOIN edw.dim_producto p ON s.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON s.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON s.sucursal_sk = su.sucursal_sk
                WHERE p.producto_sk <> -1 {where_extra}
                GROUP BY COALESCE(p.clase, 'SIN-CLASE')
            )
            SELECT a.categoria, a.unidades, COALESCE(pr.unidades, 0), COALESCE(st.stock, 0)
            FROM actual a
            LEFT JOIN previo pr ON pr.categoria = a.categoria
            LEFT JOIN stock  st ON st.categoria = a.categoria
            ORDER BY a.unidades DESC
        """
        res = self.db.execute(text(query), params).fetchall()
        return [
            {
                "categoria": str(r[0]),
                "unidades": float(r[1] or 0),
                "unidades_previo": float(r[2] or 0),
                "stock_disponible": float(r[3] or 0),
            }
            for r in res
        ]

    # ── Panel §3: stock por producto × almacén (matriz y transferencias) ───
    def get_stock_por_almacen(
        self, sucursal: str | None = None, categoria: str | None = None,
        proveedor: str | None = None, tipo_movimiento: str | None = None,
        almacen: str | None = None, dias_salidas: int = 30, limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Una fila por (codart, almacén) con stock del último snapshot y salidas de los
        últimos `dias_salidas` días EN ESE almacén — insumo de la matriz §3.1 y de la
        lógica de transferencias RN-B3 (excedente/déficit por bodega). `almacen` es
        opcional: la matriz de §3.1 lo usa para restringir a una sola bodega cuando el
        usuario filtra por almacén; las transferencias (§3.2) lo dejan en None porque
        necesitan comparar TODAS las bodegas entre sí (origen/destino)."""
        where_extra, params = self._filtros_snapshot(sucursal, almacen, categoria, proveedor, tipo_movimiento)
        params["dias"] = dias_salidas
        params["limit"] = limit

        query = f"""
            WITH ultimo AS (SELECT MAX(fecha_sk) AS fecha_sk FROM edw.fact_inventario_snapshot),
            snap AS (
                SELECT p.codart,
                       MAX(p.nombre_articulo) AS nombre,
                       MAX(COALESCE(p.clase, 'SIN-CLASE')) AS categoria,
                       al.nombre_almacen,
                       SUM(s.stock_actual)   AS stock_actual,
                       MAX(s.costo_promedio) AS costo_unitario,
                       SUM(s.punto_reorden)  AS punto_reorden_config
                FROM edw.fact_inventario_snapshot s
                JOIN ultimo u ON s.fecha_sk = u.fecha_sk
                JOIN edw.dim_producto p ON s.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON s.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON s.sucursal_sk = su.sucursal_sk
                WHERE p.producto_sk <> -1 AND al.almacen_sk <> -1 {where_extra}
                GROUP BY p.codart, al.nombre_almacen
            ),
            salidas AS (
                SELECT p.codart, al.nombre_almacen, SUM(m.cantidad_movimiento) AS salidas
                FROM edw.fact_movimientos_inventario m
                JOIN edw.dim_fecha d ON m.fecha_sk = d.fecha_sk
                JOIN edw.dim_producto p ON m.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON m.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON m.sucursal_sk = su.sucursal_sk
                WHERE m.es_salida
                  AND d.fecha_completa >= CURRENT_DATE - (:dias * INTERVAL '1 day')
                  {where_extra}
                GROUP BY p.codart, al.nombre_almacen
            ),
            relevantes AS (
                -- Corta la matriz a los artículos con actividad o stock (evita
                -- devolver decenas de miles de SKUs muertos, ~948k movimientos).
                SELECT codart FROM snap GROUP BY codart
                ORDER BY SUM(stock_actual * costo_unitario) DESC
                LIMIT :limit
            )
            SELECT sn.codart, sn.nombre, sn.categoria, sn.nombre_almacen,
                   sn.stock_actual, sn.costo_unitario, sn.punto_reorden_config,
                   COALESCE(sa.salidas, 0) AS salidas_periodo
            FROM snap sn
            JOIN relevantes r ON r.codart = sn.codart
            LEFT JOIN salidas sa ON sa.codart = sn.codart AND sa.nombre_almacen = sn.nombre_almacen
            ORDER BY sn.codart, sn.nombre_almacen
        """
        res = self.db.execute(text(query), params).fetchall()
        return [
            {
                "codart": str(r[0]),
                "nombre": str(r[1]),
                "categoria": str(r[2]),
                "almacen": str(r[3]),
                "stock_actual": float(r[4] or 0),
                "costo_unitario": float(r[5] or 0),
                "punto_reorden_config": float(r[6] or 0),
                "salidas_periodo": float(r[7] or 0),
            }
            for r in res
        ]
