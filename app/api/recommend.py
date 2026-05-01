from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import os
import math
import json
import joblib
import pandas as pd
import xgboost as xgb
import requests
from app.core.config import settings
from app.core.database import get_db
from app.models.property import Property
from app.models.user import User
from app.models.workplace import Workplace
from app.models.recommendation_history import RecommendationHistory
from app.core.security import get_current_user
from app.schemas.recommend import RecommendationResponse, GuestRecommendRequest, RecommendationHistoryResponse
from app.schemas.property import PropertyResponse

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

# --- Funciones auxiliares geometricas ---
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

def get_osrm_route(lat1, lon1, lat2, lon2, mode):
    profile_map = {
        'Auto': 'driving',
        'Bicicleta': 'cycling',
        'Caminando': 'walking'
    }
    profile = profile_map.get(mode, 'driving')
    
    # Usamos la API Publica de OSRM
    url = f"http://router.project-osrm.org/route/v1/{profile}/{lon1},{lat1};{lon2},{lat2}?overview=false"
    
    response = requests.get(url, timeout=2)
    response.raise_for_status()
    
    data = response.json()
    if data.get('code') != 'Ok' or not data.get('routes'):
        raise ValueError("No route found")
        
    route = data['routes'][0]
    distance_km = route['distance'] / 1000.0
    duration_min = route['duration'] / 60.0
    
    return distance_km, duration_min
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
            
        try:
            dist_km, tiempo = get_osrm_route(work_lat, work_lon, c.latitude, c.longitude, mode)
        except Exception as e:
            # Fallback a Haversine si OSRM publico falla o se demora
            print(f"Fallback to Haversine due to: {e}")
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
    
    # Asegurarnos de que las columnas coincidan exactamente
    for col in model_columns:
        if col not in df_eval.columns:
            df_eval[col] = 0
            
    # Reordenar para que XGBoost no se confunda
    df_eval = df_eval[model_columns]
    
    # Inferencia
    predicciones = recommender.predict(df_eval)
    
    # Combinar resultados
    resultados = []
    for idx, data in enumerate(lista_casas):
        score_crudo = float(predicciones[idx])
        score_limpio = max(0, min(100, round(score_crudo, 1)))
        
        resultados.append({
            "property": data["prop"],
            "predicted_time_min": round(data["tiempo"]),
            "match_score": score_limpio
        })
        
    # Ordenar por el que tenga mayor puntaje
    resultados = sorted(resultados, key=lambda x: x["match_score"], reverse=True)
    return resultados


def _serialize_results(resultados):
    """Serializa los resultados de XGBoost a JSON para guardar en la DB."""
    serialized = []
    for r in resultados:
        prop = r["property"]
        serialized.append({
            "property": {
                "id": prop.id,
                "publisher_id": prop.publisher_id,
                "title": prop.title,
                "property_type": prop.property_type,
                "district": prop.district,
                "address": prop.address,
                "latitude": prop.latitude,
                "longitude": prop.longitude,
                "currency": prop.currency,
                "price": prop.price,
                "total_area_sqm": prop.total_area_sqm,
                "covered_area_sqm": prop.covered_area_sqm,
                "bedrooms": prop.bedrooms,
                "bathrooms": prop.bathrooms,
                "parking": prop.parking,
                "antiquity": prop.antiquity,
                "description": prop.description,
                "images": prop.images if prop.images else [],
                "source_url": prop.source_url,
            },
            "match_score": r["match_score"],
            "predicted_time_min": r["predicted_time_min"],
        })
    return serialized


# ── Endpoints ────────────────────────────────────────────────────

@router.post("/guest", response_model=List[RecommendationResponse])
def recommend_for_guest(req: GuestRecommendRequest, db: Session = Depends(get_db)):
    """Si no esta logueado, necesita pasar los 4 datos explicitamente"""
    return generar_recomendacion(req.work_lat, req.work_lon, req.budget, req.preferred_transportation, db)


@router.post("/workplaces/{workplace_id}/generate", response_model=List[RecommendationResponse])
def generate_recommendations(
    workplace_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Ejecuta XGBoost y guarda el resultado en el historial. Usar con moderacion."""
    work = db.query(Workplace).filter(Workplace.id == workplace_id, Workplace.user_id == current_user.id).first()
    if not work:
        raise HTTPException(status_code=404, detail="Lugar de trabajo no encontrado")
    
    # Ejecutar IA
    resultados = generar_recomendacion(work.work_lat, work.work_lon, work.budget, work.preferred_transportation, db)
    
    # Serializar y guardar en historial (INSERT, no UPDATE)
    serialized = _serialize_results(resultados)
    history_entry = RecommendationHistory(
        workplace_id=workplace_id,
        results=json.dumps(serialized)
    )
    db.add(history_entry)
    db.commit()
    db.refresh(history_entry)
    
    return resultados


@router.get("/workplaces/{workplace_id}/latest", response_model=List[RecommendationResponse])
def get_latest_recommendations(
    workplace_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Devuelve la ultima recomendacion cacheada SIN ejecutar IA."""
    work = db.query(Workplace).filter(Workplace.id == workplace_id, Workplace.user_id == current_user.id).first()
    if not work:
        raise HTTPException(status_code=404, detail="Lugar de trabajo no encontrado")
    
    latest = db.query(RecommendationHistory)\
        .filter(RecommendationHistory.workplace_id == workplace_id)\
        .order_by(RecommendationHistory.created_at.desc())\
        .first()
    
    if not latest:
        raise HTTPException(status_code=404, detail="No hay recomendaciones guardadas. Genera una primero.")
    
    return json.loads(latest.results)


@router.get("/workplaces/{workplace_id}/history")
def get_recommendation_history(
    workplace_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Devuelve todo el historial de recomendaciones para metricas y analisis."""
    work = db.query(Workplace).filter(Workplace.id == workplace_id, Workplace.user_id == current_user.id).first()
    if not work:
        raise HTTPException(status_code=404, detail="Lugar de trabajo no encontrado")
    
    history = db.query(RecommendationHistory)\
        .filter(RecommendationHistory.workplace_id == workplace_id)\
        .order_by(RecommendationHistory.created_at.desc())\
        .all()
    
    return [
        {
            "id": h.id,
            "workplace_id": h.workplace_id,
            "results": json.loads(h.results),
            "created_at": h.created_at,
        }
        for h in history
    ]


# Mantener el endpoint viejo para compatibilidad (redirige a generate)
@router.get("/workplaces/{workplace_id}", response_model=List[RecommendationResponse])
def recommend_for_logged_user(workplace_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """LEGACY: Ejecuta XGBoost directamente sin cachear. Usar /generate en su lugar."""
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
