# backend/app/repositories/prediction_repository.py
"""SQL de features "de un registro vivo" para inferencia puntual: churn, anomalías,
recomendaciones y segmentación RFM de un cliente/transacción específico."""
from typing import NamedTuple

from sqlalchemy import text
from sqlalchemy.orm import Session


class ChurnFeatures(NamedTuple):
    inactivity_days: float
    average_ticket: float
    total_orders: float
    discount_ratio: float


class AnomalyFeatures(NamedTuple):
    discount_pct: float
    total_amount: float
    refund_flag: float


class ClientPurchaseHistory(NamedTuple):
    ultimos_items: list[str]
    nombre_cliente: str


class RfmFeatures(NamedTuple):
    recency: float
    frequency: float
    monetary_value: float


class PredictionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_churn_features(self, cliente_id: str) -> ChurnFeatures | None:
        query = """
            SELECT
                COALESCE(EXTRACT(DAY FROM (now() - MAX(f.fecha_completa))), 365) AS inactivity_days,
                COALESCE(AVG(v.subtotal_neto), 0) AS average_ticket,
                COUNT(DISTINCT v.num_factura) AS total_orders,
                COALESCE(SUM(v.valor_descuento) / NULLIF(SUM(v.subtotal_bruto), 0), 0) AS discount_ratio
            FROM edw.fact_ventas_detalle v
            JOIN edw.dim_fecha f ON v.fecha_sk = f.fecha_sk
            JOIN edw.dim_cliente c ON v.cliente_sk = c.cliente_sk
            JOIN public.cliente_lookup l ON c.hash_anonimo = l.hash_anonimo
            WHERE l.id_cliente_transaccional = :cliente_id
              AND v.estado_factura != 'I'
        """
        res = self.db.execute(text(query), {"cliente_id": cliente_id}).fetchone()
        if not res:
            return None
        return ChurnFeatures(
            inactivity_days=float(res[0]) if res[0] is not None else 365.0,
            average_ticket=float(res[1]) if res[1] is not None else 0.0,
            total_orders=float(res[2]) if res[2] is not None else 0.0,
            discount_ratio=float(res[3]) if res[3] is not None else 0.0,
        )

    def get_transaction_features(self, transaccion_id: str) -> AnomalyFeatures | None:
        query = """
            SELECT
                COALESCE(valor_descuento / NULLIF(subtotal_bruto, 0), 0) AS discount_pct,
                total_linea AS total_amount,
                CASE WHEN es_devolucion THEN 1.0 ELSE 0.0 END AS refund_flag
            FROM edw.fact_ventas_detalle
            WHERE num_factura = :tx_id
            LIMIT 1;
        """
        res = self.db.execute(text(query), {"tx_id": transaccion_id}).fetchone()
        if not res:
            return None
        return AnomalyFeatures(
            discount_pct=float(res[0]),
            total_amount=float(res[1]),
            refund_flag=float(res[2]),
        )

    def get_client_purchase_history(self, cliente_id: str, limit: int = 10) -> ClientPurchaseHistory:
        query = """
            SELECT p.codart, l.nombre_cliente
            FROM edw.fact_ventas_detalle v
            JOIN edw.dim_producto p ON v.producto_sk = p.producto_sk
            JOIN edw.dim_cliente c ON v.cliente_sk = c.cliente_sk
            JOIN public.cliente_lookup l ON c.hash_anonimo = l.hash_anonimo
            WHERE l.id_cliente_transaccional = :cliente_id
              AND v.estado_factura != 'I'
            ORDER BY v.fecha_sk DESC
            LIMIT :limit;
        """
        res = self.db.execute(text(query), {"cliente_id": cliente_id, "limit": limit}).fetchall()
        return ClientPurchaseHistory(
            ultimos_items=[row[0] for row in res],
            nombre_cliente=str(res[0][1]) if res else "Desconocido",
        )

    def get_rfm_features(self, cliente_id: str) -> RfmFeatures | None:
        query = """
            WITH facturas AS (
                SELECT
                    v.cliente_sk,
                    v.num_factura,
                    f.fecha_completa,
                    SUM(v.subtotal_neto) AS total_factura
                FROM edw.fact_ventas_detalle v
                JOIN edw.dim_fecha f ON v.fecha_sk = f.fecha_sk
                WHERE v.estado_factura != 'I'
                GROUP BY v.cliente_sk, v.num_factura, f.fecha_completa
            )
            SELECT
                COALESCE(EXTRACT(DAY FROM (now() - MAX(fc.fecha_completa))), 365) AS recency,
                COUNT(DISTINCT fc.num_factura) AS frequency,
                COALESCE(SUM(fc.total_factura), 0) AS monetary_value
            FROM facturas fc
            JOIN edw.dim_cliente c ON fc.cliente_sk = c.cliente_sk
            JOIN public.cliente_lookup l ON c.hash_anonimo = l.hash_anonimo
            WHERE l.id_cliente_transaccional = :cliente_id
            GROUP BY l.id_cliente_transaccional;
        """
        res = self.db.execute(text(query), {"cliente_id": cliente_id}).fetchone()
        if not res:
            return None
        return RfmFeatures(recency=float(res[0]), frequency=float(res[1]), monetary_value=float(res[2]))
