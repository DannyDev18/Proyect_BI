# backend/tests/unit/test_commission_service.py
import datetime
from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.services.commission_service import CommissionService


@pytest.fixture
def goal_repo():
    repo = MagicMock()
    # Defaults neutros para que `_calcular_variable` (motor de fórmula, único camino
    # desde la Fase 1 -- docs/features/plan_motor_metas_v3_y_comisiones_unificadas.md,
    # R-1) no reviente por MagicMocks sin configurar iterando/como número.
    repo.get_commission_lines.return_value = []
    repo.get_vendor_devoluciones_period.return_value = 0.0
    repo.get_cross_sell_accepted_amount.return_value = 0.0
    repo.get_new_or_reactivated_clients.return_value = 0
    repo.get_vendor_credit_profile.return_value = {"dias_cobro_promedio": None}
    return repo


@pytest.fixture
def commission_config_repo():
    repo = MagicMock()
    repo.get_matriz_as_reglas.return_value = []
    repo.get_config_vendedor.return_value = None
    repo.get_liquidacion.return_value = None  # sin snapshot congelado previo por defecto
    # Sin fórmula activa configurada -> cae al fallback (COMPONENTES_FALLBACK):
    # base_lineas_venta + factor_tipo_vendedor + multiplicador_cumplimiento −
    # devoluciones + bonos, mismo comportamiento histórico de referencia de estos tests.
    repo.get_formula_activa.return_value = None
    # Sin tramos configurados, cae al fallback defensivo derivado de settings
    # (RN-CM16: [0,90)->0.0x lejos, [90,100)->cerca, [100,110)->meta, [110,∞)->excelente).
    repo.get_tramos_cumplimiento_as_tramos.return_value = []
    return repo


@pytest.fixture
def service(goal_repo, commission_config_repo):
    return CommissionService(goal_repo, commission_config_repo)


# Alias -- mismo servicio, ambos nombres se usaban en secciones distintas del archivo
# antes de la Fase 1 (cuando "service" era el esquema plano sin repo y "service_variable"
# el variable con repo). Desde R-1 solo existe la comisión variable, un único servicio.
service_variable = service


def test_get_commission_tracking_calcula_comision_por_fila(service, goal_repo):
    goal_repo.get_commission_tracking_rows.return_value = [
        {
            "id": 1, "id_vendedor_origen": "VEN01", "vendedor": "Juan Pérez",
            "monto_meta": 10000.0, "comision_base_pct": 7.0, "bono_sobrecumplimiento": 500.0,
            "estado": "APROBADA", "venta_neta": 12000.0,
        },
        {
            "id": 2, "id_vendedor_origen": "VEN02", "vendedor": "Ana Ruiz",
            "monto_meta": 10000.0, "comision_base_pct": 7.0, "bono_sobrecumplimiento": 500.0,
            "estado": "APROBADA", "venta_neta": 5000.0,
        },
    ]

    filas = service.get_commission_tracking(anio=2026, mes=6)

    assert len(filas) == 2
    # Sin líneas de venta (mock vacío) la base es 0 -- ambos comisionan $0, pero el
    # tramo de cumplimiento SÍ distingue: confirma que `nivel` ya no es el esquema
    # plano legacy sino el tramo real configurable. El % de cumplimiento se mide
    # contra la meta SIN el ajuste por tipo de vendedor (`resolver_meta_sin_ajuste_
    # tipo` -- sin config_vendedor, se asume "externo", meta_cumplimiento =
    # 10000/1.10 = 9090.91): 12000/9090.91=132%, 5000/9090.91=55%.
    assert filas[0].pct_cumplimiento == pytest.approx(132.0)
    assert filas[1].pct_cumplimiento == pytest.approx(55.0)
    assert filas[1].comision_devengada == 0.0  # bajo el 90% -- compuerta de la Fase 2


def test_get_commission_tracking_excluye_vendedores_inactivos(goal_repo, commission_config_repo):
    """Petición explícita del usuario: "Cumplimiento real y comisión por vendedor"
    (panel gerencial) solo debe listar vendedores activos, mismo criterio ya aplicado a
    `GoalsService.get_commission_tracking`."""
    goal_repo.get_commission_tracking_rows.return_value = [
        {
            "id": 1, "id_vendedor_origen": "VEN01", "vendedor": "Juan Pérez",
            "monto_meta": 10000.0, "comision_base_pct": 7.0, "bono_sobrecumplimiento": 500.0,
            "estado": "APROBADA", "venta_neta": 12000.0,
        },
        {
            "id": 2, "id_vendedor_origen": "VEN02", "vendedor": "Ana Ruiz (baja)",
            "monto_meta": 10000.0, "comision_base_pct": 7.0, "bono_sobrecumplimiento": 500.0,
            "estado": "APROBADA", "venta_neta": 5000.0,
        },
    ]
    catalog_repo = MagicMock()
    catalog_repo.get_vendedores_activo_bulk.return_value = {"VEN01": True, "VEN02": False}
    service = CommissionService(goal_repo, commission_config_repo, catalog_repo)

    filas = service.get_commission_tracking(anio=2026, mes=6)

    assert len(filas) == 1
    assert filas[0].vendedor == "Juan Pérez"
    catalog_repo.get_vendedores_activo_bulk.assert_called_once_with(["VEN01", "VEN02"])


def test_get_my_commission_sin_meta_configurada_devuelve_ceros(service, goal_repo):
    goal_repo.get_goal_for_period.return_value = None
    goal_repo.get_vendor_net_sales_period.return_value = 5000.0

    resultado = service.get_my_commission("VEN01", 2026, 6)

    assert resultado.monto_meta == 0.0
    assert resultado.comision_devengada == 0.0


def test_get_my_commission_usa_meta_y_venta_real(service, goal_repo):
    goal = MagicMock(monto_meta=10000.0)
    goal_repo.get_goal_for_period.return_value = goal
    goal_repo.get_vendor_net_sales_period.return_value = 9500.0

    resultado = service.get_my_commission("VEN01", 2026, 6)

    assert resultado.venta_real == 9500.0
    # Meta sin ajuste por tipo de vendedor: 10000/1.10 = 9090.91 -> 9500/9090.91=104.5%.
    assert resultado.pct_cumplimiento == pytest.approx(104.5)


def test_get_my_commission_mensaje_meta_superada(service, goal_repo):
    goal = MagicMock(monto_meta=10000.0)
    goal_repo.get_goal_for_period.return_value = goal
    goal_repo.get_vendor_net_sales_period.return_value = 11000.0

    resultado = service.get_my_commission("VEN01", 2026, 6)

    assert resultado.mensaje_alerta == "¡Meta superada este período!"
    assert resultado.en_alerta_cierre is False


def test_get_my_commission_periodo_cerrado_no_tiene_dias_restantes(service, goal_repo):
    """Un período distinto al mes/año actuales (histórico) no debe reportar días
    restantes ni disparar la alerta de última semana."""
    goal = MagicMock(monto_meta=10000.0)
    goal_repo.get_goal_for_period.return_value = goal
    goal_repo.get_vendor_net_sales_period.return_value = 2000.0

    resultado = service.get_my_commission("VEN01", 2020, 1)

    assert resultado.dias_restantes_mes == 0
    assert resultado.en_alerta_cierre is False


def test_get_my_commission_alerta_ultima_semana_bajo_umbral(service, goal_repo, monkeypatch):
    """Fuerza 'hoy' a los últimos días del mes en curso con bajo cumplimiento -> alerta."""
    hoy_real = datetime.date.today()
    ultimo_dia = datetime.date(hoy_real.year + (hoy_real.month == 12), (hoy_real.month % 12) + 1, 1) - datetime.timedelta(days=1)

    class _FakeDate(datetime.date):
        @classmethod
        def today(cls):
            return ultimo_dia

    monkeypatch.setattr("app.services.commission_service.datetime.date", _FakeDate)

    goal = MagicMock(monto_meta=10000.0)
    goal_repo.get_goal_for_period.return_value = goal
    goal_repo.get_vendor_net_sales_period.return_value = 1000.0  # 10% cumplimiento

    resultado = service.get_my_commission("VEN01", ultimo_dia.year, ultimo_dia.month)

    assert resultado.en_alerta_cierre is True
    assert resultado.mensaje_alerta is not None
    assert "Última semana" in resultado.mensaje_alerta


def test_get_post_goal_invoices_vacio_sin_meta(service, goal_repo):
    goal_repo.get_goal_for_period.return_value = None
    assert service.get_post_goal_invoices("VEN01", 2026, 6) == []


def test_get_post_goal_invoices_delega_al_repositorio(service, goal_repo):
    goal = MagicMock(monto_meta=10000.0)
    goal_repo.get_goal_for_period.return_value = goal
    goal_repo.get_post_goal_invoices.return_value = [
        {"num_factura": "F001", "fecha": "2026-06-15", "monto_factura": 3000.0, "acumulado_venta": 10500.0},
    ]

    facturas = service.get_post_goal_invoices("VEN01", 2026, 6)

    assert len(facturas) == 1
    assert facturas[0].num_factura == "F001"
    goal_repo.get_post_goal_invoices.assert_called_once_with("VEN01", 2026, 6, 10000.0)


# ══════════════════════════════════════════════════════════════════════════════
# Snapshot de liquidación: mapeo de `settings.COMISION_MODO` -> `modo` de la BD
# (auditoría 34, H-4). `comision_liquidaciones.modo` tiene un CHECK ('sombra','oficial'),
# distinto del vocabulario del backend -- desde la Fase 1 (R-1) solo hay dos valores
# válidos de `COMISION_MODO`: "sombra" (default, no persiste como oficial) y "variable"
# (pasa a ser el esquema oficial que se liquida). "plana" ya no es un modo válido.
# ══════════════════════════════════════════════════════════════════════════════
def test_snapshot_modo_variable_se_persiste_como_oficial(service_variable, goal_repo, commission_config_repo, monkeypatch):
    monkeypatch.setattr(settings, "COMISION_MODO", "variable")
    goal_repo.get_goal_for_period.return_value = MagicMock(monto_meta=10000.0)
    goal_repo.get_vendor_net_sales_period.return_value = 9000.0

    service_variable.get_my_commission("VEN01", 2020, 1)  # período cerrado -> persiste snapshot

    commission_config_repo.save_liquidacion.assert_called_once()
    kwargs = commission_config_repo.save_liquidacion.call_args.kwargs
    assert kwargs["modo"] == "oficial"


def test_snapshot_modo_sombra_se_persiste_igual(service_variable, goal_repo, commission_config_repo, monkeypatch):
    monkeypatch.setattr(settings, "COMISION_MODO", "sombra")
    goal_repo.get_goal_for_period.return_value = MagicMock(monto_meta=10000.0)
    goal_repo.get_vendor_net_sales_period.return_value = 9000.0

    service_variable.get_my_commission("VEN01", 2020, 1)

    kwargs = commission_config_repo.save_liquidacion.call_args.kwargs
    assert kwargs["modo"] == "sombra"


def test_modo_invalido_lanza_keyerror_explicito(service_variable, goal_repo, monkeypatch):
    """"plana" ya no es un valor válido de `COMISION_MODO` (Fase 1, R-1) -- un valor
    fuera del catálogo ("sombra"/"variable") debe fallar de forma explícita, no
    degradar en silencio a no persistir."""
    monkeypatch.setattr(settings, "COMISION_MODO", "plana")
    goal_repo.get_goal_for_period.return_value = MagicMock(monto_meta=10000.0)
    goal_repo.get_vendor_net_sales_period.return_value = 9000.0

    with pytest.raises(KeyError):
        service_variable.get_my_commission("VEN01", 2020, 1)


# ══════════════════════════════════════════════════════════════════════════════
# H1/H2 (docs/auditoria/35_actualizacion_modulo_metas.md): configuración vigente al
# CIERRE del período (no "hoy") + inmutabilidad real de liquidaciones oficiales.
# ══════════════════════════════════════════════════════════════════════════════
def test_calculo_variable_resuelve_config_vigente_al_cierre_del_periodo(service_variable, goal_repo, commission_config_repo, monkeypatch):
    monkeypatch.setattr(settings, "COMISION_MODO", "sombra")  # no se congela -> siempre recalcula
    goal_repo.get_goal_for_period.return_value = MagicMock(monto_meta=10000.0)
    goal_repo.get_vendor_net_sales_period.return_value = 9000.0

    service_variable.get_my_commission("VEN01", 2026, 3)  # período cerrado (hoy > marzo 2026)

    fecha_usada_matriz = commission_config_repo.get_matriz_as_reglas.call_args.args[0]
    assert fecha_usada_matriz == datetime.date(2026, 3, 31)
    # Factores de crédito retirados del cálculo (Fase 3, R-7, auditoría 30 H4): ya no
    # se consulta la tabla en absoluto.
    commission_config_repo.get_factores_credito_as_rangos.assert_not_called()


def test_liquidacion_oficial_congelada_no_se_recalcula_ni_se_reescribe(service_variable, goal_repo, commission_config_repo, monkeypatch):
    """H2: una vez que existe un snapshot 'oficial' para el período, debe devolverse
    tal cual -- ni se recalcula con la config actual ni se vuelve a escribir."""
    monkeypatch.setattr(settings, "COMISION_MODO", "variable")
    snapshot = MagicMock()
    snapshot.detalle_json = {
        "comision_base": 100.0, "comision_post_tipo": 100.0, "nivel": "META",
        "multiplicador_cumplimiento": 1.0, "comision_post_cumplimiento": 100.0,
        "devoluciones_estimadas": 0.0, "bonos_total": 0.0, "comision_final": 555.55,
        "desglose_lineas": [],
    }
    commission_config_repo.get_liquidacion.return_value = snapshot
    goal_repo.get_goal_for_period.return_value = MagicMock(monto_meta=10000.0)
    goal_repo.get_vendor_net_sales_period.return_value = 9000.0

    resultado = service_variable.get_my_commission("VEN01", 2020, 1)

    assert resultado.comision_devengada == 555.55
    commission_config_repo.get_matriz_as_reglas.assert_not_called()
    commission_config_repo.save_liquidacion.assert_not_called()
    goal_repo.get_commission_lines.assert_not_called()


def test_liquidacion_sombra_sigue_recalculando_aunque_exista_snapshot_previo(service_variable, goal_repo, commission_config_repo, monkeypatch):
    """El modo 'sombra' (piloto, no paga) debe seguir refrescándose en cada consulta
    -- la inmutabilidad de H2 solo aplica al modo 'oficial'."""
    monkeypatch.setattr(settings, "COMISION_MODO", "sombra")
    commission_config_repo.get_liquidacion.return_value = MagicMock(detalle_json={
        "comision_base": 1.0, "comision_post_tipo": 1.0, "nivel": "LEJOS",
        "multiplicador_cumplimiento": 0.0, "comision_post_cumplimiento": 0.0,
        "devoluciones_estimadas": 0.0, "bonos_total": 0.0, "comision_final": 1.0,
        "desglose_lineas": [],
    })
    goal_repo.get_goal_for_period.return_value = MagicMock(monto_meta=10000.0)
    goal_repo.get_vendor_net_sales_period.return_value = 9000.0

    service_variable.get_my_commission("VEN01", 2020, 1)

    goal_repo.get_commission_lines.assert_called_once()
    commission_config_repo.save_liquidacion.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
# Fase 1 (docs/features/plan_motor_metas_v3_y_comisiones_unificadas.md, R-1/R-3): la
# comisión variable es la ÚNICA fuente de "Comisiones devengadas" -- ya no hay un
# esquema plano paralelo que mostrar/calcular.
# ══════════════════════════════════════════════════════════════════════════════
def test_get_commission_tracking_no_persiste_en_modo_sombra(
    service_variable, goal_repo, commission_config_repo, monkeypatch,
):
    monkeypatch.setattr(settings, "COMISION_MODO", "sombra")
    goal_repo.get_commission_tracking_rows.return_value = [
        {
            "id": 1, "id_vendedor_origen": "VEN01", "vendedor": "Juan Pérez",
            "monto_meta": 10000.0, "comision_base_pct": 7.0, "bono_sobrecumplimiento": 500.0,
            "estado": "APROBADA", "venta_neta": 12000.0,
        },
    ]

    filas = service_variable.get_commission_tracking(anio=2020, mes=1)

    assert len(filas) == 1
    assert filas[0].componentes  # traza de la fórmula expuesta para el desglose del panel


def test_get_commission_tracking_resuelve_config_una_sola_vez_por_periodo(
    service_variable, goal_repo, commission_config_repo, monkeypatch,
):
    """Guarda de rendimiento (plan §7): fórmula/matriz/tramos se resuelven UNA vez por
    llamada a `get_commission_tracking`, no una vez por vendedor -- crédito ya no se
    resuelve en absoluto (Fase 3)."""
    monkeypatch.setattr(settings, "COMISION_MODO", "sombra")
    goal_repo.get_commission_tracking_rows.return_value = [
        {
            "id": i, "id_vendedor_origen": f"VEN{i:02d}", "vendedor": f"Vendedor {i}",
            "monto_meta": 10000.0, "comision_base_pct": 7.0, "bono_sobrecumplimiento": 500.0,
            "estado": "APROBADA", "venta_neta": 9000.0,
        }
        for i in range(1, 4)
    ]

    filas = service_variable.get_commission_tracking(anio=2020, mes=1)

    assert len(filas) == 3
    assert commission_config_repo.get_matriz_as_reglas.call_count == 1
    commission_config_repo.get_factores_credito_as_rangos.assert_not_called()
    assert commission_config_repo.get_formula_activa.call_count == 1
    assert commission_config_repo.get_tramos_cumplimiento_as_tramos.call_count == 1


def test_snapshot_no_se_persiste_en_mes_en_curso(service_variable, goal_repo, commission_config_repo, monkeypatch):
    """Salvaguarda 6 existente: el mes en curso no se congela porque su cálculo cambia
    con cada consulta -- confirmamos que sigue vigente tras el fix de H-4."""
    monkeypatch.setattr(settings, "COMISION_MODO", "variable")
    hoy = datetime.date.today()
    goal_repo.get_goal_for_period.return_value = MagicMock(monto_meta=10000.0)
    goal_repo.get_vendor_net_sales_period.return_value = 9000.0

    service_variable.get_my_commission("VEN01", hoy.year, hoy.month)

    commission_config_repo.save_liquidacion.assert_not_called()
