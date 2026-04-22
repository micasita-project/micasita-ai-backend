import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error
import numpy as np
import os
import joblib

def train_model(data_path, model_output_path):
    print("Iniciando el entrenamiento del modelo Micasita-AI...")
    
    if not os.path.exists(data_path):
        print(f"Error: No se encuentra el archivo {data_path}")
        return
        
    df = pd.read_csv(data_path)
    print(f"Filas cargadas en el laboratorio: {len(df)}")
    
    # Eliminamos vivienda_id y afinidad porque no son input para el modelo
    X = df.drop(columns=['vivienda_id', 'afinidad_score'], errors='ignore')
    y = df['afinidad_score']
    
    # Guardamos solo la columna string 'modo_transporte' y dropeamos el resto (textos extras, URLs introducidos)
    columnas_texto = X.select_dtypes(include=['object', 'string']).columns
    if 'modo_transporte' in columnas_texto:
        columnas_texto = columnas_texto.drop('modo_transporte')
    X = X.drop(columns=columnas_texto, errors='ignore')
    
    # XGBoost es matematico. Convertimos texto en binarios usando dummies
    X = pd.get_dummies(X, columns=['modo_transporte'])
    
    columnas_entrenamiento = X.columns.tolist()
    
    # Separacion
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    print("Entrenando XGBoost Regressor...")
    model = xgb.XGBRegressor(
        objective='reg:squarederror',
        n_estimators=100,
        learning_rate=0.1,
        max_depth=5,
        random_state=42
    )
    
    model.fit(X_train, y_train)
    
    predictions = model.predict(X_test)
    rmse = np.sqrt(mean_squared_error(y_test, predictions))
    mae = mean_absolute_error(y_test, predictions)
    
    print("\nResultados del Examen (Metricas de Evaluacion):")
    print(f"   - RMSE: {rmse:.2f} (Error cuadratico medio)")
    print(f"   - MAE: +/- {mae:.2f} puntos (En promedio, se equivocara por {mae:.1f} pts sobre 100)")
    
    os.makedirs(os.path.dirname(model_output_path), exist_ok=True)
    
    model.save_model(model_output_path)
    joblib.dump(columnas_entrenamiento, os.path.join(os.path.dirname(model_output_path), "model_features.pkl"))
    
    print(f"\nExito! Modelo guardado en: {model_output_path}")

if __name__ == '__main__':
    path_datos = "data/processed/training_dataset.csv" 
    path_modelo = "ml_pipeline/model/xgboost_recommender.json"
    
    train_model(path_datos, path_modelo)
