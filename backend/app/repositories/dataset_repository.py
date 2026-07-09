# backend/app/repositories/dataset_repository.py
"""SQL de series históricas usadas como insumo de feature engineering para forecasting
(ventas/demanda). Se separa de `prediction_repository.py` porque son consultas de rango
histórico completo, no de "un registro vivo" (churn/anomalía/recomendación/segmento)."""
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session


class DatasetRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_daily_sales_history(self, sucursal: str | None = None, limit_days: int = 730) -> pd.DataFrame:
        """Serie diaria de ventas netas, enriquecida con las mismas exógenas que usa el
        pipeline de entrenamiento (`ml/src/data/make_dataset.py::fetch_daily_sales`):
        clientes/facturas/descuento del día. Deben coincidir en forma -- el modelo
        `sales_best_model.pkl` fue entrenado con esas columnas via
        `model.feature_names_in_` (ver app/ml/inference.py::predict_sales)."""
        filtro = "AND c.nombre_sucursal = :suc" if sucursal else ""
        query = f"""
            SELECT
                f.fecha_completa as ds,
                SUM(v.subtotal_neto) as y_sales_net,
                SUM(v.cantidad) as y_quantity,
                COUNT(DISTINCT v.cliente_sk) as n_clientes,
                COUNT(DISTINCT v.num_factura) as n_facturas,
                AVG(CASE WHEN v.subtotal_bruto > 0
                         THEN v.valor_descuento / v.subtotal_bruto ELSE 0 END) as pct_descuento_prom
            FROM edw.fact_ventas_detalle v
            JOIN edw.dim_fecha f ON v.fecha_sk = f.fecha_sk
            JOIN edw.dim_sucursal c ON v.sucursal_sk = c.sucursal_sk
            JOIN edw.dim_estado_documento ed ON v.estado_documento_sk = ed.estado_documento_sk
            WHERE ed.estado_documento_sk <> -1 {filtro}
            GROUP BY f.fecha_completa
            ORDER BY f.fecha_completa DESC
            LIMIT :limit_days;
        """
        params = {"limit_days": limit_days}
        if sucursal:
            params["suc"] = sucursal
        with self.db.connection() as conn:
            return pd.read_sql(text(query), conn, params=params)

    def get_product_sales_history(self, producto_cod: str, limit_days: int = 100) -> pd.DataFrame:
        """Serie diaria de unidades vendidas de un producto -- insumo de `predict_demand`."""
        query = """
            SELECT f.fecha_completa as ds, SUM(v.cantidad) as y_quantity
            FROM edw.fact_ventas_detalle v
            JOIN edw.dim_fecha f ON v.fecha_sk = f.fecha_sk
            JOIN edw.dim_producto p ON v.producto_sk = p.producto_sk
            JOIN edw.dim_estado_documento ed ON v.estado_documento_sk = ed.estado_documento_sk
            WHERE ed.estado_documento_sk <> -1 AND p.codart = :prod
            GROUP BY f.fecha_completa
            ORDER BY f.fecha_completa DESC
            LIMIT :limit_days;
        """
        with self.db.connection() as conn:
            return pd.read_sql(text(query), conn, params={"prod": producto_cod, "limit_days": limit_days})
