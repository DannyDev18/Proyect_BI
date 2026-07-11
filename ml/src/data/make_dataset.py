import os
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime

# Regla de negocio: un cliente se considera en abandono (churn) si no vuelve a comprar
# dentro del horizonte de 90 días siguientes a la fecha de corte. Umbral acordado como
# proxy (no existe campo de baja explícito en el origen); ajustable por env var sin tocar
# código.
CHURN_UMBRAL_DIAS = int(os.getenv("ML_CHURN_UMBRAL_DIAS", "90"))

# H-05 (docs/auditoria/11_auditoria_tecnica_modelos_ml.md): el dataset legacy calculaba
# recency/frequency y la etiqueta is_churn sobre el MISMO snapshot completo -- circular,
# el modelo aprendía a reproducir una regla determinista, no a anticipar abandono. El
# dataset nuevo usa varias fechas de corte T (espaciadas CHURN_ESPACIADO_DIAS entre sí):
# las features se calculan SOLO con transacciones <= T y la etiqueta observa si el cliente
# vuelve a comprar en (T, T+CHURN_UMBRAL_DIAS] -- información que en producción no existe
# todavía en el momento de predecir. Varios cortes (no solo el más reciente) dan más
# ejemplos de entrenamiento y cubren distintos regímenes de negocio.
CHURN_N_CORTES = int(os.getenv("ML_CHURN_N_CORTES", "6"))
CHURN_ESPACIADO_DIAS = int(os.getenv("ML_CHURN_ESPACIADO_DIAS", "90"))

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
        """`dimension='producto'`: se agrupa por `codart` (llave de negocio), NO por
        `nombre_articulo`. `dim_producto` es SCD2 (CLAUDE.md regla 7): si un artículo
        cambia de nombre, agrupar por nombre parte su serie histórica en dos (H-21,
        docs/auditoria/11_auditoria_tecnica_modelos_ml.md). Excluye el centinela
        `producto_sk = -1` ('producto desconocido', 58.121 filas / 11.2% del hecho):
        sin este filtro entra como un pseudo-producto que mezcla demanda de artículos no
        resueltos (regla de negocio 12, CLAUDE.md)."""
        if dimension == 'producto':
            sql = """
                SELECT
                    df.fecha_completa as ds,
                    p.codart as producto,
                    SUM(fvd.cantidad) as y_quantity
                FROM edw.fact_ventas_detalle fvd
                JOIN edw.dim_fecha df ON fvd.fecha_sk = df.fecha_sk
                JOIN edw.dim_producto p ON fvd.producto_sk = p.producto_sk
                JOIN edw.dim_estado_documento ed ON fvd.estado_documento_sk = ed.estado_documento_sk
                WHERE ed.estado_documento_sk <> -1 AND fvd.producto_sk <> -1
                GROUP BY df.fecha_completa, p.codart
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

    def fetch_customer_transactions(self) -> pd.DataFrame:
        """Todas las transacciones válidas por cliente (fecha + monto): insumo crudo para
        construir los snapshots temporales de `fetch_churn_data` (H-05). Se excluye el
        centinela `cliente_sk = -1` por el mismo motivo que en `fetch_rfm_metrics` (H-16)."""
        sql = """
            SELECT fvd.cliente_sk, df.fecha_completa, fvd.subtotal_neto
            FROM edw.fact_ventas_detalle fvd
            JOIN edw.dim_fecha df ON fvd.fecha_sk = df.fecha_sk
            JOIN edw.dim_estado_documento ed ON fvd.estado_documento_sk = ed.estado_documento_sk
            WHERE ed.estado_documento_sk <> -1 AND fvd.cliente_sk <> -1;
        """
        df = pd.read_sql(sql, self.engine)
        if not df.empty:
            df['fecha_completa'] = pd.to_datetime(df['fecha_completa'])
        return df

    def fetch_churn_data(
        self,
        horizonte_dias: int = CHURN_UMBRAL_DIAS,
        n_cortes: int = CHURN_N_CORTES,
        espaciado_dias: int = CHURN_ESPACIADO_DIAS,
    ) -> pd.DataFrame:
        """Dataset de churn con corte temporal (H-05, ver constantes arriba). Para cada
        fecha de corte T: features (recency/frequency/monetary_value/average_ticket)
        calculadas solo con transacciones <= T; etiqueta is_churn = 1 si el cliente NO
        vuelve a comprar en (T, T+horizonte_dias]. Reemplaza el dataset legacy (circular:
        recency y la etiqueta se derivaban del mismo snapshot completo)."""
        tx = self.fetch_customer_transactions()
        if tx.empty:
            return pd.DataFrame()

        max_date = tx['fecha_completa'].max()
        min_date = tx['fecha_completa'].min()
        horizonte = pd.Timedelta(days=horizonte_dias)

        cortes = []
        corte = max_date - horizonte
        while corte - horizonte >= min_date and len(cortes) < n_cortes:
            cortes.append(corte)
            corte = corte - pd.Timedelta(days=espaciado_dias)

        frames = []
        for corte in cortes:
            hist = tx[tx['fecha_completa'] <= corte]
            if hist.empty:
                continue
            agg = hist.groupby('cliente_sk').agg(
                last_purchase=('fecha_completa', 'max'),
                frequency=('fecha_completa', 'nunique'),
                monetary_value=('subtotal_neto', 'sum'),
            )
            agg['recency'] = (corte - agg['last_purchase']).dt.days
            agg['average_ticket'] = agg['monetary_value'] / agg['frequency']

            futuro = tx[(tx['fecha_completa'] > corte) & (tx['fecha_completa'] <= corte + horizonte)]
            clientes_que_vuelven = set(futuro['cliente_sk'].unique())
            agg['is_churn'] = (~agg.index.isin(clientes_que_vuelven)).astype(int)
            agg['fecha_corte'] = corte
            frames.append(agg.reset_index())

        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)[
            ['cliente_sk', 'fecha_corte', 'recency', 'frequency', 'monetary_value', 'average_ticket', 'is_churn']
        ]

    def fetch_market_basket(self) -> pd.DataFrame:
        """Líneas de venta más recientes para reglas de asociación. La transacción real
        es la factura (num_factura), no la combinación fecha/cliente/sucursal que
        colapsaba varias compras de un mismo cliente-día en una sola canasta. Se
        excluyen devoluciones porque no son 'compras conjuntas'; con el DDL nuevo,
        `es_devolucion` migró de `fact_ventas_detalle` a la junk dimension
        `dim_estado_documento` (cambio C-1, docs/auditoria/12_fase0_analisis_capa_contratos_ml.md).
        Se usa `codart` (llave de negocio) en vez de `nombre_articulo` (H-10): el backend
        identifica productos por código, no por nombre a texto libre. Excluye el centinela
        `producto_sk = -1` ('producto desconocido'): no es un artículo real y no debe
        entrar a las reglas de asociación (regla de negocio 12, CLAUDE.md)."""
        sql = f"""
            SELECT
                fvd.num_factura as transaction_id,
                p.codart as product_code
            FROM edw.fact_ventas_detalle fvd
            JOIN edw.dim_producto p ON fvd.producto_sk = p.producto_sk
            JOIN edw.dim_estado_documento ed ON fvd.estado_documento_sk = ed.estado_documento_sk
            WHERE ed.estado_documento_sk <> -1 AND NOT ed.es_devolucion AND fvd.producto_sk <> -1
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

