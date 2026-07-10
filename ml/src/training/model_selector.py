import logging
import pandas as pd
import numpy as np
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score, roc_auc_score, accuracy_score, classification_report
from sklearn.model_selection import RandomizedSearchCV, TimeSeriesSplit, StratifiedKFold
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier, HistGradientBoostingRegressor
import xgboost as xgb
import lightgbm as lgb
import catboost as cb
import optuna

logger = logging.getLogger("ML.ModelSelector")

def evaluate_reg(y_true, y_pred, is_log_transformed=False):
    if is_log_transformed:
        # El target Y_test se pasa puro, solo Y_pred contiene la proyección en logaritmo
        y_pred = np.expm1(y_pred)
    mse = mean_squared_error(y_true, y_pred)
    rmse = np.sqrt(mse)
    mae = mean_absolute_error(y_true, y_pred)
    r2 = r2_score(y_true, y_pred)
    return {"RMSE": rmse, "MAE": mae, "R2": r2}

def find_best_regression_model(X_train, y_train, is_log_transformed=False, cv_splits=3):
    logger.info("Iniciando competencia de Modelos de Regresión...")
    tscv = TimeSeriesSplit(n_splits=cv_splits)
    
    models = {
        "RandomForest": (RandomForestRegressor(random_state=42, n_jobs=-1), {
            'n_estimators': [50, 100, 200],
            'max_depth': [5, 10, None],
            'min_samples_leaf': [1, 5]
        }),
        "XGBoost": (xgb.XGBRegressor(random_state=42, objective='reg:squarederror', n_jobs=-1), {
            'n_estimators': [100, 200, 300],
            'learning_rate': [0.01, 0.05, 0.1],
            'max_depth': [3, 5, 7],
            'subsample': [0.8, 1.0]
        }),
        "LightGBM": (lgb.LGBMRegressor(random_state=42, n_jobs=-1, verbose=-1), {
            'n_estimators': [100, 200, 300],
            'learning_rate': [0.01, 0.05, 0.1],
            'num_leaves': [31, 50, 100],
            'max_depth': [-1, 5, 10]
        }),
        "CatBoost": (cb.CatBoostRegressor(random_state=42, verbose=0, thread_count=-1), {
            'iterations': [100, 200, 300],
            'learning_rate': [0.01, 0.05, 0.1],
            'depth': [4, 6, 8]
        }),
        "HistGradientBoosting": (HistGradientBoostingRegressor(random_state=42), {
            'max_iter': [100, 200],
            'learning_rate': [0.01, 0.1],
            'max_depth': [5, 10, None]
        })
    }
    
    best_overall_score = float('inf')
    best_model_info = None

    for name, (model, params) in models.items():
        logger.info(f"Evaluando {name} con RandomizedSearchCV...")
        # CatBoost y LightGBM ya paralelizan internamente (thread_count/n_jobs=-1 en el
        # propio estimador); si RandomizedSearchCV TAMBIÉN paraleliza con n_jobs=-1, las dos
        # capas de threads compiten por los mismos núcleos y el fit puede quedarse colgado
        # indefinidamente dentro de Docker (deadlock de paralelismo anidado, observado en la
        # reconstrucción del modelo de demanda: RandomForest/XGBoost tardaron segundos,
        # LightGBM no retornó tras 10+ minutos). Para ambos, el nivel externo va secuencial.
        search = RandomizedSearchCV(
            estimator=model,
            param_distributions=params,
            n_iter=5,
            cv=tscv,
            scoring='neg_root_mean_squared_error',
            random_state=42,
            n_jobs=1 if name in ("CatBoost", "LightGBM") else -1
        )
        try:
            search.fit(X_train, y_train)
            best_rmse = -search.best_score_
            logger.info(f"{name} Mejor RMSE de validación: {best_rmse:.4f}")
            if best_rmse < best_overall_score:
                best_overall_score = best_rmse
                best_model_info = (name, search.best_estimator_, search.best_params_)
        except Exception as e:
            logger.error(f"Fallo entrenar {name}: {e}")

    logger.info(f"\n+++ GANADOR ABSOLUTO REGRESIÓN: {best_model_info[0]} +++")
    logger.info(f"Mejores parámetros: {best_model_info[2]}")
    return best_model_info[1]

def find_best_classification_model(X_train, y_train, cv_splits=3):
    logger.info("Iniciando competencia de Modelos de Clasificación...")
    cv = StratifiedKFold(n_splits=cv_splits, shuffle=True, random_state=42)
    
    models = {
        "RandomForest": (RandomForestClassifier(random_state=42, n_jobs=-1, class_weight='balanced'), {
            'n_estimators': [50, 100],
            'max_depth': [5, 10],
            'min_samples_leaf': [1, 5]
        }),
        "XGBoost": (xgb.XGBClassifier(random_state=42, eval_metric='logloss', use_label_encoder=False, scale_pos_weight=y_train.value_counts()[0]/y_train.value_counts()[1]), {
            'n_estimators': [100, 200],
            'learning_rate': [0.01, 0.1],
            'max_depth': [3, 5]
        }),
        "LightGBM": (lgb.LGBMClassifier(random_state=42, class_weight='balanced', verbose=-1), {
            'n_estimators': [100, 200],
            'learning_rate': [0.01, 0.1],
            'num_leaves': [31, 50]
        }),
         "CatBoost": (cb.CatBoostClassifier(random_state=42, verbose=0, auto_class_weights='Balanced'), {
            'iterations': [100, 200],
            'learning_rate': [0.01, 0.1],
            'depth': [4, 6]
        }),
    }
    
    best_overall_score = -float('inf')
    best_model_info = None

    for name, (model, params) in models.items():
        logger.info(f"Evaluando {name}...")
        # Ver comentario equivalente en find_best_regression_model: CatBoost/LightGBM
        # paralelizan internamente, así que el search debe ir secuencial para evitar el
        # deadlock de paralelismo anidado dentro de Docker.
        search = RandomizedSearchCV(
            estimator=model,
            param_distributions=params,
            n_iter=4,
            cv=cv,
            scoring='roc_auc',
            random_state=42,
            n_jobs=1 if name in ("CatBoost", "LightGBM") else -1
        )
        try:
            search.fit(X_train, y_train)
            best_auc = search.best_score_
            logger.info(f"{name} Mejor ROC-AUC de validación: {best_auc:.4f}")
            if best_auc > best_overall_score:
                best_overall_score = best_auc
                best_model_info = (name, search.best_estimator_, search.best_params_)
        except Exception as e:
            logger.error(f"Fallo entrenar {name}: {e}")

    logger.info(f"\n+++ GANADOR ABSOLUTO CLASIFICACIÓN: {best_model_info[0]} +++")
    logger.info(f"Mejores parámetros: {best_model_info[2]}")
    return best_model_info[1]
