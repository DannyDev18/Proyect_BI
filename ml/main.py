# ml/main.py
import logging
import pandas as pd
from src.data.make_dataset import SalesTimeSerieExtractor, DEMANDA_MIN_MESES_VENTA
from src.features.build_features import build_preprocessing_pipeline, select_features_and_target

from src.training.train_sales_prediction import train_sales_model, evaluate_model, save_model as save_sales_model
from src.training.train_customer_segmentation import evaluar_estabilidad_k, save_segmentation_model, train_rfm_segmentation
from src.training.train_churn_prediction import train_churn_model, evaluate_churn_classifier, save_churn_model
from src.training.train_recommendation_engine import construir_item_item, recomendar_desde_reglas, save_recommendation_rules
from src.training.backtest_recommendation import construir_canastas, evaluar_estrategia, split_temporal

# Ventana y horizonte de test ganadores del backtest de Fase 3 (ml/notebooks/
# experimentos_cross_selling.py, ml/contracts/models/recommendation.json notes):
# item-item con ventana=2 años obtuvo el mejor Precision@5 (0.0769) de los 31
# candidatos evaluados, con cobertura=97.9%.
RECOMMENDATION_VENTANA_ANIOS = 2
RECOMMENDATION_HORIZONTE_TEST_DIAS = 90
from src.training.train_demand_forecasting import train_demand_forecaster, evaluate_demand_model, save_demand_model
from src.training.train_anomaly_detection import estimar_contamination_iqr, save_anomaly_model, train_isolation_forest
from src.utils.stats_baseline import fit_ols_baseline, guardar_diagnostico_ols
from src.utils.model_export import resolve_models_dir

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

    # Fase 4 (§6): baseline OLS de referencia sobre el mismo split de entrenamiento (nunca
    # el holdout) -- si el RandomForest no supera claramente este OLS, es señal de alerta.
    diagnostico_ols = fit_ols_baseline(df_train, list(X_train.columns), 'y_sales_net')
    ruta_ols = guardar_diagnostico_ols("sales", diagnostico_ols, resolve_models_dir())
    if "error" in diagnostico_ols:
        logger.warning(f"  > Baseline OLS no disponible: {diagnostico_ols['error']}")
    else:
        logger.info(f"  > BASELINE OLS: R2_ajustado={diagnostico_ols['r2_ajustado']:.4f}, F_pvalue={diagnostico_ols['f_pvalue']:.4g}")

    save_sales_model(
        model,
        metrics=metrics,
        features=list(X_train.columns),
        data_range={"desde": str(df_features.index.min().date()), "hasta": str(df_features.index.max().date())},
        extra_meta={
            "statsmodels_baseline": {
                "r2": diagnostico_ols.get("r2"),
                "r2_ajustado": diagnostico_ols.get("r2_ajustado"),
                "f_statistic": diagnostico_ols.get("f_statistic"),
                "f_pvalue": diagnostico_ols.get("f_pvalue"),
                "p_values_significativas": diagnostico_ols.get("p_values_significativas"),
                "vif": diagnostico_ols.get("vif"),
                "summary_path": ruta_ols,
            } if "error" not in diagnostico_ols else {"error": diagnostico_ols["error"]},
        },
    )
    logger.info("Modelo de Ventas guardado con éxito.\n")


def train_demand_forecasting(extractor: SalesTimeSerieExtractor):
    logger.info("=== 2. ENTRENANDO PREDICCION DE DEMANDA DE PRODUCTOS (BODEGA) ===")
    # Fase 2 (docs/features/plan_mejora_pipeline_ml.md §4.1): grano (fecha, codart,
    # almacén) -- decisión de negocio "la reposición se decide por bodega". Reemplaza el
    # dataset global apilado (fetch_sales_by_dimension('producto')) que era D-1
    # (docs/auditoria/38_mejora_pipeline_ml.md): el backtest por SKU de esa auditoría
    # midió que el decil de mayor volumen tenía MAE 40x y RMSE 150x peor que los bajos,
    # porque el modelo global no distinguía producto.
    df_raw = extractor.fetch_demand_by_product_warehouse()
    if len(df_raw) < 30:
        logger.error("Datos insuficientes para Forecasting.")
        return

    # Ventana reciente: misma justificación que ventas (quiebre estructural del negocio,
    # H-08 -- antes demanda entrenaba con el histórico completo sin este recorte).
    fecha_corte = df_raw.index.max() - pd.DateOffset(years=VENTANA_ENTRENAMIENTO_VENTAS_ANIOS)
    df_raw = df_raw.loc[df_raw.index >= fecha_corte]

    # Umbral mínimo de historia (auditoría 38: 66.5% de las 12.654 combinaciones
    # (producto, almacén) tienen actividad en <=3 de 36 meses, mediana=2 -- series
    # demasiado ralas para que lags/rolling aporten señal real). Las combinaciones bajo
    # el umbral se excluyen del entrenamiento; en producción caen al pronóstico
    # estadístico existente (WarehouseService._forecast_estadistico), no al modelo.
    n_combos_totales = df_raw.groupby(["producto", "almacen"]).ngroups
    meses_activos = (
        df_raw.reset_index()[["ds", "producto", "almacen"]]
        .assign(anio_mes=lambda d: d["ds"].dt.to_period("M"))
        .groupby(["producto", "almacen"])["anio_mes"].nunique()
        .rename("n_meses_activos")
        .reset_index()
    )
    combos_elegibles = meses_activos.loc[meses_activos["n_meses_activos"] >= DEMANDA_MIN_MESES_VENTA, ["producto", "almacen"]]
    df_raw = df_raw.reset_index().merge(combos_elegibles, on=["producto", "almacen"], how="inner").set_index("ds")
    logger.info(
        f"  > Combinaciones (producto, almacén) elegibles (>= {DEMANDA_MIN_MESES_VENTA} meses con "
        f"actividad): {len(combos_elegibles)} de {n_combos_totales} totales."
    )
    if len(df_raw) < 30:
        logger.error("Datos insuficientes tras el filtro de historia mínima para Forecasting.")
        return

    # We train the forecaster predicting y_quantity (units)
    pipeline = build_preprocessing_pipeline(target_col='y_quantity')
    df_features = pipeline.fit_transform(df_raw)

    train_size = int(len(df_features) * 0.8)
    df_train = df_features.iloc[:train_size]
    df_test = df_features.iloc[train_size:]

    # Target is quantity for warehouse logistics; y en escala real (unidades), no log1p (H-01).
    X_train, y_train = select_features_and_target(df_train, 'y_quantity')
    X_test, y_test = select_features_and_target(df_test, 'y_quantity')

    # hyperparameter_search=True (revierte D-2): antes demanda era el único de los 3
    # modelos de regresión que entrenaba sin búsqueda de hiperparámetros.
    model = train_demand_forecaster(X_train, y_train, hyperparameter_search=True)
    y_pred = model.predict(X_test)
    metrics = evaluate_demand_model(y_test, y_pred, is_log_transformed=False)

    for k, v in metrics.items():
        logger.info(f"  > METRICA DEMANDA {k}: {v:.4f}")

    # Fase 4 (§6): mismo baseline OLS que ventas, sobre el split de entrenamiento.
    diagnostico_ols = fit_ols_baseline(df_train, list(X_train.columns), 'y_quantity')
    ruta_ols = guardar_diagnostico_ols("demand", diagnostico_ols, resolve_models_dir())
    if "error" in diagnostico_ols:
        logger.warning(f"  > Baseline OLS no disponible: {diagnostico_ols['error']}")
    else:
        logger.info(f"  > BASELINE OLS: R2_ajustado={diagnostico_ols['r2_ajustado']:.4f}, F_pvalue={diagnostico_ols['f_pvalue']:.4g}")

    save_demand_model(
        model,
        metrics=metrics,
        features=list(X_train.columns),
        data_range={"desde": str(df_features.index.min().date()), "hasta": str(df_features.index.max().date())},
        extra_meta={
            "statsmodels_baseline": {
                "r2": diagnostico_ols.get("r2"),
                "r2_ajustado": diagnostico_ols.get("r2_ajustado"),
                "f_statistic": diagnostico_ols.get("f_statistic"),
                "f_pvalue": diagnostico_ols.get("f_pvalue"),
                "p_values_significativas": diagnostico_ols.get("p_values_significativas"),
                "vif": diagnostico_ols.get("vif"),
                "summary_path": ruta_ols,
            } if "error" not in diagnostico_ols else {"error": diagnostico_ols["error"]},
        },
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

    # Fase 4 (§6): barrido K=2..8 (codo + silueta + Davies-Bouldin) como evidencia de
    # estabilidad -- documenta que K=4 no es arbitrario. K=4 en sí sigue siendo una
    # decisión de negocio (4 segmentos accionables), no se cambia por este barrido.
    logger.info("  > Evaluando estabilidad de K (K=2..8)...")
    estabilidad_k = evaluar_estabilidad_k(X_rfm)

    pipeline, silhouette, davies_bouldin = train_rfm_segmentation(X_rfm, n_clusters=4)
    save_segmentation_model(
        pipeline, silhouette=silhouette, n_rows=len(X_rfm),
        davies_bouldin=davies_bouldin, estabilidad_k=estabilidad_k,
    )
    logger.info("Motor de Segmentación guardado con éxito.\n")


def train_customer_churn(extractor: SalesTimeSerieExtractor):
    logger.info("=== 4. ENTRENANDO PREDICCIÓN DE ABANDONO (CHURN) (VENTAS) ===")
    # Dataset con corte temporal (H-05): fetch_churn_data ya arma features/etiqueta sin
    # circularidad -- ver ml/src/data/make_dataset.py::fetch_churn_data.
    df_churn = extractor.fetch_churn_data()
    if df_churn.empty or len(df_churn) < 20:
        logger.error("Datos de Churn insuficientes.")
        return

    # Fase 4 (§6): se agrega 'recency' -- ya la calculaba fetch_churn_data (días desde la
    # última compra AL CORTE T, sin fuga H-05) pero no se usaba como feature, pese a ser
    # típicamente la señal más predictiva de abandono en un esquema RFM.
    feature_cols = ['recency', 'frequency', 'monetary_value', 'average_ticket']
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
    # Fase 4 (docs/features/plan_mejora_pipeline_ml.md §6): antes esta función entrenaba
    # co-ocurrencia (min_support=0.005, sin ventana) -- un algoritmo DISTINTO al ganador
    # documentado (item-item, ventana 2 años, ml/notebooks/experimentos_cross_selling.py),
    # que se había publicado manualmente vía un script aparte
    # (ml/notebooks/publicar_ganador_cross_selling.py). Como esta función es la que
    # invoca el reentrenamiento automático (ml/retrain_all.py::ENTRENADORES), reentrenar
    # "association" habría sobrescrito el artefacto ganador con uno peor -- neutralizado
    # hasta ahora solo porque `metrics` nunca traía 'precision_at_5' y el gating rechaza
    # por seguridad cualquier candidato sin la métrica del `metric_gate` (ver
    # `promotion.py::evaluar_gate`). Se alinea el entrenamiento real con el ganador y se
    # calculan las métricas del backtest temporal para que el gating funcione de verdad.
    df_basket = extractor.fetch_market_basket(ventana_anios=RECOMMENDATION_VENTANA_ANIOS)
    if df_basket.empty:
        logger.error("Transacciones insuficientes para Market Basket Analysis.")
        return

    df_train, df_test = split_temporal(df_basket, horizonte_dias=RECOMMENDATION_HORIZONTE_TEST_DIAS)
    canastas_test = construir_canastas(df_test)

    metrics = {"n_reglas": 0}
    if not canastas_test.empty:
        item_item_holdout = construir_item_item(df_train, top_k_vecinos=20)
        if item_item_holdout is not None and not item_item_holdout.empty:
            catalogo = extractor.fetch_product_catalog()
            precios = dict(zip(catalogo["product_code"], catalogo["precio_oficial"].fillna(0.0)))
            metricas_backtest = evaluar_estrategia(
                lambda ctx, k, r=item_item_holdout: recomendar_desde_reglas(r, ctx, k),
                canastas_test, precios=precios,
            )
            metrics = metricas_backtest.to_dict()
            for k, v in metrics.items():
                logger.info(f"  > METRICA RECOMENDACIÓN {k}: {v}")
        else:
            logger.warning("No se pudo construir item-item sobre el split de entrenamiento para el backtest.")
    else:
        logger.warning("Sin canastas de test tras el split temporal -- no se calculan métricas de gating.")

    # Artefacto de producción: reentrenado con TODA la ventana (sin holdout), mismo
    # criterio que documenta recommendation.json notes -- el backtest ya validó la
    # estrategia sobre el holdout; este paso maximiza los datos servidos.
    rules_df = construir_item_item(df_basket, top_k_vecinos=20)
    if rules_df is not None and not rules_df.empty:
        metrics["n_reglas"] = len(rules_df)
        save_recommendation_rules(
            rules_df,
            algorithm="item-item (similitud coseno, top-20 vecinos)",
            n_transactions=df_basket['transaction_id'].nunique(),
            metrics=metrics,
            data_range={
                "ventana_anios": RECOMMENDATION_VENTANA_ANIOS,
                "fecha_min_entrenamiento": str(pd.to_datetime(df_basket["fecha"]).min().date()),
                "fecha_max_entrenamiento": str(pd.to_datetime(df_basket["fecha"]).max().date()),
                "n_lineas_entrenamiento": len(df_basket),
            },
        )
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

    # Fase 4 (§6): contamination data-driven (regla IQR sobre 'margen'), no un 1% fijo.
    contamination = estimar_contamination_iqr(df_txs, columna="margen")
    model = train_isolation_forest(df_txs, contamination=contamination)

    scores = model.decision_function(df_txs)
    metrics = {
        "pct_flagged_outlier": float((model.predict(df_txs) == -1).mean()),
        "decision_function_mean": float(scores.mean()),
        "decision_function_std": float(scores.std()),
        "contamination_usado": contamination,
    }
    for k, v in metrics.items():
        logger.info(f"  > METRICA ANOMALIAS {k}: {v:.4f}")

    save_anomaly_model(
        model,
        metrics=metrics,
        features=list(df_txs.columns),
        data_range={"n_filas_entrenamiento": len(df_txs), "n_excluidas_sin_costo": n_excluidas},
        extra_meta={
            "criterio_contamination": (
                "IQR sobre 'margen' (Q1-1.5*IQR, Q3+1.5*IQR), acotado a "
                "[0.005, 0.05] -- reemplaza el valor fijo 0.01 sin evidencia (Fase 4)."
            ),
        },
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
