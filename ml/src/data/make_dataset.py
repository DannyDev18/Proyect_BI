import os
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime

class SalesTimeSerieExtractor:
    def __init__(self):
        pg_user = os.getenv("PG_USER", "etl_user")
        pg_password = os.getenv("PG_PASSWORD", "CHANGE_ME")
        pg_host = os.getenv("PG_HOST", "localhost")
        pg_port = os.getenv("PG_PORT", "5433")
        pg_db = os.getenv("PG_DB", "edw")
        
        url = f"postgresql+psycopg2://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"
        self.engine = create_engine(url)

    def fetch_daily_sales(self) -> pd.DataFrame:
        sql = """
            SELECT 
                df.fecha_completa as ds,
                SUM(fvd.subtotal_neto) as y_sales_net,
                SUM(fvd.cantidad) as y_quantity
            FROM edw.fact_ventas_detalle fvd
            JOIN edw.dim_fecha df ON fvd.fecha_sk = df.fecha_sk
            GROUP BY df.fecha_completa
            ORDER BY df.fecha_completa;
        """
        df = pd.read_sql(sql, self.engine)
        if not df.empty:
            df['ds'] = pd.to_datetime(df['ds'])
            df.set_index('ds', inplace=True)
        return df

    def fetch_sales_by_dimension(self, dimension='producto') -> pd.DataFrame:
        if dimension == 'producto':
            sql = """
                SELECT 
                    df.fecha_completa as ds,
                    p.nombre_articulo as producto,
                    SUM(fvd.cantidad) as y_quantity
                FROM edw.fact_ventas_detalle fvd
                JOIN edw.dim_fecha df ON fvd.fecha_sk = df.fecha_sk
                JOIN edw.dim_producto p ON fvd.producto_sk = p.producto_sk
                GROUP BY df.fecha_completa, p.nombre_articulo
                ORDER BY df.fecha_completa;
            """
        else:
            return pd.DataFrame()
        df = pd.read_sql(sql, self.engine)
        if not df.empty:
            df['ds'] = pd.to_datetime(df['ds'])
            df.set_index('ds', inplace=True)
        return df

    def fetch_rfm_metrics(self) -> pd.DataFrame:
        sql = """
            SELECT 
                cliente_sk,
                MAX(df.fecha_completa) as last_purchase_date,
                COUNT(DISTINCT fvd.fecha_sk) as frequency,
                SUM(fvd.subtotal_neto) as monetary_value
            FROM edw.fact_ventas_detalle fvd
            JOIN edw.dim_fecha df ON fvd.fecha_sk = df.fecha_sk
            GROUP BY cliente_sk;
        """
        df = pd.read_sql(sql, self.engine)
        if not df.empty:
            max_date = pd.to_datetime(df['last_purchase_date']).max()
            df['recency'] = (max_date - pd.to_datetime(df['last_purchase_date'])).dt.days
        return df

    def fetch_churn_data(self) -> pd.DataFrame:
        df = self.fetch_rfm_metrics()
        if not df.empty:
            df['is_churn'] = (df['recency'] > 90).astype(int)
        return df

    def fetch_market_basket(self) -> pd.DataFrame:
        sql = """
            SELECT 
                fvd.fecha_sk || '_' || fvd.cliente_sk || '_' || fvd.sucursal_sk as transaction_id,
                p.nombre_articulo as product_name
            FROM edw.fact_ventas_detalle fvd
            JOIN edw.dim_producto p ON fvd.producto_sk = p.producto_sk
            LIMIT 50000;
        """
        return pd.read_sql(sql, self.engine)

    def fetch_transactions_for_anomalies(self) -> pd.DataFrame:
        sql = """
            SELECT 
                subtotal_neto,
                cantidad,
                costo_total,
                (subtotal_neto - costo_total) as margen
            FROM edw.fact_ventas_detalle
            LIMIT 20000;
        """
        return pd.read_sql(sql, self.engine)

    def fetch_goals_data(self) -> pd.DataFrame:
        sql = """
            WITH MonthlySales AS (
                SELECT 
                    f.vendedor_sk,
                    f.sucursal_sk,
                    d.anio,
                    d.mes,
                    d.anio * 100 + d.mes as anio_mes_id,
                    SUM(f.subtotal_neto) as ventas_historicas,
                    SUM(f.cantidad) as unidades_historicas
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                WHERE f.estado_factura != 'I'
                GROUP BY f.vendedor_sk, f.sucursal_sk, d.anio, d.mes
            ),
            FeatureEnriched AS (
                SELECT
                    a.vendedor_sk,
                    a.sucursal_sk,
                    a.anio,
                    a.mes,
                    a.ventas_historicas,
                    a.unidades_historicas,
                    
                    -- Ventas hace exactamente 1 anio
                    LAG(a.ventas_historicas, 12) OVER (
                        PARTITION BY a.vendedor_sk, a.sucursal_sk 
                        ORDER BY a.anio, a.mes
                    ) as ventas_anio_anterior,
                    
                    -- Promedio Movil 3 meses (suavizador historico) excluyendo mes actual (LAG)
                    AVG(a.ventas_historicas) OVER (
                        PARTITION BY a.vendedor_sk, a.sucursal_sk 
                        ORDER BY a.anio, a.mes 
                        ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING
                    ) as promedio_movil_3m

                FROM MonthlySales a
            )
            SELECT 
                a.vendedor_sk,
                a.sucursal_sk,
                a.anio,
                a.mes,
                a.ventas_historicas,
                a.unidades_historicas,
                COALESCE(a.ventas_anio_anterior, 0) as ventas_anio_anterior,
                COALESCE(a.promedio_movil_3m, a.ventas_historicas) as promedio_movil_3m,
                -- Meta predictiva Limitada (Target ratio)
                CASE 
                    WHEN a.ventas_historicas = 0 AND b.ventas_historicas = 0 THEN 1.0
                    WHEN a.ventas_historicas = 0 AND b.ventas_historicas > 0 THEN 1.5
                    ELSE LEAST(COALESCE((b.ventas_historicas / NULLIF(a.ventas_historicas, 0)), 1.0), 1.5)
                END as y_ventas_futuras
            FROM FeatureEnriched a
            JOIN MonthlySales b 
                ON a.vendedor_sk = b.vendedor_sk 
                AND a.sucursal_sk = b.sucursal_sk
                AND (
                    (a.anio = b.anio AND a.mes + 1 = b.mes)
                    OR (a.anio + 1 = b.anio AND a.mes = 12 AND b.mes = 1)
                )
        """
        return pd.read_sql(sql, self.engine)
