# backend/app/services/prediction_service.py
"""Orquestación de los 6 casos de uso de inferencia ML del dashboard. Cada método
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
from app.core.exceptions import ExternalDataError, PermissionDeniedError
from app.ml import inference
from app.ml.forecasting import walk_forward_forecast
from app.ml.model_loader import ModelLoader
from app.ml.preprocessing import build_preprocessing_pipeline, select_features_and_target
from app.repositories.catalog_repository import CatalogRepository
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.prediction_repository import PredictionRepository
from app.repositories.recommendation_event_repository import RecommendationEventRepository

logger = logging.getLogger("Backend.PredictionService")

# Horizonte diario interno del walk-forward (el modelo sigue siendo diario -- ver
# docs/auditoria/21_mejora_features_ventas_y_granularidad.md): se genera un forecast diario
# más largo y se bucketiza a semana/mes en el servicio, sin entrenar modelos nuevos por
# granularidad. "semana" = 12 semanas (~84 días); "mes" = 6 meses (~180 días).
DIAS_A_PROYECTAR_POR_GRANULARIDAD = {"semana": 84, "mes": 180}
DIAS_VISUALIZACION_HISTORIAL_POR_GRANULARIDAD = {"semana": 26 * 7, "mes": 24 * 31}

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

    # ── Caso de uso: Predicción de ventas (Gerencia) ───────────────────────────
    def get_sales_forecast(
        self,
        sucursal: str | None = None,
        vendedor: str | None = None,
        almacen: str | None = None,
        granularidad: str = "semana",
    ) -> dict[str, Any]:
        if granularidad not in DIAS_A_PROYECTAR_POR_GRANULARIDAD:
            granularidad = "semana"
        dias_a_proyectar = DIAS_A_PROYECTAR_POR_GRANULARIDAD[granularidad]
        dias_visualizacion = DIAS_VISUALIZACION_HISTORIAL_POR_GRANULARIDAD[granularidad]

        try:
            df_hist_raw = self.dataset_repo.get_daily_sales_history(
                sucursal=sucursal, vendedor=vendedor, almacen=almacen,
            )
        except Exception as e:
            logger.error(f"Fallo consultando historial de ventas: {e}")
            raise ExternalDataError("No se pudo consultar el historial de ventas del EDW.") from e

        if df_hist_raw.empty:
            return {
                "granularidad": granularidad, "periodos_proyectados": 0,
                "historial_y_prediccion": [], "metricas": {}, "insights": ["Sin historial de ventas"],
            }

        df_hist_raw["ds"] = pd.to_datetime(df_hist_raw["ds"])
        df_hist_raw = df_hist_raw.sort_values("ds").set_index("ds")
        df_hist_raw = df_hist_raw.resample("D").sum().fillna(0)

        try:
            # El modelo sigue siendo diario (walk_forward_forecast sin cambios); la
            # granularidad solo controla cuántos días diarios se generan y cómo se
            # bucketizan para el dashboard (docs/auditoria/21_...md).
            generated_preds = walk_forward_forecast(
                self.model_loader, df_hist_raw, "y_sales_net", dias_a_proyectar, inference.predict_sales,
            )

            meta_sales = self.model_loader.get_meta("sales_rf")
            mae_real = meta_sales.get("metrics", {}).get("MAE")
            resultado = self._build_forecast_series(df_hist_raw, generated_preds, mae_real, granularidad, dias_visualizacion)
            metricas = self._build_forecast_metrics(df_hist_raw, generated_preds, meta_sales, dias_a_proyectar)
            insights = self._build_forecast_insights(metricas, granularidad)
        except Exception as e:
            # Igual que en los demás casos de uso: un fallo del modelo no debe tumbar el
            # dashboard gerencial completo. Se loguea en ERROR, no queda mudo.
            logger.error(f"Fallo la inferencia de ventas para sucursal={sucursal}, vendedor={vendedor}, almacen={almacen}: {e}")
            return {
                "granularidad": granularidad, "periodos_proyectados": 0,
                "historial_y_prediccion": [], "metricas": {}, "insights": ["No se pudo generar la predicción de ventas."],
            }

        return {
            "granularidad": granularidad,
            "periodos_proyectados": self._contar_periodos(generated_preds, granularidad),
            "historial_y_prediccion": resultado,
            "metricas": metricas,
            "insights": insights,
        }

    @staticmethod
    def _bucket_freq(granularidad: str) -> tuple[str, dict]:
        if granularidad == "mes":
            return "MS", {}
        return "W-MON", {"label": "left", "closed": "left"}

    @classmethod
    def _contar_periodos(cls, generated_preds: list[tuple], granularidad: str) -> int:
        if not generated_preds:
            return 0
        freq, kwargs = cls._bucket_freq(granularidad)
        serie = pd.Series({d: v for d, v in generated_preds}).sort_index()
        return int(serie.resample(freq, **kwargs).sum().shape[0])

    @classmethod
    def _build_forecast_series(
        cls,
        df_hist_raw: pd.DataFrame,
        generated_preds: list[tuple],
        mae: float | None,
        granularidad: str,
        dias_visualizacion: int,
    ) -> list[dict]:
        # H-09 (docs/auditoria/11_auditoria_tecnica_modelos_ml.md): el intervalo ya no es
        # un +-15% fijo fabricado -- se usa el MAE real (diario) del holdout de
        # entrenamiento (sidecar sales.meta.json), escalado por bucket con
        # mae_diario * sqrt(dias_en_bucket) (errores diarios ~independientes; misma
        # aproximación explícita que el resto del módulo, ver docs/auditoria/21_...md).
        freq, kwargs = cls._bucket_freq(granularidad)

        serie_real = df_hist_raw["y_sales_net"].tail(dias_visualizacion)
        bucket_real = serie_real.resample(freq, **kwargs).sum() if not serie_real.empty else pd.Series(dtype=float)

        if generated_preds:
            serie_pred = pd.Series({d: v for d, v in generated_preds}).sort_index()
            bucket_pred = serie_pred.resample(freq, **kwargs).sum()
            dias_por_bucket = serie_pred.resample(freq, **kwargs).count()
        else:
            bucket_pred = pd.Series(dtype=float)
            dias_por_bucket = pd.Series(dtype=float)

        todas_fechas = sorted(set(bucket_real.index) | set(bucket_pred.index))

        resultado = []
        for fecha_bucket in todas_fechas:
            monto_real = float(bucket_real[fecha_bucket]) if fecha_bucket in bucket_real.index else None
            tiene_pred = fecha_bucket in bucket_pred.index
            if tiene_pred:
                val = float(bucket_pred[fecha_bucket])
                n_dias = int(dias_por_bucket[fecha_bucket])
                margen = (mae * (n_dias ** 0.5)) if mae is not None else val * 0.15
                monto_predicho = round(val, 2)
                intervalo_superior = round(val + margen, 2)
                intervalo_inferior = round(max(0.0, val - margen), 2)
            else:
                monto_predicho = None
                intervalo_superior = None
                intervalo_inferior = None
            resultado.append({
                "fecha": fecha_bucket.strftime("%Y-%m-%d"),
                "monto_real": round(monto_real, 2) if monto_real is not None else None,
                "monto_predicho": monto_predicho,
                "intervalo_superior": intervalo_superior,
                "intervalo_inferior": intervalo_inferior,
            })

        # Pivote: el último bucket real también lleva monto_predicho para que la línea de
        # predicción no tenga un salto (gap) visual, si ese bucket no coincide con el primero
        # de la predicción (bucketing por semana/mes puede unirlos, ver docs/auditoria/21_...md).
        ultimo_real_idx = next((i for i in range(len(resultado) - 1, -1, -1) if resultado[i]["monto_real"] is not None), None)
        if ultimo_real_idx is not None and resultado[ultimo_real_idx]["monto_predicho"] is None:
            resultado[ultimo_real_idx]["monto_predicho"] = resultado[ultimo_real_idx]["monto_real"]

        return resultado

    def _build_forecast_metrics(
        self, df_hist_raw: pd.DataFrame, generated_preds: list[tuple], meta_sales: dict, dias_a_proyectar: int,
    ) -> dict:
        total_historico = float(df_hist_raw["y_sales_net"].sum())
        ventas_futuras = sum(v for _, v in generated_preds)

        if len(df_hist_raw) >= dias_a_proyectar:
            ventas_pasadas = float(df_hist_raw["y_sales_net"].tail(dias_a_proyectar).sum())
        else:
            ventas_pasadas = 1.0
        crecimiento_esperado = ((ventas_futuras / ventas_pasadas) - 1.0) * 100 if ventas_pasadas > 0 else 0.0

        df_mensual = df_hist_raw.resample("ME").sum()
        try:
            import locale
            locale.setlocale(locale.LC_TIME, "es_ES.UTF-8")
        except Exception:
            pass
        mejor_mes = df_mensual["y_sales_net"].idxmax().strftime("%B %Y").title() if not df_mensual.empty else ""
        peor_mes = df_mensual["y_sales_net"].idxmin().strftime("%B %Y").title() if not df_mensual.empty else ""

        # H-09 (cerrado): mae_modelo/r2_modelo vienen del holdout real de entrenamiento
        # (sales.meta.json), no de valores fabricados. nivel_confianza es un PROXY
        # basado en R2 (no un intervalo de confianza estadístico estricto) -- se declara
        # así explícitamente en vez de presentar un 95% fijo sin respaldo.
        metrics_entrenamiento = meta_sales.get("metrics", {})
        mae_modelo = metrics_entrenamiento.get("MAE")
        r2_modelo = metrics_entrenamiento.get("R2")
        nivel_confianza = round(max(0.0, min(r2_modelo, 1.0)) * 100, 1) if r2_modelo is not None else None

        return {
            "ventas_acumuladas": round(total_historico, 2),
            "venta_esperada": round(ventas_futuras, 2),
            "crecimiento_esperado": round(crecimiento_esperado, 2),
            "mes_mayor_venta": mejor_mes,
            "mes_menor_venta": peor_mes,
            "promedio_mensual": round(float(df_mensual["y_sales_net"].mean()) if not df_mensual.empty else 0.0, 2),
            "mae_modelo": round(mae_modelo, 2) if mae_modelo is not None else None,
            "r2_modelo": round(r2_modelo, 4) if r2_modelo is not None else None,
            "nivel_confianza": nivel_confianza,
            "fecha_entrenamiento": self.model_loader.get_training_date("sales_rf"),
            # H-21-1 (docs/auditoria/21_...md): antes el frontend hardcodeaba "Gradient
            # Boosting" -- se expone el algoritmo real ganador de la competencia (sidecar).
            "algoritmo": meta_sales.get("algorithm", "Desconocido"),
        }

    @staticmethod
    def _build_forecast_insights(metricas: dict, granularidad: str) -> list[str]:
        unidad_plural = "semanas" if granularidad == "semana" else "meses"
        unidad_prev = "la semana anterior" if granularidad == "semana" else "el mes anterior"
        crecimiento = metricas.get("crecimiento_esperado", 0.0)
        insights = []
        if crecimiento > 6:
            insights.append(f"El modelo estima un crecimiento positivo del {crecimiento:.1f}% para el próximo horizonte.")
        elif crecimiento < -6:
            insights.append(f"Se detecta una tendencia a la baja del {abs(crecimiento):.1f}% respecto a {unidad_prev}.")
        else:
            insights.append("Las predicciones sugieren estabilidad lateral sin saltos bruscos en el horizonte.")
        if metricas.get("mes_mayor_venta"):
            insights.append(f"Históricamente el negocio ha dependido fuerte de estacionalidades; el top del periodo es {metricas['mes_mayor_venta']}.")
        mae = metricas.get("mae_modelo")
        if mae is not None:
            insights.append(f"El intervalo mostrado usa el error absoluto medio diario real del modelo (+-${mae:,.0f}/día), agregado por {unidad_plural[:-1] if granularidad == 'semana' else 'mes'} sobre el horizonte mostrado.")
        return insights

    # ── Caso de uso: Predicción de demanda logística (Bodega) ─────────────────
    def get_demand_forecast(self, producto_cod: str) -> float:
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
            df_live = df_features[["frequency", "monetary_value", "average_ticket"]]
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

    # ── Caso de uso: Detección de anomalías transaccionales (Admin) ───────────
    def get_anomaly_status(self, transaccion_id: str) -> dict[str, Any]:
        features = self.prediction_repo.get_transaction_features(transaccion_id)
        if features is None:
            return {"score": 0.0, "es_anomalia": False}

        df_live = pd.DataFrame([features._asdict()])
        try:
            # H-04 cerrado en Fase 4: score real de decision_function(), ya no un valor
            # hardcodeado (-0.85/0.15).
            result = inference.detect_anomalies(self.model_loader, df_live)
            is_anom = int(result["is_anomaly_pred"].iloc[0]) == -1
            score = float(result["anomaly_score"].iloc[0])
            return {"score": round(score, 4), "es_anomalia": is_anom}
        except Exception as e:
            logger.error(f"Fallo detección de anomalías para transaccion_id={transaccion_id}: {e}")
            return {"score": 0.0, "es_anomalia": False}

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

    def search_clientes(self, query: str) -> list[dict[str, Any]]:
        if not self.catalog_repo:
            return []
        return self.catalog_repo.search_clientes(query)

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
