# backend/app/repositories/anomalia_revision_repository.py
"""Triage de anomalías (Fase 2 Admin, docs/features/plan_correcciones_pendientes.md
§3). Acceso a `public.anomalias_revisiones`."""
from __future__ import annotations

import datetime

from sqlalchemy.orm import Session

from app.models.anomalia_revision import AnomaliaRevision
from app.schemas.pagination import Page, PaginationParams


class AnomaliaRevisionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create(self, transaccion_id: str, score: float) -> AnomaliaRevision:
        """Idempotente por `transaccion_id` (UNIQUE): si el admin vuelve a consultar la
        misma transacción, no duplica el ítem de triage ni pisa el estado ya trabajado."""
        existente = (
            self.db.query(AnomaliaRevision)
            .filter(AnomaliaRevision.transaccion_id == transaccion_id)
            .first()
        )
        if existente:
            return existente

        nueva = AnomaliaRevision(transaccion_id=transaccion_id, score=score, estado="nueva")
        self.db.add(nueva)
        self.db.commit()
        self.db.refresh(nueva)
        return nueva

    def get_page(self, params: PaginationParams, estado: str | None = None) -> Page[AnomaliaRevision]:
        query = self.db.query(AnomaliaRevision)
        if estado is not None:
            query = query.filter(AnomaliaRevision.estado == estado)
        query = query.order_by(AnomaliaRevision.fecha_deteccion.desc())

        total = query.count()
        items = query.offset((params.page - 1) * params.page_size).limit(params.page_size).all()
        total_pages = -(-total // params.page_size) if total else 0
        return Page(items=items, total=total, page=params.page, page_size=params.page_size, total_pages=total_pages)

    def actualizar_estado(
        self, revision_id: int, estado: str, revisor_id: int, nota: str | None,
    ) -> AnomaliaRevision | None:
        revision = self.db.query(AnomaliaRevision).filter(AnomaliaRevision.id == revision_id).first()
        if revision is None:
            return None

        revision.estado = estado
        revision.revisor_id = revisor_id
        revision.nota = nota
        revision.fecha_revision = datetime.datetime.now(datetime.timezone.utc)
        self.db.commit()
        self.db.refresh(revision)
        return revision
