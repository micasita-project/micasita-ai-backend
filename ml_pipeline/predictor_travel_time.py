"""
Predictor del tiempo de viaje REAL (con tráfico), entrenado en
`ml_pipeline/train_travel_time.py` sobre etiquetas de TomTom.

Reemplaza el uso de OSRM "a secas" para el tiempo mostrado al usuario: OSRM da
tiempo de flujo libre (sin tráfico); este modelo corrige ese número según modo,
hora, día y geografía relativa. TomTom no se llama nunca desde aquí ni desde
producción — solo se usó una vez, para generar los datos de entrenamiento.

No confundir con `ml_pipeline/predictor.py` (el modelo viejo, circular, que
predecía `afinidad_score` a partir de las mismas variables que lo generaban).
Ese modelo queda fuera del pipeline de recomendación.
"""

import os
import joblib
import pandas as pd
import numpy as np
import xgboost as xgb

MODEL_PATH = "ml_pipeline/model/xgboost_travel_time.json"
FEATURES_PATH = "ml_pipeline/model/travel_time_features.pkl"

NUM_COLS = [
    "osrm_min", "osrm_dist_km", "hora", "dia_semana", "hacia_el_centro",
    "work_dist_centro_km", "prop_dist_centro_km",
]


class TravelTimePredictor:
    def __init__(self, model_path: str = MODEL_PATH, features_path: str = FEATURES_PATH):
        self.model = xgb.XGBRegressor()
        self.columns: list = []
        self.disponible = os.path.exists(model_path) and os.path.exists(features_path)
        if self.disponible:
            self.model.load_model(model_path)
            self.columns = joblib.load(features_path)

    def predict_minutes(self, rows: list[dict]) -> list[float]:
        """
        Recibe filas con: osrm_min, osrm_dist_km, modo, hora, dia_semana,
        hacia_el_centro, work_dist_centro_km, prop_dist_centro_km.

        Devuelve el tiempo corregido en minutos (ya invertido el log1p del
        entrenamiento). Si el modelo no está disponible, devuelve `osrm_min`
        tal cual — degrada a "sin corrección", nunca revienta la recomendación.
        """
        if not rows:
            return []
        if not self.disponible:
            return [float(r["osrm_min"]) for r in rows]

        df = pd.DataFrame(rows)
        X = pd.get_dummies(df[NUM_COLS + ["modo"]], columns=["modo"])
        for col in self.columns:
            if col not in X.columns:
                X[col] = 0
        X = X[self.columns].astype(float)

        pred_log = self.model.predict(X)
        return [float(m) for m in np.expm1(pred_log)]


# Singleton, igual que ml_pipeline.predictor
predictor_travel_time = TravelTimePredictor()
