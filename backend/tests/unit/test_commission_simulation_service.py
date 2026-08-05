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
from app.services.commission_simulation_service import _meses_anteriores


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
    # Auditoría 45: sin tramos de cumplimiento configurados, el motor compartido cae al
    # fallback defensivo (`TRAMOS_CUMPLIMIENTO_FALLBACK`, reproduce los 4 tramos fijos
    # previos a esta auditoría) -- mismo motivo que `get_formula_activa=None` arriba.
    repo.get_tramos_cumplimiento_as_tramos.return_value = []
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

    assert fechas_matriz == [datetime.date(2026, 3, 31), datetime.date(2026, 2, 28), datetime.date(2026, 1, 31)]
    # Factores de crédito retirados del cálculo (Fase 3, R-7, auditoría 30 H4).
    commission_config_repo.get_factores_credito_as_rangos.assert_not_called()


def test_simulacion_no_recalcula_config_por_vendedor_solo_por_periodo(service, commission_config_repo, goal_repo):
    """Varios vendedores en el mismo mes no deben disparar consultas de config
    repetidas -- una sola resolución de vigencia por período, no por vendedor."""
    goal_repo.get_vendors_with_sales_in_period.return_value = ["VEN01", "VEN02", "VEN03"]

    service.simular(meses=1, anio_desde=2026, mes_desde=6)

    assert commission_config_repo.get_matriz_as_reglas.call_count == 1
    commission_config_repo.get_factores_credito_as_rangos.assert_not_called()
    # Auditoría 45: los tramos de cumplimiento se resuelven UNA vez por período, igual
    # que matriz -- no una vez por vendedor.
    assert commission_config_repo.get_tramos_cumplimiento_as_tramos.call_count == 1


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
    commission_config_repo.get_factores_credito_as_rangos.assert_not_called()
    assert commission_config_repo.get_matriz_as_reglas.call_args.args[0] == datetime.date.today()
    # Auditoría 45: una sola resolución de tramos de cumplimiento para toda la
    # proyección, sin importar cuántos meses de historial o vendedores se procesen.
    assert commission_config_repo.get_tramos_cumplimiento_as_tramos.call_count == 1


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


# ══════════════════════════════════════════════════════════════════════════════
# Auditoría 45 (docs/features/plan_comisiones_sobrecumplimiento_umbral_y_desglose.md
# §3.3): el desglose de la proyección promedia los componentes `sumar`/`restar`
# (montos en $, distintos cada mes) pero NO los `multiplicar` (factores constantes
# entre meses históricos, ver docstring de `proyectar_comision_variable`) -- la suma
# del desglose promediado debe reproducir exactamente `comision_variable_proyectada`.
# ══════════════════════════════════════════════════════════════════════════════
def test_proyeccion_desglose_promedio_reproduce_la_comision_total(service, goal_repo):
    hoy = datetime.date.today()
    anio_ancla, mes_ancla = hoy.year, hoy.month - 1
    if mes_ancla == 0:
        anio_ancla, mes_ancla = anio_ancla - 1, 12
    periodos = _meses_anteriores(anio_ancla, mes_ancla, 3)
    margenes = {p: (i + 1) * 1000.0 for i, p in enumerate(periodos)}

    def _lineas(vendedor, anio, mes):
        margen = margenes.get((anio, mes), 0.0)
        return [MagicMock(
            codart="A1", clase="B", subclase=None, es_servicio=False,
            subtotal_neto=margen, margen_bruto=margen, valor_descuento=0.0, dias_plazo=0,
        )]
    goal_repo.get_commission_lines.side_effect = _lineas
    goal_repo.get_vendor_net_sales_period.side_effect = lambda v, a, m: margenes.get((a, m), 0.0)

    resumen = service.proyectar_comision_variable(meses_historico=3)
    fila = resumen.detalle[0]

    assert fila.componentes  # el desglose no viene vacío
    assert fila.componentes[-1].acumulado_tras_paso == pytest.approx(fila.comision_variable_proyectada, abs=0.01)
    # El componente de líneas es la única base activa (sin cobranza/contado en el
    # fallback) -- su monto promediado debe ser el promedio real de los 3 meses:
    # (1000+2000+3000)/3 = 2000 de margen, con tasa 5% (grupo C default) = 100.0.
    base_lineas = next(c for c in fila.componentes if c.componente == "base_lineas_venta")
    assert base_lineas.monto == pytest.approx(100.0, abs=0.01)


# ══════════════════════════════════════════════════════════════════════════════
# Fase 4 (docs/features/plan_motor_metas_v3_y_comisiones_unificadas.md, R-4,
# auditoría 47 A-0.6): `reconstruir_mes_especifico` ganó dos modos explícitos --
# antes SIEMPRE usaba la configuración de hoy sin decirlo, y el usuario leía eso
# como "el simulador no concuerda con las comisiones reales".
# ══════════════════════════════════════════════════════════════════════════════
def test_reconstruccion_fiel_usa_config_vigente_al_cierre_del_periodo(service, commission_config_repo):
    """`usar_configuracion_de_hoy=False` debe resolver matriz/tramos con la fecha de
    CIERRE del período (2026-03-31), no con la fecha de hoy -- exactamente igual que
    `CommissionService`."""
    resumen = service.reconstruir_mes_especifico(2026, 3, usar_configuracion_de_hoy=False)

    assert resumen.modo == "reconstruccion_fiel"
    fecha_usada = commission_config_repo.get_matriz_as_reglas.call_args.args[0]
    assert fecha_usada == datetime.date(2026, 3, 31)


def test_reconstruccion_con_config_de_hoy_se_etiqueta_como_tal(service, commission_config_repo):
    """Default (`usar_configuracion_de_hoy=True`, compatibilidad): sigue usando la
    configuración de hoy, pero ahora la respuesta lo declara explícitamente."""
    resumen = service.reconstruir_mes_especifico(2026, 3)

    assert resumen.modo == "config_actual"
    fecha_usada = commission_config_repo.get_matriz_as_reglas.call_args.args[0]
    assert fecha_usada == datetime.date.today()


def test_proyeccion_se_etiqueta_como_proyeccion(service):
    resumen = service.proyectar_comision_variable(meses_historico=3)
    assert resumen.modo == "proyeccion"


def test_reconstruccion_fiel_coincide_con_el_calculo_real(
    goal_repo, commission_config_repo, catalog_repo,
):
    """Test de paridad (garantía permanente contra R-4): con el mismo `goal_repo`/
    `commission_config_repo`, la reconstrucción fiel (`usar_configuracion_de_hoy=
    False`) de un mes cerrado debe coincidir centavo a centavo con lo que
    `CommissionService.get_commission_tracking` calcularía para ese mismo período --
    ambos delegan en el mismo `calcular_comision_variable_completa` con la misma
    `fecha_config` (vigente al cierre)."""
    from app.services.commission_service import CommissionService

    goal_repo.get_commission_tracking_rows.return_value = [{
        "id": 1, "id_vendedor_origen": "VEN01", "vendedor": "Vendedor Uno",
        "monto_meta": 10000.0, "comision_base_pct": 7.0, "bono_sobrecumplimiento": 0.0,
        "estado": "APROBADA", "venta_neta": 9000.0,
    }]

    simulador = CommissionSimulationService(goal_repo, commission_config_repo, catalog_repo)
    real_service = CommissionService(goal_repo, commission_config_repo)

    resumen_simulado = simulador.reconstruir_mes_especifico(2026, 3, usar_configuracion_de_hoy=False)
    filas_reales = real_service.get_commission_tracking(2026, 3)

    assert resumen_simulado.detalle[0].comision_variable_proyectada == pytest.approx(
        filas_reales[0].comision_devengada, abs=0.01,
    )
