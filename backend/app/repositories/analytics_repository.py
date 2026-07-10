# backend/app/repositories/analytics_repository.py
"""SQL de KPIs de Gerencia/Bodega/Ventas. Construcción dinámica de filtros WHERE con
f-strings pero SIEMPRE con bind params para los valores (no hay concatenación de datos
de usuario en el SQL, solo de nombres de columna/cláusula fijos del propio código)."""
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.utils.validators import sanitize_date_str


class AnalyticsRepository:
    def __init__(self, db: Session):
        self.db = db

    # ── Gerencia ───────────────────────────────────────────────────────────
    def get_management_kpis(
        self, sucursal: str | None = None, start_date: str | None = None,
        end_date: str | None = None, categoria: str | None = None, vendedor: str | None = None,
    ) -> dict[str, Any]:
        where_v, params = self._build_ventas_filters(sucursal, start_date, end_date, categoria, vendedor)
        
        # Construir filtros para devoluciones (sin categoría porque no existe en dim_producto)
        where_d, params_d = self._build_devoluciones_filters(sucursal, start_date, end_date, vendedor)
        # Combinar parámetros
        params.update(params_d)

        query_ventas = f"""
            WITH ventas_agg AS (
                SELECT
                    SUM(CASE WHEN f.subtotal_neto > 0 THEN f.subtotal_neto ELSE 0 END) as net_sales,
                    SUM(CASE WHEN f.subtotal_neto > 0 THEN f.costo_total ELSE 0 END) as net_cost,
                    COUNT(DISTINCT CASE WHEN f.subtotal_neto > 0 THEN f.num_factura ELSE NULL END) as cnt_facturas
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_sucursal s ON f.sucursal_sk = s.sucursal_sk
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_producto p ON f.producto_sk = p.producto_sk
                JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                LEFT JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
                {where_v}
            ),
            devoluciones_agg AS (
                SELECT
                    COALESCE(SUM(dev.total_linea_devolucion), 0) as total_devoluciones
                FROM edw.fact_devoluciones dev
                JOIN edw.dim_sucursal s ON dev.sucursal_sk = s.sucursal_sk
                JOIN edw.dim_fecha d ON dev.fecha_sk = d.fecha_sk
                LEFT JOIN edw.dim_vendedor v ON dev.vendedor_sk = v.vendedor_sk
                {where_d}
            )
            SELECT
                COALESCE(v.net_sales, 0.0) - d.total_devoluciones as total_ventas_netas,
                (COALESCE(v.net_sales, 0.0) - d.total_devoluciones) / NULLIF(v.cnt_facturas, 0) as ticket_promedio,
                CASE 
                    WHEN COALESCE(v.net_sales, 0.0) - d.total_devoluciones = 0 THEN 0
                    ELSE ((COALESCE(v.net_sales, 0.0) - d.total_devoluciones) - COALESCE(v.net_cost, 0.0)) / (COALESCE(v.net_sales, 0.0) - d.total_devoluciones) * 100.0
                END as margen_promedio
            FROM ventas_agg v
            CROSS JOIN devoluciones_agg d
        """
        
        query_sucursales = f"""
            WITH ventas_sucursal AS (
                SELECT f.sucursal_sk, COALESCE(SUM(f.subtotal_neto), 0) as net_sales
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_sucursal s ON f.sucursal_sk = s.sucursal_sk
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_producto p ON f.producto_sk = p.producto_sk
                JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                LEFT JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
                {where_v}
                GROUP BY f.sucursal_sk
            ),
            devoluciones_sucursal AS (
                SELECT dev.sucursal_sk, COALESCE(SUM(dev.total_linea_devolucion), 0) as total_devoluciones
                FROM edw.fact_devoluciones dev
                JOIN edw.dim_sucursal s ON dev.sucursal_sk = s.sucursal_sk
                JOIN edw.dim_fecha d ON dev.fecha_sk = d.fecha_sk
                LEFT JOIN edw.dim_vendedor v ON dev.vendedor_sk = v.vendedor_sk
                {where_d}
                GROUP BY dev.sucursal_sk
            )
            SELECT s.nombre_sucursal, 
                v.net_sales - COALESCE(d.total_devoluciones, 0) as net_sales
            FROM edw.dim_sucursal s
            LEFT JOIN ventas_sucursal v ON s.sucursal_sk = v.sucursal_sk
            LEFT JOIN devoluciones_sucursal d ON s.sucursal_sk = d.sucursal_sk
            WHERE v.net_sales - COALESCE(d.total_devoluciones, 0) != 0
            ORDER BY net_sales DESC
        """
        
        query_vendedores = f"""
            WITH ventas_vendedor AS (
                SELECT f.vendedor_sk, COALESCE(SUM(f.subtotal_neto), 0) as net_sales
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_sucursal s ON f.sucursal_sk = s.sucursal_sk
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_producto p ON f.producto_sk = p.producto_sk
                JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                LEFT JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
                {where_v}
                GROUP BY f.vendedor_sk
            ),
            devoluciones_vendedor AS (
                SELECT dev.vendedor_sk, COALESCE(SUM(dev.total_linea_devolucion), 0) as total_devoluciones
                FROM edw.fact_devoluciones dev
                JOIN edw.dim_sucursal s ON dev.sucursal_sk = s.sucursal_sk
                JOIN edw.dim_fecha d ON dev.fecha_sk = d.fecha_sk
                LEFT JOIN edw.dim_vendedor v ON dev.vendedor_sk = v.vendedor_sk
                {where_d}
                GROUP BY dev.vendedor_sk
            )
            SELECT v.nombre_vendedor,
                ventas.net_sales - COALESCE(devoluciones.total_devoluciones, 0) as net_sales
            FROM edw.dim_vendedor v
            LEFT JOIN ventas_vendedor ventas ON v.vendedor_sk = ventas.vendedor_sk
            LEFT JOIN devoluciones_vendedor devoluciones ON v.vendedor_sk = devoluciones.vendedor_sk
            WHERE ventas.net_sales - COALESCE(devoluciones.total_devoluciones, 0) != 0
            ORDER BY net_sales DESC
            LIMIT 15
        """
        
        res_v = self.db.execute(text(query_ventas), params).fetchone()
        res_s = self.db.execute(text(query_sucursales), params).fetchall()
        res_vend = self.db.execute(text(query_vendedores), params).fetchall()

        return {
            "total_sales": float(res_v[0]) if res_v and res_v[0] is not None else 0.0,
            "ticket": float(res_v[1]) if res_v and res_v[1] is not None else 0.0,
            "margen": float(res_v[2]) if res_v and res_v[2] is not None else 0.0,
            "branch_map": {row[0]: float(row[1]) for row in res_s} if res_s else {},
            "vend_map": {row[0]: float(row[1]) for row in res_vend} if res_vend else {},
        }

    def get_revenue_by_category(
        self, sucursal: str | None = None, start_date: str | None = None,
        end_date: str | None = None, vendedor: str | None = None,
    ) -> list[dict[str, Any]]:
        where_v, params = self._build_ventas_filters(sucursal, start_date, end_date, None, vendedor, require_clase=True)
        where_d, params_d = self._build_devoluciones_filters(sucursal, start_date, end_date, vendedor)
        params.update(params_d)
    
        query = f"""
            WITH ventas_por_categoria AS (
                SELECT 
                    p.clase as categoria,
                    COALESCE(SUM(f.subtotal_neto), 0) as total_ventas
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_producto p ON f.producto_sk = p.producto_sk
                JOIN edw.dim_sucursal s ON f.sucursal_sk = s.sucursal_sk
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                LEFT JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
                {where_v}
                GROUP BY p.clase
            ),
            devoluciones_por_categoria AS (
                SELECT 
                    p.clase as categoria,
                    COALESCE(SUM(dev.total_linea_devolucion), 0) as total_devoluciones
                FROM edw.fact_devoluciones dev
                JOIN edw.dim_producto p ON dev.producto_sk = p.producto_sk
                JOIN edw.dim_sucursal s ON dev.sucursal_sk = s.sucursal_sk
                JOIN edw.dim_fecha d ON dev.fecha_sk = d.fecha_sk
                LEFT JOIN edw.dim_vendedor v ON dev.vendedor_sk = v.vendedor_sk
                {where_d}
                GROUP BY p.clase
            )
            SELECT 
                COALESCE(v.categoria, d.categoria) as categoria,
                v.total_ventas - COALESCE(d.total_devoluciones, 0) as net_sales
            FROM ventas_por_categoria v
            FULL OUTER JOIN devoluciones_por_categoria d 
                ON v.categoria = d.categoria
            WHERE COALESCE(v.categoria, d.categoria) IS NOT NULL
            ORDER BY net_sales DESC
            LIMIT 10
        """
        res = self.db.execute(text(query), params).fetchall()
        return [{"cat": str(row[0]), "v": float(row[1] or 0)} for row in res]

    def get_categories(self) -> list[str]:
        res = self.db.execute(text(
            "SELECT DISTINCT clase FROM edw.dim_producto WHERE clase IS NOT NULL ORDER BY clase"
        )).fetchall()
        return [str(row[0]) for row in res]

    def get_sucursales(self) -> list[str]:
        res = self.db.execute(text(
            "SELECT DISTINCT nombre_sucursal FROM edw.dim_sucursal WHERE nombre_sucursal IS NOT NULL ORDER BY nombre_sucursal"
        )).fetchall()
        return [str(row[0]) for row in res]

    def get_vendedores(self) -> list[str]:
        res = self.db.execute(text(
            "SELECT DISTINCT nombre_vendedor FROM edw.dim_vendedor WHERE nombre_vendedor IS NOT NULL ORDER BY nombre_vendedor"
        )).fetchall()
        return [str(row[0]) for row in res]

    @staticmethod
    def _build_devoluciones_filters(sucursal, start_date, end_date, vendedor):
        """Construye filtros específicos para la tabla de devoluciones"""
        start_date = sanitize_date_str(start_date)
        end_date = sanitize_date_str(end_date)

        filtros = []
        params: dict[str, Any] = {}
        
        if sucursal:
            filtros.append("s.nombre_sucursal = :sucursal")
            params["sucursal"] = sucursal
        if vendedor:
            filtros.append("v.nombre_vendedor = :vendedor")
            params["vendedor"] = vendedor
        if start_date:
            filtros.append("d.fecha_completa >= :start_date")
            params["start_date"] = start_date
        if end_date:
            filtros.append("d.fecha_completa <= :end_date")
            params["end_date"] = end_date

        return ("WHERE " + " AND ".join(filtros)) if filtros else "", params

    @staticmethod
    def _build_ventas_filters(sucursal, start_date, end_date, categoria, vendedor, require_clase=False):
        start_date = sanitize_date_str(start_date)
        end_date = sanitize_date_str(end_date)

        filtros = ["ed.estado_documento_sk <> -1"]
        params: dict[str, Any] = {}
        if require_clase:
            filtros.append("p.clase IS NOT NULL")
        if sucursal:
            filtros.append("s.nombre_sucursal = :sucursal")
            params["sucursal"] = sucursal
        if vendedor:
            filtros.append("v.nombre_vendedor = :vendedor")
            params["vendedor"] = vendedor
        if start_date:
            filtros.append("d.fecha_completa >= :start_date")
            params["start_date"] = start_date
        if end_date:
            filtros.append("d.fecha_completa <= :end_date")
            params["end_date"] = end_date
        if categoria:
            filtros.append("p.clase = :categoria")
            params["categoria"] = categoria

        return "WHERE " + " AND ".join(filtros), params

    # ── Bodega: alertas de inventario reales (antes mock) ─────────────────
    def get_inventory_alerts(self, sucursal: str | None = None) -> dict[str, Any]:
        """Usa `edw.fact_inventario_snapshot` de la fecha más reciente disponible
        (es una foto diaria; sumar todo el histórico duplicaría conteos). Columnas
        confirmadas en `edw/03_hechos.sql`: alerta_desabastecimiento, alerta_sobrestock,
        stock_actual. NO existen `dias_abastecimiento_cob`/`inmovilizado_flag` que
        menciona docs/features/dashboards.md -- son campos deseados a futuro, requieren
        cambios de ETL, no se inventan aquí."""
        params: dict[str, Any] = {}
        filtro_suc = ""
        if sucursal:
            filtro_suc = "AND su.nombre_sucursal = :sucursal"
            params["sucursal"] = sucursal

        query_counts = f"""
            WITH ultimo_snapshot AS (SELECT MAX(fecha_sk) AS fecha_sk FROM edw.fact_inventario_snapshot)
            SELECT
                COUNT(*) FILTER (WHERE s.alerta_sobrestock) as items_sobrestock,
                COUNT(*) FILTER (WHERE s.alerta_desabastecimiento) as items_riesgo_desabasto
            FROM edw.fact_inventario_snapshot s
            JOIN ultimo_snapshot u ON s.fecha_sk = u.fecha_sk
            JOIN edw.dim_sucursal su ON s.sucursal_sk = su.sucursal_sk
            WHERE 1=1 {filtro_suc}
        """
        query_transfers = f"""
            WITH ultimo_snapshot AS (SELECT MAX(fecha_sk) AS fecha_sk FROM edw.fact_inventario_snapshot),
            inv AS (
                SELECT s.producto_sk, s.sucursal_sk, s.stock_actual, s.alerta_desabastecimiento, s.alerta_sobrestock
                FROM edw.fact_inventario_snapshot s JOIN ultimo_snapshot u ON s.fecha_sk = u.fecha_sk
            ),
            faltantes AS (SELECT producto_sk, sucursal_sk AS sucursal_destino_sk FROM inv WHERE alerta_desabastecimiento = TRUE),
            sobrantes AS (SELECT producto_sk, sucursal_sk AS sucursal_origen_sk, stock_actual AS stock_origen FROM inv WHERE alerta_sobrestock = TRUE)
            SELECT
                p.nombre_articulo, so_suc.nombre_sucursal AS origen, sd_suc.nombre_sucursal AS destino,
                ROUND(so.stock_origen * 0.3) AS cantidad_sugerida
            FROM faltantes sd
            JOIN sobrantes so ON sd.producto_sk = so.producto_sk AND sd.sucursal_destino_sk != so.sucursal_origen_sk
            JOIN edw.dim_producto p ON sd.producto_sk = p.producto_sk
            JOIN edw.dim_sucursal so_suc ON so.sucursal_origen_sk = so_suc.sucursal_sk
            JOIN edw.dim_sucursal sd_suc ON sd.sucursal_destino_sk = sd_suc.sucursal_sk
            {("WHERE so_suc.nombre_sucursal = :sucursal OR sd_suc.nombre_sucursal = :sucursal") if sucursal else ""}
            LIMIT 10
        """
        counts = self.db.execute(text(query_counts), params).fetchone()
        transfers = self.db.execute(text(query_transfers), params).fetchall()

        return {
            "items_sobrestock": int(counts[0]) if counts and counts[0] is not None else 0,
            "items_riesgo_desabasto": int(counts[1]) if counts and counts[1] is not None else 0,
            "transferencias_recomendadas": [
                {
                    "producto": str(row[0]),
                    "origen": str(row[1]),
                    "destino": str(row[2]),
                    "cantidad_sugerida": float(row[3]),
                    "explicacion": (
                        f"{row[2]} reporta riesgo de desabastecimiento mientras que "
                        f"{row[1]} tiene stock en nivel de sobrestock para el mismo producto."
                    ),
                }
                for row in transfers
            ],
        }

    # ── Ventas: cumplimiento de metas real (antes mock) ────────────────────
    def get_latest_period(self) -> tuple[int, int]:
        row = self.db.execute(text("""
            SELECT MAX(d.anio), MAX(d.mes) FROM edw.fact_ventas_detalle f
            JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
            WHERE d.anio = (SELECT MAX(d2.anio) FROM edw.fact_ventas_detalle f2 JOIN edw.dim_fecha d2 ON f2.fecha_sk = d2.fecha_sk)
        """)).fetchone()
        if row and row[0]:
            return int(row[0]), int(row[1])
        import datetime
        now = datetime.datetime.now()
        return now.year, now.month

    def get_sales_performance(self, anio: int, mes: int, sucursal: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"anio": anio, "mes": mes}
        filtro_suc_m = ""
        filtro_suc_v = ""
        if sucursal:
            filtro_suc_m = "AND m.sucursal = :sucursal"
            filtro_suc_v = "AND s.nombre_sucursal = :sucursal"
            params["sucursal"] = sucursal

        # No se filtra por estado ('APROBADA' vs 'PROPUESTA'): un sistema recién puesto en
        # marcha puede no tener nada aprobado todavía, y mostrar 0 en el agregado mientras
        # el ranking sí muestra metas individuales (que tampoco filtra por estado) sería
        # inconsistente. Se muestra la meta vigente sin importar si ya fue aprobada.
        query_meta = f"""
            SELECT COALESCE(SUM(m.monto_meta), 0)
            FROM public.metas_comerciales_operativas m
            WHERE m.anio = :anio AND m.mes = :mes {filtro_suc_m}
        """
        query_actual = f"""
            SELECT COALESCE(SUM(f.subtotal_neto), 0)
            FROM edw.fact_ventas_detalle f
            JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
            JOIN edw.dim_sucursal s ON f.sucursal_sk = s.sucursal_sk
            JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
            WHERE d.anio = :anio AND d.mes = :mes AND ed.estado_documento_sk <> -1 {filtro_suc_v}
        """
        query_ranking = f"""
            SELECT v.nombre_vendedor,
                   COALESCE(SUM(f.subtotal_neto), 0) as ventas,
                   COALESCE(MAX(m.monto_meta), 0) as meta
            FROM edw.dim_vendedor v
            LEFT JOIN edw.fact_ventas_detalle f ON f.vendedor_sk = v.vendedor_sk
                AND f.fecha_sk IN (SELECT fecha_sk FROM edw.dim_fecha WHERE anio = :anio AND mes = :mes)
            LEFT JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                AND ed.estado_documento_sk <> -1
            LEFT JOIN public.metas_comerciales_operativas m ON m.id_vendedor_origen = v.codven
                AND m.anio = :anio AND m.mes = :mes
            GROUP BY v.nombre_vendedor
            HAVING COALESCE(SUM(f.subtotal_neto), 0) > 0
            ORDER BY ventas DESC
            LIMIT 15
        """
        meta_mensual = float(self.db.execute(text(query_meta), params).scalar() or 0.0)
        cumplimiento_actual = float(self.db.execute(text(query_actual), params).scalar() or 0.0)
        ranking = self.db.execute(text(query_ranking), params).fetchall()

        import datetime
        # Proyección lineal simple: ritmo de venta transcurrido extrapolado a 30 días.
        # Solo tiene sentido para el mes en curso; para meses cerrados el propio
        # cumplimiento_actual ya es el resultado final (no se distingue aquí porque el
        # caller siempre pide el período vigente -- ver get_latest_period()).
        dias_transcurridos = min(datetime.datetime.now().day, 28)
        meta_proyectada = (cumplimiento_actual / dias_transcurridos * 30) if dias_transcurridos else cumplimiento_actual

        return {
            "meta_mensual": meta_mensual,
            "cumplimiento_actual": cumplimiento_actual,
            "meta_proyectada": round(meta_proyectada, 2),
            "ranking_vendedores": [
                {
                    "nombre": str(row[0]),
                    "ventas": float(row[1]),
                    "meta": float(row[2]),
                    "cumple": float(row[1]) >= float(row[2]) if row[2] else False,
                }
                for row in ranking
            ],
        }