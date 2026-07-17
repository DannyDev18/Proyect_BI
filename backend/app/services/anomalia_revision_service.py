# backend/app/services/anomalia_revision_service.py
"""Triage de anomalías (Fase 2 Admin, docs/features/plan_correcciones_pendientes.md
§3). Capa fina sobre AnomaliaRevisionRepository -- traduce ORM -> schemas y valida."""
from __future__ import annotations

from app.core.exceptions import NotFoundError
from app.repositories.anomalia_revision_repository import AnomaliaRevisionRepository
from app.schemas.analytics import AnomaliaRevisionResponse
from app.schemas.pagination import Page, PaginationParams


class AnomaliaRevisionService:
    def __init__(self, repo: AnomaliaRevisionRepository):
        self.repo = repo

    def registrar_deteccion(self, transaccion_id: str, score: float) -> None:
        """Crea el ítem de triage si no existe (idempotente por transaccion_id). No
        devuelve nada -- el resultado de la detección ya lo responde AnomaliaResponse
        en la ruta /anomalies; esto solo alimenta la cola de trabajo."""
        self.repo.get_or_create(transaccion_id, score)

    def listar(self, params: PaginationParams, estado: str | None = None) -> Page[AnomaliaRevisionResponse]:
        pagina = self.repo.get_page(params, estado=estado)
        return Page(
            items=[AnomaliaRevisionResponse.model_validate(r) for r in pagina.items],
            total=pagina.total, page=pagina.page, page_size=pagina.page_size, total_pages=pagina.total_pages,
        )

    def actualizar(
        self, revision_id: int, estado: str, revisor_id: int, nota: str | None,
    ) -> AnomaliaRevisionResponse:
        revision = self.repo.actualizar_estado(revision_id, estado, revisor_id, nota)
        if revision is None:
            raise NotFoundError(f"No existe la revisión de anomalía id={revision_id}.")
        return AnomaliaRevisionResponse.model_validate(revision)
