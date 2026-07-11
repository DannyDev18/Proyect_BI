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

# Horizonte diario interno del walk-forward (el modelo sigue siendo diario -- ver
# docs/auditoria/21_mejora_features_ventas_y_granularidad.md): se genera un forecast diario
# más largo y se bucketiza a semana/mes en el servicio, sin entrenar modelos nuevos por
# granularidad. "semana" = 12 semanas (~84 días); "mes" = 6 meses (~180 días).
DIAS_A_PROYECTAR_POR_GRANULARIDAD = {"semana": 84, "mes": 180}
DIAS_VISUALIZACION_HISTORIAL_POR_GRANULARIDAD = {"semana": 26 * 7, "mes": 24 * 31}


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
