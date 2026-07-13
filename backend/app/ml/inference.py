# backend/app/ml/inference.py
"""Funciones puras de inferencia: reciben un `ModelLoader` + DataFrame, sin acceso a
DB/HTTP. Esto es lo que se testea con un `ModelLoader` fake (modelo dummy) sin
necesitar los `.pkl` reales -- ver backend/tests/unit/test_inference.py.

Fase 4: las columnas de entrada se seleccionan vía `loader.get_features(key)` (contrato
declarado en el sidecar `.meta.json`), no `model.feature_names_in_` -- ver
app/ml/model_loader.py para el porqué (H-07)."""
import pandas as pd

from app.ml.contract_validation import enforce, validate_features, validate_prediction
from app.ml.model_loader import ModelLoader


def _select_features(loader: ModelLoader, key: str, X: pd.DataFrame) -> pd.DataFrame:
    features = loader.get_features(key)
    return X[features] if features else X


def _validate_features_or_raise(loader: ModelLoader, key: str, columns) -> None:
    """Fase de integración Metas y Comisiones (docs/auditoria/15_...): toda inferencia
    usada por el módulo pasa primero por `contract_validation.py` -- ModelLoader ->
    ContractValidator (backend-native) -> Modelo -> validación de salida -> Servicio."""
    contract = loader.get_contract(key)
    result = validate_features(contract, columns)
    enforce(contract, result, context=f"inference.{key}.features")


def _validate_prediction_or_raise(loader: ModelLoader, key: str, value: float) -> None:
    contract = loader.get_contract(key)
    result = validate_prediction(contract, value)
    enforce(contract, result, context=f"inference.{key}.prediction")


def predict_sales(loader: ModelLoader, X: pd.DataFrame) -> pd.Series:
    model = loader.get('sales_rf')
    X = _select_features(loader, 'sales_rf', X)
    _validate_features_or_raise(loader, 'sales_rf', X.columns)
    # El artefacto es un TransformedTargetRegressor autocontenido: predict() ya
    # devuelve USD directamente, sin expm1 manual (H-01, cerrado en Fase 3).
    preds = pd.Series(model.predict(X))
    for v in preds:
        _validate_prediction_or_raise(loader, 'sales_rf', float(v))
    return preds


def predict_demand(loader: ModelLoader, X: pd.DataFrame) -> pd.Series:
    model = loader.get('demand_rf')
    X = _select_features(loader, 'demand_rf', X)
    _validate_features_or_raise(loader, 'demand_rf', X.columns)
    # Ídem ventas: predict() devuelve unidades reales (H-01, cerrado en Fase 3).
    preds = pd.Series(model.predict(X))
    for v in preds:
        _validate_prediction_or_raise(loader, 'demand_rf', float(v))
    return preds


def predict_churn(loader: ModelLoader, X: pd.DataFrame) -> pd.DataFrame:
    model = loader.get('churn_rf')
    X = _select_features(loader, 'churn_rf', X)
    preds = model.predict(X)
    probs = model.predict_proba(X)[:, 1]  # probabilidad de clase 1 (churn)
    return pd.DataFrame({'is_churn_pred': preds, 'churn_probability': probs})


def detect_anomalies(loader: ModelLoader, X: pd.DataFrame) -> pd.DataFrame:
    model = loader.get('anomaly')
    X = _select_features(loader, 'anomaly', X)
    _validate_features_or_raise(loader, 'anomaly', X.columns)
    # H-04 (cerrado en Fase 4): se expone decision_function() real -- antes el score
    # que llegaba al dashboard era un valor hardcodeado (-0.85/0.15) en prediction_service.
    preds = model.predict(X)  # 1 = normal, -1 = anomalía (convención IsolationForest)
    scores = model.decision_function(X)
    for s in scores:
        _validate_prediction_or_raise(loader, 'anomaly', float(s))
    return pd.DataFrame({'is_anomaly_pred': preds, 'anomaly_score': scores})


def get_recommendations(loader: ModelLoader, item_history: list | None = None, top_n: int = 5) -> pd.DataFrame:
    """H-10 (cerrado en Fase 3/4): el artefacto reconstruido emite reglas DIRECCIONALES
    (una fila A->B y otra B->A por cada par), así que filtrar solo por `item_A` ya no
    pierde la mitad de las coincidencias como con el motor legacy simétrico.

    Contrato v0.2.0 (docs/auditoria/25_modulo_cross_selling.md): el ganador del backtest
    (filtrado colaborativo item-item) expone `score` (ranking genérico, no comparable en
    escala con `lift`) en vez de `lift` -- se ordena por `score` para servir cualquier
    estrategia publicada bajo este contrato.

    `item_history` puede ser el historial de un cliente (caso original) o los productos
    más vendidos de un vendedor (integración Metas y Comisiones: sugerir qué más vender
    junto a lo que el vendedor ya coloca bien, para ayudarlo a cerrar su meta)."""
    rules = loader.get('association')
    _validate_features_or_raise(loader, 'association', rules.columns)
    if item_history:
        return rules[rules['item_A'].isin(item_history)].sort_values('score', ascending=False).head(top_n)
    return rules.sort_values('score', ascending=False).head(max(top_n, 10))


def get_basket_recommendations(loader: ModelLoader, canasta: list[str], excluir: list[str], top_n: int) -> pd.DataFrame:
    """Recomendación por canasta (asistente de Venta Cruzada, docs/auditoria/25_...md):
    filtra reglas por `item_A` en la canasta simulada, excluye lo ya presente en la
    canasta y lo ya comprado por el cliente (`excluir`), agrega por `item_B` (máximo
    `score` entre todos los productos de la canasta que lo sugieren) y ordena
    descendente. Reutiliza el mismo artefacto/contrato `association` que
    `get_recommendations` (por-cliente) -- ambos casos de uso comparten inference.py y
    el mismo artefacto, solo cambian las heurísticas en el servicio (plan §2.3.e)."""
    rules = loader.get('association')
    _validate_features_or_raise(loader, 'association', rules.columns)
    if not canasta:
        return rules.iloc[0:0]
    excluidos = set(canasta) | set(excluir)
    candidatas = rules[rules['item_A'].isin(canasta) & ~rules['item_B'].isin(excluidos)]
    if candidatas.empty:
        return candidatas
    mejor_por_item_b = candidatas.loc[candidatas.groupby('item_B')['score'].idxmax()]
    return mejor_por_item_b.sort_values('score', ascending=False).head(top_n)


def predict_segmentation(loader: ModelLoader, X_rfm: pd.DataFrame) -> pd.Series:
    model = loader.get('segmentation')
    X_rfm = _select_features(loader, 'segmentation', X_rfm)
    # El artefacto es un Pipeline(StandardScaler+KMeans) autocontenido: predict() escala
    # y clasifica en una sola llamada (H-02, cerrado en Fase 3).
    return pd.Series(model.predict(X_rfm))


def get_cluster_to_segment(loader: ModelLoader) -> dict[str, str]:
    """Mapeo cluster_id -> nombre de negocio persistido en el sidecar al entrenar,
    ordenado por centroides (H-12, cerrado en Fase 3): reemplaza el dict hardcodeado que
    antes vivía en prediction_service.py y que quedaba desalineado tras cada
    reentrenamiento (las etiquetas de K-Means son arbitrarias entre corridas)."""
    return loader.get_meta('segmentation').get('cluster_to_segment', {})
