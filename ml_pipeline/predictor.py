"""
Predictor del modelo de recomendación (XGBoost).

Centraliza la carga del modelo entrenado y la inferencia de `match_score`.
El modelo y las columnas de features se cargan una sola vez al importar el
módulo (singleton `predictor`).
"""

import os
import joblib
import pandas as pd
import xgboost as xgb

MODEL_PATH = "ml_pipeline/model/xgboost_recommender.json"
FEATURES_PATH = "ml_pipeline/model/model_features.pkl"


class RecommenderModel:
    def __init__(self, model_path: str = MODEL_PATH, features_path: str = FEATURES_PATH):
        self.model = xgb.XGBRegressor()
        self.columns: list = []
        if os.path.exists(model_path):
            self.model.load_model(model_path)
        if os.path.exists(features_path):
            self.columns = joblib.load(features_path)

    def predict_scores(self, rows: list[dict]) -> list[float]:
        """
        Recibe filas con features crudas (incluyendo `modo_transporte`),
        aplica el mismo One-Hot Encoding y orden de columnas del entrenamiento
        y devuelve la lista de scores predichos.
        """
        df = pd.DataFrame(rows)
        df = pd.get_dummies(df, columns=["modo_transporte"])

        # Asegurar que estén todas las columnas del modelo, en el mismo orden
        for col in self.columns:
            if col not in df.columns:
                df[col] = 0
        df = df[self.columns]

        return [float(p) for p in self.model.predict(df)]


# Singleton cargado una vez al inicio
predictor = RecommenderModel()
