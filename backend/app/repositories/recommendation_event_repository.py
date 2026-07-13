# backend/app/repositories/recommendation_event_repository.py
"""Telemetría del módulo de Venta Cruzada (docs/auditoria/25_modulo_cross_selling.md,
regla RN-CS2): registra sugerencias mostradas/aceptadas/rechazadas y calcula la tasa
de conversión. Vive en public.* (no en edw.*), mismo patrón que goal_repository."""
import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.recommendation_event import RecommendationEvent


class RecommendationEventRepository:
    def __init__(self, db: Session):
        self.db = db

    def log_event(
        self,
        usuario_id: int,
        producto_origen_cod: str,
        producto_sugerido_cod: str,
        evento: str,
        score_lift: float | None = None,
        motivo: str | None = None,
        cliente_sk: int | None = None,
    ) -> RecommendationEvent:
        event = RecommendationEvent(
            usuario_id=usuario_id,
            cliente_sk=cliente_sk,
            producto_origen_cod=producto_origen_cod,
            producto_sugerido_cod=producto_sugerido_cod,
            score_lift=score_lift,
            motivo=motivo,
            evento=evento,
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def get_conversion_kpis(
        self, desde: datetime.date | None = None, hasta: datetime.date | None = None,
    ) -> dict[str, int | float]:
        query = self.db.query(
            RecommendationEvent.evento, func.count(RecommendationEvent.id),
        )
        if desde is not None:
            query = query.filter(RecommendationEvent.fecha >= desde)
        if hasta is not None:
            query = query.filter(RecommendationEvent.fecha < hasta + datetime.timedelta(days=1))
        conteos = dict(query.group_by(RecommendationEvent.evento).all())

        mostradas = int(conteos.get("mostrada", 0))
        aceptadas = int(conteos.get("aceptada", 0))
        rechazadas = int(conteos.get("rechazada", 0))
        tasa_conversion = (aceptadas / mostradas * 100) if mostradas > 0 else 0.0
        return {
            "sugerencias_mostradas": mostradas,
            "sugerencias_aceptadas": aceptadas,
            "sugerencias_rechazadas": rechazadas,
            "tasa_conversion_pct": round(tasa_conversion, 2),
        }
