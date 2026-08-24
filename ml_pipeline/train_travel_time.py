"""
Entrena el modelo que reemplaza al pipeline circular.

Objetivo: `tt_min` (TomTom, tiempo real con tráfico) — una etiqueta OBSERVADA,
no una fórmula escrita a mano. Entrada: lo que ya se conoce antes de llamar a
TomTom (tiempo/distancia de OSRM, modo, hora, día, geografía relativa), que es
exactamente lo mismo que hay disponible en producción en el momento de inferir.

En producción, `predictor_travel_time.py` carga este modelo y corrige el tiempo
de OSRM sin volver a llamar a TomTom nunca — TomTom se usó una sola vez, aquí,
para generar la etiqueta.

Uso:
    python ml_pipeline/train_travel_time.py
"""

import os
import json

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import GroupKFold
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

DATA_PATH = "data/processed/travel_time_dataset.csv"
MODEL_PATH = "ml_pipeline/model/xgboost_travel_time.json"
FEATURES_PATH = "ml_pipeline/model/travel_time_features.pkl"

# Cota de sanidad, no un filtro de "usuarios reales". Un pair walking de 551 min
# es un dato correcto (TomTom lo midió), pero está tan lejos del rango que
# opera la app (radio de búsqueda acotado) que no aporta señal relevante y
# alarga la cola de la distribución sin necesidad. Se recorta el 1% más extremo
# por modo en vez de un número fijo, para no sesgar arbitrariamente cada modo.
RECORTE_PERCENTIL = 0.99

CAT_COLS = ["modo"]
NUM_COLS = [
    "osrm_min", "osrm_dist_km", "hora", "dia_semana", "hacia_el_centro",
    "work_dist_centro_km", "prop_dist_centro_km",
]


def cargar(path):
    df = pd.read_csv(path)
    antes = len(df)
    df = df[(df.osrm_status == "ok") & (df.tt_status == "ok")]
    print(f"filas válidas: {len(df)} de {antes} "
          f"({antes - len(df)} descartadas por fallo de OSRM o TomTom)")

    recortadas = 0
    partes = []
    for modo, g in df.groupby("modo"):
        tope = g.tt_min.quantile(RECORTE_PERCENTIL)
        keep = g[g.tt_min <= tope]
        recortadas += len(g) - len(keep)
        partes.append(keep)
    df = pd.concat(partes, ignore_index=True)
    print(f"recortado el {RECORTE_PERCENTIL:.0%} percentil por modo: "
          f"{recortadas} filas fuera del rango operativo de la app")
    return df


def construir_X(df, columnas_modelo=None):
    X = pd.get_dummies(df[NUM_COLS + CAT_COLS], columns=CAT_COLS)
    if columnas_modelo is not None:
        for c in columnas_modelo:
            if c not in X.columns:
                X[c] = 0
        X = X[columnas_modelo]
    return X.astype(float)


def evaluar(nombre, y_true_min, y_pred_min):
    mae = mean_absolute_error(y_true_min, y_pred_min)
    rmse = np.sqrt(mean_squared_error(y_true_min, y_pred_min))
    r2 = r2_score(y_true_min, y_pred_min)
    mape = np.mean(np.abs((y_true_min - y_pred_min) / y_true_min.clip(lower=1))) * 100
    print(f"  {nombre:<32} MAE {mae:6.2f} min   RMSE {rmse:6.2f} min   "
          f"MAPE {mape:5.1f} %   R² {r2:6.4f}")
    return mae


def main():
    df = cargar(DATA_PATH)
    X = construir_X(df)
    y_min = df.tt_min.values
    y_log = np.log1p(y_min)
    grupos = df.workplace_id.values  # generaliza a centros de trabajo no vistos

    params = dict(objective="reg:squarederror", n_estimators=400, learning_rate=0.05,
                  max_depth=5, subsample=0.85, colsample_bytree=0.85,
                  min_child_weight=3, reg_lambda=1.5, random_state=42)

    print(f"\n{'=' * 78}\nVALIDACIÓN CRUZADA (GroupKFold por centro de trabajo, 5 pliegues)\n{'=' * 78}")
    kf = GroupKFold(n_splits=5)
    pred_modelo = np.zeros(len(y_min))
    pred_lineal = np.zeros(len(y_min))
    for tr, te in kf.split(X, y_log, grupos):
        m = xgb.XGBRegressor(**params).fit(X.iloc[tr], y_log[tr])
        pred_modelo[te] = np.expm1(m.predict(X.iloc[te]))

        lr = LinearRegression().fit(X.iloc[tr], y_log[tr])
        pred_lineal[te] = np.expm1(lr.predict(X.iloc[te]))

    print()
    evaluar("OSRM crudo (línea base, sin modelo)", pd.Series(y_min), df.osrm_min.values)
    evaluar("Regresión lineal (log-tiempo)", pd.Series(y_min), pred_lineal)
    evaluar("XGBoost (log-tiempo)", pd.Series(y_min), pred_modelo)

    print(f"\n{'=' * 78}\nDESGLOSE POR MODO (el modelo entrenado arriba, out-of-fold)\n{'=' * 78}")
    for modo in df.modo.unique():
        mask = (df.modo == modo).values
        evaluar(f"XGBoost — {modo}", pd.Series(y_min[mask]), pred_modelo[mask])
        evaluar(f"  (referencia) OSRM crudo — {modo}",
                pd.Series(y_min[mask]), df.osrm_min.values[mask])

    print(f"\n{'=' * 78}\nENTRENAMIENTO FINAL (100% de los datos) Y GUARDADO\n{'=' * 78}")
    modelo_final = xgb.XGBRegressor(**params).fit(X, y_log)
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    modelo_final.save_model(MODEL_PATH)
    import joblib
    joblib.dump(list(X.columns), FEATURES_PATH)
    print(f"  modelo   : {MODEL_PATH}")
    print(f"  features : {FEATURES_PATH}")

    imp = modelo_final.get_booster().get_score(importance_type="gain")
    tot = sum(imp.values())
    print(f"\n{'=' * 78}\nIMPORTANCIA POR GANANCIA\n{'=' * 78}")
    for k, v in sorted(imp.items(), key=lambda x: -x[1]):
        print(f"  {k:<28} {v / tot * 100:5.1f} %")


if __name__ == "__main__":
    main()
