# backend/tests/unit/test_system_service.py
"""SystemService probado con repositorio/ModelLoader mockeados (docs/auditoria/
33_actualizacion_modulo_gerencia.md, H4): reemplaza el mock estático `PROVENANCE_FACTS`
del frontend. Ningún test toca la BD ni carga modelos reales."""
from datetime import datetime
from unittest.mock import MagicMock

from app.services.system_service import SystemService


def test_get_provenance_incluye_ultima_carga_y_modelos_activos():
    system_repo = MagicMock()
    system_repo.get_ultima_carga_dw.return_value = datetime(2026, 7, 15, 10, 0, 0)

    model_loader = MagicMock()
    model_loader.keys.return_value = ["sales_rf", "anomaly"]
    model_loader.is_loaded.side_effect = lambda k: {"sales_rf": True, "anomaly": False}[k]
    model_loader.get_meta.return_value = {"algorithm": "RandomForestRegressor", "trained_at": "2026-07-11T00:00:00Z"}

    service = SystemService(system_repo, model_loader)
    provenance = service.get_provenance()

    assert provenance["ultima_carga_dw"] == "2026-07-15T10:00:00"
    modelos_por_nombre = {m["nombre"]: m for m in provenance["modelos"]}
    sales = modelos_por_nombre["Random Forest (Ventas)"]
    assert sales["activo"] is True
    assert sales["algoritmo"] == "RandomForestRegressor"

    anomaly = modelos_por_nombre["Isolation Forest (Anomalías)"]
    assert anomaly["activo"] is False
    assert anomaly["algoritmo"] is None  # no se consulta meta de un modelo no cargado


def test_get_provenance_sin_carga_exitosa_devuelve_none():
    system_repo = MagicMock()
    system_repo.get_ultima_carga_dw.return_value = None
    model_loader = MagicMock()
    model_loader.keys.return_value = []

    service = SystemService(system_repo, model_loader)
    provenance = service.get_provenance()

    assert provenance["ultima_carga_dw"] is None
    assert provenance["modelos"] == []
