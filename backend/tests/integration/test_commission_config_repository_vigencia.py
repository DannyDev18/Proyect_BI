# backend/tests/integration/test_commission_config_repository_vigencia.py
"""C-3 (docs/features/plan_correcciones_pendientes.md; auditoría 35 H4): un cambio de
tipo externo/interno de un vendedor no debe reescribir retroactivamente lo que un
período ya calculado usó. Verifica el mismo patrón de vigencias que
ComisionMatrizCategoria/ComisionFactorCredito, ahora aplicado a ComisionConfigVendedor."""
import datetime

import pytest

from app.database.session import SessionLocal
from app.models.commission_config import ComisionConfigVendedor
from app.repositories.commission_config_repository import CommissionConfigRepository

pytestmark = pytest.mark.integration

VENDEDOR_TEST = "TEST-C3-VIG"


@pytest.fixture
def db():
    session = SessionLocal()
    session.query(ComisionConfigVendedor).filter(
        ComisionConfigVendedor.id_vendedor_origen == VENDEDOR_TEST
    ).delete()
    session.commit()
    yield session
    session.rollback()
    session.query(ComisionConfigVendedor).filter(
        ComisionConfigVendedor.id_vendedor_origen == VENDEDOR_TEST
    ).delete()
    session.commit()
    session.close()


def test_upsert_cierra_la_vigencia_anterior_en_vez_de_sobrescribirla(db):
    repo = CommissionConfigRepository(db)

    primera = repo.upsert_config_vendedor(VENDEDOR_TEST, tipo="externo", factor_tipo=1.0, fecha_ingreso=None)
    assert primera.vigente_hasta is None

    segunda = repo.upsert_config_vendedor(VENDEDOR_TEST, tipo="interno", factor_tipo=0.8, fecha_ingreso=None)

    db.refresh(primera)
    assert primera.vigente_hasta is not None, "la fila anterior debe cerrarse, no editarse"
    assert primera.tipo == "externo", "la fila cerrada conserva el tipo con el que se calculó en su momento"
    assert segunda.vigente_hasta is None
    assert segunda.tipo == "interno"


def test_get_config_vendedor_con_fecha_historica_ignora_cambios_posteriores(db):
    """Simula el escenario real que motivó C-3: una config abierta hace 60 días
    (vigente antes de que existiera cualquier cambio reciente) y una liquidación de
    hace 30 días que debe seguir viendo esa config original, aunque hoy se cambie."""
    repo = CommissionConfigRepository(db)
    hoy = datetime.date.today()
    hace_60_dias = hoy - datetime.timedelta(days=60)
    fecha_periodo_pasado = hoy - datetime.timedelta(days=30)

    db.add(ComisionConfigVendedor(
        id_vendedor_origen=VENDEDOR_TEST, tipo="externo", factor_tipo=1.0,
        vigente_desde=hace_60_dias, vigente_hasta=None,
    ))
    db.commit()

    config_periodo_pasado_antes = repo.get_config_vendedor(VENDEDOR_TEST, fecha_periodo_pasado)
    assert config_periodo_pasado_antes is not None
    assert config_periodo_pasado_antes.tipo == "externo"

    repo.upsert_config_vendedor(VENDEDOR_TEST, tipo="interno", factor_tipo=0.8, fecha_ingreso=None)

    # RN-CM5/RN-CM6: el período de hace 30 días sigue viendo "externo" (la config
    # vigente en ese momento), sin importar que hoy se haya cambiado a "interno".
    config_periodo_pasado_tras_cambio = repo.get_config_vendedor(VENDEDOR_TEST, fecha_periodo_pasado)
    assert config_periodo_pasado_tras_cambio.tipo == "externo"

    config_hoy = repo.get_config_vendedor(VENDEDOR_TEST, hoy)
    assert config_hoy.tipo == "interno"


def test_get_all_config_vendedores_solo_lista_vigencias_abiertas(db):
    repo = CommissionConfigRepository(db)
    repo.upsert_config_vendedor(VENDEDOR_TEST, tipo="externo", factor_tipo=1.0, fecha_ingreso=None)
    repo.upsert_config_vendedor(VENDEDOR_TEST, tipo="interno", factor_tipo=0.8, fecha_ingreso=None)

    listado = [c for c in repo.get_all_config_vendedores() if c.id_vendedor_origen == VENDEDOR_TEST]
    assert len(listado) == 1
    assert listado[0].tipo == "interno"
