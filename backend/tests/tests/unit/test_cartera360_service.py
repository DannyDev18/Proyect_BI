# backend/tests/unit/test_cartera360_service.py
"""Cartera360Service.get_detalle_cliente probado con dependencias mockeadas (docs/
auditoria/34_actualizacion_modulo_ventas.md, H-V2): el `codven` del vendedor autenticado
siempre debe propagarse a PredictionService como restricción de cartera."""
from unittest.mock import MagicMock

from app.services.cartera360_service import Cartera360Service


def test_get_detalle_cliente_propaga_codven_como_restriccion():
    cartera360_repo = MagicMock()
    prediction_service = MagicMock()
    prediction_service.get_churn_risk.return_value = {"probabilidad_abandono": 0.0, "riesgo_alto": False}
    prediction_service.get_customer_segment.return_value = {"segmento": 1, "nombre_segmento": "VIP"}
    prediction_service.get_product_recommendations.return_value = {"recomendaciones": []}
    catalog_repo = MagicMock()
    service = Cartera360Service(cartera360_repo, prediction_service, catalog_repo)

    service.get_detalle_cliente("CLI-001", "V001")

    prediction_service.get_churn_risk.assert_called_once_with("CLI-001", "V001")
    prediction_service.get_customer_segment.assert_called_once_with("CLI-001", "V001")
    prediction_service.get_product_recommendations.assert_called_once_with("CLI-001", "V001")
