# backend/tests/unit/test_goal_ml_service.py
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import ValidationError
from app.repositories.goal_repository import VendorMonthlySales, VendorRecentSales
from app.services.goal_ml_service import GoalMLService
from app.services.goal_pipeline_stages import PipelineConfigV3


@pytest.fixture
def goal_repo():
    repo = MagicMock()
    # Motor v2 (docs/auditoria/46_motor_metas_configurable.md): índice de empresa vacío
    # por defecto (sin respaldo estacional) y sin trazabilidad persistida previa -- cada
    # test que necesite otro comportamiento lo sobre-escribe explícitamente.
    repo.get_indice_estacional_empresa.return_value = {}
    repo.get_trazabilidad.return_value = None
    # R-8/auditoría 47 A-0.4: sin vendedores de 0 meses de historia por defecto -- el
    # test dedicado a ese camino lo sobre-escribe explícitamente.
    repo.get_active_vendors_without_history.return_value = []
    return repo


@pytest.fixture
def dataset_repo():
    return MagicMock()


@pytest.fixture
def service(goal_repo, dataset_repo):
    loader = MagicMock()
    loader.is_loaded.return_value = False  # sin modelos cargados salvo que un test lo cambie
    return GoalMLService(goal_repo, dataset_repo, loader)


def _historial(n=12, base=1000.0):
    return [VendorMonthlySales(anio=2025, mes=m, ventas=base, unidades=10.0) for m in range(1, n + 1)]


def test_suggest_goal_lanza_validation_error_sin_historico(service, goal_repo):
    goal_repo.get_vendor_monthly_history.return_value = []
    with pytest.raises(ValidationError):
        service.suggest_goal("VEN01")


def test_suggest_goal_calcula_sin_senal_ml_de_anomalias(service, goal_repo):
    """El modelo `anomaly` fue decomisionado por completo (docs/auditoria/51_...md):
    `GoalMLService` ya no consulta ninguna señal de meses atípicos ML, la meta se
    calcula 100% con `IQRGoalCalculationEngine`."""
    goal_repo.get_vendor_monthly_history.return_value = _historial()

    resultado = service.suggest_goal("VEN01")

    assert resultado.meta_sugerida_estadistica == pytest.approx(1000.0)
    assert resultado.meses_atipicos_ml_detectados == 0


# ── Generación OFICIAL de metas (docs/auditoria/19_/20_...md): grano vendedor, IQR puro ──
def _vendor(vendedor: str, unidades_anterior: float = 20.0) -> VendorRecentSales:
    return VendorRecentSales(vendedor_origen=vendedor, unidades_anterior=unidades_anterior)


def test_generate_proposals_una_fila_por_vendedor_sin_sucursal(service, goal_repo):
    """Antes de la corrección, la consulta de tendencias traía una fila por
    vendedor×sucursal y se insertaba una meta por cada una -- duplicando registros para
    un mismo vendedor. Ahora es una fila por vendedor (docs/auditoria/19_...md)."""
    goal_repo.get_vendors_with_recent_sales.return_value = [_vendor("VEN01"), _vendor("VEN02")]
    goal_repo.get_vendor_monthly_history.return_value = _historial()
    goal_repo.find_proposal.return_value = None

    creados = service.generate_proposals(anio=2026, mes=7, factor_presion=1.1)

    assert creados == 2
    assert goal_repo.insert_proposal.call_count == 2
    inserted_vendedores = {call.args[2] for call in goal_repo.insert_proposal.call_args_list}
    assert inserted_vendedores == {"VEN01", "VEN02"}


def test_generate_proposals_actualiza_propuesta_existente_sin_tocar_aprobada(service, goal_repo):
    goal_repo.get_vendors_with_recent_sales.return_value = [_vendor("VEN01")]
    goal_repo.get_vendor_monthly_history.return_value = _historial()
    goal_repo.find_proposal.return_value = (7, "APROBADA")

    creados = service.generate_proposals(anio=2026, mes=7)

    assert creados == 0
    goal_repo.insert_proposal.assert_not_called()
    goal_repo.update_proposal_amounts.assert_not_called()


def test_generate_proposals_vendedor_sin_historico_recibe_benchmark_del_equipo(service, goal_repo):
    """R-8/auditoría 47 A-0.4: un vendedor activo sin NINGUNA venta histórica (el caso
    real de VEN20/VEN05/VEN06/VEN08 -- 0 meses de historia) no aparece en
    `get_vendors_with_recent_sales` (exige venta el mes anterior), así que antes de este
    fix nunca entraba al lote y jamás recibía una meta. Ahora `generate_proposals` lo
    incluye vía `get_active_vendors_without_history` y le asigna el benchmark puro del
    equipo (mediana de los vendedores CON historial), sin invocar el motor IQR."""
    goal_repo.get_vendors_with_recent_sales.return_value = [_vendor("VEN01"), _vendor("VEN02")]
    goal_repo.get_active_vendors_without_history.return_value = ["VEN99"]
    goal_repo.get_vendor_monthly_history.return_value = _historial()
    goal_repo.find_proposal.return_value = None

    creados = service.generate_proposals(anio=2026, mes=7)

    assert creados == 3
    inserted = {call.args[2]: call.args[3] for call in goal_repo.insert_proposal.call_args_list}
    assert set(inserted) == {"VEN01", "VEN02", "VEN99"}
    # VEN01/VEN02 comparten histórico idéntico -> misma meta -> la mediana del equipo
    # (excluyendo a VEN99, que no aporta datos reales) es ese mismo monto.
    assert inserted["VEN99"] == pytest.approx(inserted["VEN01"], rel=1e-6)

    traza_ven99 = goal_repo.insert_proposal.call_args_list[
        [c.args[2] for c in goal_repo.insert_proposal.call_args_list].index("VEN99")
    ].args[5]
    assert '"metodo_estadistico": "sin_historico"' in traza_ven99
    assert '"meses_historico_usados": 0' in traza_ven99


def test_generate_proposals_no_duplica_vendedor_con_venta_reciente_y_sin_historico(service, goal_repo):
    """Un `codven` no debería poder aparecer en ambas listas a la vez en la práctica,
    pero si el repositorio lo hiciera, `generate_proposals` debe tratarlo como "con
    historial" (la fuente de verdad real) y no duplicar la fila."""
    goal_repo.get_vendors_with_recent_sales.return_value = [_vendor("VEN01")]
    goal_repo.get_active_vendors_without_history.return_value = ["VEN01"]
    goal_repo.get_vendor_monthly_history.return_value = _historial()
    goal_repo.find_proposal.return_value = None

    creados = service.generate_proposals(anio=2026, mes=7)

    assert creados == 1
    goal_repo.insert_proposal.assert_called_once()


# ── E9/E13/E15/E16 con datos reales del repositorio (no un no-op permanente) ───────────
def test_generate_proposals_con_capacidad_y_cartera_activas_consulta_metricas_reales(goal_repo, dataset_repo):
    """Antes de este cambio, E9 (capacidad) llamaba siempre con `None,None,None` -- un
    no-op garantizado. Con la etapa activa, el servicio debe pedirle a
    `GoalRepository.get_metricas_cartera_vendedor` los insumos reales UNA vez por
    vendedor (no una vez por monto y otra por unidades) y usarlos para topar la meta."""
    loader = MagicMock()
    loader.is_loaded.return_value = False
    pipeline = PipelineConfigV3(capacidad_activa=True, capacidad_holgura=1.10, cartera_activa=True, redondeo_multiplo=1)
    service = GoalMLService(goal_repo, dataset_repo, loader, pipeline_config=pipeline)

    goal_repo.get_vendors_with_recent_sales.return_value = [_vendor("VEN01")]
    goal_repo.get_vendor_monthly_history.return_value = _historial(base=10000.0)
    goal_repo.find_proposal.return_value = None
    goal_repo.get_metricas_cartera_vendedor.return_value = {
        "clientes_activos_mes": 5.0, "promedio_clientes_activos_ventana": 5.0,
        "ticket_promedio": 50.0, "frecuencia_compra_mensual": 1.0,
    }

    service.generate_proposals(anio=2026, mes=7)

    # Un vendedor -> una sola consulta de cartera (compartida entre E9 y E13, y entre
    # el ajuste de monto y de unidades), nunca una consulta por cada llamada.
    goal_repo.get_metricas_cartera_vendedor.assert_called_once_with("VEN01", 2026, 7)
    meta_monto = goal_repo.insert_proposal.call_args.args[3]
    # Capacidad real = 5 clientes x $50 ticket x 1 frecuencia = $250; con holgura 1.10 el
    # techo es $275 -- muy por debajo de los $10.000 de meta estadística sin ajustar.
    assert meta_monto == pytest.approx(275.0)


def test_generate_proposals_con_capacidad_activa_sin_cartera_medible_es_no_op(goal_repo, dataset_repo):
    """Sin cartera medible (repositorio real devuelve todo `None`), E9 debe omitirse
    -- nunca aplicar un tope de capacidad 0."""
    loader = MagicMock()
    loader.is_loaded.return_value = False
    pipeline = PipelineConfigV3(capacidad_activa=True)
    service = GoalMLService(goal_repo, dataset_repo, loader, pipeline_config=pipeline)

    goal_repo.get_vendors_with_recent_sales.return_value = [_vendor("VEN01")]
    goal_repo.get_vendor_monthly_history.return_value = _historial(base=1000.0)
    goal_repo.find_proposal.return_value = None
    goal_repo.get_metricas_cartera_vendedor.return_value = {
        "clientes_activos_mes": None, "promedio_clientes_activos_ventana": None,
        "ticket_promedio": None, "frecuencia_compra_mensual": None,
    }

    service.generate_proposals(anio=2026, mes=7)

    meta_monto = goal_repo.insert_proposal.call_args.args[3]
    assert meta_monto == pytest.approx(1000.0)


def test_generate_proposals_con_cumplimiento_historico_activo_ajusta_la_meta(goal_repo, dataset_repo):
    loader = MagicMock()
    loader.is_loaded.return_value = False
    pipeline = PipelineConfigV3(cumplimiento_activo=True, cumplimiento_peso=0.5)
    service = GoalMLService(goal_repo, dataset_repo, loader, pipeline_config=pipeline)

    goal_repo.get_vendors_with_recent_sales.return_value = [_vendor("VEN01")]
    goal_repo.get_vendor_monthly_history.return_value = _historial(base=1000.0)
    goal_repo.find_proposal.return_value = None
    goal_repo.get_cumplimiento_historico_promedio.return_value = 1.2  # 120% promedio real

    service.generate_proposals(anio=2026, mes=7)

    goal_repo.get_cumplimiento_historico_promedio.assert_called_once_with("VEN01", 2026, 7)
    meta_monto = goal_repo.insert_proposal.call_args.args[3]
    # 1000 * (1 + (1.2-1)*0.5) = 1100
    assert meta_monto == pytest.approx(1100.0)


def test_pipeline_sin_etapas_opcionales_activas_nunca_consulta_cartera_ni_cumplimiento(service, goal_repo):
    """Semilla real (todas las etapas opcionales desactivadas, `PipelineConfigV3()` por
    defecto): no debe gastarse ninguna consulta extra al EDW por vendedor."""
    goal_repo.get_vendors_with_recent_sales.return_value = [_vendor("VEN01")]
    goal_repo.get_vendor_monthly_history.return_value = _historial()
    goal_repo.find_proposal.return_value = None

    service.generate_proposals(anio=2026, mes=7)

    goal_repo.get_metricas_cartera_vendedor.assert_not_called()
    goal_repo.get_cumplimiento_historico_promedio.assert_not_called()


def test_get_commercial_recommendations_vacio_sin_top_productos(service, goal_repo):
    goal_repo.get_vendor_top_products.return_value = []
    assert service.get_commercial_recommendations("VEN01") == []


def test_classify_vendor_risk_marca_en_riesgo_y_alta_probabilidad(service):
    ranking = [
        {"nombre": "A", "ventas": 90000.0, "meta": 100000.0, "cumple": False},
        {"nombre": "B", "ventas": 100.0, "meta": 100000.0, "cumple": False},
    ]
    resultado = service.classify_vendor_risk(ranking)
    estados = {r.nombre: r.estado for r in resultado}
    assert estados["A"] == "alta_probabilidad"
    assert estados["B"] == "en_riesgo"


def test_classify_vendor_risk_maneja_meta_cero(service):
    resultado = service.classify_vendor_risk([{"nombre": "Z", "ventas": 500.0, "meta": 0.0, "cumple": False}])
    assert resultado[0].pct_cumplimiento == 0.0


