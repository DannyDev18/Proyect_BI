# backend/app/services/cartera360_service.py
"""Servicio del módulo Ventas — Cartera de Clientes 360
(docs/features/propuesta_nuevos_modulos_roi.md §4, auditoría 32). Compone los 3 modelos
ML ya servidos (churn, RFM, cross-sell) SIN entrenar nada nuevo -- reutiliza
`PredictionService` tal cual, nunca duplica sus queries."""
from app.core.config import settings
from app.repositories.catalog_repository import CatalogRepository
from app.repositories.cartera360_repository import Cartera360Repository
from app.services.prediction_service import PredictionService


class Cartera360Service:
    def __init__(
        self,
        cartera360_repo: Cartera360Repository,
        prediction_service: PredictionService,
        catalog_repo: CatalogRepository,
    ):
        self.cartera360_repo = cartera360_repo
        self.prediction_service = prediction_service
        self.catalog_repo = catalog_repo

    def get_lista_trabajo(self, codven: str) -> list[dict]:
        """Lista de trabajo diaria priorizada por valor histórico × riesgo de fuga REAL
        del modelo `churn_rf` (mejora de verificación 2026-07-14 -- la versión original
        solo usaba una señal estadística binaria de caída de frecuencia, sin el modelo).

        Two-stage (auditoría 32 H1: la cartera puede tener hasta ~31,000 clientes, no se
        puede correr el modelo sobre todos):
        1. Shortlist barata (SQL, sin ML) de hasta `VENTAS360_CANDIDATOS_ENRIQUECER`
           candidatos por valor histórico × alerta de caída de frecuencia.
        2. Churn real SOLO para ese shortlist, en UN lote (`get_churn_risk_batch`, una
           consulta + una inferencia vectorizada, no N round-trips).
        3. Rerank final = valor_histórico × (1 + probabilidad_abandono_real), truncado a
           `VENTAS360_MAX_CARTERA`. Todo cliente devuelto ya trae su churn real -- no hace
           falta abrir el detalle para saber el riesgo, solo para segmento/recomendaciones.
        """
        cartera = self.cartera360_repo.get_lista_trabajo(codven)
        if not cartera:
            return []

        for cliente in cartera:
            factor_shortlist = 2.0 if cliente["alerta_caida_frecuencia"] else 1.0
            cliente["_score_shortlist"] = cliente["valor_historico"] * factor_shortlist

        shortlist = sorted(cartera, key=lambda c: c["_score_shortlist"], reverse=True)[
            : settings.VENTAS360_CANDIDATOS_ENRIQUECER
        ]
        churn_map = self.prediction_service.get_churn_risk_batch([c["cliente_id"] for c in shortlist])

        for cliente in shortlist:
            churn = churn_map.get(cliente["cliente_id"], {"probabilidad_abandono": 0.0, "riesgo_alto": False})
            cliente["probabilidad_abandono"] = churn["probabilidad_abandono"]
            cliente["prioridad"] = round(cliente["valor_historico"] * (1 + churn["probabilidad_abandono"] / 100), 2)
            del cliente["_score_shortlist"]

        return sorted(shortlist, key=lambda c: c["prioridad"], reverse=True)[: settings.VENTAS360_MAX_CARTERA]

    def get_detalle_cliente(self, cliente_id: str, codven: str) -> dict:
        """Enriquecimiento bajo demanda (1 cliente, no un loop de cartera): churn real
        del modelo, segmento RFM y recomendaciones de venta cruzada — mismos 3 casos de
        uso que ya sirve `PredictionService` para el resto del dashboard de Ventas.

        `codven` siempre se pasa como restricción (docs/auditoria/
        34_actualizacion_modulo_ventas.md, H-V2): este módulo es self-scope por diseño
        (RN-V3, sin override para gerencia/administrador) -- antes el docstring del
        router afirmaba esa restricción pero `get_detalle_cliente` no la aplicaba,
        permitiendo consultar el detalle de un cliente fuera de la cartera propia."""
        churn = self.prediction_service.get_churn_risk(cliente_id, codven)
        segmento = self.prediction_service.get_customer_segment(cliente_id, codven)
        recomendaciones = self.prediction_service.get_product_recommendations(cliente_id, codven)
        return {
            "cliente_id": cliente_id,
            "probabilidad_abandono": churn["probabilidad_abandono"],
            "riesgo_alto": churn["riesgo_alto"],
            "segmento": segmento["segmento"],
            "nombre_segmento": segmento["nombre_segmento"],
            "productos_recomendados": recomendaciones["recomendaciones"],
        }

    def registrar_gestion(self, usuario_id: int, cliente_id: str, evento: str, motivo: str | None) -> int:
        cliente_sk = self.catalog_repo.get_cliente_sk_vigente(cliente_id)
        registro = self.cartera360_repo.log_gestion(usuario_id, cliente_sk, evento, motivo)
        return registro.id

    def get_tasa_recuperacion(self, usuario_id: int | None = None) -> dict:
        return self.cartera360_repo.get_tasa_recuperacion(usuario_id)
