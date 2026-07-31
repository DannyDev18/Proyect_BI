# backend/tests/unit/test_commission_simulation_service.py
"""Auditoría 34, H-8: la simulación retroactiva debe resolver la matriz de categorías y
los factores de crédito vigentes AL CIERRE DE CADA PERÍODO simulado, no los vigentes hoy
-- de lo contrario un cambio de configuración posterior reescribe silenciosamente lo que
"el esquema nuevo habría pagado" en meses ya simulados, contradiciendo el propio diseño
de vigencias (`vigente_desde`/`vigente_hasta`) de `comision_matriz_categorias` y
`comision_factores_credito`."""
import datetime
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import ValidationError
from app.services.commission_engine import ultimo_dia_mes as _ultimo_dia_mes
from app.services.commission_simulation_service import CommissionSimulationService


@pytest.fixture
def goal_repo():
    repo = MagicMock()
    repo.get_vendors_with_sales_in_period.return_value = ["VEN01"]
    repo.get_goal_for_period.return_value = MagicMock(monto_meta=10000.0, comision_base_pct=7.0, bono_sobrecumplimiento=0.0)
    repo.get_vendor_net_sales_period.return_value = 9000.0
    repo.get_commission_lines.return_value = []
    repo.get_vendor_devoluciones_period.return_value = 0.0
    # Bonos (docs/auditoria/35_actualizacion_modulo_metas.md, H3): la simulación ahora
    # los calcula igual que la liquidación real -- sin datos de venta cruzada/clientes
    # nuevos/cobranza por defecto en estos tests (bonos_total=0.0).
    repo.get_cross_sell_accepted_amount.return_value = 0.0
    repo.get_new_or_reactivated_clients.return_value = 0
    repo.get_vendor_credit_profile.return_value = {"dias_cobro_promedio": None}
    return repo


@pytest.fixture
def commission_config_repo():
    repo = MagicMock()
    repo.get_matriz_as_reglas.return_value = []
    repo.get_factores_credito_as_rangos.return_value = []
    repo.get_config_vendedor.return_value = None
    # Auditoría 44 (docs/features/plan_comisiones_sobre_cobros.md): sin fórmula activa
    # configurada, el motor compartido (`commission_variable_engine`) cae al fallback
    # defensivo que reproduce la estructura histórica (líneas de venta × tipo ×
    # cumplimiento − devoluciones + bonos) -- que es la que estos tests, preexistentes a
    # la fórmula editable, ejercitan. Sin este default, `MagicMock()[1]` se itera como
    # una lista vacía (comportamiento por defecto de MagicMock), dejando 'claves_activas'
    # vacío y ningún componente se calcula.
    repo.get_formula_activa.return_value = None
    return repo


@pytest.fixture
def catalog_repo():
    repo = MagicMock()
    repo.get_vendedores_info.return_value = {"VEN01": "Vendedor Uno"}
    return repo


@pytest.fixture
def service(goal_repo, commission_config_repo, catalog_repo):
    return CommissionSimulationService(goal_repo, commission_config_repo, catalog_repo)


def test_ultimo_dia_mes():
    assert _ultimo_dia_mes(2026, 2) == datetime.date(2026, 2, 28)
    assert _ultimo_dia_mes(2026, 12) == datetime.date(2026, 12, 31)
    assert _ultimo_dia_mes(2024, 2) == datetime.date(2024, 2, 29)  # bisiesto


def test_simulacion_resuelve_config_vigente_por_periodo_no_por_hoy(service, commission_config_repo):
    service.simular(meses=3, anio_desde=2026, mes_desde=3)

    fechas_matriz = [c.args[0] for c in commission_config_repo.get_matriz_as_reglas.call_args_list]
    fechas_credito = [c.args[0] for c in commission_config_repo.get_factores_credito_as_rangos.call_args_list]

    assert fechas_matriz == [datetime.date(2026, 3, 31), datetime.date(2026, 2, 28), datetime.date(2026, 1, 31)]
    assert fechas_credito == [datetime.date(2026, 3, 31), datetime.date(2026, 2, 28), datetime.date(2026, 1, 31)]


def test_simulacion_no_recalcula_config_por_vendedor_solo_por_periodo(service, commission_config_repo, goal_repo):
    """Varios vendedores en el mismo mes no deben disparar consultas de config
    repetidas -- una sola resolución de vigencia por período, no por vendedor."""
    goal_repo.get_vendors_with_sales_in_period.return_value = ["VEN01", "VEN02", "VEN03"]

    service.simular(meses=1, anio_desde=2026, mes_desde=6)

    assert commission_config_repo.get_matriz_as_reglas.call_count == 1
    assert commission_config_repo.get_factores_credito_as_rangos.call_count == 1


# ══════════════════════════════════════════════════════════════════════════════
# H3 (docs/auditoria/35_actualizacion_modulo_metas.md): la simulación debe incluir los
# bonos igual que la liquidación real -- antes siempre pasaba bonos_total=0.0 y
# subestimaba el costo del esquema variable frente a lo que realmente se paga.
# ══════════════════════════════════════════════════════════════════════════════
def test_simulacion_incluye_bono_de_cliente_nuevo_en_la_comision_variable(service, commission_config_repo, goal_repo):
    goal_repo.get_new_or_reactivated_clients.return_value = 2  # 2 clientes nuevos

    resumen = service.simular(meses=1, anio_desde=2026, mes_desde=6)

    from app.core.config import settings
    bono_esperado = 2 * settings.COMISION_BONO_CLIENTE_NUEVO
    assert resumen.detalle[0].comision_variable == pytest.approx(bono_esperado)  # sin líneas, la comisión es solo el bono


def test_simulacion_sin_bonos_coincide_con_bonos_total_cero(service, commission_config_repo, goal_repo):
    """Caso base (sin venta cruzada/clientes nuevos/cobranza sana): el resultado debe
    ser idéntico al de antes del fix (bonos_total=0.0), sin regresión."""
    resumen = service.simular(meses=1, anio_desde=2026, mes_desde=6)
    assert resumen.detalle[0].comision_variable == 0.0  # sin líneas ni bonos -> comisión variable nula


# ══════════════════════════════════════════════════════════════════════════════
# `proyectar_comision_variable`: proyección hacia adelante que consume el panel
# "Simulación" de gerencia -- distinta de `simular()` en alcance (solo esquema
# variable, config vigente HOY, ventana fija de 3 o 6 meses hacia atrás).
# ══════════════════════════════════════════════════════════════════════════════
def test_proyeccion_rechaza_ventanas_fuera_de_3_o_6_meses(service):
    with pytest.raises(ValidationError):
        service.proyectar_comision_variable(meses_historico=12)
    with pytest.raises(ValidationError):
        service.proyectar_comision_variable(meses_historico=1)


def test_proyeccion_resuelve_config_una_sola_vez_con_la_fecha_de_hoy(service, commission_config_repo):
    """A diferencia de `simular()` (que resuelve la config vigente en cada período
    histórico), la proyección usa la config vigente HOY -- una sola resolución, sin
    importar cuántos meses de historial se pidan."""
    service.proyectar_comision_variable(meses_historico=6)

    assert commission_config_repo.get_matriz_as_reglas.call_count == 1
    assert commission_config_repo.get_factores_credito_as_rangos.call_count == 1
    assert commission_config_repo.get_matriz_as_reglas.call_args.args[0] == datetime.date.today()


def test_proyeccion_periodo_es_el_mes_siguiente_al_actual(service):
    resumen = service.proyectar_comision_variable(meses_historico=3)

    hoy = datetime.date.today()
    anio_esperado, mes_esperado = hoy.year, hoy.month + 1
    if mes_esperado == 13:
        anio_esperado, mes_esperado = anio_esperado + 1, 1

    assert resumen.periodo_proyectado == f"{anio_esperado:04d}-{mes_esperado:02d}"
    assert resumen.meses_historico == 3


def test_proyeccion_no_expone_ningun_dato_del_esquema_plano(service):
    resumen = service.proyectar_comision_variable(meses_historico=3)
    assert not hasattr(resumen, "costo_total_plana")
    assert not hasattr(resumen, "comision_plana")
    assert all(not hasattr(d, "comision_plana") for d in resumen.detalle)


def test_proyeccion_enriquece_el_detalle_con_nombre_de_vendedor(service):
    resumen = service.proyectar_comision_variable(meses_historico=3)
    assert resumen.detalle[0].vendedor_origen == "VEN01"
    assert resumen.detalle[0].nombre_vendedor == "Vendedor Uno"
