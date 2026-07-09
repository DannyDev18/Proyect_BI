# ml/main.py
import logging
import pandas as pd
from src.data.make_dataset import SalesTimeSerieExtractor
from src.features.build_features import build_preprocessing_pipeline, select_features_and_target

from src.training.train_sales_prediction import train_sales_model, evaluate_model, save_model as save_sales_model
from src.training.train_customer_segmentation import train_rfm_segmentation, save_segmentation_model
from src.training.train_churn_prediction import train_churn_model, evaluate_churn_classifier, save_churn_model
from src.training.train_recommendation_engine import train_association_rules, save_recommendation_rules
from src.training.train_demand_forecasting import train_demand_forecaster, evaluate_demand_model, save_demand_model
from src.training.train_anomaly_detection import train_isolation_forest, save_anomaly_model
from src.training.train_goals_prediction import train_goals_prediction, save_goals_model

# Formato estandar MLOps
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MLOps.Orchestrator")

# El EDW tiene ~8.5 años de historia de ventas (2018-2026) con una tendencia de crecimiento
# sostenida del negocio (~31% de crecimiento en el monto diario promedio entre 2018 y 2026,
# validado por EDA). Entrenar con el histórico completo y evaluar con el último 20%
# cronológico compara el modelo contra un régimen de ventas estructuralmente distinto
# (mucho más alto) al de los años tempranos, lo que degrada el R2 (-0.03 medido en backtest,
# ver ml/REPORTE_MEJORA_MODELOS.md). Restringir a una ventana reciente evita ese quiebre
# estructural y mejoró el R2 a +0.21 en el mismo backtest.
VENTANA_ENTRENAMIENTO_VENTAS_ANIOS = 3

def train_general_sales_prediction(extractor: SalesTimeSerieExtractor):
    logger.info("=== 1. ENTRENANDO PREDICCIÓN DE VENTAS GENERALES (GERENCIA) ===")
    df_raw = extractor.fetch_daily_sales()
    if len(df_raw) < 30:
        logger.error("Data insuficiente en la EDW (> 30 días solicitados) para entrenar el modelo.")
        return

    pipeline = build_preprocessing_pipeline()
    df_features = pipeline.fit_transform(df_raw)

    # Ventana reciente: ver VENTANA_ENTRENAMIENTO_VENTAS_ANIOS arriba.
    fecha_corte = df_features.index.max() - pd.DateOffset(years=VENTANA_ENTRENAMIENTO_VENTAS_ANIOS)
    df_features = df_features.loc[df_features.index >= fecha_corte]

    train_size = int(len(df_features) * 0.8)
    df_train = df_features.iloc[:train_size]
    df_test = df_features.iloc[train_size:]
    
    X_train, y_train = select_features_and_target(df_train, 'y_sales_net')
    X_test, y_test = select_features_and_target(df_test, 'y_sales_net')
    
    model = train_sales_model(X_train, y_train, hyperparameter_search=False)
    y_pred = model.predict(X_test)
    metrics = evaluate_model(y_test, y_pred)
    
    for k, v in metrics.items():
        logger.info(f"  > METRICA {k}: {v:.4f}")
        
    save_sales_model(model)
    logger.info("Modelo de Ventas guardado con éxito.\n")


def train_demand_forecasting(extractor: SalesTimeSerieExtractor):
    logger.info("=== 2. ENTRENANDO PREDICCION DE DEMANDA DE PRODUCTOS (BODEGA) ===")
    # Extract demands grouped by product
    df_raw = extractor.fetch_sales_by_dimension(dimension='producto')
    if len(df_raw) < 30:
        logger.error("Datos insuficientes para Forecasting.")
        return
    
    # We train the forecaster predicting y_quantity (units)
    pipeline = build_preprocessing_pipeline(target_col='y_quantity')
    df_features = pipeline.fit_transform(df_raw)
    
    train_size = int(len(df_features) * 0.8)
    df_train = df_features.iloc[:train_size]
    df_test = df_features.iloc[train_size:]
    
    # Target is quantity for warehouse logistics
    X_train, y_train = select_features_and_target(df_train, 'y_quantity')
    X_test, y_test = select_features_and_target(df_test, 'y_quantity')
    
    model = train_demand_forecaster(X_train, y_train, hyperparameter_search=False)
    y_pred = model.predict(X_test)
    metrics = evaluate_demand_model(y_test, y_pred)
    
    for k, v in metrics.items():
        logger.info(f"  > METRICA DEMANDA {k}: {v:.4f}")
        
    save_demand_model(model)
    logger.info("Modelo de Proyección Logística guardado con éxito.\n")


def train_customer_segmentation(extractor: SalesTimeSerieExtractor):
    logger.info("=== 3. ENTRENANDO SEGMENTACIÓN DE CLIENTES (VENTAS) ===")
    df_rfm = extractor.fetch_rfm_metrics()
    if df_rfm.empty or len(df_rfm) < 10:
        logger.error("Datos RFM insuficientes.")
        return
        
    # Descartar codcli para clustering
    X_rfm = df_rfm[['recency', 'frequency', 'monetary_value']].copy()
    
    artifacts = train_rfm_segmentation(X_rfm, n_clusters=4)
    save_segmentation_model(artifacts)
    logger.info("Motor de Segmentación guardado con éxito.\n")


def train_customer_churn(extractor: SalesTimeSerieExtractor):
    logger.info("=== 4. ENTRENANDO PREDICCIÓN DE ABANDONO (CHURN) (VENTAS) ===")
    df_churn = extractor.fetch_churn_data()
    if df_churn.empty or len(df_churn) < 20:
        logger.error("Datos de Churn insuficientes.")
        return
        
    # Crear Average Ticket para evitar leak directo de Recency
    df_churn['average_ticket'] = df_churn['monetary_value'] / df_churn['frequency']
    
    X = df_churn[['frequency', 'monetary_value', 'average_ticket']]
    y = df_churn['is_churn']
    
    # Train-test split standard
    from sklearn.model_selection import train_test_split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    model = train_churn_model(X_train, y_train)
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)
    
    evaluate_churn_classifier(y_test, y_pred, y_proba)
    save_churn_model(model)
    logger.info("Modelo de Abandono guardado con éxito.\n")


def train_recommendations(extractor: SalesTimeSerieExtractor):
    logger.info("=== 5. ENTRENANDO REGLAS DE RECOMENDACIÓN (VENTAS) ===")
    df_basket = extractor.fetch_market_basket()
    if df_basket.empty:
        logger.error("Transacciones insuficientes para Market Basket Analysis.")
        return
        
    rules_df = train_association_rules(df_basket, min_support=0.005) # support 0.5% due to high volume dummy data
    if rules_df is not None:
        save_recommendation_rules(rules_df)
    logger.info("Reglas guardadas con éxito.\n")


def train_anomaly_detection(extractor: SalesTimeSerieExtractor):
    logger.info("=== 6. ENTRENANDO DETECTOR DE ANOMALÍAS (ADMINISTRADOR) ===")
    df_txs = extractor.fetch_transactions_for_anomalies()
    if df_txs.empty:
        logger.error("No hay transacciones suficientes.")
        return
        
    import numpy as np
    
    # Limpiar nulos para isolation forest y asegurar dtypes numéricos
    df_txs = df_txs.fillna(0.0)
    
    model = train_isolation_forest(df_txs, contamination=0.01)
    save_anomaly_model(model)
    logger.info("Detector de Anomalías guardado con éxito.\n")


def train_goals_prediction_pipeline(extractor: SalesTimeSerieExtractor):
    logger.info("=== 7. ENTRENANDO PREDICCION DE METAS (GERENCIA) ===")
    df_raw = extractor.fetch_goals_data()
    if df_raw.empty or len(df_raw) < 10:
        logger.error("Data insuficiente para modelo de metas.")
        return
        
    model = train_goals_prediction(df_raw)
    save_goals_model(model)


def run_ml_pipeline():
    logger.info("=== INICIANDO EXPERIMENTO ML OPS ORQUESTADO ===")
    extractor = SalesTimeSerieExtractor()
    
    train_general_sales_prediction(extractor)
    train_demand_forecasting(extractor)
    train_customer_segmentation(extractor)
    train_customer_churn(extractor)
    train_recommendations(extractor)
    train_anomaly_detection(extractor)
    train_goals_prediction_pipeline(extractor)
    
    logger.info("=== ML PIPELINE ORQUESTADO COMPLETADO EXITOSAMENTE ===")


if __name__ == "__main__":
    run_ml_pipeline()
