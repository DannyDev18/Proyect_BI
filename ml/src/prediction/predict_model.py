# ml/src/prediction/predict_model.py
import os
import joblib
import logging
import pandas as pd

logger = logging.getLogger("MLOps.MultiPredictor")

class MultiModelPredictor:
    """
    Clase centralizada (Singleton Proxy) para cargar en memoria y operar todos
    los modelos de Machine Learning entrenados, optimizando la inferencia del Backend.
    """
    def __init__(self, models_dir: str = None):
        self.models_dir = models_dir or os.getenv("ML_MODELS_DIR", "/app/ml_models")
        self.models = {}
        self._load_models()

    def _load_models(self):
        """Carga perezosa/pesada inicial de los .pkl en memoria dict.
        Los nombres de archivo deben coincidir con los que escriben los `save_*`
        de cada `train_*` (ver src/training/): son el modelo GANADOR de la
        competencia multi-algoritmo, no el RandomForest base."""
        model_files = {
            'sales_rf': 'sales_best_model.pkl',
            'demand_rf': 'demand_best_model.pkl',
            'churn_rf': 'churn_best_classifier.pkl',
            'segmentation': 'kmeans_rfm_model.pkl',
            'association': 'association_rules.pkl',
            'anomaly': 'isolation_forest_model.pkl',
            'goals_rf': 'goals_best_model.pkl'
        }
        
        for key, filename in model_files.items():
            path = os.path.join(self.models_dir, filename)
            if os.path.exists(path):
                try:
                    self.models[key] = joblib.load(path)
                    logger.info(f"Loaded {key} ML model.")
                except Exception as e:
                    logger.error(f"Failed to load {filename}: {e}")
            else:
                logger.warning(f"Model {filename} not found at {path}. Not loaded.")

    def predict_sales(self, df_features: pd.DataFrame) -> pd.Series:
        if 'sales_rf' not in self.models:
            raise ValueError("Sales prediction model not loaded.")
        import numpy as np
        model = self.models['sales_rf']
        X = df_features[model.feature_names_in_]
        return pd.Series(model.predict(X))

    def predict_demand(self, df_features: pd.DataFrame) -> pd.Series:
        if 'demand_rf' not in self.models:
            raise ValueError("Demand prediction model not loaded.")
        import numpy as np
        model = self.models['demand_rf']
        X = df_features[model.feature_names_in_]
        return pd.Series(model.predict(X))

    def predict_churn(self, df_features: pd.DataFrame) -> pd.DataFrame:
        if 'churn_rf' not in self.models:
            raise ValueError("Churn prediction model not loaded.")
        model = self.models['churn_rf']
        preds = model.predict(df_features)
        probs = model.predict_proba(df_features)[:, 1] # prob class 1 (Churn)
        return pd.DataFrame({'is_churn_pred': preds, 'churn_probability': probs})

    def detect_anomalies(self, df_transactions: pd.DataFrame) -> pd.Series:
        if 'anomaly' not in self.models:
            raise ValueError("Anomaly Detection model not loaded.")
        # returns 1 for normal, -1 for anomaly
        return pd.Series(self.models['anomaly'].predict(df_transactions))

    def get_recommendations(self, item_history: list = None) -> pd.DataFrame:
        if 'association' not in self.models:
            raise ValueError("Association Rules model not loaded.")
        rules = self.models['association']
        # If item_history specified, filter rules
        if item_history:
            return rules[rules['item_A'].isin(item_history)].head(5)
        return rules.head(10)

    def predict_segmentation(self, df_rfm: pd.DataFrame) -> pd.Series:
        """Devuelve el ID de cluster para clientes usando recency, frequency, monetary"""
        if 'segmentation' not in self.models:
            raise ValueError("Segmentation model not loaded.")
        return pd.Series(self.models['segmentation'].predict(df_rfm))
