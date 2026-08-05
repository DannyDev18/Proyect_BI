# ml/main.py
import json
import logging
import os

import joblib
import numpy as np
import pandas as pd
from src.data.make_dataset import (
    DEMANDA_MIN_MESES_VENTA, RANKER_ESPACIADO_DIAS, RANKER_HORIZONTE_DIAS, RANKER_N_CORTES,
    RANKER_RATIO_NEGATIVOS, RANKER_TOP_CANDIDATOS, SalesTimeSerieExtractor,
)
from src.features.build_features import build_preprocessing_pipeline, select_features_and_target
from src.features.cross_sell_ranker_features import (
    FEATURE_COLUMNS, calcular_economia_catalogo, calcular_rfm_a_corte, calcular_ventas_por_producto_ventanas,
    construir_dataset_ranking, construir_features_candidatos, preparar_matriz_features,
)

from src.training.train_customer_segmentation import evaluar_estabilidad_k, save_segmentation_model, train_rfm_segmentation
from src.training.train_churn_prediction import train_churn_model, evaluate_churn_classifier, save_churn_model
from src.training.train_recommendation_engine import construir_item_item, recomendar_desde_reglas, save_recommendation_rules
from src.training.train_cross_sell_ranker import evaluate_ranker, save_cross_sell_ranker_model, train_ranker
from src.training.backtest_recommendation import (
    construir_canastas, construir_canastas_con_contexto, evaluar_estrategia, evaluar_estrategia_reranked, split_temporal,
)

# Ventana y horizonte de test ganadores del backtest de Fase 3 (ml/notebooks/
# experimentos_cross_selling.py, ml/contracts/models/recommendation.json notes):
# item-item con ventana=2 años obtuvo el mejor Precision@5 (0.0769) de los 31
# candidatos evaluados, con cobertura=97.9%.
RECOMMENDATION_VENTANA_ANIOS = 2
RECOMMENDATION_HORIZONTE_TEST_DIAS = 90

# Regla de decisión del ranker de Venta Cruzada, FIJADA ANTES de ver resultados (Fase 2,
# docs/features/plan_refactor_venta_cruzada_ia.md §2.4): línea base documentada del
# ganador item-item (ml/contracts/models/recommendation.json notes). El ranker solo se
# promueve (entra a registry.json como campeón) si iguala o supera AMBOS umbrales sobre
# el backtest fresco medido en esta misma corrida -- no basta con superar la cifra
# histórica si además degrada la cobertura.
RANKER_LINEA_BASE_PRECISION_AT_5 = 0.0769
RANKER_LINEA_BASE_COBERTURA = 0.979
from src.training.train_demand_forecasting import train_demand_forecaster, evaluate_demand_model, save_demand_model
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


def train_cross_sell_ranker(extractor: SalesTimeSerieExtractor):
    """7º modelo del proyecto (Fase 2, docs/features/plan_refactor_venta_cruzada_ia.md).
    Auditoría previa: docs/auditoria/40_refactor_venta_cruzada.md (A0-0: volumen de
    sobra; A0-5: afinidad item-item fuertemente local por sucursal -- `sucursal` entra
    como feature explícita del ranker, ver contrato). No reemplaza `association`
    (item-item, etapa 1 de candidatos): este modelo REORDENA los candidatos que ese
    artefacto propone (etapa 2, arquitectura de dos etapas del plan §3)."""
    logger.info("=== 7. ENTRENANDO RANKER DE VENTA CRUZADA (VENTAS) ===")
    models_dir = resolve_models_dir()

    item_item_rules = joblib.load(os.path.join(models_dir, "recommendation.pkl"))
    churn_model = joblib.load(os.path.join(models_dir, "churn.pkl"))
    segmentation_pipeline = joblib.load(os.path.join(models_dir, "segmentation.pkl"))

    tx = extractor.fetch_cross_sell_transacciones()
    catalogo = extractor.fetch_product_catalog()
    if tx.empty or catalogo.empty:
        logger.error("Datos insuficientes (transacciones o catálogo vacíos) para el ranker de Venta Cruzada.")
        return

    dataset = construir_dataset_ranking(
        tx, item_item_rules, catalogo,
        horizonte_dias=RANKER_HORIZONTE_DIAS, n_cortes=RANKER_N_CORTES, espaciado_dias=RANKER_ESPACIADO_DIAS,
        ratio_negativos=RANKER_RATIO_NEGATIVOS, top_candidatos=RANKER_TOP_CANDIDATOS,
    )
    if dataset.empty or len(dataset) < 100:
        logger.error("Dataset de ranking insuficiente para entrenar el ranker de Venta Cruzada.")
        return
    logger.info(f"  > Dataset de ranking: {len(dataset)} filas, {dataset['label'].mean():.2%} positivos.")

    # p_abandono/segmento_rfm: los modelos YA ENTRENADOS entran como FEATURES de entrada
    # (decisión de arquitectura del plan §3), no solo como servicios aparte.
    rfm_cols = ["recency", "frequency", "monetary_value", "average_ticket"]
    dataset["p_abandono"] = churn_model.predict_proba(dataset[rfm_cols])[:, 1]
    dataset["segmento_rfm"] = segmentation_pipeline.predict(dataset[["recency", "frequency", "monetary_value"]])

    sucursal_valores = sorted(dataset["sucursal"].astype(str).unique().tolist())
    X_full = preparar_matriz_features(dataset, sucursal_valores)
    feature_cols = list(X_full.columns)
    y_full = dataset["label"]

    # Split CRONOLÓGICO por corte (R-9 del plan: la fuga temporal ya ocurrió una vez en
    # este pipeline, H-05 de churn) -- cortes antiguos entrenan, recientes evalúan.
    # Nunca aleatorio, aunque churn use split aleatorio estratificado (sus filas son
    # cortes ya independientes entre sí; aquí varios clientes comparten corte).
    cortes_unicos = sorted(dataset["corte"].unique())
    idx_split = max(1, int(len(cortes_unicos) * 0.8))
    cortes_train = set(cortes_unicos[:idx_split])
    es_train = dataset["corte"].isin(cortes_train)

    X_train, y_train = X_full.loc[es_train], y_full.loc[es_train]
    X_test, y_test = X_full.loc[~es_train], y_full.loc[~es_train]
    logger.info(
        f"  > Split cronológico: {len(cortes_train)}/{len(cortes_unicos)} cortes entrenan "
        f"({len(X_train)} filas), {len(cortes_unicos) - len(cortes_train)} cortes evalúan ({len(X_test)} filas)."
    )

    model = train_ranker(X_train, y_train)
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)
    metrics_holdout = evaluate_ranker(y_test, y_pred, y_proba)
    for k, v in metrics_holdout.items():
        logger.info(f"  > METRICA RANKER (holdout clasificación) {k}: {v}")

    # --- Backtest §2.4: mismo protocolo/mismas métricas que la auditoría 25 (Precision@K/
    # Recall@K/Hit-Rate@5/cobertura), en dos etapas: item-item genera candidatos (igual
    # que producción), el ranker los reordena. Baseline y candidato medidos FRESCOS sobre
    # el MISMO test set en esta misma corrida (no se asume que la cifra histórica sigue
    # vigente con más datos acumulados desde entonces).
    df_basket = extractor.fetch_market_basket(ventana_anios=RECOMMENDATION_VENTANA_ANIOS)
    df_train_b, df_test_b = split_temporal(df_basket, horizonte_dias=RECOMMENDATION_HORIZONTE_TEST_DIAS)
    t_split = pd.to_datetime(df_basket["fecha"]).max() - pd.Timedelta(days=RECOMMENDATION_HORIZONTE_TEST_DIAS)

    item_item_holdout = construir_item_item(df_train_b, top_k_vecinos=20)
    catalogo_precios = dict(zip(catalogo["product_code"], catalogo["precio_oficial"].fillna(0.0)))

    if item_item_holdout is None or item_item_holdout.empty:
        logger.error("No se pudo construir item-item de holdout -- se aborta el backtest del ranker.")
        return

    canastas_plain = construir_canastas(df_test_b)
    baseline_metrics = evaluar_estrategia(
        lambda ctx, k, r=item_item_holdout: recomendar_desde_reglas(r, ctx, k), canastas_plain, precios=catalogo_precios,
    )
    logger.info(f"  > LÍNEA BASE (item-item, fresca sobre este test set): {baseline_metrics.to_dict()}")

    # Features del re-ranking calculadas TODAS a T=t_split (no por-transacción exacta):
    # es un límite superior conservador -- ninguna fila usa información posterior al
    # corte de todo el test set, evitando cualquier fuga dentro de la ventana de test.
    hist_at_split = tx.loc[tx["fecha"] <= t_split]
    catalogo_economia = calcular_economia_catalogo(catalogo)
    rfm_at_split = calcular_rfm_a_corte(hist_at_split, t_split)
    ventas_ventanas_at_split = calcular_ventas_por_producto_ventanas(hist_at_split, t_split)
    sucursal_habitual_at_split = hist_at_split.groupby("cliente_sk")["sucursal_sk"].agg(lambda s: s.mode().iat[0])
    contexto_at_split = (
        hist_at_split.sort_values("fecha").groupby("cliente_sk")["codart"]
        .apply(lambda s: list(dict.fromkeys(s.tolist()[::-1]))[:5])
    )
    grupos_cliente = hist_at_split.groupby("cliente_sk")
    rfm_para_modelos = rfm_at_split.reindex(columns=rfm_cols)
    p_abandono_map = pd.Series(
        churn_model.predict_proba(rfm_at_split[rfm_cols].fillna(0.0))[:, 1], index=rfm_at_split.index,
    ).to_dict() if not rfm_at_split.empty else {}
    segmento_map = pd.Series(
        segmentation_pipeline.predict(rfm_at_split[["recency", "frequency", "monetary_value"]].fillna(0.0)),
        index=rfm_at_split.index,
    ).to_dict() if not rfm_at_split.empty else {}

    def _reranker(candidatos: list[str], cliente_sk, _fecha) -> list[str]:
        if not candidatos:
            return []
        hist_cliente = grupos_cliente.get_group(cliente_sk) if cliente_sk in grupos_cliente.groups else hist_at_split.iloc[0:0]
        rfm_cliente = rfm_at_split.loc[cliente_sk] if cliente_sk in rfm_at_split.index else pd.Series(dtype=float)
        sucursal_cliente = sucursal_habitual_at_split.get(cliente_sk, "desconocida")
        contexto = contexto_at_split.get(cliente_sk, [])
        candidatos_validos = [c for c in candidatos if c in catalogo_economia.index]
        if not candidatos_validos:
            return []
        feats = construir_features_candidatos(
            hist_cliente, hist_at_split, candidatos_validos, contexto, t_split,
            item_item_holdout, catalogo_economia, ventas_ventanas_at_split, rfm_cliente, sucursal_cliente,
        )
        feats["p_abandono"] = p_abandono_map.get(cliente_sk, float(np.mean(list(p_abandono_map.values()))) if p_abandono_map else 0.5)
        feats["segmento_rfm"] = segmento_map.get(cliente_sk, -1)
        X = preparar_matriz_features(feats, sucursal_valores)
        X = X.reindex(columns=feature_cols, fill_value=0)
        proba = model.predict_proba(X)[:, 1]
        return list(feats.index[np.argsort(-proba)])

    canastas_ctx = construir_canastas_con_contexto(df_test_b)
    reranked_metrics = evaluar_estrategia_reranked(
        lambda ctx, k, r=item_item_holdout: recomendar_desde_reglas(r, ctx, k),
        _reranker, canastas_ctx, precios=catalogo_precios, pool_candidatos=RANKER_TOP_CANDIDATOS,
    )
    logger.info(f"  > RANKER (re-ranking sobre los mismos candidatos item-item): {reranked_metrics.to_dict()}")

    p5_ranker = reranked_metrics.precision_at.get(5, 0.0)
    cobertura_ranker = reranked_metrics.cobertura
    p5_baseline_fresco = baseline_metrics.precision_at.get(5, 0.0)
    cobertura_baseline_fresco = baseline_metrics.cobertura

    # Regla de decisión FIJADA ANTES de ver resultados (§2.4 del plan): supera la cifra
    # histórica Y la línea base fresca de este mismo test set, sin degradar cobertura.
    promovido = (
        p5_ranker >= RANKER_LINEA_BASE_PRECISION_AT_5
        and p5_ranker >= p5_baseline_fresco
        and cobertura_ranker >= RANKER_LINEA_BASE_COBERTURA * 0.99
        and cobertura_ranker >= cobertura_baseline_fresco * 0.99
    )
    razon = (
        f"Precision@5 ranker={p5_ranker:.4f} vs. línea base histórica={RANKER_LINEA_BASE_PRECISION_AT_5:.4f} "
        f"y fresca={p5_baseline_fresco:.4f}; cobertura ranker={cobertura_ranker:.4f} vs. histórica="
        f"{RANKER_LINEA_BASE_COBERTURA:.4f} y fresca={cobertura_baseline_fresco:.4f}. "
        f"{'PROMOVIDO' if promovido else 'NO PROMOVIDO (se mantiene el motor item-item actual sin ranker)'}."
    )
    logger.info(f"  > DECISIÓN DE PROMOCIÓN: {razon}")

    metrics_finales = {
        **metrics_holdout,
        "precision_at_5": p5_ranker,
        "recall_at_5": reranked_metrics.recall_at.get(5, 0.0),
        "hit_rate_5": reranked_metrics.hit_rate_5,
        "cobertura": cobertura_ranker,
    }
    ruta = save_cross_sell_ranker_model(
        model,
        metrics=metrics_finales,
        features=feature_cols,
        data_range={
            "cortes_entrenamiento": len(cortes_unicos),
            "corte_min": str(cortes_unicos[0].date()) if cortes_unicos else None,
            "corte_max": str(cortes_unicos[-1].date()) if cortes_unicos else None,
            "n_filas_dataset": len(dataset),
        },
        extra_meta={
            "backtest_linea_base_item_item_fresco": baseline_metrics.to_dict(),
            "backtest_ranker_reranking": reranked_metrics.to_dict(),
            "decision_promocion": {"promovido": promovido, "razon": razon},
            "sucursal_valores_entrenamiento": sucursal_valores,
        },
    )

    # Gating de esta primera corrida: comparación NO es contra un `cross_sell_ranker`
    # anterior (no existe, es el primer entrenamiento) sino contra la línea base del
    # item-item, ya evaluada arriba (regla propia del plan §2.4, distinta del gating
    # estándar de `promotion.py` que compara versión-contra-versión del MISMO modelo).
    # Solo si promueve se agrega la clave a registry.json -- así `retrain_all.py`/
    # `promotion.py` heredan el gating estándar version-a-version en reentrenamientos futuros.
    if promovido:
        registry_path = os.path.join(models_dir, "registry.json")
        with open(registry_path, "r", encoding="utf-8") as f:
            registry = json.load(f)
        meta_path = os.path.splitext(ruta)[0] + ".meta.json"
        with open(meta_path, "r", encoding="utf-8") as f:
            version = json.load(f)["version"]
        registry["cross_sell_ranker"] = {
            "champion": "cross_sell_ranker.pkl",
            "version": version,
            "metric_gate": {"name": "precision_at_5", "direction": "maximize", "min_delta": -0.005},
        }
        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump(registry, f, ensure_ascii=False, indent=2)
            f.write("\n")
        logger.info("  > 'cross_sell_ranker' agregado a registry.json como campeón (Fase 2 promovida).")

        contrato_path = os.path.join(os.path.dirname(__file__), "contracts", "models", "cross_sell_ranker.json")
        with open(contrato_path, "r", encoding="utf-8") as f:
            contrato = json.load(f)
        contrato["status"] = "active"
        contrato["notes"] = (
            f"PROMOVIDO (Fase 2, {pd.Timestamp.now(tz='UTC').date()}). {razon} "
            f"Ganador: {type(model).__name__}. Dataset: {len(dataset)} filas, "
            f"{len(cortes_unicos)} cortes ({cortes_unicos[0].date()}..{cortes_unicos[-1].date()})."
        )
        with open(contrato_path, "w", encoding="utf-8") as f:
            json.dump(contrato, f, ensure_ascii=False, indent=2)
            f.write("\n")
        logger.info("  > Contrato cross_sell_ranker.json actualizado a status=active.")
    else:
        logger.warning("  > Ranker NO promovido: el módulo de Venta Cruzada se queda con el motor item-item actual.")
        # Sin campeón previo que revertir (es el primer intento) y sin entrada en
        # registry.json: dejar el .pkl/.meta.json en la raíz de ml/models/ lo dejaría
        # huérfano (test_registry.py::test_ningun_pkl_en_raiz_es_huerfano) y el backend
        # nunca debe poder cargarlo por accidente. La versión ya quedó archivada en
        # models/versions/cross_sell_ranker/ (save_artifact, registry_key) -- el registro
        # histórico se conserva ahí, solo se retira el archivo "estable" de la raíz.
        meta_ruta = os.path.splitext(ruta)[0] + ".meta.json"
        for candidato in (ruta, meta_ruta):
            if os.path.exists(candidato):
                os.remove(candidato)
        logger.info("  > cross_sell_ranker.pkl retirado de la raíz de ml/models/ (queda archivado en versions/).")

    reporte_path = os.path.join(os.path.dirname(__file__), "REPORTE_MEJORA_MODELOS.md")
    with open(reporte_path, "a", encoding="utf-8") as f:
        f.write(
            f"\n\n## cross_sell_ranker -- {pd.Timestamp.now(tz='UTC').isoformat()}\n\n"
            f"Fase 2 de docs/features/plan_refactor_venta_cruzada_ia.md (7º modelo, ranking sobre "
            f"candidatos item-item). Dataset: {len(dataset)} filas ({dataset['label'].mean():.2%} positivos), "
            f"{len(cortes_unicos)} cortes mensuales ({cortes_unicos[0].date()}..{cortes_unicos[-1].date()}), "
            f"split cronológico {len(cortes_train)}/{len(cortes_unicos)} cortes train/{len(cortes_unicos)-len(cortes_train)} test.\n\n"
            f"Ganador de la competencia: **{type(model).__name__}**. Métricas de clasificación (holdout): "
            f"{ {k: round(v, 4) for k, v in metrics_holdout.items()} }.\n\n"
            f"**Backtest de ranking (mismo protocolo, auditoría 25):**\n"
            f"- Línea base item-item (fresca, mismo test set): {baseline_metrics.to_dict()}\n"
            f"- Ranker (re-ranking de los mismos candidatos): {reranked_metrics.to_dict()}\n"
            f"- Línea base histórica documentada (contrato recommendation v0.2.0): "
            f"Precision@5={RANKER_LINEA_BASE_PRECISION_AT_5}, cobertura={RANKER_LINEA_BASE_COBERTURA}\n\n"
            f"**Decisión (regla fijada antes de ver resultados, §2.4 del plan):** "
            f"{'PROMOVIDO -- ' if promovido else 'NO PROMOVIDO -- '}{razon}\n"
        )
    logger.info("Ranker de Venta Cruzada: entrenamiento y backtest completados.\n")


def run_ml_pipeline():
    logger.info("=== INICIANDO EXPERIMENTO ML OPS ORQUESTADO ===")
    extractor = SalesTimeSerieExtractor()

    train_demand_forecasting(extractor)
    train_customer_segmentation(extractor)
    train_customer_churn(extractor)
    train_recommendations(extractor)
    train_cross_sell_ranker(extractor)

    logger.info("=== ML PIPELINE ORQUESTADO COMPLETADO EXITOSAMENTE ===")


if __name__ == "__main__":
    run_ml_pipeline()
