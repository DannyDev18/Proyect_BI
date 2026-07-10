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

from app.core.exceptions import ExternalDataError
from app.ml import inference
from app.ml.forecasting import walk_forward_forecast
from app.ml.model_loader import ModelLoader
from app.ml.preprocessing import build_preprocessing_pipeline, select_features_and_target
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.prediction_repository import PredictionRepository

logger = logging.getLogger("Backend.PredictionService")

DIAS_A_PROYECTAR_VENTAS = 14
DIAS_VISUALIZACION_HISTORIAL = 90


class PredictionService:
    def __init__(
        self,
        prediction_repo: PredictionRepository,
        dataset_repo: DatasetRepository,
        model_loader: ModelLoader,
    ):
        self.prediction_repo = prediction_repo
        self.dataset_repo = dataset_repo
        self.model_loader = model_loader

    # ── Caso de uso: Predicción de ventas semanal (Gerencia) ──────────────────
    def get_sales_forecast_weekly(self, sucursal: str | None = None) -> dict[str, Any]:
        try:
            df_hist_raw = self.dataset_repo.get_daily_sales_history(sucursal=sucursal)
        except Exception as e:
            logger.error(f"Fallo consultando historial de ventas: {e}")
            raise ExternalDataError("No se pudo consultar el historial de ventas del EDW.") from e

        if df_hist_raw.empty:
            return {"dias_proyectados": 0, "historial_y_prediccion": [], "metricas": {}, "insights": ["Sin historial de ventas"]}

        df_hist_raw["ds"] = pd.to_datetime(df_hist_raw["ds"])
        df_hist_raw = df_hist_raw.sort_values("ds").set_index("ds")
        df_hist_raw = df_hist_raw.resample("D").sum().fillna(0)

        try:
            generated_preds = walk_forward_forecast(
                self.model_loader, df_hist_raw, "y_sales_net", DIAS_A_PROYECTAR_VENTAS, inference.predict_sales,
            )

            mae_real = self.model_loader.get_meta("sales_rf").get("metrics", {}).get("MAE")
            resultado = self._build_forecast_series(df_hist_raw, generated_preds, mae_real)
            metricas = self._build_forecast_metrics(df_hist_raw, generated_preds)
            insights = self._build_forecast_insights(metricas)
        except Exception as e:
            # Igual que en los demás casos de uso: un fallo del modelo no debe tumbar el
            # dashboard gerencial completo. Se loguea en ERROR, no queda mudo.
            logger.error(f"Fallo la inferencia de ventas para sucursal={sucursal}: {e}")
            return {"dias_proyectados": 0, "historial_y_prediccion": [], "metricas": {}, "insights": ["No se pudo generar la predicción de ventas."]}

        return {
            "dias_proyectados": DIAS_A_PROYECTAR_VENTAS,
            "historial_y_prediccion": resultado,
            "metricas": metricas,
            "insights": insights,
        }

    @staticmethod
    def _build_forecast_series(df_hist_raw: pd.DataFrame, generated_preds: list[tuple], mae: float | None = None) -> list[dict]:
        # H-09 (docs/auditoria/11_auditoria_tecnica_modelos_ml.md): el intervalo ya no es
        # un +-15% fijo fabricado -- se usa el MAE real del holdout de entrenamiento
        # (sidecar sales.meta.json). Si no hay MAE disponible (modelo no cargado), se
        # cae al +-15% como aproximación explícita, no silenciosa.
        margen = mae if mae is not None else None
        resultado = []
        # Solo se envían al dashboard los últimos N días de historial (el modelo usa
        # hasta 730 días para entrenar/predecir, pero graficar todo sería ilegible).
        df_visual = df_hist_raw.tail(DIAS_VISUALIZACION_HISTORIAL)
        for date_idx, row in df_visual.iterrows():
            resultado.append({
                "fecha": date_idx.strftime("%Y-%m-%d"),
                "monto_real": round(float(row["y_sales_net"]), 2),
                "monto_predicho": None,
                "intervalo_superior": None,
                "intervalo_inferior": None,
            })
        if resultado:
            # Pivote: el último día real también lleva monto_predicho para que la
            # línea de predicción del gráfico no tenga un salto (gap) visual.
            resultado[-1]["monto_predicho"] = resultado[-1]["monto_real"]

        for p_date, val in generated_preds:
            if margen is not None:
                intervalo_superior = val + margen
                intervalo_inferior = max(0.0, val - margen)
            else:
                intervalo_superior = val * 1.15
                intervalo_inferior = val * 0.85
            resultado.append({
                "fecha": p_date.strftime("%Y-%m-%d"),
                "monto_real": None,
                "monto_predicho": round(val, 2),
                "intervalo_superior": round(intervalo_superior, 2),
                "intervalo_inferior": round(intervalo_inferior, 2),
            })
        return resultado

    def _build_forecast_metrics(self, df_hist_raw: pd.DataFrame, generated_preds: list[tuple]) -> dict:
        total_historico = float(df_hist_raw["y_sales_net"].sum())
        ventas_futuras = sum(v for _, v in generated_preds)

        if len(df_hist_raw) >= DIAS_A_PROYECTAR_VENTAS:
            ventas_pasadas = float(df_hist_raw["y_sales_net"].tail(DIAS_A_PROYECTAR_VENTAS).sum())
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
        metrics_entrenamiento = self.model_loader.get_meta("sales_rf").get("metrics", {})
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
        }

    @staticmethod
    def _build_forecast_insights(metricas: dict) -> list[str]:
        crecimiento = metricas.get("crecimiento_esperado", 0.0)
        insights = []
        if crecimiento > 6:
            insights.append(f"El modelo estima un crecimiento positivo del {crecimiento:.1f}% para el próximo horizonte.")
        elif crecimiento < -6:
            insights.append(f"Se detecta una tendencia a la baja del {abs(crecimiento):.1f}% respecto a la quincena anterior.")
        else:
            insights.append("Las predicciones sugieren estabilidad lateral sin saltos bruscos en el horizonte.")
        if metricas.get("mes_mayor_venta"):
            insights.append(f"Históricamente el negocio ha dependido fuerte de estacionalidades; el top del periodo es {metricas['mes_mayor_venta']}.")
        mae = metricas.get("mae_modelo")
        if mae is not None:
            insights.append(f"El intervalo mostrado usa el error absoluto medio real del modelo (+-${mae:,.0f}/día) sobre el horizonte de {DIAS_A_PROYECTAR_VENTAS} días.")
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

    # ── Caso de uso: Riesgo de abandono (Churn) ───────────────────────────────
    def get_churn_risk(self, cliente_id: str) -> dict[str, Any]:
        features = self.prediction_repo.get_churn_features(cliente_id)
        if features is None:
            return {"probabilidad_abandono": 0.0, "riesgo_alto": False}

        df_live = pd.DataFrame([features._asdict()])
        try:
            preds = inference.predict_churn(self.model_loader, df_live)
            prob = float(preds["churn_probability"].iloc[0])
            return {"probabilidad_abandono": round(prob * 100, 2), "riesgo_alto": prob > 0.5}
        except Exception as e:
            # H-03 cerrado en Fase 4: get_churn_features ahora produce las mismas 3
            # columnas/semántica que el contrato de entrenamiento (ml/contracts/models/churn.json).
            # Se sigue degradando con gracia ante cualquier otro fallo inesperado.
            logger.error(f"Fallo inferencia de churn para cliente_id={cliente_id}: {e}")
            return {"probabilidad_abandono": 0.0, "riesgo_alto": False}

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
    def get_product_recommendations(self, cliente_id: str) -> dict[str, Any]:
        historial = self.prediction_repo.get_client_purchase_history(cliente_id)
        try:
            # H-10 cerrado en Fase 4: item_B ya es codart (no nombre_articulo), y el
            # score expuesto es 'lift' (afinidad real), no 'support' (popularidad bruta).
            recs_df = inference.get_recommendations(self.model_loader, historial.ultimos_items or None)
            recomendaciones = [
                {"producto_cod": str(row["item_B"]), "score": float(row["lift"])}
                for _, row in recs_df.iterrows()
            ]
            return {"nombre_cliente": historial.nombre_cliente, "recomendaciones": recomendaciones}
        except Exception as e:
            logger.error(f"Fallo el motor de recomendaciones para cliente_id={cliente_id}: {e}")
            return {"nombre_cliente": historial.nombre_cliente, "recomendaciones": []}

    # ── Caso de uso: Segmentación RFM interactiva ─────────────────────────────
    def get_customer_segment(self, cliente_id: str) -> dict[str, Any]:
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
