# backend/app/repositories/analytics_repository.py
"""SQL de KPIs de Gerencia/Bodega/Ventas. Construcción dinámica de filtros WHERE con
f-strings pero SIEMPRE con bind params para los valores (no hay concatenación de datos
de usuario en el SQL, solo de nombres de columna/cláusula fijos del propio código)."""
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.metricas.venta_neta import FILTRO_ESTADO_VALIDO, SQL_VENTA_BRUTA
from app.utils.validators import sanitize_date_str


def _clases_excluidas_margen() -> list[str]:
    """Clases de `dim_producto` que no participan del cálculo de margen/ROI
    (docs/auditoria/39_madurez_bi_toma_decisiones.md, H-01). Lista separada por comas en
    `ANALYTICS_CLASES_EXCLUIDAS_MARGEN`; vacía = no excluir nada."""
    return [c.strip() for c in settings.ANALYTICS_CLASES_EXCLUIDAS_MARGEN.split(",") if c.strip()]


class AnalyticsRepository:
    def __init__(self, db: Session):
        self.db = db

    # ── Gerencia ───────────────────────────────────────────────────────────
    def get_management_kpis(
        self, sucursal: str | None = None, start_date: str | None = None,
        end_date: str | None = None, categoria: str | None = None, vendedor: str | None = None,
        almacen: str | None = None,
    ) -> dict[str, Any]:
        where_v, params = self._build_ventas_filters(sucursal, start_date, end_date, categoria, vendedor, almacen=almacen)

        # Construir filtros para devoluciones (sin categoría porque no existe en dim_producto)
        where_d, params_d = self._build_devoluciones_filters(sucursal, start_date, end_date, vendedor, almacen=almacen)
        # Combinar parámetros
        params.update(params_d)

        # docs/auditoria/39_madurez_bi_toma_decisiones.md, H-01: las clases excluidas salen
        # del universo de MARGEN/ROI pero NO del de ingresos -- vender chatarra es ingreso
        # real; lo que no es real es su costo derivado de `ultcos` en otra unidad de medida.
        clases_excl = _clases_excluidas_margen()
        if clases_excl:
            params["clases_excl_margen"] = clases_excl
            aplica_margen = "AND (p.clase IS NULL OR p.clase <> ALL(:clases_excl_margen))"
        else:
            aplica_margen = ""

        query_ventas = f"""
            WITH ventas_agg AS (
                SELECT
                    -- G-02: definición canónica en `app/services/metricas/venta_neta.py`.
                    {SQL_VENTA_BRUTA} as net_sales,
                    SUM(CASE WHEN f.subtotal_neto > 0 {aplica_margen} THEN f.subtotal_neto ELSE 0 END) as margen_sales,
                    SUM(CASE WHEN f.subtotal_neto > 0 {aplica_margen} THEN f.costo_total ELSE 0 END) as net_cost,
                    COUNT(DISTINCT CASE WHEN f.subtotal_neto > 0 THEN f.num_factura ELSE NULL END) as cnt_facturas
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_sucursal s ON f.sucursal_sk = s.sucursal_sk
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_producto p ON f.producto_sk = p.producto_sk
                JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                LEFT JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
                JOIN edw.dim_almacen al ON f.almacen_sk = al.almacen_sk
                {where_v}
            ),
            devoluciones_agg AS (
                SELECT
                    COALESCE(SUM(dev.total_linea_devolucion), 0) as total_devoluciones
                FROM edw.fact_devoluciones dev
                JOIN edw.dim_sucursal s ON dev.sucursal_sk = s.sucursal_sk
                JOIN edw.dim_fecha d ON dev.fecha_sk = d.fecha_sk
                LEFT JOIN edw.dim_vendedor v ON dev.vendedor_sk = v.vendedor_sk
                JOIN edw.dim_almacen al ON dev.almacen_sk = al.almacen_sk
                {where_d}
            )
            SELECT
                COALESCE(v.net_sales, 0.0) - d.total_devoluciones as total_ventas_netas,
                (COALESCE(v.net_sales, 0.0) - d.total_devoluciones) / NULLIF(v.cnt_facturas, 0) as ticket_promedio,
                -- Margen sobre el universo costeable (H-01). Las devoluciones no son
                -- atribuibles a una clase de producto en `fact_devoluciones`, así que se
                -- restan completas, igual que en la consulta validada en la auditoría 39.
                CASE
                    WHEN COALESCE(v.margen_sales, 0.0) - d.total_devoluciones = 0 THEN 0
                    ELSE ((COALESCE(v.margen_sales, 0.0) - d.total_devoluciones) - COALESCE(v.net_cost, 0.0)) / (COALESCE(v.margen_sales, 0.0) - d.total_devoluciones) * 100.0
                END as margen_promedio,
                -- RN-BI2: retorno sobre costo de mercadería vendida (reemplaza el
                -- `margen * 1.15` de H-02). NULL cuando no hay costo con el que comparar,
                -- para poder comunicarlo como "sin base" en vez de mostrar 0%.
                CASE
                    WHEN COALESCE(v.net_cost, 0.0) <= 0 THEN NULL
                    ELSE ((COALESCE(v.margen_sales, 0.0) - d.total_devoluciones) - v.net_cost) / v.net_cost * 100.0
                END as roi_real,
                COALESCE(v.net_cost, 0.0) as costo_mercaderia
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
                JOIN edw.dim_almacen al ON f.almacen_sk = al.almacen_sk
                {where_v}
                GROUP BY f.sucursal_sk
            ),
            devoluciones_sucursal AS (
                SELECT dev.sucursal_sk, COALESCE(SUM(dev.total_linea_devolucion), 0) as total_devoluciones
                FROM edw.fact_devoluciones dev
                JOIN edw.dim_sucursal s ON dev.sucursal_sk = s.sucursal_sk
                JOIN edw.dim_fecha d ON dev.fecha_sk = d.fecha_sk
                LEFT JOIN edw.dim_vendedor v ON dev.vendedor_sk = v.vendedor_sk
                JOIN edw.dim_almacen al ON dev.almacen_sk = al.almacen_sk
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
                JOIN edw.dim_almacen al ON f.almacen_sk = al.almacen_sk
                {where_v}
                GROUP BY f.vendedor_sk
            ),
            devoluciones_vendedor AS (
                SELECT dev.vendedor_sk, COALESCE(SUM(dev.total_linea_devolucion), 0) as total_devoluciones
                FROM edw.fact_devoluciones dev
                JOIN edw.dim_sucursal s ON dev.sucursal_sk = s.sucursal_sk
                JOIN edw.dim_fecha d ON dev.fecha_sk = d.fecha_sk
                LEFT JOIN edw.dim_vendedor v ON dev.vendedor_sk = v.vendedor_sk
                JOIN edw.dim_almacen al ON dev.almacen_sk = al.almacen_sk
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
            # None (no 0.0) cuando no hay costo con el que comparar -- se comunica como
            # "sin base de cálculo", criterio de aceptación de G-04 del plan de madurez BI.
            "roi_real": float(res_v[3]) if res_v and res_v[3] is not None else None,
            "costo_mercaderia": float(res_v[4]) if res_v and res_v[4] is not None else 0.0,
            "branch_map": {row[0]: float(row[1]) for row in res_s} if res_s else {},
            "vend_map": {row[0]: float(row[1]) for row in res_vend} if res_vend else {},
        }

    def get_revenue_by_category(
        self, sucursal: str | None = None, start_date: str | None = None,
        end_date: str | None = None, vendedor: str | None = None, almacen: str | None = None,
    ) -> list[dict[str, Any]]:
        where_v, params = self._build_ventas_filters(
            sucursal, start_date, end_date, None, vendedor, require_clase=True, almacen=almacen,
        )
        where_d, params_d = self._build_devoluciones_filters(sucursal, start_date, end_date, vendedor, almacen=almacen)
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
                JOIN edw.dim_almacen al ON f.almacen_sk = al.almacen_sk
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
                JOIN edw.dim_almacen al ON dev.almacen_sk = al.almacen_sk
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
        # Excluir el registro centinela -1 ("desconocido", regla de negocio 12 del CLAUDE.md):
        # no es un vendedor real y ofrecerlo como filtro del dashboard producía series
        # vacías/500 en /gerencia/sales-prediction (hallazgo de la verificación del doc 22).
        res = self.db.execute(text(
            "SELECT DISTINCT nombre_vendedor FROM edw.dim_vendedor "
            "WHERE nombre_vendedor IS NOT NULL AND vendedor_sk <> -1 ORDER BY nombre_vendedor"
        )).fetchall()
        return [str(row[0]) for row in res]

    def get_almacenes(self) -> list[str]:
        # Mismo criterio que get_vendedores: centinela -1 fuera del catálogo de filtros.
        res = self.db.execute(text(
            "SELECT DISTINCT nombre_almacen FROM edw.dim_almacen "
            "WHERE nombre_almacen IS NOT NULL AND almacen_sk <> -1 ORDER BY nombre_almacen"
        )).fetchall()
        return [str(row[0]) for row in res]

    @staticmethod
    def _build_devoluciones_filters(sucursal, start_date, end_date, vendedor, almacen=None):
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
        if almacen:
            filtros.append("al.nombre_almacen = :almacen")
            params["almacen"] = almacen
        if start_date:
            filtros.append("d.fecha_completa >= :start_date")
            params["start_date"] = start_date
        if end_date:
            filtros.append("d.fecha_completa <= :end_date")
            params["end_date"] = end_date

        return ("WHERE " + " AND ".join(filtros)) if filtros else "", params

    @staticmethod
    def _build_ventas_filters(sucursal, start_date, end_date, categoria, vendedor, require_clase=False, almacen=None):
        start_date = sanitize_date_str(start_date)
        end_date = sanitize_date_str(end_date)

        # docs/auditoria/39_madurez_bi_toma_decisiones.md, H-05: excluir la centinela NO es
        # lo mismo que aplicar la regla de negocio 1 (`estado='P'`). Hoy coinciden porque
        # `dim_estado_documento` tiene solo 2 filas y la centinela es justamente la única
        # con estado_factura='A', pero es una equivalencia frágil: al cargar un estado
        # nuevo el filtro dejaría de significar lo que su nombre supone, en silencio.
        # Se explicita la regla 1 conservando la exclusión de la centinela.
        filtros = [FILTRO_ESTADO_VALIDO]
        params: dict[str, Any] = {"estado_valido": settings.ESTADO_DOCUMENTO_VALIDO}
        if require_clase:
            filtros.append("p.clase IS NOT NULL")
        if sucursal:
            filtros.append("s.nombre_sucursal = :sucursal")
            params["sucursal"] = sucursal
        if vendedor:
            filtros.append("v.nombre_vendedor = :vendedor")
            params["vendedor"] = vendedor
        if almacen:
            filtros.append("al.nombre_almacen = :almacen")
            params["almacen"] = almacen
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
    def get_inventory_alerts(self, almacenes_permitidos: list[str] | None = None) -> dict[str, Any]:
        """Usa `edw.fact_inventario_snapshot` de la fecha más reciente disponible
        (es una foto diaria; sumar todo el histórico duplicaría conteos). Columnas
        confirmadas en `edw/03_hechos.sql`: alerta_desabastecimiento, alerta_sobrestock,
        stock_actual. NO existen `dias_abastecimiento_cob`/`inmovilizado_flag` que
        menciona docs/features/dashboards.md -- son campos deseados a futuro, requieren
        cambios de ETL, no se inventan aquí.

        `almacenes_permitidos` (docs/auditoria/42_..., hallazgo Bodega-sucursal): RLS real
        del rol `bodega` -- reemplaza el filtro por `sucursal` que este endpoint legado
        tenía antes. `edw.dim_sucursal` agrupa varios `codalm` muy distintos bajo el mismo
        nombre (ej. "PRINCIPAL: MATRIZ" agrupa 8 almacenes, incluidas camionetas de
        vendedores individuales y bodegas de consignación) -- filtrar por sucursal no es
        la unidad de acceso real del rol bodega (esa es `usuario_almacenes`, por `codalm`),
        y forzarla producía 0 filas para cualquier usuario cuyo `usuarios.sucursal` no
        calzara textualmente con `dim_sucursal.nombre_sucursal`."""
        params: dict[str, Any] = {}
        filtro_alm = ""
        filtro_transfer = ""
        if almacenes_permitidos is not None:
            if not almacenes_permitidos:
                filtro_alm = "AND 1 = 0"
                filtro_transfer = "AND 1 = 0"
            else:
                placeholders = ", ".join(f":alm_{i}" for i in range(len(almacenes_permitidos)))
                for i, codalm in enumerate(almacenes_permitidos):
                    params[f"alm_{i}"] = codalm
                filtro_alm = f"AND al.codalm IN ({placeholders})"
                placeholders_o = ", ".join(f":alm_o_{i}" for i in range(len(almacenes_permitidos)))
                placeholders_d = ", ".join(f":alm_d_{i}" for i in range(len(almacenes_permitidos)))
                for i, codalm in enumerate(almacenes_permitidos):
                    params[f"alm_o_{i}"] = codalm
                    params[f"alm_d_{i}"] = codalm
                filtro_transfer = (
                    f"AND (al_origen.codalm IN ({placeholders_o}) OR al_destino.codalm IN ({placeholders_d}))"
                )

        query_counts = f"""
            WITH ultimo_snapshot AS (SELECT MAX(fecha_sk) AS fecha_sk FROM edw.fact_inventario_snapshot)
            SELECT
                COUNT(*) FILTER (WHERE s.alerta_sobrestock) as items_sobrestock,
                COUNT(*) FILTER (WHERE s.alerta_desabastecimiento) as items_riesgo_desabasto
            FROM edw.fact_inventario_snapshot s
            JOIN ultimo_snapshot u ON s.fecha_sk = u.fecha_sk
            JOIN edw.dim_almacen al ON s.almacen_sk = al.almacen_sk
            WHERE 1=1 {filtro_alm}
        """
        query_transfers = f"""
            WITH ultimo_snapshot AS (SELECT MAX(fecha_sk) AS fecha_sk FROM edw.fact_inventario_snapshot),
            inv AS (
                SELECT s.producto_sk, s.sucursal_sk, s.almacen_sk, s.stock_actual, s.alerta_desabastecimiento, s.alerta_sobrestock
                FROM edw.fact_inventario_snapshot s JOIN ultimo_snapshot u ON s.fecha_sk = u.fecha_sk
            ),
            faltantes AS (SELECT producto_sk, sucursal_sk AS sucursal_destino_sk, almacen_sk AS almacen_destino_sk FROM inv WHERE alerta_desabastecimiento = TRUE),
            sobrantes AS (SELECT producto_sk, sucursal_sk AS sucursal_origen_sk, almacen_sk AS almacen_origen_sk, stock_actual AS stock_origen FROM inv WHERE alerta_sobrestock = TRUE)
            SELECT
                p.nombre_articulo, so_suc.nombre_sucursal AS origen, sd_suc.nombre_sucursal AS destino,
                ROUND(so.stock_origen * 0.3) AS cantidad_sugerida
            FROM faltantes sd
            JOIN sobrantes so ON sd.producto_sk = so.producto_sk AND sd.sucursal_destino_sk != so.sucursal_origen_sk
            JOIN edw.dim_producto p ON sd.producto_sk = p.producto_sk
            JOIN edw.dim_sucursal so_suc ON so.sucursal_origen_sk = so_suc.sucursal_sk
            JOIN edw.dim_sucursal sd_suc ON sd.sucursal_destino_sk = sd_suc.sucursal_sk
            JOIN edw.dim_almacen al_origen ON so.almacen_origen_sk = al_origen.almacen_sk
            JOIN edw.dim_almacen al_destino ON sd.almacen_destino_sk = al_destino.almacen_sk
            WHERE 1=1 {filtro_transfer}
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

    def get_sales_performance(
        self, anio: int, mes: int, sucursal: str | None = None, vendedor: str | None = None,
    ) -> dict[str, Any]:
        """`sucursal` (docs/auditoria/34_actualizacion_modulo_ventas.md, H-V8): antes
        `query_meta` filtraba por `m.sucursal`, una columna que NO existe en
        `public.metas_comerciales_operativas` -- el grano de esa tabla es
        `(anio, mes, id_vendedor_origen)`, nunca sucursal (regla de negocio 10,
        `edw.dim_vendedor` no tiene sucursal propia). Se resuelve restringiendo las
        metas a los vendedores que efectivamente vendieron en esa sucursal en el
        período, no por una columna inexistente. `sucursal` queda como filtro
        OPCIONAL para gerencia (vista exploratoria por sucursal, `ai-summary`).

        `vendedor` (auditoría A-0.3, docs/features/plan_correcciones_integrales_
        sistema.md, decisión B-3, 2026-07-29): filtro real para el rol `ventas` --
        `sucursal` se retira como discriminador de RLS porque el `SELECT` de A-0.3
        contra el EDW real mostró que el 90.9% de los vendedores activos (10 de 11 en
        los últimos 12 meses) transaccionan en 4 a 7 de las 7 sucursales totales
        (promedio 5.18); forzar la sucursal asignada al usuario le ocultaba al propio
        vendedor la mayoría de sus ventas reales. `vendedor` filtra por
        `id_vendedor_origen`/`dim_vendedor.codven` -- el mismo grano ya usado por
        `mi-comision`, `meta-sugerida`, `churn-risk`, etc. en este módulo (regla 10).
        Cuando se pasa `vendedor`, `query_ranking` se omite (comparar un vendedor
        contra sí mismo no aporta nada, y esta vista es personal, no comparativa) --
        `ranking_vendedores` vuelve `[]`, coherente con que ningún consumidor del
        panel del vendedor lo usa (solo `ai-summary`, de gerencia, sigue pidiéndolo
        sin `vendedor`)."""
        params: dict[str, Any] = {"anio": anio, "mes": mes}
        filtro_vendedores_sucursal = ""
        filtro_suc_v = ""
        filtro_suc_r = ""
        if vendedor:
            params["vendedor"] = vendedor
        elif sucursal:
            filtro_vendedores_sucursal = """
                AND m.id_vendedor_origen IN (
                    SELECT DISTINCT v2.codven
                    FROM edw.fact_ventas_detalle f2
                    JOIN edw.dim_vendedor v2 ON f2.vendedor_sk = v2.vendedor_sk
                    JOIN edw.dim_sucursal s2 ON f2.sucursal_sk = s2.sucursal_sk
                    JOIN edw.dim_fecha d2 ON f2.fecha_sk = d2.fecha_sk
                    WHERE d2.anio = :anio AND d2.mes = :mes AND s2.nombre_sucursal = :sucursal
                )
            """
            filtro_suc_v = "AND s.nombre_sucursal = :sucursal"
            filtro_suc_r = "AND s.nombre_sucursal = :sucursal"
            params["sucursal"] = sucursal

        # No se filtra por estado ('APROBADA' vs 'PROPUESTA'): un sistema recién puesto en
        # marcha puede no tener nada aprobado todavía, y mostrar 0 en el agregado mientras
        # el ranking sí muestra metas individuales (que tampoco filtra por estado) sería
        # inconsistente. Se muestra la meta vigente sin importar si ya fue aprobada.
        query_meta = f"""
            SELECT COALESCE(SUM(m.monto_meta), 0)
            FROM public.metas_comerciales_operativas m
            WHERE m.anio = :anio AND m.mes = :mes
              {"AND m.id_vendedor_origen = :vendedor" if vendedor else filtro_vendedores_sucursal}
        """
        query_actual = f"""
            SELECT COALESCE(SUM(f.subtotal_neto), 0)
            FROM edw.fact_ventas_detalle f
            JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
            JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
            {"JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk" if vendedor else
             "JOIN edw.dim_sucursal s ON f.sucursal_sk = s.sucursal_sk"}
            WHERE d.anio = :anio AND d.mes = :mes AND ed.estado_documento_sk <> -1
              {"AND v.codven = :vendedor" if vendedor else filtro_suc_v}
        """
        meta_mensual = float(self.db.execute(text(query_meta), params).scalar() or 0.0)
        cumplimiento_actual = float(self.db.execute(text(query_actual), params).scalar() or 0.0)

        if vendedor:
            ranking: list[Any] = []
        else:
            query_ranking = f"""
                SELECT v.nombre_vendedor,
                       COALESCE(SUM(f.subtotal_neto), 0) as ventas,
                       COALESCE(MAX(m.monto_meta), 0) as meta
                FROM edw.dim_vendedor v
                LEFT JOIN edw.fact_ventas_detalle f ON f.vendedor_sk = v.vendedor_sk
                    AND f.fecha_sk IN (SELECT fecha_sk FROM edw.dim_fecha WHERE anio = :anio AND mes = :mes)
                LEFT JOIN edw.dim_sucursal s ON f.sucursal_sk = s.sucursal_sk
                LEFT JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                    AND ed.estado_documento_sk <> -1
                LEFT JOIN public.metas_comerciales_operativas m ON m.id_vendedor_origen = v.codven
                    AND m.anio = :anio AND m.mes = :mes
                WHERE 1=1 {filtro_suc_r}
                GROUP BY v.nombre_vendedor
                HAVING COALESCE(SUM(f.subtotal_neto), 0) > 0
                ORDER BY ventas DESC
                LIMIT 15
            """
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

    # ── Dashboard "Mi Negocio" del vendedor (auditoría 43, Fase 5) ────────────────
    def get_evolucion_mensual_vendedor(self, codven: str, meses: int = 6) -> list[dict[str, Any]]:
        """Venta neta real vs. meta configurada, mes a mes, para UN vendedor -- grano
        `(anio, mes, id_vendedor_origen)` (regla 10). Usa la definición canónica de
        **Venta Neta** (G-02, `app/services/metricas/venta_neta.py`: venta bruta con
        líneas positivas menos devoluciones, filtrando `estado_factura` -- no solo el
        centinela) para que coincida con `GoalRepository.get_vendor_net_sales_period`
        (la cifra que ya muestra "Mi Meta y Comisión"); una versión anterior de este
        método sumaba `subtotal_neto` sin restar devoluciones y sin el filtro de estado,
        y difería de esa cifra en miles de dólares en datos reales (auditoría 43,
        validado en vivo: VEN02 mostraba $47.559,92 aquí contra $54.976,83 en el panel
        de comisión para el mismo mes). `meses` cuenta desde el mes actual hacia atrás,
        incluyéndolo."""
        rows = self.db.execute(
            text(
                f"""
                WITH meses_base AS (
                    SELECT DISTINCT d.anio, d.mes
                    FROM edw.dim_fecha d
                    WHERE d.fecha_completa <= CURRENT_DATE
                      AND d.fecha_completa >= CURRENT_DATE - (:meses || ' months')::interval
                ),
                ventas_brutas AS (
                    SELECT d.anio, d.mes, {SQL_VENTA_BRUTA} AS venta_bruta
                    FROM edw.fact_ventas_detalle f
                    JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
                    JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                    JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                    WHERE v.codven = :codven AND {FILTRO_ESTADO_VALIDO}
                      AND d.fecha_completa <= CURRENT_DATE
                      AND d.fecha_completa >= CURRENT_DATE - (:meses || ' months')::interval
                    GROUP BY d.anio, d.mes
                ),
                devoluciones AS (
                    SELECT d.anio, d.mes, COALESCE(SUM(fd.total_linea_devolucion), 0.0) AS devolucion
                    FROM edw.fact_devoluciones fd
                    JOIN edw.dim_vendedor v ON fd.vendedor_sk = v.vendedor_sk
                    JOIN edw.dim_fecha d ON fd.fecha_sk = d.fecha_sk
                    WHERE v.codven = :codven
                      AND d.fecha_completa <= CURRENT_DATE
                      AND d.fecha_completa >= CURRENT_DATE - (:meses || ' months')::interval
                    GROUP BY d.anio, d.mes
                )
                SELECT mb.anio, mb.mes,
                       COALESCE(vb.venta_bruta, 0) - COALESCE(dv.devolucion, 0) AS venta,
                       COALESCE(m.monto_meta, 0) AS meta
                FROM meses_base mb
                LEFT JOIN ventas_brutas vb ON vb.anio = mb.anio AND vb.mes = mb.mes
                LEFT JOIN devoluciones dv ON dv.anio = mb.anio AND dv.mes = mb.mes
                LEFT JOIN public.metas_comerciales_operativas m
                    ON m.anio = mb.anio AND m.mes = mb.mes AND m.id_vendedor_origen = :codven
                ORDER BY mb.anio, mb.mes
                """
            ),
            {"codven": codven, "meses": meses, "estado_valido": settings.ESTADO_DOCUMENTO_VALIDO},
        ).fetchall()
        return [
            {"anio": int(r[0]), "mes": int(r[1]), "venta_real": float(r[2]), "meta": float(r[3])}
            for r in rows
        ]

    def get_top_productos_vendedor(self, codven: str, meses: int = 3, limit: int = 5) -> list[dict[str, Any]]:
        """Productos más vendidos POR este vendedor (no del catálogo general), últimos
        `meses` -- mismo filtro de estado que la definición canónica de Venta Neta
        (líneas positivas, `estado_factura` válido); sin restar devoluciones por
        producto porque `fact_devoluciones` no tiene ese grano (mismo criterio
        documentado en `venta_neta.py`)."""
        rows = self.db.execute(
            text(
                f"""
                SELECT p.codart, MAX(p.nombre_articulo) AS nombre,
                       {SQL_VENTA_BRUTA} AS venta,
                       SUM(CASE WHEN f.subtotal_neto > 0 THEN f.cantidad ELSE 0 END) AS unidades
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                JOIN edw.dim_producto p ON f.producto_sk = p.producto_sk
                WHERE v.codven = :codven AND {FILTRO_ESTADO_VALIDO}
                  AND p.producto_sk <> -1
                  AND d.fecha_completa >= CURRENT_DATE - (:meses || ' months')::interval
                GROUP BY p.codart
                ORDER BY venta DESC
                LIMIT :limit
                """
            ),
            {"codven": codven, "meses": meses, "limit": limit, "estado_valido": settings.ESTADO_DOCUMENTO_VALIDO},
        ).fetchall()
        return [
            {"codart": str(r[0]), "nombre": r[1] or "", "venta": float(r[2] or 0), "unidades": float(r[3] or 0)}
            for r in rows
        ]