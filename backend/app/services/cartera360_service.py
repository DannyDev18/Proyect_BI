# backend/app/services/cartera360_service.py
"""Servicio del módulo Ventas — Cartera de Clientes 360 / "Mi Ruta Inteligente de
Ventas" (docs/features/propuesta_nuevos_modulos_roi.md §4, auditoría 32;
docs/features/plan_refactor_cartera360_ruta_inteligente.md). Compone los modelos ML
ya servidos (churn, RFM, cross-sell) SIN entrenar nada nuevo -- reutiliza
`PredictionService` tal cual, nunca duplica sus queries."""
import datetime
import calendar
from typing import Any

from app.core.config import settings
from app.repositories.catalog_repository import CatalogRepository
from app.repositories.cartera360_repository import Cartera360Repository
from app.services.prediction_service import PredictionService


def _estado_cartera(dias_sin_comprar: int) -> str:
    """Fase 4 §4.2 (docs/features/plan_correcciones_integrales_sistema.md): estado de
    cartera derivado de `dias_sin_comprar` real (recency), con umbrales configurables
    en `settings` -- nunca hardcodeado en el frontend."""
    if dias_sin_comprar <= settings.CARTERA360_DIAS_ACTIVO:
        return "activo"
    if dias_sin_comprar > settings.CARTERA360_DIAS_INACTIVO:
        return "inactivo"
    return "potencial"


def _dias_habiles_restantes_mes(hoy: datetime.date) -> int:
    """Cuenta lunes-viernes desde HOY (inclusive) hasta el fin de mes -- usado para
    prorratear la meta mensual en un objetivo diario (§4.1 del plan). Regla determinista
    documentada, no un supuesto: sábado/domingo no cuentan como día hábil comercial."""
    ultimo_dia = calendar.monthrange(hoy.year, hoy.month)[1]
    dias = 0
    for d in range(hoy.day, ultimo_dia + 1):
        if datetime.date(hoy.year, hoy.month, d).weekday() < 5:
            dias += 1
    return max(dias, 1)


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

    def _priorizar(self, codven: str) -> tuple[list[dict], list[dict]]:
        """Two-stage compartido (auditoría 32 H1): shortlist barata por valor histórico
        × alerta de caída de frecuencia, churn real SOLO para ese shortlist en un lote,
        rerank final. Devuelve (cartera_completa_sin_enriquecer, shortlist_reranked) --
        separado de `get_lista_trabajo` para que `get_ruta_hoy` (Fase 2) pueda usar el
        tamaño real de la cartera completa en las tarjetas del header sin una segunda
        consulta al EDW."""
        cartera = self.cartera360_repo.get_lista_trabajo(codven)
        if not cartera:
            return [], []

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
            cliente["riesgo_alto"] = churn["riesgo_alto"]
            cliente["prioridad"] = round(cliente["valor_historico"] * (1 + churn["probabilidad_abandono"] / 100), 2)
            del cliente["_score_shortlist"]

        reranked = sorted(shortlist, key=lambda c: c["prioridad"], reverse=True)
        return cartera, reranked

    def get_lista_trabajo(self, codven: str) -> list[dict]:
        """Lista de trabajo diaria priorizada por valor histórico × riesgo de fuga REAL
        del modelo `churn_rf`. Contrato sin cambios (consumido también por
        `NotificationService` -- R-2 del plan de refactor: cambios solo aditivos)."""
        _, reranked = self._priorizar(codven)
        pagina = reranked[: settings.VENTAS360_MAX_CARTERA]
        for cliente in pagina:
            cliente["estado_cartera"] = _estado_cartera(cliente["dias_sin_comprar"])
        return pagina

    def get_detalle_cliente(self, cliente_id: str, codven: str) -> dict:
        """Enriquecimiento bajo demanda (1 cliente, no un loop de cartera): churn real
        del modelo, segmento RFM y recomendaciones de venta cruzada — mismos 3 casos de
        uso que ya sirve `PredictionService` para el resto del dashboard de Ventas."""
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

    # ── "Mi Ruta Inteligente de Ventas" (Fase 2, motor de priorización) ───────────

    def _clasificar_alerta(self, cliente: dict, percentil_90_valor: float, segmento_nombre: str | None) -> dict:
        """6 clasificaciones deterministas (§4.4), evaluadas en orden de severidad: la
        primera regla que aplica gana (un cliente en riesgo crítico no se re-etiqueta
        como "oportunidad" aunque también tenga una recomendación activa)."""
        riesgo_alto = cliente["riesgo_alto"]
        valor = cliente["valor_historico"]
        dias_sin_comprar = cliente["dias_sin_comprar"]
        frecuencia = cliente["frecuencia_promedio_dias"]

        if riesgo_alto and valor >= percentil_90_valor:
            return {"codigo": "riesgo_critico", "etiqueta": "Riesgo crítico"}
        if riesgo_alto:
            return {"codigo": "riesgo_medio", "etiqueta": "Riesgo medio"}
        if segmento_nombre == "Campeones":
            return {"codigo": "premium", "etiqueta": "Premium"}
        if frecuencia and dias_sin_comprar < frecuencia:
            return {"codigo": "estable", "etiqueta": "Estable"}
        return {"codigo": "oportunidad", "etiqueta": "Oportunidad"}

    @staticmethod
    def _motivo_cliente(cliente: dict, shap_top2: list[dict]) -> str:
        """Motivo por plantilla determinista (§4.2, sin LLM -- DEC-5): combina la señal
        de frecuencia (real, ya calculada) con las 2 features SHAP de mayor contribución
        al riesgo de churn, cuando existen."""
        partes = []
        if cliente["frecuencia_promedio_dias"]:
            partes.append(
                f"Lleva {cliente['dias_sin_comprar']} días sin comprar "
                f"(su ciclo habitual es de {cliente['frecuencia_promedio_dias']:.0f} días)"
            )
        else:
            partes.append(f"Lleva {cliente['dias_sin_comprar']} días sin comprar")
        if shap_top2:
            factores = ", ".join(f["feature"] for f in shap_top2[:2])
            partes.append(f"señales de riesgo del modelo: {factores}")
        return "; ".join(partes) + "."

    def get_ruta_hoy(self, codven: str) -> dict[str, Any]:
        """Motor de priorización de Fase 2 (§4.2, §4.3): reutiliza el two-stage
        existente para la cartera completa, y enriquece SOLO el top
        `CARTERA360_RUTA_TOP_N` (oferta real, motivo con SHAP, clasificación de alerta)
        -- evita N+1 de inferencia/recomendación sobre los hasta 300 candidatos del
        shortlist (decisión de rendimiento de la Fase 2, ver docs/auditoria/
        41_refactor_cartera360.md).

        Rotación de la ruta (hallazgo post-Fase 3): `valor_historico`/`probabilidad_
        abandono` no cambian de un día para otro solo porque el vendedor ya gestionó al
        cliente -- sin excluir explícitamente a los ya atendidos, el ranking devolvería
        los MISMOS `CARTERA360_RUTA_TOP_N` clientes todos los días, sin que la cartera
        completa reciba cobertura real. Antes de tomar el top N final se descarta, del
        pool de `CARTERA360_RUTA_POOL_FILTRADO` candidatos ya rerankeados:
        (a) cualquier cliente con una gestión registrada HOY (cualquier resultado -- ya
            se actuó sobre él, reaparece mañana si el riesgo/valor lo siguen justificando)
        (b) cualquier cliente con `proxima_accion_fecha` en el FUTURO (el vendedor ya
            prometió un seguimiento en una fecha concreta -- no debe competir por un cupo
            de hoy; una fecha vencida u hoy mismo SÍ sigue elegible, es una acción debida)."""
        cartera_completa, reranked = self._priorizar(codven)

        hoy = datetime.date.today()
        hoy_iso = hoy.isoformat()
        pool = reranked[: settings.CARTERA360_RUTA_POOL_FILTRADO]
        ultimas_gestiones = self.cartera360_repo.get_ultima_gestion_por_cliente_ids(
            [c["cliente_id"] for c in pool]
        )

        def _elegible_hoy(cliente_id: str) -> bool:
            g = ultimas_gestiones.get(cliente_id)
            if not g:
                return True
            if g["fecha"] and g["fecha"][:10] == hoy_iso:
                return False
            if g["proxima_accion_fecha"] and g["proxima_accion_fecha"] > hoy_iso:
                return False
            return True

        top_n = [c for c in pool if _elegible_hoy(c["cliente_id"])][: settings.CARTERA360_RUTA_TOP_N]

        valores = sorted(c["valor_historico"] for c in reranked) if reranked else []
        percentil_90_valor = valores[int(len(valores) * 0.9)] if valores else 0.0

        # Auditoría 41 (Fase 2, hallazgo de latencia): segmentación RFM y explicación
        # SHAP se piden en LOTE para el top_n (mismo patrón que el churn batch del
        # two-stage) -- evita reconstruir el TreeExplainer y consultar RFM por cliente.
        top_n_ids = [c["cliente_id"] for c in top_n]
        segmentos = self.prediction_service.get_customer_segment_batch(top_n_ids)
        shap_por_cliente = self.prediction_service.get_churn_explanation_batch(top_n_ids)

        clientes_ruta: list[dict[str, Any]] = []
        oportunidades_activas = 0
        valor_potencial_ruta = 0.0

        for cliente in top_n:
            segmento = segmentos.get(cliente["cliente_id"], {"segmento": -1, "nombre_segmento": "Sin historial"})
            shap = shap_por_cliente.get(cliente["cliente_id"], [])
            clasificacion = self._clasificar_alerta(cliente, percentil_90_valor, segmento["nombre_segmento"])

            oferta = None
            recomendaciones = self.prediction_service.get_product_recommendations(cliente["cliente_id"], codven)
            top_reco = recomendaciones.get("recomendaciones") or []
            if top_reco:
                codart = top_reco[0]["producto_cod"]
                info = self.catalog_repo.get_products_info([codart]).get(codart)
                if info:
                    oferta = {
                        "codart": codart, "nombre": info["nombre"], "precio": info["precio"],
                        "motivo": "Recomendado por afinidad de compra (modelo de venta cruzada)",
                    }
                    oportunidades_activas += 1

            perfil = self.cartera360_repo.get_perfil_cliente(cliente["cliente_id"])
            ticket_promedio = perfil["ticket_promedio"] if perfil else 0.0
            valor_potencial_ruta += ticket_promedio or 0.0

            tiempo_restante = None
            if cliente["frecuencia_promedio_dias"]:
                tiempo_restante = round(cliente["frecuencia_promedio_dias"] - cliente["dias_sin_comprar"], 1)

            ultima_gestion = ultimas_gestiones.get(cliente["cliente_id"])

            clientes_ruta.append({
                "cliente_id": cliente["cliente_id"],
                "nombre_cliente": cliente["nombre_cliente"],
                "prioridad": cliente["prioridad"],
                "score_desglose": {
                    "valor_historico": cliente["valor_historico"],
                    "probabilidad_abandono": cliente["probabilidad_abandono"],
                },
                "probabilidad_recompra": round(100 - cliente["probabilidad_abandono"], 2),
                "dias_sin_comprar": cliente["dias_sin_comprar"],
                "frecuencia_promedio_dias": cliente["frecuencia_promedio_dias"],
                "tiempo_restante_dias": tiempo_restante,
                "valor_historico": cliente["valor_historico"],
                "motivo": self._motivo_cliente(cliente, shap),
                "clasificacion": clasificacion,
                "oferta_sugerida": oferta,
                "ultima_gestion_evento": ultima_gestion["evento"] if ultima_gestion else None,
                "ultima_gestion_fecha": ultima_gestion["fecha"] if ultima_gestion else None,
                "proxima_accion_fecha": ultima_gestion["proxima_accion_fecha"] if ultima_gestion else None,
            })

        clientes_con_alerta = sum(1 for c in reranked if c["riesgo_alto"])
        ingreso_potencial_en_riesgo = round(
            sum(c["valor_historico"] * c["probabilidad_abandono"] / 100 for c in reranked), 2
        )
        clientes_recuperados_mes = self._contar_recuperados_mes(codven)

        anio, mes = hoy.year, hoy.month
        meta_mensual = self.cartera360_repo.get_meta_mensual_vendedor(codven, anio, mes)
        objetivo_diario = round(meta_mensual / _dias_habiles_restantes_mes(hoy), 2) if meta_mensual else None
        ventas_dia = self.cartera360_repo.get_ventas_dia(codven, hoy)

        tarjetas = {
            "clientes_asignados": len(cartera_completa),
            "clientes_con_alerta": clientes_con_alerta,
            "clientes_recuperados_mes": clientes_recuperados_mes,
            "ingreso_potencial_en_riesgo": ingreso_potencial_en_riesgo,
            "oportunidades_activas": oportunidades_activas,
            "valor_potencial_ruta_hoy": round(valor_potencial_ruta, 2),
            "objetivo_diario": objetivo_diario,
            "avance_dia": round(ventas_dia, 2),
        }
        return {"tarjetas": tarjetas, "clientes": clientes_ruta}

    def _contar_recuperados_mes(self, codven: str) -> int:
        """Clientes de ESTE vendedor con evento `recompro` en el mes en curso (§4.1) --
        valor real = 0 en el arranque (D-1), sube con el uso del módulo."""
        return self.cartera360_repo.get_recuperados_mes_actual_por_vendedor(codven)
