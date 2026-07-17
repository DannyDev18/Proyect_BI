# backend/tests/integration/test_anomalia_revision_repository.py
"""Fase 2 Admin (docs/features/plan_correcciones_pendientes.md §3): flujo completo de
triage de anomalías contra Postgres real, sin depender de que una transacción real del
EDW resulte calificada como anómala por el modelo."""
import pytest

from app.database.session import SessionLocal
from app.models.anomalia_revision import AnomaliaRevision
from app.repositories.anomalia_revision_repository import AnomaliaRevisionRepository
from app.schemas.pagination import PaginationParams

pytestmark = pytest.mark.integration

TXN_TEST = "TXN-TEST-TRIAGE-001"


@pytest.fixture
def db():
    session = SessionLocal()
    session.query(AnomaliaRevision).filter(AnomaliaRevision.transaccion_id == TXN_TEST).delete()
    session.commit()
    yield session
    session.rollback()
    session.query(AnomaliaRevision).filter(AnomaliaRevision.transaccion_id == TXN_TEST).delete()
    session.commit()
    session.close()


def test_get_or_create_es_idempotente_por_transaccion(db):
    repo = AnomaliaRevisionRepository(db)
    primera = repo.get_or_create(TXN_TEST, score=-0.62)
    assert primera.estado == "nueva"

    # Volver a "detectar" la misma transacción no debe crear una segunda fila ni
    # perder el estado si ya fue trabajada.
    primera.estado = "revisada"
    db.commit()

    segunda = repo.get_or_create(TXN_TEST, score=-0.62)
    assert segunda.id == primera.id
    assert segunda.estado == "revisada"


def test_get_page_filtra_por_estado(db):
    repo = AnomaliaRevisionRepository(db)
    repo.get_or_create(TXN_TEST, score=-0.5)

    pagina_nuevas = repo.get_page(PaginationParams(page=1, page_size=25), estado="nueva")
    assert any(r.transaccion_id == TXN_TEST for r in pagina_nuevas.items)

    pagina_confirmadas = repo.get_page(PaginationParams(page=1, page_size=25), estado="confirmada")
    assert not any(r.transaccion_id == TXN_TEST for r in pagina_confirmadas.items)


def test_actualizar_estado_registra_revisor_y_fecha(db):
    repo = AnomaliaRevisionRepository(db)
    creada = repo.get_or_create(TXN_TEST, score=-0.5)

    actualizada = repo.actualizar_estado(creada.id, estado="confirmada", revisor_id=1, nota="fraude confirmado")
    assert actualizada is not None
    assert actualizada.estado == "confirmada"
    assert actualizada.revisor_id == 1
    assert actualizada.fecha_revision is not None


def test_actualizar_estado_de_id_inexistente_devuelve_none(db):
    repo = AnomaliaRevisionRepository(db)
    assert repo.actualizar_estado(999999999, estado="revisada", revisor_id=1, nota=None) is None
