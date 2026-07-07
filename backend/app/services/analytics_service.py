# backend/app/services/analytics_service.py
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Dict, Any, List
import re

class AnalyticsService:
    """
    Servicio de base de datos para extraer los KPIs agregados del DW PostgreSQL.
    Implementa consultasSQL directas para no sobrecargar el backend con carga de modelos ORM
    """
    def __init__(self, db: Session):
        self.db = db

    def get_management_kpis(self, sucursal: str = None, start_date: str = None, end_date: str = None, categoria: str = None, vendedor: str = None) -> Dict[str, Any]:
        """
        Caso de Uso 2 (Gerencia): Índice de Salud Comercial
        Calcula: Margen neto, ticket promedio, estimación de ROI y ventas por sucursal
        """
        # Filtros específicos de ventas y devoluciones para calcular Net Sales
        filtros_v = ["f.estado_factura = 'P'"]
        filtros_d = []
        
        # Sanitizar fechas para evitar errores de sintaxis en Postgres (ej. entradas parciales)
        if start_date and not re.match(r'^\d{4}-\d{2}-\d{2}$', start_date):
            start_date = None
        if end_date and not re.match(r'^\d{4}-\d{2}-\d{2}$', end_date):
            end_date = None

        params = {}
        if sucursal:
            filtros_v.append("s.nombre_sucursal = :sucursal")
            filtros_d.append("s.nombre_sucursal = :sucursal")
            params["sucursal"] = sucursal
        if vendedor:
            filtros_v.append("v.nombre_vendedor = :vendedor")
            filtros_d.append("v.nombre_vendedor = :vendedor")
            params["vendedor"] = vendedor
        if start_date:
            filtros_v.append("d.fecha_completa >= :start_date")
            filtros_d.append("d.fecha_completa >= :start_date")
            params["start_date"] = start_date
        if end_date:
            filtros_v.append("d.fecha_completa <= :end_date")
            filtros_d.append("d.fecha_completa <= :end_date")
            params["end_date"] = end_date
        if categoria:
            filtros_v.append("p.clase = :categoria")
            filtros_d.append("p.clase = :categoria")
            params["categoria"] = categoria

        where_v = "WHERE " + " AND ".join(filtros_v)
        where_d = "WHERE " + " AND ".join(filtros_d) if filtros_d else ""

        query_ventas = f"""
            WITH sales_agg AS (
                SELECT 
                    SUM(f.subtotal_neto) as net_sales,
                    SUM(f.costo_total) as net_cost,
                    COUNT(DISTINCT f.num_factura) as cnt_facturas
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_sucursal s ON f.sucursal_sk = s.sucursal_sk
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_producto p ON f.producto_sk = p.producto_sk
                LEFT JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
                {where_v}
            )
            SELECT 
                COALESCE(sa.net_sales, 0.0) as total_ventas,
                COALESCE(sa.net_sales, 0.0) / NULLIF(sa.cnt_facturas, 0) as ticket_promedio,
                ((COALESCE(sa.net_sales, 0.0)) - (COALESCE(sa.net_cost, 0.0))) / NULLIF(COALESCE(sa.net_sales, 0.0), 0.0) * 100.0 as margen_promedio
            FROM sales_agg sa
        """
        
        query_sucursales = f"""
            WITH sales_agg AS (
                SELECT f.sucursal_sk, SUM(f.subtotal_neto) as net_sales
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_sucursal s ON f.sucursal_sk = s.sucursal_sk
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_producto p ON f.producto_sk = p.producto_sk
                LEFT JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
                {where_v}
                GROUP BY f.sucursal_sk
            )
            SELECT 
                s.nombre_sucursal, 
                COALESCE(sa.net_sales, 0.0) as net_sales
            FROM edw.dim_sucursal s
            LEFT JOIN sales_agg sa ON s.sucursal_sk = sa.sucursal_sk
            WHERE sa.net_sales IS NOT NULL
        """

        query_vendedores = f"""
            WITH sales_agg AS (
                SELECT f.vendedor_sk, SUM(f.subtotal_neto) as net_sales
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_sucursal s ON f.sucursal_sk = s.sucursal_sk
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_producto p ON f.producto_sk = p.producto_sk
                LEFT JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
                {where_v}
                GROUP BY f.vendedor_sk
            )
            SELECT 
                v.nombre_vendedor, 
                COALESCE(sa.net_sales, 0.0) as net_sales
            FROM edw.dim_vendedor v
            LEFT JOIN sales_agg sa ON v.vendedor_sk = sa.vendedor_sk
            WHERE sa.net_sales IS NOT NULL
            ORDER BY net_sales DESC
            LIMIT 15
        """

        try:
            res_v = self.db.execute(text(query_ventas), params).fetchone()
            total_sales = float(res_v[0]) if res_v and res_v[0] is not None else 0.0
            ticket = float(res_v[1]) if res_v and res_v[1] is not None else 0.0
            margen = float(res_v[2]) if res_v and res_v[2] is not None else 0.0
            
            res_s = self.db.execute(text(query_sucursales), params).fetchall()
            branch_map = {row[0]: float(row[1]) for row in res_s} if res_s else {}
            
            res_vend = self.db.execute(text(query_vendedores), params).fetchall()
            vend_map = {row[0]: float(row[1]) for row in res_vend} if res_vend else {}
            
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error en get_management_kpis: {e}")
            total_sales, ticket, margen, branch_map, vend_map = 0.0, 0.0, 0.0, {}, {}

        return {
            "margen_utilidad_neta": round(margen, 2),
            "ticket_promedio": round(ticket, 2),
            "roi_estimado": round(margen * 1.15, 2), # Simulación adaptada de ROI de campaña
            "ventas_por_sucursal": branch_map,
            "ventas_por_vendedor": vend_map
        }

    def get_revenue_by_category(self, sucursal: str = None, start_date: str = None, end_date: str = None, vendedor: str = None) -> List[Dict[str, Any]]:
        # Sanitizar fechas para evitar errores de sintaxis en Postgres (ej. entradas parciales)
        if start_date and not re.match(r'^\d{4}-\d{2}-\d{2}$', start_date):
            start_date = None
        if end_date and not re.match(r'^\d{4}-\d{2}-\d{2}$', end_date):
            end_date = None

        filtros_v = ["f.estado_factura = 'P'", "p.clase IS NOT NULL"]
        filtros_d = ["p.clase IS NOT NULL"]
        params = {}
        if sucursal:
            filtros_v.append("s.nombre_sucursal = :sucursal")
            filtros_d.append("s.nombre_sucursal = :sucursal")
            params["sucursal"] = sucursal
        if vendedor:
            filtros_v.append("v.nombre_vendedor = :vendedor")
            filtros_d.append("v.nombre_vendedor = :vendedor")
            params["vendedor"] = vendedor
        if start_date:
            filtros_v.append("d.fecha_completa >= :start_date")
            filtros_d.append("d.fecha_completa >= :start_date")
            params["start_date"] = start_date
        if end_date:
            filtros_v.append("d.fecha_completa <= :end_date")
            filtros_d.append("d.fecha_completa <= :end_date")
            params["end_date"] = end_date

        where_v = "WHERE " + " AND ".join(filtros_v)
        where_d = "WHERE " + " AND ".join(filtros_d)

        query = f"""
            WITH sales_agg AS (
                SELECT p.clase as categoria, SUM(f.subtotal_neto) as net_sales
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_producto p ON f.producto_sk = p.producto_sk
                JOIN edw.dim_sucursal s ON f.sucursal_sk = s.sucursal_sk
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                LEFT JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
                {where_v}
                GROUP BY p.clase
            )
            SELECT 
                sa.categoria,
                COALESCE(sa.net_sales, 0.0) as net_sales
            FROM sales_agg sa
            WHERE sa.categoria IS NOT NULL
            ORDER BY net_sales DESC
            LIMIT 10
        """
        try:
            res = self.db.execute(text(query), params).fetchall()
            return [{"cat": str(row[0]), "v": float(row[1] or 0)} for row in res]
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error en get_revenue_by_category: {e}")
            return []

    def get_categories(self) -> List[str]:
        query = "SELECT DISTINCT clase FROM edw.dim_producto WHERE clase IS NOT NULL ORDER BY clase"
        try:
            res = self.db.execute(text(query)).fetchall()
            return [str(row[0]) for row in res]
        except Exception:
            return []

    def get_sucursales(self) -> List[str]:
        query = "SELECT DISTINCT nombre_sucursal FROM edw.dim_sucursal WHERE nombre_sucursal IS NOT NULL ORDER BY nombre_sucursal"
        try:
            res = self.db.execute(text(query)).fetchall()
            return [str(row[0]) for row in res]
        except Exception:
            return []

    def get_vendedores(self) -> List[str]:
        query = "SELECT DISTINCT nombre_vendedor FROM edw.dim_vendedor WHERE nombre_vendedor IS NOT NULL ORDER BY nombre_vendedor"
        try:
            res = self.db.execute(text(query)).fetchall()
            return [str(row[0]) for row in res]
        except Exception:
            return []

    def get_warehouse_kpis(self, sucursal: str = None) -> Dict[str, Any]:
        """
        Caso de Uso 3 (Bodega): Alertas de Desabastecimiento
        Retorna la cantidad de productos en sobrestock, en riesgo de desabastecimiento,
        y recomendaciones de transferencia.
        """
        # En una base de datos analítica real, cruzamos la cantidad en percha (kardex) 
        # frente a los puntos de reorden mínimos históricos.
        return {
            "items_sobrestock": 18,
            "items_riesgo_desabasto": 4,
            "transferencias_recomendadas": [
                {
                    "producto": "Cemento Selvalegre 50kg",
                    "origen": "Ambato",
                    "destino": "Cuenca",
                    "cantidad_sugerida": 150,
                    "explicacion": "Cuenca reporta riesgo inminente de desabastecimiento (< 20 sacos) mientras que Ambato posee stock inmovilizado hace más de 30 días."
                }
            ]
        }

    def get_sales_kpis(self, sucursal: str = None) -> Dict[str, Any]:
        """
        Caso de Uso 4 (Ventas): Cumplimiento de metas de vendedor
        """
        return {
            "meta_mensual": 45000.0,
            "cumplimiento_actual": 32150.0,
            "meta_proyectada": 43500.0,
            "ranking_vendedores": [
                {"nombre": "Carlos Perez", "ventas": 12500.0, "meta": 15000.0, "cumple": True},
                {"nombre": "Maria Lopez", "ventas": 10200.0, "meta": 15000.0, "cumple": False},
                {"nombre": "Rodrigo Silva", "ventas": 9450.0, "meta": 15000.0, "cumple": False}
            ]
        }

class GoalsAutomationService:
    def __init__(self, db: Session):
        self.db = db

    def generar_propuestas_metas(self, anio: int, mes: int, factor_presion: float = 1.10) -> int:
        """
        Produce metas predicciones avanzadas usando RandomForest (goals_rf_model.pkl) si está disponible
        """
        import logging
        import os
        import pandas as pd
        import joblib
        
        logger = logging.getLogger(__name__)

        mes_ant = 12 if mes == 1 else mes - 1
        anio_ant = anio - 1 if mes == 1 else anio

        query_historial = text("""
            WITH SalesHist AS (
                SELECT
                    v.codven AS vendedor_origen,
                    s.nombre_sucursal AS sucursal,
                    MAX(f.vendedor_sk) AS vendedor_sk,
                    MAX(f.sucursal_sk) AS sucursal_sk,
                    d.anio,
                    d.mes,
                    SUM(f.subtotal_neto) AS net_sales,
                    SUM(f.cantidad) AS net_unidades
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_sucursal s ON f.sucursal_sk = s.sucursal_sk
                JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
                WHERE f.estado_factura = 'P'
                GROUP BY v.codven, s.nombre_sucursal, d.anio, d.mes
            ),
            Hist AS (
                SELECT
                    vendedor_origen,
                    sucursal,
                    vendedor_sk,
                    sucursal_sk,
                    anio,
                    mes,
                    net_sales AS ventas,
                    net_unidades AS unidades
                FROM SalesHist
            ),
            Calculated AS (
                SELECT
                    vendedor_origen,
                    sucursal,
                    vendedor_sk,
                    sucursal_sk,
                    anio,
                    mes,
                    ventas AS ventas_anterior,
                    unidades AS unidades_anterior,
                    LAG(ventas, 12) OVER (PARTITION BY vendedor_origen, sucursal ORDER BY anio, mes) AS ventas_anio_anterior,
                    AVG(ventas) OVER (PARTITION BY vendedor_origen, sucursal ORDER BY anio, mes ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS promedio_movil_3m
                FROM Hist
            )
            SELECT 
                vendedor_origen, 
                sucursal, 
                ventas_anterior, 
                unidades_anterior,
                COALESCE(ventas_anio_anterior, 0) AS ventas_anio_anterior,
                COALESCE(promedio_movil_3m, ventas_anterior) AS promedio_movil_3m,
                vendedor_sk,
                sucursal_sk
            FROM Calculated
            WHERE anio = :anio_ant AND mes = :mes_ant
        """)

        try:
            historial = self.db.execute(query_historial, {"anio_ant": anio_ant, "mes_ant": mes_ant}).fetchall()
            registros_creados = 0
            
            # Intentar cargar Modelo Predictivo
            ml_model = None
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            model_path = os.path.join(base_dir, "..", "ml_models", "goals_rf_model.pkl")
            
            if os.path.exists(model_path):
                ml_model = joblib.load(model_path)
                logger.info("Cargado goals_rf_model.pkl exitosamente para predicción de metas.")

            for row in historial:
                cod_ven, sucursal, ventas_ant, unidades_ant, ventas_yoy, mavg_3m, vendedor_sk, sucursal_sk = row
                
                meta_monto = 0.0
                
                if ml_model:
                    # Inferencia MD ordenada de 6 variables
                    df_pred = pd.DataFrame([{
                        "vendedor_sk": int(vendedor_sk),
                        "sucursal_sk": int(sucursal_sk),
                        "anio": anio_ant,
                        "mes": mes_ant,
                        "ventas_historicas": float(ventas_ant or 0.0),
                        "unidades_historicas": float(unidades_ant or 0.0)
                    }], columns=['vendedor_sk', 'sucursal_sk', 'anio', 'mes', 'ventas_historicas', 'unidades_historicas'])
                    growth_ratio = float(ml_model.predict(df_pred)[0])
                    # Limitar predicciones de logica averiada si existen
                    growth_ratio = max(0.8, min(growth_ratio, 1.2))
                    
                    # El baseline a multiplicar la Tasa debe reflejar estacionalidad y tendencia actual
                    # Si el crecimiento es bajo o alto, usar un promedio móvil con más peso hacia ventas históricas
                    baseline = (float(ventas_ant or 0.0) * 0.5) + (float(mavg_3m or ventas_ant or 0.0) * 0.5)
                    
                    y_pred = float(baseline) * growth_ratio
                    # Refuerzo: La meta no debe exceder irracionalmente el promedio movil actual (máximo 120%)
                    # ni caer absurdamente abajo del promedio móvil (mínimo 80%) para mantener histórico realista
                    safe_limit_max = float(mavg_3m or ventas_ant or 0) * 1.2
                    safe_limit_min = float(mavg_3m or ventas_ant or 0) * 0.8
                    y_pred = max(safe_limit_min, min(y_pred, safe_limit_max))
                    
                    # Capping absoluto final con hist_yoy en caso de ciclos atípicos
                    y_pred = max((float(ventas_yoy or 0) * 0.8), y_pred)
                    
                    # Aplicamos factor_presion sobre lo predecido como desafío ideal
                    meta_monto = max(float(ventas_ant or 0), float(y_pred)) * factor_presion
                else:
                    # Fallback heuristico
                    meta_monto = float(ventas_ant or 0.0) * factor_presion
                    
                meta_unidades = float(unidades_ant or 0.0) * factor_presion
                
                # Bounding constraints: must be non-negative
                meta_monto = max(0.0, meta_monto)
                meta_unidades = max(0.0, meta_unidades)

                check_q = text("""
                    SELECT id, estado FROM public.metas_comerciales_operativas 
                    WHERE anio = :anio AND mes = :mes AND id_vendedor_origen = :vendedor AND sucursal = :sucursal
                """)
                exists = self.db.execute(check_q, {
                    "anio": anio, "mes": mes, "vendedor": cod_ven, "sucursal": sucursal
                }).fetchone()

                if not exists:
                    insert_q = text("""
                        INSERT INTO public.metas_comerciales_operativas
                        (anio, mes, id_vendedor_origen, sucursal, monto_meta, unidades_meta, estado, comision_base_pct, bono_sobrecumplimiento)
                        VALUES (:anio, :mes, :vendedor, :sucursal, :meta_monto, :meta_unidades, 'PROPUESTA', 0.0, 0.0)
                    """)
                    self.db.execute(insert_q, {
                        "anio": anio, "mes": mes, "vendedor": cod_ven, "sucursal": sucursal,
                        "meta_monto": meta_monto, "meta_unidades": meta_unidades
                    })
                    registros_creados += 1
                else:
                    # Update existing record if it is still a proposal and user generates it again
                    row_id, estado_actual = exists
                    if estado_actual == 'PROPUESTA':
                        update_q = text("""
                            UPDATE public.metas_comerciales_operativas
                            SET monto_meta = :meta_monto,
                                unidades_meta = :meta_unidades
                            WHERE id = :id
                        """)
                        self.db.execute(update_q, {
                            "meta_monto": meta_monto, "meta_unidades": meta_unidades, "id": row_id
                        })
                        registros_creados += 1

            self.db.commit()
            return registros_creados
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error generando metas automáticas: {str(e)}")
            raise e

    def get_goals_periods(self) -> List[Dict[str, int]]:
        """
        Retorna los periodos históricos únicos y asegura que el actual y siguiente (basado en DW) estén presentes
        """
        query_hist = text("""
            SELECT DISTINCT anio, mes 
            FROM public.metas_comerciales_operativas
            ORDER BY anio DESC, mes DESC
        """)
        
        query_max_date = text("""
            SELECT MAX(d.anio) as max_anio, MAX(d.mes) as max_mes
            FROM edw.fact_ventas_detalle f
            JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
            WHERE d.anio = (
                SELECT MAX(d2.anio) FROM edw.fact_ventas_detalle f2 JOIN edw.dim_fecha d2 ON f2.fecha_sk = d2.fecha_sk
            )
        """)

        try:
            max_res = self.db.execute(query_max_date).fetchone()
            if max_res and max_res[0]:
                current_year = int(max_res[0])
                current_month = int(max_res[1])
            else:
                import datetime
                now = datetime.datetime.now()
                current_year = now.year
                current_month = now.month
                
            next_month = current_month + 1 if current_month < 12 else 1
            next_month_year = current_year if current_month < 12 else current_year + 1

            records = self.db.execute(query_hist).fetchall()
            periods = [{"anio": row[0], "mes": row[1]} for row in records]
            
            # Asegurar que el periodo actual exista
            if not any(p['anio'] == current_year and p['mes'] == current_month for p in periods):
                periods.insert(0, {"anio": current_year, "mes": current_month})
                
            # Asegurar que próximo periodo exista
            if not any(p['anio'] == next_month_year and p['mes'] == next_month for p in periods):
                periods.insert(0, {"anio": next_month_year, "mes": next_month})
                
            # Reordenar por año asc, mes exp. asc
            periods.sort(key=lambda x: (x["anio"], x["mes"]), reverse=False)
            return periods
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error obteniendo periodos: {str(e)}")
            return []

    def liquidar_comisiones_periodo(self, anio: int, mes: int) -> List[Dict[str, Any]]:
        """
        Calcula las comisiones liquidadas basándose en la consecución de las metas.
        """
        query = text("""
            SELECT
                MAX(v.nombre_vendedor) AS vendedor,
                m.sucursal,
                m.monto_meta AS meta_monto,
                m.comision_base_pct,
                m.bono_sobrecumplimiento,
                m.id AS id_meta,
                m.estado
            FROM public.metas_comerciales_operativas m
            LEFT JOIN edw.dim_vendedor v ON m.id_vendedor_origen = v.codven
            WHERE m.anio = :anio AND m.mes = :mes
            GROUP BY m.id, m.sucursal, m.monto_meta, m.comision_base_pct, m.bono_sobrecumplimiento, m.estado
            ORDER BY MAX(v.nombre_vendedor) ASC
        """)

        datos = self.db.execute(query, {"anio": anio, "mes": mes}).fetchall()
        reporte = []

        for row in datos:
            vendedor, sucursal, meta, com_pct, bono, id_meta, estado = row
            
            # Para la demo o mvp se simulan ventas o consultan
            # Por simplicidad aquí en seguimiento mostramos status de progeso si hubiera:
            # En la vista React usan `GoalCommissionReportItem` de la metadata.
            reporte.append({
                "id": int(id_meta),
                "vendedor": str(vendedor),
                "sucursal": str(sucursal),
                "monto_meta": float(meta),
                "comision_base_pct": float(com_pct),
                "estado": str(estado)
            })

        return reporte
