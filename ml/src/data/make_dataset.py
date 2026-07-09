import os
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime

# Regla de negocio: un cliente se considera en abandono (churn) si no compra hace más de
# 90 días. Umbral acordado como proxy (no existe campo de baja explícito en el origen);
# ajustable por env var sin tocar código.
CHURN_UMBRAL_DIAS = int(os.getenv("ML_CHURN_UMBRAL_DIAS", "90"))

# Tamaños de muestra para los modelos no supervisados. Se muestrean las N líneas MÁS
# RECIENTES (ORDER BY venta_sk DESC) para que la corrida sea determinista y refleje el
# régimen actual del negocio (antes: LIMIT sin ORDER BY = muestra arbitraria no reproducible).
MUESTRA_MARKET_BASKET = int(os.getenv("ML_MUESTRA_MARKET_BASKET", "50000"))
MUESTRA_ANOMALIAS = int(os.getenv("ML_MUESTRA_ANOMALIAS", "20000"))


class SalesTimeSerieExtractor:
    def __init__(self):
        pg_user = os.getenv("PG_USER", "etl_user")
        pg_password = os.getenv("PG_PASSWORD")
        if not pg_password:
            raise ValueError("PG_PASSWORD no está definida en el entorno (revisar .env / docker compose).")
        pg_host = os.getenv("PG_HOST", "localhost")
        pg_port = os.getenv("PG_PORT", "5433")
        pg_db = os.getenv("PG_DB", "edw")

        url = f"postgresql+psycopg2://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"
        self.engine = create_engine(url)

    def fetch_daily_sales(self) -> pd.DataFrame:
        """Serie diaria de ventas netas enriquecida con variables exógenas de la propia
        `fact_ventas_detalle` (mezcla de clientes/facturas/descuento del día), además del
        target. Se evaluaron también `fact_cobros_cxc` (cobranza del día) y
        `fact_inventario_snapshot` (stockouts) como exógenas adicionales, pero se
        descartaron con evidencia empírica: `fact_inventario_snapshot` casi no tiene
        histórico (<1% de cobertura antes de 2026, es una tabla poblada solo hacia
        adelante) y `valor_cobrado_dia` empeoró el R2 en backtest (-0.11 vs -0.02),
        probablemente por su fuerte correlación con la misma tendencia de crecimiento
        del negocio que el propio target, lo que confunde al `RandomizedSearchCV` con
        pocas iteraciones. Ver ml/REPORTE_MEJORA_MODELOS.md para el detalle del experimento."""
        sql = """
            SELECT
                df.fecha_completa as ds,
                SUM(fvd.subtotal_neto) as y_sales_net,
                SUM(fvd.cantidad) as y_quantity,
                COUNT(DISTINCT fvd.cliente_sk) as n_clientes,
                COUNT(DISTINCT fvd.num_factura) as n_facturas,
                AVG(CASE WHEN fvd.subtotal_bruto > 0
                         THEN fvd.valor_descuento / fvd.subtotal_bruto ELSE 0 END) as pct_descuento_prom
            FROM edw.fact_ventas_detalle fvd
            JOIN edw.dim_fecha df ON fvd.fecha_sk = df.fecha_sk
            JOIN edw.dim_estado_documento ed ON fvd.estado_documento_sk = ed.estado_documento_sk
            WHERE ed.estado_documento_sk <> -1
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
                JOIN edw.dim_estado_documento ed ON fvd.estado_documento_sk = ed.estado_documento_sk
                WHERE ed.estado_documento_sk <> -1
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
        """RFM por cliente. Excluye `cliente_sk = -1` (centinela 'desconocido'): sin este
        filtro entra al cálculo como un pseudo-cliente de valor monetario enorme y
        distorsiona tanto los centroides de K-Means como el dataset de churn (H-16,
        docs/auditoria/11_auditoria_tecnica_modelos_ml.md)."""
        sql = """
            SELECT
                cliente_sk,
                MAX(df.fecha_completa) as last_purchase_date,
                COUNT(DISTINCT fvd.fecha_sk) as frequency,
                SUM(fvd.subtotal_neto) as monetary_value
            FROM edw.fact_ventas_detalle fvd
            JOIN edw.dim_fecha df ON fvd.fecha_sk = df.fecha_sk
            JOIN edw.dim_estado_documento ed ON fvd.estado_documento_sk = ed.estado_documento_sk
            WHERE ed.estado_documento_sk <> -1 AND fvd.cliente_sk <> -1
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
            df['is_churn'] = (df['recency'] > CHURN_UMBRAL_DIAS).astype(int)
        return df

    def fetch_market_basket(self) -> pd.DataFrame:
        """Líneas de venta más recientes para reglas de asociación. La transacción real
        es la factura (num_factura), no la combinación fecha/cliente/sucursal que
        colapsaba varias compras de un mismo cliente-día en una sola canasta. Se
        excluyen devoluciones porque no son 'compras conjuntas'; con el DDL nuevo,
        `es_devolucion` migró de `fact_ventas_detalle` a la junk dimension
        `dim_estado_documento` (cambio C-1, docs/auditoria/12_fase0_analisis_capa_contratos_ml.md)."""
        sql = f"""
            SELECT
                fvd.num_factura as transaction_id,
                p.nombre_articulo as product_name
            FROM edw.fact_ventas_detalle fvd
            JOIN edw.dim_producto p ON fvd.producto_sk = p.producto_sk
            JOIN edw.dim_estado_documento ed ON fvd.estado_documento_sk = ed.estado_documento_sk
            WHERE ed.estado_documento_sk <> -1 AND NOT ed.es_devolucion
            ORDER BY fvd.venta_sk DESC
            LIMIT {MUESTRA_MARKET_BASKET};
        """
        return pd.read_sql(sql, self.engine)

    def fetch_transactions_for_anomalies(self) -> pd.DataFrame:
        """Transacciones recientes para IsolationForest. El viejo centinela de calidad
        pct_margen = -9999.9999 (docs/auditoria/05_auditoria_ml_calidad_datos.md, DQ-1)
        ya no existe como tal: con el DDL nuevo, `pct_margen` es 0.0 por convención
        (subtotal_neto=0 o margen_bruto NULL) y solo se *clipea* a ese límite numérico
        como techo/piso de la columna NUMERIC(8,4), no como marca de calidad
        (docs/auditoria/13_impacto_dim_estado_documento.md, H13-04). Filtrar
        `pct_margen > -9999` hoy excluiría por error transacciones con margen
        genuinamente extremo que clipean justo en ese límite, así que se elimina."""
        sql = f"""
            SELECT
                subtotal_neto,
                cantidad,
                costo_total,
                (subtotal_neto - costo_total) as margen
            FROM edw.fact_ventas_detalle
            ORDER BY venta_sk DESC
            LIMIT {MUESTRA_ANOMALIAS};
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
                    SUM(f.subtotal_neto) as ventas_historicas,
                    SUM(f.cantidad) as unidades_historicas
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                WHERE ed.estado_documento_sk <> -1
                GROUP BY f.vendedor_sk, f.sucursal_sk, d.anio, d.mes
            ),
            
            -- Calculamos el promedio del mismo mes en años anteriores (Estacionalidad interanual)
            SeasonalityCalc AS (
                SELECT 
                    curr.vendedor_sk,
                    curr.sucursal_sk,
                    curr.anio,
                    curr.mes,
                    AVG(prev.ventas_historicas) as avg_estacional
                FROM MonthlySales curr
                LEFT JOIN MonthlySales prev 
                    ON curr.vendedor_sk = prev.vendedor_sk 
                   AND curr.sucursal_sk = prev.sucursal_sk 
                   AND prev.mes = curr.mes 
                   AND prev.anio < curr.anio
                GROUP BY curr.vendedor_sk, curr.sucursal_sk, curr.anio, curr.mes
            ),
            
            -- Calculamos la tendencia del año actual sin el mes pico máximo
            TrendCalc AS (
                SELECT 
                    curr.vendedor_sk,
                    curr.sucursal_sk,
                    curr.anio,
                    curr.mes,
                    AVG(prev.ventas_historicas) FILTER (
                        WHERE prev.ventas_historicas < (
                            SELECT MAX(p2.ventas_historicas) 
                            FROM MonthlySales p2 
                            WHERE p2.vendedor_sk = curr.vendedor_sk 
                              AND p2.sucursal_sk = curr.sucursal_sk 
                              AND p2.anio = curr.anio 
                              AND p2.mes < curr.mes
                        ) OR (
                            SELECT COUNT(*) 
                            FROM MonthlySales p2 
                            WHERE p2.vendedor_sk = curr.vendedor_sk 
                              AND p2.sucursal_sk = curr.sucursal_sk 
                              AND p2.anio = curr.anio 
                              AND p2.mes < curr.mes
                        ) <= 2
                    ) AS avg_tendencia_sin_max
                FROM MonthlySales curr
                LEFT JOIN MonthlySales prev 
                    ON curr.vendedor_sk = prev.vendedor_sk 
                   AND curr.sucursal_sk = prev.sucursal_sk 
                   AND curr.anio = prev.anio 
                   AND prev.mes < curr.mes
                GROUP BY curr.vendedor_sk, curr.sucursal_sk, curr.anio, curr.mes
            ),
            
            -- Enriquecimiento de características con estacionales y tendencias sin max
            FeatureEnriched AS (
                SELECT
                    a.vendedor_sk,
                    a.sucursal_sk,
                    a.anio,
                    a.mes,
                    a.ventas_historicas,
                    a.unidades_historicas,
                    
                    -- Ventas hace exactamente 1 año
                    LAG(a.ventas_historicas, 12) OVER (
                        PARTITION BY a.vendedor_sk, a.sucursal_sk 
                        ORDER BY a.anio, a.mes
                    ) as ventas_anio_anterior,
                    
                    -- Combinación estacionalidad + tendencia sin pico
                    COALESCE(
                        (s.avg_estacional + t.avg_tendencia_sin_max) / 2.0,
                        s.avg_estacional,
                        t.avg_tendencia_sin_max,
                        a.ventas_historicas,
                        0.0
                    ) AS promedio_movil_3m
                FROM MonthlySales a
                LEFT JOIN SeasonalityCalc s 
                    ON a.vendedor_sk = s.vendedor_sk 
                   AND a.sucursal_sk = s.sucursal_sk 
                   AND a.anio = s.anio 
                   AND a.mes = s.mes
                LEFT JOIN TrendCalc t 
                    ON a.vendedor_sk = t.vendedor_sk 
                   AND a.sucursal_sk = t.sucursal_sk 
                   AND a.anio = t.anio 
                   AND a.mes = t.mes
            )
            SELECT
                a.vendedor_sk,
                a.sucursal_sk,
                a.anio,
                a.mes,
                a.ventas_historicas,
                a.unidades_historicas,
                COALESCE(a.ventas_anio_anterior, 0.0) as ventas_anio_anterior,
                COALESCE(a.promedio_movil_3m, a.ventas_historicas) as promedio_movil_3m,
                -- Estacionalidad histórica del MES OBJETIVO (mes de "b", no de "a"): el driver
                -- real del ratio de crecimiento es cuán fuerte es estacionalmente el mes que
                -- viene comparado con el actual. No es fuga de datos: solo usa años anteriores
                -- a b.anio (misma regla que SeasonalityCalc), información disponible de antemano.
                COALESCE(s_obj.avg_estacional, a.ventas_historicas, 0.0) as estacionalidad_mes_objetivo,
                -- Índice estacional relativo: >1 implica que el mes objetivo suele vender más
                -- que el mes actual (proxy directo y estable del ratio de crecimiento esperado).
                COALESCE(
                    s_obj.avg_estacional / NULLIF(COALESCE(a.promedio_movil_3m, a.ventas_historicas), 0.0),
                    1.0
                ) as indice_estacional_relativo,
                -- Meta predictiva Limitada (Target ratio)
                CASE
                    WHEN a.ventas_historicas = 0 AND b.ventas_historicas = 0 THEN 1.0
                    WHEN a.ventas_historicas = 0 AND b.ventas_historicas > 0 THEN 1.5
                    ELSE LEAST(COALESCE((b.ventas_historicas / NULLIF(a.ventas_historicas, 0.0)), 1.0), 1.5)
                END as y_ventas_futuras
            FROM FeatureEnriched a
            JOIN MonthlySales b
                ON a.vendedor_sk = b.vendedor_sk
                AND a.sucursal_sk = b.sucursal_sk
                AND (
                    (a.anio = b.anio AND a.mes + 1 = b.mes)
                    OR (a.anio + 1 = b.anio AND a.mes = 12 AND b.mes = 1)
                )
            LEFT JOIN SeasonalityCalc s_obj
                ON s_obj.vendedor_sk = b.vendedor_sk
               AND s_obj.sucursal_sk = b.sucursal_sk
               AND s_obj.anio = b.anio
               AND s_obj.mes = b.mes
        """
        return pd.read_sql(sql, self.engine)
