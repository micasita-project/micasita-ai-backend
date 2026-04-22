from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import os
import math
import random
import joblib
import pandas as pd
import xgboost as xgb
from app.core.database import get_db
from app.models.property import Property
from app.models.user import User
from app.core.security import get_current_user
from app.schemas.recommend import RecommendationResponse, GuestRecommendRequest

router = APIRouter(prefix="/recommend", tags=["IA Recomendaciones"])

# Cargar el cerebro XGBoost en memoria al arrancar
modelo_path = "ml_pipeline/model/xgboost_recommender.json"
features_path = "ml_pipeline/model/model_features.pkl"

recommender = xgb.XGBRegressor()
if os.path.exists(modelo_path):
    recommender.load_model(modelo_path)

model_columns = []
if os.path.exists(features_path):
    model_columns = joblib.load(features_path)

# --- Funciones auxiliares geométricas (Podras reemplazarlas por OpenStreetMap OSRM luego) ---
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def simulate_commute_time(distance_km, mode):
    if mode == 'Caminando':
        speed = 5.0  
    elif mode == 'Bicicleta':
        speed = 15.0 
    else: 
        speed = 20.0 
    return (distance_km / speed) * 60
# -----------------------------------------------------------------------------------------

def generar_recomendacion(work_lat, work_lon, budget, mode, db):
    casas = db.query(Property).all()
    if not casas:
        return []
    
    # Armar Dataframe con pandas exactamente como el dataset de entrenamiento
    datos_dict = []
    lista_casas = []
    
    for c in casas:
        if not c.price:
            continue
            
        dist_km = haversine(work_lat, work_lon, c.latitude, c.longitude)
        tiempo = simulate_commute_time(dist_km, mode)
        
        datos_dict.append({
            "precio_alquiler": float(c.price),
            "area_m2": float(c.total_area_sqm),
            "presupuesto_usuario": float(budget),
            "distancia_km_simulada": dist_km,
            "tiempo_viaje_min": tiempo,
            "modo_transporte": mode
        })
        lista_casas.append({"prop": c, "tiempo": tiempo})
        
    if not datos_dict:
        return []
        
    df_eval = pd.DataFrame(datos_dict)
    
    # Aplicar el mismo One-Hot Encoding que en el entrenamiento
    df_eval = pd.get_dummies(df_eval, columns=['modo_transporte'])
    
    # Asegurarnos de que las columnas coincidan exactamente añadiendo missing cols
    for col in model_columns:
        if col not in df_eval.columns:
            df_eval[col] = 0
            
    # Reordenar para que XGBoost no se confunda
    df_eval = df_eval[model_columns]
    
    # Inferencia! PREDECIR!
    predicciones = recommender.predict(df_eval)
    
    # Combinar resultados
    resultados = []
    for idx, data in enumerate(lista_casas):
        score_crudo = float(predicciones[idx])
        score_limpio = max(0, min(100, round(score_crudo, 1))) # limitar de 0 a 100
        
        resultados.append({
            "property": data["prop"],
            "predicted_time_min": round(data["tiempo"]),
            "match_score": score_limpio
        })
        
    # Ordenar por el que tenga mayor puntaje (El top recomendado primero)
    resultados = sorted(resultados, key=lambda x: x["match_score"], reverse=True)
    return resultados

@router.post("/guest", response_model=List[RecommendationResponse])
def recommend_for_guest(req: GuestRecommendRequest, db: Session = Depends(get_db)):
    """Si no está logueado, necesita pasar los 4 datos explícitamente"""
    return generar_recomendacion(req.work_lat, req.work_lon, req.budget, req.preferred_transportation, db)

from app.models.workplace import Workplace

@router.get("/workplaces/{workplace_id}", response_model=List[RecommendationResponse])
def recommend_for_logged_user(workplace_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Si está logueado, ¡solo presionó un trabajo! Sacamos los datos de ese Workplace"""
    work = db.query(Workplace).filter(Workplace.id == workplace_id, Workplace.user_id == current_user.id).first()
    if not work:
        raise HTTPException(status_code=404, detail="Lugar de trabajo no encontrado")
        
    return generar_recomendacion(
        work.work_lat, 
        work.work_lon, 
        work.budget, 
        work.preferred_transportation, 
        db
    )
