# backend/app/services/prediction_service.py
"""Orquestación de los 5 casos de uso de inferencia ML del dashboard. Cada método
sigue el mismo patrón: repository (datos) -> app/ml/preprocessing (features) ->
app/ml/inference (predicción) -> reglas de negocio de formateo del payload.

Reemplaza la versión anterior donde estas 4 responsabilidades vivían mezcladas en una
sola función por caso de uso, con un `predictor` global a nivel de módulo importado
desde el paquete `ml/` externo (fuera de `backend/`)."""
import datetime
import logging
from typing import Any

import pandas as pd

from app.core.config import settings
from app.core.exceptions import PermissionDeniedError
from app.ml import inference
from app.ml.model_loader import ModelLoader
from app.ml.preprocessing import build_preprocessing_pipeline, select_features_and_target
from app.repositories.catalog_repository import CatalogRepository
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.prediction_repository import PredictionRepository
from app.repositories.recommendation_event_repository import RecommendationEventRepository

logger = logging.getLogger("Backend.PredictionService")

# Fuentes del artefacto `association` cuyo `score` es un lift de asociación (>1 = afinidad
# real): CROSS_SELL_MIN_LIFT solo aplica a estas. Ver contrato recommendation.json v0.2.0
# ("score... NO es la misma escala matemática entre fuentes").
_FUENTES_ESCALA_LIFT = {"coocurrencia", "apriori", "asociacion"}


class PredictionService:
    def __init__(
        self,
        prediction_repo: PredictionRepository,
        dataset_repo: DatasetRepository,
        model_loader: ModelLoader,
        catalog_repo: CatalogRepository | None = None,
        recommendation_event_repo: RecommendationEventRepository | None = None,
    ):
        self.prediction_repo = prediction_repo
        self.dataset_repo = dataset_repo
        self.model_loader = model_loader
        self.catalog_repo = catalog_repo
        self.recommendation_event_repo = recommendation_event_repo
        # Fase 6 (docs/features/plan_refactor_venta_cruzada_ia.md §2.1 Opción A):
        # cache en memoria de la explicación SHAP por cliente -- shap.TreeExplainer
        # sobre 4 features es barato pero no gratis; el perfil de un cliente no cambia
        # dentro del ciclo de vida de un worker (recency/frequency/etc. solo cambian
        # con nuevas ventas). Se invalida solo al reiniciar el proceso -- suficiente
        # para el volumen de este módulo, sin infra de caché distribuida nueva.
        self._churn_explanation_cache: dict[str, list[dict[str, Any]]] = {}

    # ── Caso de uso: Predicción de demanda logística (Bodega) ─────────────────
    def get_demand_forecast(self, producto_cod: str) -> float:
        """Usada solo por el endpoint legado `/demand-forecasting` (H23-7, sin almacén
        en su contrato). El modelo `demand_rf` reentrenado en Fase 2
        (docs/features/plan_mejora_pipeline_ml.md §4.1) predice por combinación
        (producto, almacén) y requiere `almacen_sk`; sin un almacén conocido aquí, la
        serie agrega todos los almacenes y `inference.predict_demand` fallará al armar
        la matriz de features -- el `except` de abajo ya degrada con gracia a 0.0
        (comportamiento documentado en
        `ml/contracts/models/demand.json::known_serving_mismatch`, no un descuido). El
        camino con almacén conocido vive en `WarehouseService._forecast_ml_producto`."""
        df_hist = self.dataset_repo.get_product_sales_history(producto_cod)
        if df_hist.empty:
            return 0.0

        df_hist["ds"] = pd.to_datetime(df_hist["ds"])
        df_hist = df_hist.sort_values("ds").set_index("ds")
        df_hist = df_hist.resample("D").sum().fillna(0)

        pipeline = build_preprocessing_pipeline("y_quantity")
        next_day = df_hist.index[-1] + pd.Timedelta(days=1)
        df_hist.loc[next_day] = 0.0
        df_feat = pipeline.fit_transform(df_hist)

        X, _ = select_features_and_target(df_feat, "y_quantity")
        X_live = X.iloc[[-1]]
        try:
            preds = inference.predict_demand(self.model_loader, X_live)
            return float(preds.iloc[0])
        except Exception as e:
            # Degradar con gracia: un widget de demanda roto no debe tumbar el dashboard
            # de bodega completo. Se loguea en ERROR (visible), no queda mudo.
            logger.error(f"Fallo inferencia de demanda para producto_cod={producto_cod}: {e}")
            return 0.0

    def _verificar_pertenencia_cartera(self, cliente_id: str, codven_restriccion: str | None) -> None:
        """RLS de cartera (docs/auditoria/34_actualizacion_modulo_ventas.md, H-V2): si el
        llamador pasa `codven_restriccion` (rol `ventas`, sin override -- gerencia/admin
        pasan `None`), el cliente consultado debe pertenecer a la cartera de ESE
        vendedor. Antes `churn-risk`/`recommendations`/`clientes/{id}/segmento` no
        verificaban esto -- cualquier vendedor autenticado podía consultar cualquier
        cliente del sistema."""
        if codven_restriccion is None:
            return
        assert self.catalog_repo is not None
        if not self.catalog_repo.cliente_pertenece_a_vendedor(cliente_id, codven_restriccion):
            raise PermissionDeniedError(
                f"El cliente '{cliente_id}' no pertenece a la cartera del vendedor autenticado."
            )

    # ── Caso de uso: Riesgo de abandono (Churn) ───────────────────────────────
    def get_churn_risk(self, cliente_id: str, codven_restriccion: str | None = None) -> dict[str, Any]:
        self._verificar_pertenencia_cartera(cliente_id, codven_restriccion)
        features = self.prediction_repo.get_churn_features(cliente_id)
        if features is None:
            return {"probabilidad_abandono": 0.0, "riesgo_alto": False}

        df_live = pd.DataFrame([features._asdict()])
        try:
            preds = inference.predict_churn(self.model_loader, df_live)
            prob = float(preds["churn_probability"].iloc[0])
            return {"probabilidad_abandono": round(prob * 100, 2), "riesgo_alto": prob > settings.CHURN_UMBRAL_RIESGO_ALTO}
        except Exception as e:
            # H-03 cerrado en Fase 4: get_churn_features ahora produce las mismas 3
            # columnas/semántica que el contrato de entrenamiento (ml/contracts/models/churn.json).
            # Se sigue degradando con gracia ante cualquier otro fallo inesperado.
            logger.error(f"Fallo inferencia de churn para cliente_id={cliente_id}: {e}")
            return {"probabilidad_abandono": 0.0, "riesgo_alto": False}

    def get_churn_explanation(self, cliente_id: str, codven_restriccion: str | None = None) -> list[dict[str, Any]]:
        """Fase 6 (docs/features/plan_refactor_venta_cruzada_ia.md §2.1 Opción A):
        explicabilidad REAL de `churn_rf` -- SHAP TreeExplainer sobre las 4 features
        del contrato (recency/frequency/monetary_value/average_ticket). `churn_rf` es
        siempre un ensamble de árboles (RF/XGBoost/LightGBM/CatBoost, competencia de
        `model_selector.find_best_classification_model`), así que TreeExplainer aplica
        sin importar cuál ganó. Etiquetado "Explicación del modelo" en el frontend, NO
        "IA generativa" (R-3 del plan). Cacheado por cliente (ver `__init__`)."""
        self._verificar_pertenencia_cartera(cliente_id, codven_restriccion)
        if cliente_id in self._churn_explanation_cache:
            return self._churn_explanation_cache[cliente_id]

        features = self.prediction_repo.get_churn_features(cliente_id)
        if features is None:
            return []

        df_live = pd.DataFrame([features._asdict()])
        try:
            import shap

            X = inference._select_features(self.model_loader, 'churn_rf', df_live)
            model = self.model_loader.get('churn_rf')
            explainer = shap.TreeExplainer(model)
            shap_values = explainer(X).values
            # RandomForest/CatBoost devuelven (n_muestras, n_features, n_clases);
            # XGBoost/LightGBM ya devuelven (n_muestras, n_features) para la clase
            # positiva -- se normaliza a la contribución de la clase 1 (churn) en
            # ambos casos, no se asume un shape fijo entre los 4 algoritmos posibles.
            valores = shap_values[0, :, 1] if shap_values.ndim == 3 else shap_values[0]

            contribuciones = [
                {"feature": col, "valor": float(X[col].iloc[0]), "contribucion": float(valores[i])}
                for i, col in enumerate(X.columns)
            ]
            contribuciones.sort(key=lambda c: abs(c["contribucion"]), reverse=True)
        except Exception as e:
            logger.error(f"Fallo explicación SHAP de churn para cliente_id={cliente_id}: {e}")
            contribuciones = []

        self._churn_explanation_cache[cliente_id] = contribuciones
        return contribuciones

    def get_customer_segment_batch(self, cliente_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Mismo patrón de `get_churn_risk_batch` aplicado a segmentación RFM (auditoría
        41, Fase 2 del refactor Cartera 360: `get_ruta_hoy` enriquece hasta
        `CARTERA360_RUTA_TOP_N` clientes por request -- una consulta + una predicción
        vectorizada evita N round-trips)."""
        if not cliente_ids:
            return {}
        df_rfm = self.prediction_repo.get_rfm_features_batch(cliente_ids)
        if df_rfm.empty:
            return {cid: {"segmento": -1, "nombre_segmento": "Sin historial"} for cid in cliente_ids}
        try:
            X = df_rfm[["recency", "frequency", "monetary_value"]]
            clusters = inference.predict_segmentation(self.model_loader, X)
            cluster_to_segment = inference.get_cluster_to_segment(self.model_loader)
            resultado = {
                str(row["cliente_id"]): {
                    "segmento": int(clusters.iloc[i]),
                    "nombre_segmento": cluster_to_segment.get(str(int(clusters.iloc[i])), f"Segmento {int(clusters.iloc[i])}"),
                }
                for i, row in df_rfm.reset_index(drop=True).iterrows()
            }
        except Exception as e:
            logger.error(f"Fallo segmentación RFM en lote ({len(cliente_ids)} clientes): {e}")
            resultado = {}
        for cid in cliente_ids:
            resultado.setdefault(cid, {"segmento": -1, "nombre_segmento": "Sin historial"})
        return resultado

    def get_churn_explanation_batch(self, cliente_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        """Mismo patrón anti N+1 aplicado a la explicación SHAP (auditoría 41, Fase 2):
        una sola consulta de features + un solo `TreeExplainer(...)` vectorizado sobre
        las N filas, en vez de reconstruir el explainer y consultar la BD por cliente."""
        if not cliente_ids:
            return {}
        df_features = self.prediction_repo.get_churn_features_batch(cliente_ids)
        if df_features.empty:
            return {cid: [] for cid in cliente_ids}
        try:
            import shap

            X = df_features[["recency", "frequency", "monetary_value", "average_ticket"]]
            model = self.model_loader.get('churn_rf')
            explainer = shap.TreeExplainer(model)
            shap_values = explainer(X).values
            valores_clase1 = shap_values[:, :, 1] if shap_values.ndim == 3 else shap_values

            resultado: dict[str, list[dict[str, Any]]] = {}
            for i, row in df_features.reset_index(drop=True).iterrows():
                contribuciones = [
                    {"feature": col, "valor": float(X[col].iloc[i]), "contribucion": float(valores_clase1[i, j])}
                    for j, col in enumerate(X.columns)
                ]
                contribuciones.sort(key=lambda c: abs(c["contribucion"]), reverse=True)
                resultado[str(row["cliente_id"])] = contribuciones
        except Exception as e:
            logger.error(f"Fallo explicación SHAP en lote ({len(cliente_ids)} clientes): {e}")
            resultado = {}
        for cid in cliente_ids:
            resultado.setdefault(cid, [])
            self._churn_explanation_cache[cid] = resultado[cid]
        return resultado

    def get_churn_risk_batch(self, cliente_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Misma inferencia que `get_churn_risk`, pero para un lote de clientes con UNA
        sola consulta + UNA sola llamada vectorizada al modelo (en vez de N round-trips)
        -- usada por Cartera 360 para rerankear un conjunto acotado de candidatos con el
        churn real (auditoría 32 H1: nunca recorrer la cartera completa con inferencia
        por cliente)."""
        if not cliente_ids:
            return {}
        df_features = self.prediction_repo.get_churn_features_batch(cliente_ids)
        if df_features.empty:
            return {cid: {"probabilidad_abandono": 0.0, "riesgo_alto": False} for cid in cliente_ids}
        try:
            df_live = df_features[["recency", "frequency", "monetary_value", "average_ticket"]]
            preds = inference.predict_churn(self.model_loader, df_live)
            resultado = {
                str(row["cliente_id"]): {
                    "probabilidad_abandono": round(float(preds["churn_probability"].iloc[i]) * 100, 2),
                    "riesgo_alto": bool(preds["churn_probability"].iloc[i] > settings.CHURN_UMBRAL_RIESGO_ALTO),
                }
                for i, row in df_features.reset_index(drop=True).iterrows()
            }
        except Exception as e:
            logger.error(f"Fallo inferencia de churn en lote ({len(cliente_ids)} clientes): {e}")
            resultado = {}
        # Clientes sin historial suficiente (no aparecieron en df_features) degradan a 0%.
        for cid in cliente_ids:
            resultado.setdefault(cid, {"probabilidad_abandono": 0.0, "riesgo_alto": False})
        return resultado

    # ── Caso de uso: Recomendación de productos (Cross-selling) ───────────────
    def get_product_recommendations(self, cliente_id: str, codven_restriccion: str | None = None) -> dict[str, Any]:
        self._verificar_pertenencia_cartera(cliente_id, codven_restriccion)
        historial = self.prediction_repo.get_client_purchase_history(cliente_id)
        try:
            # H-10 cerrado en Fase 4: item_B ya es codart (no nombre_articulo). Contrato
            # v0.2.0 (docs/auditoria/25_...md): el ganador (item-item) expone `score`, no
            # `lift` -- ver inference.get_recommendations.
            recs_df = inference.get_recommendations(self.model_loader, historial.ultimos_items or None)
            recomendaciones = [
                {"producto_cod": str(row["item_B"]), "score": float(row["score"])}
                for _, row in recs_df.iterrows()
            ]
            return {"nombre_cliente": historial.nombre_cliente, "recomendaciones": recomendaciones}
        except Exception as e:
            logger.error(f"Fallo el motor de recomendaciones para cliente_id={cliente_id}: {e}")
            return {"nombre_cliente": historial.nombre_cliente, "recomendaciones": []}

    # ── Caso de uso: Asistente de Venta Cruzada por canasta (docs/auditoria/25_...md) ──
    def get_basket_recommendations(
        self, items: list[str], cliente_id: str | None = None, top_n: int | None = None,
    ) -> list[dict[str, Any]]:
        """RN-CS1: hasta `top_n` sugerencias enriquecidas con catálogo (nombre, precio,
        categoría), excluyendo la canasta y lo ya comprado por el cliente. Fallback por
        popularidad de categoría cuando ninguna regla del artefacto supera
        `CROSS_SELL_MIN_LIFT`. Degrada con gracia (lista vacía) ante cualquier fallo del
        modelo -- un widget roto no debe tumbar el asistente de venta."""
        top_n = top_n or settings.CROSS_SELL_TOP_N
        # Se pide un pool bastante más grande que top_n: no solo para reordenar por
        # margen, sino porque la diversificación por categoría (RN-CS3, abajo) necesita
        # suficientes candidatos de categorías distintas a la del producto en la canasta
        # -- con un pool chico, los vecinos item-item de mayor score tienden a
        # concentrarse en la misma categoría (hallazgo de uso real, auditoría 25 §6.1).
        pool_n = max(top_n * 6, 30)
        ya_comprados = []
        if cliente_id and self.catalog_repo:
            historial = self.prediction_repo.get_client_purchase_history(cliente_id, limit=50)
            ya_comprados = historial.ultimos_items

        try:
            recs_df = inference.get_basket_recommendations(
                self.model_loader, items, excluir=ya_comprados, top_n=pool_n,
            )
            # CROSS_SELL_MIN_LIFT solo tiene sentido para fuentes en escala de `lift`
            # (>1 = afinidad real); el ganador del backtest (item-item) expone similitud
            # coseno en [0,1] -- aplicarle el mismo umbral rechazaría TODAS las filas
            # siempre (docs/auditoria/25_modulo_cross_selling.md, bug encontrado en la
            # verificación end-to-end de esta fase). Otras fuentes de score no acotado
            # a [0,1] se sirven tal cual, ya limitadas a `top_n` por inference.
            candidatos = [
                (str(row["item_B"]), float(row["score"]), str(row.get("fuente") or "asociacion"))
                for _, row in recs_df.iterrows()
                if str(row.get("fuente")) not in _FUENTES_ESCALA_LIFT or float(row["score"]) >= settings.CROSS_SELL_MIN_LIFT
            ]
        except Exception as e:
            logger.error(f"Fallo el motor de recomendaciones por canasta para items={items}: {e}")
            candidatos = []

        if not candidatos and self.catalog_repo and items:
            # RN-CS1 fallback: producto más vendido de la categoría del último producto
            # de la canasta, excluyendo lo ya presente.
            info_ultimo = self.catalog_repo.get_products_info([items[-1]]).get(items[-1])
            if info_ultimo and info_ultimo["categoria"]:
                top_cod = self.catalog_repo.get_top_producto_categoria(info_ultimo["categoria"], items + ya_comprados)
                if top_cod:
                    candidatos = [(top_cod, 0.0, "popularidad_categoria")]

        if not candidatos or not self.catalog_repo:
            return []

        info_productos = self.catalog_repo.get_products_info([cod for cod, _, _ in candidatos])
        sugerencias = []
        for cod, score, fuente in candidatos:
            info = info_productos.get(cod)
            if not info:
                continue
            motivo = (
                "Popular en esta categoría" if fuente == "popularidad_categoria"
                else "Clientes con productos similares en su canasta también compraron este producto"
            )
            # RN-CS1: priorizar margen SOLO cuando es derivable (dim_producto.costo_promedio
            # no nulo, auditoría 25 H25-4) -- factor multiplicativo sobre el score nativo de
            # cada fuente (preserva el orden dentro de una misma fuente, no lo colapsa).
            margen_unitario = info.get("margen_unitario")
            factor_margen = 1.0
            if margen_unitario is not None and info["precio"] > 0:
                factor_margen = 1.0 + settings.CROSS_SELL_PESO_MARGEN * max(0.0, margen_unitario / info["precio"])
            sugerencias.append({
                "codart": cod, "nombre": info["nombre"], "precio": info["precio"],
                "categoria": info["categoria"], "score": score, "motivo": motivo, "fuente": fuente,
                "margen_unitario": margen_unitario,
                # Fase 5 (docs/features/plan_refactor_venta_cruzada_ia.md, explicabilidad
                # honesta de §2.1 para el caso sin ranker promovido -- ver auditoría 40):
                # el orden final es literalmente `score × factor_margen`, así que exponer
                # ambos sumandos por separado es la descomposición REAL del ranking, no
                # una aproximación. `factor_margen` nunca se pierde tras el sort.
                "factor_margen": round(factor_margen, 4),
                "_orden": score * factor_margen,
            })
        sugerencias.sort(key=lambda s: s.pop("_orden"), reverse=True)
        seleccion = self._diversificar_por_categoria(sugerencias, top_n)

        # RN-CS3 (inyección de diversidad entre categorías): algunos productos tienen
        # sus top-20 vecinos item-item TODOS en la misma categoría (p.ej. baterías --
        # hallazgo de uso real, auditoría 25 §6.1): el tope por categoría de arriba no
        # ayuda si no hay candidatos de OTRA categoría en el pool. Cuando la selección
        # queda concentrada en una sola categoría, se reemplazan hasta 2 de las
        # sugerencias de menor score por los mejores vendidos de OTRAS categorías --
        # así el vendedor siempre ve opciones para ampliar la venta más allá de
        # variantes del mismo producto.
        categorias_representadas = {s["categoria"] for s in seleccion}
        if len(categorias_representadas) <= 1 and self.catalog_repo and len(seleccion) > 1:
            ya_incluidos = list({*(s["codart"] for s in seleccion), *items, *ya_comprados})
            n_diversos = min(2, len(seleccion) - 1)
            diversos = self.catalog_repo.get_top_productos_diversos(
                list(categorias_representadas), ya_incluidos, n_diversos,
            )
            if diversos:
                info_diversos = self.catalog_repo.get_products_info([d["codart"] for d in diversos])
                nuevas = []
                for d in diversos:
                    info = info_diversos.get(d["codart"])
                    if not info:
                        continue
                    nuevas.append({
                        "codart": d["codart"], "nombre": info["nombre"], "precio": info["precio"],
                        "categoria": info["categoria"], "score": 0.0,
                        "motivo": "Producto popular de otra categoría — buena opción para ampliar la venta",
                        "fuente": "popularidad_otra_categoria",
                        "margen_unitario": info.get("margen_unitario"),
                        "factor_margen": 1.0,
                    })
                if nuevas:
                    seleccion = seleccion[: max(0, len(seleccion) - len(nuevas))] + nuevas

        return seleccion

    @staticmethod
    def _diversificar_por_categoria(sugerencias: list[dict[str, Any]], top_n: int) -> list[dict[str, Any]]:
        """RN-CS3: tope `CROSS_SELL_MAX_POR_CATEGORIA` de sugerencias por categoría entre
        las `top_n` finales -- sin esto, el asistente devolvía solo variantes de la
        categoría del producto en la canasta (hallazgo de uso real, auditoría 25 §6.1).
        Primera pasada: respeta el tope y el orden ya calculado (score x margen).
        Segunda pasada: si no alcanzaron `top_n` candidatos diversos, rellena con los
        sobrantes en orden -- prioriza diversidad sin dejar huecos vacíos."""
        seleccion: list[dict[str, Any]] = []
        sobrantes: list[dict[str, Any]] = []
        conteo_categoria: dict[str, int] = {}
        for s in sugerencias:
            cat = s["categoria"]
            if conteo_categoria.get(cat, 0) < settings.CROSS_SELL_MAX_POR_CATEGORIA:
                seleccion.append(s)
                conteo_categoria[cat] = conteo_categoria.get(cat, 0) + 1
            else:
                sobrantes.append(s)
            if len(seleccion) >= top_n:
                break
        if len(seleccion) < top_n:
            seleccion.extend(sobrantes[: top_n - len(seleccion)])
        return seleccion[:top_n]

    def log_recommendation_event(
        self,
        usuario_id: int,
        producto_origen_cod: str,
        producto_sugerido_cod: str,
        evento: str,
        score_lift: float | None = None,
        motivo: str | None = None,
        cliente_id: str | None = None,
    ) -> int | None:
        if not self.recommendation_event_repo:
            return None
        cliente_sk = None
        if cliente_id and self.catalog_repo:
            cliente_sk = self.catalog_repo.get_cliente_sk_vigente(cliente_id)
        event = self.recommendation_event_repo.log_event(
            usuario_id=usuario_id, producto_origen_cod=producto_origen_cod,
            producto_sugerido_cod=producto_sugerido_cod, evento=evento,
            score_lift=score_lift, motivo=motivo, cliente_sk=cliente_sk,
        )
        return event.id

    def get_top_combinaciones(self, limit: int | None = None) -> list[dict[str, Any]]:
        if not self.catalog_repo:
            return []
        limit = limit or settings.CROSS_SELL_TOP_COMBINACIONES_N
        return self.catalog_repo.get_top_combinaciones(limit=limit, dias=settings.CROSS_SELL_TOP_COMBINACIONES_DIAS)

    def get_conversion_kpis(self, desde=None, hasta=None) -> dict[str, Any]:
        if not self.recommendation_event_repo:
            return {"sugerencias_mostradas": 0, "sugerencias_aceptadas": 0, "sugerencias_rechazadas": 0, "tasa_conversion_pct": 0.0}
        return self.recommendation_event_repo.get_conversion_kpis(desde=desde, hasta=hasta)

    def search_productos(self, query: str) -> list[dict[str, Any]]:
        if not self.catalog_repo:
            return []
        return self.catalog_repo.search_productos(query)

    def search_clientes(self, query: str, codven_restriccion: str | None = None) -> list[dict[str, Any]]:
        if not self.catalog_repo:
            return []
        return self.catalog_repo.search_clientes(query, codven_restriccion=codven_restriccion)

    # ── Caso de uso: Segmentación RFM interactiva ─────────────────────────────
    def get_customer_segment(self, cliente_id: str, codven_restriccion: str | None = None) -> dict[str, Any]:
        self._verificar_pertenencia_cartera(cliente_id, codven_restriccion)
        features = self.prediction_repo.get_rfm_features(cliente_id)
        if features is None:
            return {"segmento": -1, "nombre_segmento": "Sin historial"}

        df_rfm = pd.DataFrame([features._asdict()])
        try:
            cluster_id = int(inference.predict_segmentation(self.model_loader, df_rfm).iloc[0])
            # H-12 cerrado en Fase 4: el mapeo cluster_id -> nombre de negocio se lee del
            # sidecar (persistido al entrenar, ordenado por centroides), no de un dict
            # hardcodeado que quedaba desalineado tras cada reentrenamiento.
            cluster_to_segment = inference.get_cluster_to_segment(self.model_loader)
            nombre = cluster_to_segment.get(str(cluster_id), f"Segmento {cluster_id}")
            return {"segmento": cluster_id, "nombre_segmento": nombre}
        except Exception as e:
            logger.error(f"Fallo segmentación RFM para cliente_id={cliente_id}: {e}")
            return {"segmento": -1, "nombre_segmento": "Error"}
