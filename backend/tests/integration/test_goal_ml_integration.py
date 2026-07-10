# backend/tests/integration/test_goal_ml_integration.py
"""Integración ML del módulo Metas y Comisiones (docs/auditoria/15_...). A diferencia de
`test_goals_generation.py` (que ESCRIBE en `metas_comerciales_operativas`), estas pruebas
son de solo lectura: validan el flujo completo ModelLoader -> ContractValidator ->
Modelo -> validación de salida -> GoalMLService contra el EDW y los `.pkl` reales."""
import pytest

from app.database.session import SessionLocal
from app.ml.model_loader import ModelLoader
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.goal_repository import GoalRepository
from app.services.goal_ml_service import GoalMLService
from app.services.goals_service import GoalsService

pytestmark = pytest.mark.integration

MODELS_DIR = "c:/Proyect_BI/ml/models"
CONTRACTS_DIR = "c:/Proyect_BI/ml/contracts/models"
# Vendedor/sucursal reales verificados contra el EDW en la auditoría 14
# (docs/auditoria/14_fase0_analisis_modulo_metas_comisiones.md, §3).
VENDEDOR_ORIGEN = "VEN01"
SUCURSAL = "SUC. EL REY"


@pytest.fixture
def loader() -> ModelLoader:
    loader = ModelLoader(models_dir=MODELS_DIR, contracts_dir=CONTRACTS_DIR)
    loader.load_all()
    return loader


@pytest.fixture
def goal_ml_service(loader):
    db = SessionLocal()
    try:
        goal_repo = GoalRepository(db)
        dataset_repo = DatasetRepository(db)
        goals_service = GoalsService(goal_repo, loader)
        yield GoalMLService(goal_repo, dataset_repo, loader, goals_service)
    finally:
        db.close()


def test_model_loader_carga_los_7_modelos_y_sus_contratos(loader):
    for key in ["sales_rf", "demand_rf", "churn_rf", "segmentation", "association", "anomaly", "goals_rf"]:
        assert loader.is_loaded(key), f"Modelo '{key}' no cargó desde {MODELS_DIR}"
        contrato = loader.get_contract(key)
        assert contrato is not None, f"Contrato de '{key}' no cargó desde {CONTRACTS_DIR}"
        assert contrato.is_active, f"Contrato de '{key}' debería estar 'active' (Fase 3 de la reconstrucción ML)"


def test_suggest_goal_devuelve_meta_estadistica_y_trazabilidad(goal_ml_service):
    resultado = goal_ml_service.suggest_goal(VENDEDOR_ORIGEN, SUCURSAL)

    assert resultado.vendedor_origen == VENDEDOR_ORIGEN
    assert resultado.meta_sugerida_estadistica >= 0
    assert resultado.meses_historico_usados >= 3
    assert resultado.metodo_estadistico in ("estadistico_iqr_v1", "estadistico_iqr_ml_v1")
    # meta_sugerida_ia puede ser None si el trend no resuelve para el próximo período,
    # pero si el modelo está cargado (verificado arriba) no debe lanzar excepción.


def test_forecast_cierre_pasa_por_contrato_y_devuelve_prediccion_en_rango_plausible(goal_ml_service):
    resultado = goal_ml_service.forecast_cierre(sucursal=SUCURSAL, meta_mensual=50000.0)

    assert resultado.sucursal == SUCURSAL
    assert resultado.dias_restantes >= 0
    # Si contract_validation.py NO hubiera bloqueado una predicción fuera de rango
    # (ml/contracts/models/sales.json: plausible_range=[0, 5000000]), esta aserción
    # es la que lo detectaría -- la validación real ya ocurrió dentro de inference.predict_sales.
    assert 0 <= resultado.proyeccion_cierre <= 5_000_000 * 30  # 30 días acumulados, cota generosa


def test_get_commercial_recommendations_no_lanza_si_hay_top_productos(goal_ml_service):
    recomendaciones = goal_ml_service.get_commercial_recommendations(VENDEDOR_ORIGEN)
    assert isinstance(recomendaciones, list)
    for r in recomendaciones:
        assert r.producto_cod
        assert isinstance(r.score_afinidad, float)


def test_get_category_recommendations_mapea_categorias_reales(goal_ml_service):
    recomendaciones = goal_ml_service.get_category_recommendations(top_n=5)
    assert isinstance(recomendaciones, list)
    for r in recomendaciones:
        assert r.categoria_origen
        assert r.categoria_sugerida
        assert r.producto_sugerido


def test_classify_vendor_risk_clasifica_sin_lanzar(goal_ml_service):
    ranking_falso = [
        {"nombre": "Vendedor Alto Ritmo", "ventas": 100000.0, "meta": 50000.0, "cumple": True},
        {"nombre": "Vendedor Bajo Ritmo", "ventas": 1000.0, "meta": 50000.0, "cumple": False},
    ]
    clasificacion = goal_ml_service.classify_vendor_risk(ranking_falso)
    estados = {c.nombre: c.estado for c in clasificacion}
    assert estados["Vendedor Alto Ritmo"] == "alta_probabilidad"
    assert estados["Vendedor Bajo Ritmo"] == "en_riesgo"
