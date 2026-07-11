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

    # y_train/y_test se pasan en escala real (USD): train_sales_model aplica log1p
    # internamente y devuelve un TransformedTargetRegressor autocontenido (H-01).
    model = train_sales_model(X_train, y_train, hyperparameter_search=False)
    y_pred = model.predict(X_test)
    metrics = evaluate_model(y_test, y_pred, is_log_transformed=False)

    for k, v in metrics.items():
        logger.info(f"  > METRICA {k}: {v:.4f}")

    save_sales_model(
        model,
        metrics=metrics,
        features=list(X_train.columns),
        data_range={"desde": str(df_features.index.min().date()), "hasta": str(df_features.index.max().date())},
    )
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

    # Ventana reciente: misma justificación que ventas (quiebre estructural del negocio,
    # H-08 -- antes demanda entrenaba con el histórico completo sin este recorte).
    fecha_corte = df_features.index.max() - pd.DateOffset(years=VENTANA_ENTRENAMIENTO_VENTAS_ANIOS)
    df_features = df_features.loc[df_features.index >= fecha_corte]

    train_size = int(len(df_features) * 0.8)
    df_train = df_features.iloc[:train_size]
    df_test = df_features.iloc[train_size:]

    # Target is quantity for warehouse logistics; y en escala real (unidades), no log1p (H-01).
    X_train, y_train = select_features_and_target(df_train, 'y_quantity')
    X_test, y_test = select_features_and_target(df_test, 'y_quantity')

    model = train_demand_forecaster(X_train, y_train, hyperparameter_search=False)
    y_pred = model.predict(X_test)
    metrics = evaluate_demand_model(y_test, y_pred, is_log_transformed=False)

    for k, v in metrics.items():
        logger.info(f"  > METRICA DEMANDA {k}: {v:.4f}")

    save_demand_model(
        model,
        metrics=metrics,
        features=list(X_train.columns),
        data_range={"desde": str(df_features.index.min().date()), "hasta": str(df_features.index.max().date())},
    )
    logger.info("Modelo de Proyección Logística guardado con éxito.\n")


def train_customer_segmentation(extractor: SalesTimeSerieExtractor):
    logger.info("=== 3. ENTRENANDO SEGMENTACIÓN DE CLIENTES (VENTAS) ===")
    df_rfm = extractor.fetch_rfm_metrics()
    if df_rfm.empty or len(df_rfm) < 10:
        logger.error("Datos RFM insuficientes.")
        return
        
    # Descartar codcli para clustering
    X_rfm = df_rfm[['recency', 'frequency', 'monetary_value']].copy()

    pipeline, silhouette = train_rfm_segmentation(X_rfm, n_clusters=4)
    save_segmentation_model(pipeline, silhouette=silhouette, n_rows=len(X_rfm))
    logger.info("Motor de Segmentación guardado con éxito.\n")


def train_customer_churn(extractor: SalesTimeSerieExtractor):
    logger.info("=== 4. ENTRENANDO PREDICCIÓN DE ABANDONO (CHURN) (VENTAS) ===")
    # Dataset con corte temporal (H-05): fetch_churn_data ya arma features/etiqueta sin
    # circularidad -- ver ml/src/data/make_dataset.py::fetch_churn_data.
    df_churn = extractor.fetch_churn_data()
    if df_churn.empty or len(df_churn) < 20:
        logger.error("Datos de Churn insuficientes.")
        return

    feature_cols = ['frequency', 'monetary_value', 'average_ticket']
    X = df_churn[feature_cols]
    y = df_churn['is_churn']

    # Train-test split standard
    from sklearn.model_selection import train_test_split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    model = train_churn_model(X_train, y_train)
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)

    metrics = evaluate_churn_classifier(y_test, y_pred, y_proba)
    save_churn_model(
        model,
        metrics=metrics,
        features=feature_cols,
        data_range={"desde": str(df_churn['fecha_corte'].min().date()), "hasta": str(df_churn['fecha_corte'].max().date())},
    )
    logger.info("Modelo de Abandono guardado con éxito.\n")


def train_recommendations(extractor: SalesTimeSerieExtractor):
    logger.info("=== 5. ENTRENANDO REGLAS DE RECOMENDACIÓN (VENTAS) ===")
    df_basket = extractor.fetch_market_basket()
    if df_basket.empty:
        logger.error("Transacciones insuficientes para Market Basket Analysis.")
        return

    rules_df = train_association_rules(df_basket, min_support=0.005) # support 0.5% due to high volume dummy data
    if rules_df is not None:
        save_recommendation_rules(rules_df, n_transactions=df_basket['transaction_id'].nunique())
    logger.info("Reglas guardadas con éxito.\n")


def train_anomaly_detection(extractor: SalesTimeSerieExtractor):
    logger.info("=== 6. ENTRENANDO DETECTOR DE ANOMALÍAS (ADMINISTRADOR) ===")
    df_txs = extractor.fetch_transactions_for_anomalies()
    if df_txs.empty:
        logger.error("No hay transacciones suficientes.")
        return

    # H-19 (docs/auditoria/11_auditoria_tecnica_modelos_ml.md): con el EDW nuevo,
    # costo_total/margen ahora son NULLables REALES (cambio C-2) cuando el artículo no
    # tiene costo en SAP. El legacy hacía fillna(0.0), lo que reintroducía exactamente el
    # "margen 100% artificial" que el EDW acaba de eliminar como centinela -- ese 100%
    # artificial se aprendía como patrón normal, no como anomalía real. Se excluyen esas
    # filas en vez de imputarlas: no hay evidencia suficiente para asumir una mediana por
    # producto en esta pasada.
    n_antes = len(df_txs)
    df_txs = df_txs.dropna(subset=['costo_total', 'margen'])
    n_excluidas = n_antes - len(df_txs)
    if n_excluidas:
        logger.info(f"Excluidas {n_excluidas} filas ({n_excluidas / n_antes:.1%}) sin costo_total (H-19).")

    model = train_isolation_forest(df_txs, contamination=0.01)

    scores = model.decision_function(df_txs)
    metrics = {
        "pct_flagged_outlier": float((model.predict(df_txs) == -1).mean()),
        "decision_function_mean": float(scores.mean()),
        "decision_function_std": float(scores.std()),
    }
    for k, v in metrics.items():
        logger.info(f"  > METRICA ANOMALIAS {k}: {v:.4f}")

    save_anomaly_model(
        model,
        metrics=metrics,
        features=list(df_txs.columns),
        data_range={"n_filas_entrenamiento": len(df_txs), "n_excluidas_sin_costo": n_excluidas},
    )
    logger.info("Detector de Anomalías guardado con éxito.\n")


def run_ml_pipeline():
    logger.info("=== INICIANDO EXPERIMENTO ML OPS ORQUESTADO ===")
    extractor = SalesTimeSerieExtractor()

    train_general_sales_prediction(extractor)
    train_demand_forecasting(extractor)
    train_customer_segmentation(extractor)
    train_customer_churn(extractor)
    train_recommendations(extractor)
    train_anomaly_detection(extractor)

    logger.info("=== ML PIPELINE ORQUESTADO COMPLETADO EXITOSAMENTE ===")


if __name__ == "__main__":
    run_ml_pipeline()
