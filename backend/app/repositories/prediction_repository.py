# backend/app/repositories/prediction_repository.py
"""SQL de features "de un registro vivo" para inferencia puntual: churn, anomalías,
recomendaciones y segmentación RFM de un cliente/transacción específico.

Fase 4 (docs/ml_contracts.md): las columnas y su semántica se alinean EXACTAMENTE con
el contrato de cada modelo (`ml/contracts/models/*.json`), construido durante el
entrenamiento (Fase 3) en `ml/src/data/make_dataset.py`. Antes había un mismatch de
nombres y semántica entre entrenamiento y serving (H-03 churn, H-04 anomalías, H-14
RFM) que hacía que estos endpoints nunca produjeran una predicción válida."""
from typing import NamedTuple

import pandas as pd
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session


class ChurnFeatures(NamedTuple):
    """Mismas 3 columnas y semántica que ml/contracts/models/churn.json: frequency =
    días distintos de compra, monetary_value = SUM(subtotal_neto), average_ticket =
    monetary_value/frequency -- calculadas 'a fecha de hoy' (T=now()), igual que el
    entrenamiento las calculaba 'a fecha de corte T' (H-03, cerrado)."""
    frequency: float
    monetary_value: float
    average_ticket: float


class AnomalyFeatures(NamedTuple):
    """Mismas 4 columnas que ml/contracts/models/anomalies.json (H-04, cerrado)."""
    subtotal_neto: float
    cantidad: float
    costo_total: float
    margen: float


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
                COUNT(DISTINCT f.fecha_completa) AS frequency,
                COALESCE(SUM(v.subtotal_neto), 0) AS monetary_value
            FROM edw.fact_ventas_detalle v
            JOIN edw.dim_fecha f ON v.fecha_sk = f.fecha_sk
            JOIN edw.dim_cliente c ON v.cliente_sk = c.cliente_sk
            JOIN public.cliente_lookup l ON c.hash_anonimo = l.hash_anonimo
            JOIN edw.dim_estado_documento ed ON v.estado_documento_sk = ed.estado_documento_sk
            WHERE l.id_cliente_transaccional = :cliente_id
              AND ed.estado_documento_sk <> -1
            GROUP BY l.id_cliente_transaccional
        """
        res = self.db.execute(text(query), {"cliente_id": cliente_id}).fetchone()
        if not res:
            return None
        frequency = float(res[0]) if res[0] else 0.0
        monetary_value = float(res[1]) if res[1] is not None else 0.0
        average_ticket = monetary_value / frequency if frequency > 0 else 0.0
        return ChurnFeatures(frequency=frequency, monetary_value=monetary_value, average_ticket=average_ticket)

    def get_churn_features_batch(self, cliente_ids: list[str]) -> pd.DataFrame:
        """Misma feature de `get_churn_features`, pero para un lote de clientes en UNA
        sola consulta (mismo contrato de columnas que `ChurnFeatures`) -- usada por el
        módulo Cartera 360 (docs/features/propuesta_nuevos_modulos_roi.md §4) para
        rerankear un conjunto acotado de candidatos con el churn real del modelo, sin
        recorrer la cartera completa con una consulta por cliente (auditoría 32 H1)."""
        if not cliente_ids:
            return pd.DataFrame(columns=["cliente_id", "frequency", "monetary_value", "average_ticket"])
        query = text("""
            SELECT
                l.id_cliente_transaccional AS cliente_id,
                COUNT(DISTINCT f.fecha_completa) AS frequency,
                COALESCE(SUM(v.subtotal_neto), 0) AS monetary_value
            FROM edw.fact_ventas_detalle v
            JOIN edw.dim_fecha f ON v.fecha_sk = f.fecha_sk
            JOIN edw.dim_cliente c ON v.cliente_sk = c.cliente_sk
            JOIN public.cliente_lookup l ON c.hash_anonimo = l.hash_anonimo
            JOIN edw.dim_estado_documento ed ON v.estado_documento_sk = ed.estado_documento_sk
            WHERE l.id_cliente_transaccional IN :cliente_ids
              AND ed.estado_documento_sk <> -1
            GROUP BY l.id_cliente_transaccional
        """).bindparams(bindparam("cliente_ids", expanding=True))
        df = pd.read_sql(query, self.db.connection(), params={"cliente_ids": cliente_ids})
        df["frequency"] = df["frequency"].astype(float)
        df["monetary_value"] = df["monetary_value"].astype(float)
        df["average_ticket"] = df.apply(
            lambda r: r["monetary_value"] / r["frequency"] if r["frequency"] > 0 else 0.0, axis=1,
        )
        return df

    def get_transaction_features(self, transaccion_id: str) -> AnomalyFeatures | None:
        query = """
            SELECT fvd.subtotal_neto, fvd.cantidad, fvd.costo_total,
                   (fvd.subtotal_neto - fvd.costo_total) AS margen
            FROM edw.fact_ventas_detalle fvd
            WHERE fvd.num_factura = :tx_id
            LIMIT 1;
        """
        res = self.db.execute(text(query), {"tx_id": transaccion_id}).fetchone()
        if not res or res[2] is None:
            # costo_total NULL: misma política de nulos del entrenamiento (H-19, cerrado
            # en Fase 3) -- se excluye en vez de imputar con 0 (reintroduciría el margen
            # 100% artificial que el EDW nuevo eliminó como centinela).
            return None
        return AnomalyFeatures(
            subtotal_neto=float(res[0]),
            cantidad=float(res[1]),
            costo_total=float(res[2]),
            margen=float(res[3]),
        )

    def get_client_purchase_history(self, cliente_id: str, limit: int = 10) -> ClientPurchaseHistory:
        query = """
            SELECT p.codart, l.nombre_cliente
            FROM edw.fact_ventas_detalle v
            JOIN edw.dim_producto p ON v.producto_sk = p.producto_sk
            JOIN edw.dim_cliente c ON v.cliente_sk = c.cliente_sk
            JOIN public.cliente_lookup l ON c.hash_anonimo = l.hash_anonimo
            JOIN edw.dim_estado_documento ed ON v.estado_documento_sk = ed.estado_documento_sk
            WHERE l.id_cliente_transaccional = :cliente_id
              AND ed.estado_documento_sk <> -1
            ORDER BY v.fecha_sk DESC
            LIMIT :limit;
        """
        res = self.db.execute(text(query), {"cliente_id": cliente_id, "limit": limit}).fetchall()
        return ClientPurchaseHistory(
            ultimos_items=[row[0] for row in res],
            nombre_cliente=str(res[0][1]) if res else "Desconocido",
        )

    def get_rfm_features(self, cliente_id: str) -> RfmFeatures | None:
        """frequency = días distintos de compra (COUNT DISTINCT fecha_completa), igual
        semántica que ml/src/data/make_dataset.py::fetch_rfm_metrics (antes contaba
        facturas, no días -- H-14 parcialmente cerrado). recency queda relativa a
        `now()` porque este endpoint sirve el estado ACTUAL del cliente, a diferencia
        del entrenamiento que usa el máximo del dataset histórico -- esa diferencia es
        esperable en un sistema en vivo, no un bug."""
        query = """
            WITH compras_por_dia AS (
                SELECT
                    v.cliente_sk,
                    f.fecha_completa,
                    SUM(v.subtotal_neto) AS total_dia
                FROM edw.fact_ventas_detalle v
                JOIN edw.dim_fecha f ON v.fecha_sk = f.fecha_sk
                JOIN edw.dim_estado_documento ed ON v.estado_documento_sk = ed.estado_documento_sk
                WHERE ed.estado_documento_sk <> -1
                GROUP BY v.cliente_sk, f.fecha_completa
            )
            SELECT
                COALESCE(EXTRACT(DAY FROM (now() - MAX(cd.fecha_completa))), 365) AS recency,
                COUNT(DISTINCT cd.fecha_completa) AS frequency,
                COALESCE(SUM(cd.total_dia), 0) AS monetary_value
            FROM compras_por_dia cd
            JOIN edw.dim_cliente c ON cd.cliente_sk = c.cliente_sk
            JOIN public.cliente_lookup l ON c.hash_anonimo = l.hash_anonimo
            WHERE l.id_cliente_transaccional = :cliente_id
            GROUP BY l.id_cliente_transaccional;
        """
        res = self.db.execute(text(query), {"cliente_id": cliente_id}).fetchone()
        if not res:
            return None
        return RfmFeatures(recency=float(res[0]), frequency=float(res[1]), monetary_value=float(res[2]))
