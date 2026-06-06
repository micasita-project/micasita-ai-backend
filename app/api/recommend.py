from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
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
from app.models.recommendation_preference import RecommendationPreference
from app.models.recommendation_history import RecommendationHistory
from app.models.favorite import Favorite
from app.core.security import get_current_user, get_current_user_optional
from app.schemas.recommend import RecommendationPageResponse, GuestRecommendRequest
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
    """
    Simula el tiempo de viaje cuando OSRM falla.
    Usa un factor de 1.4 para compensar que Haversine es en línea recta.
    """
    routing_factor = 1.4
    real_dist = distance_km * routing_factor
    
    mode_lower = mode.lower()
    if mode_lower == 'walking' or mode_lower == 'caminando':
        speed = 4.5 # km/h
    elif mode_lower == 'cycling' or mode_lower == 'bicicleta':
        speed = 12.0 # km/h
    else: 
        speed = 15.0 # km/h (Promedio real en Lima con tráfico)
        
    return (real_dist / speed) * 60

def get_osrm_route(lat1, lon1, lat2, lon2, mode):
    # Ya viene en inglés (driving, walking, cycling)
    profile = mode.lower()
    
    # Usamos la API Publica de OSRM
    url = f"http://router.project-osrm.org/route/v1/{profile}/{lon1},{lat1};{lon2},{lat2}?overview=false"
    
    response = requests.get(url, timeout=5) # Mas tiempo para API publica
    response.raise_for_status()
    
    data = response.json()
    if data.get('code') != 'Ok' or not data.get('routes'):
        raise ValueError("No route found")
        
    route = data['routes'][0]
    distance_km = route['distance'] / 1000.0
    duration_min = route['duration'] / 60.0
    
    return distance_km, duration_min
# -----------------------------------------------------------------------------------------

BUDGET_TOLERANCE = 1.15  # Mostrar casas hasta un 15% sobre el presupuesto declarado
USD_TO_PEN = float(os.getenv("USD_TO_PEN", "3.75"))  # Tipo de cambio configurable vía .env


def _to_pen(price: float, currency: str | None) -> float:
    """Convierte price a soles. Si currency es USD multiplica por el tipo de cambio."""
    if currency and currency.upper() == "USD":
        return price * USD_TO_PEN
    return price

def generar_recomendacion(
    work_lat, work_lon, budget, mode, db,
    max_distance_km=None,
    user_home_lat=None, user_home_lon=None,
    user_id=None
):
    import time

    casas = db.query(Property).filter(Property.status == "approved").all()
    if not casas:
        return {"results": [], "total": 0, "message": "No hay viviendas disponibles en el sistema.", "min_price_in_area": None}

    # Calcular tiempo de viaje actual si tiene casa guardada (para field time_saved_mins)
    current_commute_time = None
    if user_home_lat is not None and user_home_lon is not None:
        try:
            _, current_commute_time = get_osrm_route(user_home_lat, user_home_lon, work_lat, work_lon, mode)
        except Exception:
            dist = haversine(user_home_lat, user_home_lon, work_lat, work_lon)
            current_commute_time = simulate_commute_time(dist, mode)

    budget_limit = budget * BUDGET_TOLERANCE

    # Clasificar casas:
    # - casas_en_radio: todas en el radio elegido (sin filtro de presupuesto) → para calcular min_price_in_area
    # - casas_candidatas: en radio Y dentro del presupuesto → las que evalúa el modelo
    casas_en_radio = []
    casas_candidatas = []
    for c in casas:
        if not c.price:
            continue
        straight_dist = haversine(work_lat, work_lon, c.latitude, c.longitude)
        if max_distance_km is not None and straight_dist > max_distance_km:
            continue
        casas_en_radio.append(c)
        if _to_pen(c.price, c.currency) <= budget_limit:
            casas_candidatas.append((straight_dist, c))

    if not casas_en_radio:
        radio_txt = f"{int(max_distance_km)} km" if max_distance_km else "la zona seleccionada"
        return {"results": [], "total": 0, "message": f"No encontramos viviendas disponibles en un radio de {radio_txt}.", "min_price_in_area": None}

    if not casas_candidatas:
        min_price = round(min(_to_pen(c.price, c.currency) for c in casas_en_radio), 2)
        return {
            "results": [], "total": 0,
            "message": f"Ninguna vivienda en esta zona entra en tu presupuesto. Las más económicas parten desde S/ {min_price:,.0f}.",
            "min_price_in_area": min_price,
        }

    # Ordenar por distancia para que OSRM procese primero las más cercanas
    # y el circuit breaker actúe sobre las más lejanas si hay problemas
    casas_candidatas.sort(key=lambda x: x[0])

    # Armar DataFrame con pandas exactamente como el dataset de entrenamiento
    datos_dict = []
    lista_casas = []

    osrm_timeouts = 0

    # Normalizar modo para XGBoost (English)
    mode_english = mode.lower()

    for straight_dist, c in casas_candidatas:
        try:
            if osrm_timeouts >= 5:
                # Circuit breaker: demasiados fallos consecutivos, usar Haversine para el resto
                raise Exception("OSRM Circuit Breaker activo")

            dist_km, tiempo = get_osrm_route(work_lat, work_lon, c.latitude, c.longitude, mode)
            osrm_timeouts = 0  # reset en cada éxito

            # Delay cortés para no saturar la API pública de OSRM
            time.sleep(0.05)

        except Exception as e:
            if "Timeout" in str(type(e)) or "Timeout" in str(e) or "Circuit Breaker" in str(e):
                osrm_timeouts += 1
            # Fallback a Haversine si OSRM falla
            dist_km = straight_dist
            tiempo = simulate_commute_time(dist_km, mode)

        datos_dict.append({
            "precio_alquiler": _to_pen(c.price, c.currency),
            "area_m2": float(c.total_area_sqm),
            "presupuesto_usuario": float(budget),
            "distancia_km_simulada": dist_km,
            "tiempo_viaje_min": tiempo,
            "modo_transporte": mode_english
        })

        # Calcular ahorro de tiempo vs vivienda actual
        time_saved = None
        if current_commute_time is not None:
            time_saved = current_commute_time - tiempo

        lista_casas.append({"prop": c, "tiempo": tiempo, "time_saved": time_saved})

    df_eval = pd.DataFrame(datos_dict)

    # Aplicar el mismo One-Hot Encoding que en el entrenamiento
    df_eval = pd.get_dummies(df_eval, columns=['modo_transporte'])

    # Asegurarnos de que las columnas coincidan exactamente con las del modelo entrenado
    for col in model_columns:
        if col not in df_eval.columns:
            df_eval[col] = 0

    # Reordenar para que XGBoost no se confunda
    df_eval = df_eval[model_columns]

    # Inferencia
    predicciones = recommender.predict(df_eval)

    # Obtener favoritos del usuario si está logueado
    fav_ids = set()
    if user_id:
        fav_ids = set(row[0] for row in db.query(Favorite.property_id).filter(Favorite.user_id == user_id).all())

    # Combinar y devolver todos los resultados ordenados por score (sin límite artificial)
    resultados = []
    for idx, data in enumerate(lista_casas):
        score_crudo = float(predicciones[idx])
        score_limpio = max(0, min(100, round(score_crudo, 1)))

        prop = data["prop"]
        prop.is_favorite = prop.id in fav_ids

        resultados.append({
            "property": prop,
            "predicted_time_min": round(data["tiempo"]),
            "match_score": score_limpio,
            "time_saved_mins": round(data["time_saved"]) if data["time_saved"] is not None else None
        })

    ordered = sorted(resultados, key=lambda x: x["match_score"], reverse=True)
    return {"results": ordered, "total": len(ordered), "message": None, "min_price_in_area": None}


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
                "features": prop.features if prop.features else [],
                "source_url": prop.source_url,
                "status": prop.status
            },
            "match_score": r["match_score"],
            "predicted_time_min": r["predicted_time_min"],
            "time_saved_mins": r.get("time_saved_mins"),
        })
    return serialized


# ── Endpoints ────────────────────────────────────────────────────

@router.post(
    "/guest",
    response_model=RecommendationPageResponse,
    summary="Recomendaciones para visitante",
    response_description="Viviendas recomendadas con mensaje explicativo si el presupuesto no alcanza en la zona",
)
def recommend_for_guest(req: GuestRecommendRequest, current_user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    """
    Genera recomendaciones sin necesidad de cuenta registrada.

    Requiere pasar manualmente las coordenadas del trabajo, presupuesto y medio de transporte.
    Si se envía token JWT, el campo `is_favorite` refleja el estado real del usuario.
    Si se envían `home_lat`/`home_lon`, calcula el campo `time_saved_mins`.
    """
    return generar_recomendacion(
        req.work_lat, req.work_lon, req.budget, req.preferred_transportation, db,
        max_distance_km=req.max_distance_km,
        user_home_lat=req.home_lat,
        user_home_lon=req.home_lon,
        user_id=current_user.id if current_user else None
    )


@router.post(
    "/workplaces/{workplace_id}/generate",
    response_model=RecommendationPageResponse,
    summary="Generar recomendaciones (con historial)",
    response_description="Viviendas recomendadas por XGBoost, guardadas en historial",
    responses={
        400: {"description": "El workplace no tiene preferencias de recomendación configuradas"},
        404: {"description": "Workplace no encontrado"},
    },
)
def generate_recommendations(
    workplace_id: int,
    max_distance_km: float = 10.0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Ejecuta el modelo XGBoost usando las preferencias guardadas del workplace y almacena el resultado.

    Cada llamada crea una nueva entrada en el historial (no sobrescribe).
    El parámetro `max_distance_km` de query sobreescribe el valor de las preferencias si se envía explícitamente.
    Devuelve todos los resultados que cumplan presupuesto y distancia, sin límite artificial.
    Usar con moderación — cada llamada consulta OSRM por cada vivienda candidata.
    """
    work = db.query(Workplace).filter(Workplace.id == workplace_id, Workplace.user_id == current_user.id).first()
    if not work:
        raise HTTPException(status_code=404, detail="Lugar de trabajo no encontrado")

    pref = db.query(RecommendationPreference).filter(RecommendationPreference.workplace_id == workplace_id).first()
    if not pref:
        raise HTTPException(status_code=400, detail="Faltan preferencias de recomendación para este lugar de trabajo")

    # Usar max_distance_km de las preferencias si no se envía explícitamente por query
    dist = max_distance_km if max_distance_km != 10.0 else pref.max_distance_km

    # Ejecutar IA
    resultados = generar_recomendacion(
        work.work_lat, work.work_lon, pref.budget, pref.preferred_transportation, db,
        max_distance_km=dist,
        user_home_lat=current_user.home_lat,
        user_home_lon=current_user.home_lon,
        user_id=current_user.id
    )
    
    # Serializar y guardar en historial (INSERT, no UPDATE)
    serialized = _serialize_results(resultados["results"])
    history_entry = RecommendationHistory(
        workplace_id=workplace_id,
        results=json.dumps(serialized)
    )
    db.add(history_entry)
    db.commit()
    db.refresh(history_entry)
    
    return resultados


@router.get(
    "/workplaces/{workplace_id}/latest",
    response_model=RecommendationPageResponse,
    summary="Última recomendación (caché)",
    response_description="Última recomendación guardada con is_favorite actualizado en tiempo real",
    responses={
        404: {"description": "Workplace no encontrado o sin recomendaciones guardadas"},
    },
)
def get_latest_recommendations(
    workplace_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Devuelve la última recomendación guardada sin ejecutar el modelo XGBoost.

    El campo `is_favorite` se actualiza en tiempo real aunque el caché sea antiguo.
    Usar este endpoint para la carga inicial de la pantalla de resultados.
    """
    work = db.query(Workplace).filter(Workplace.id == workplace_id, Workplace.user_id == current_user.id).first()
    if not work:
        raise HTTPException(status_code=404, detail="Lugar de trabajo no encontrado")
    
    latest = db.query(RecommendationHistory)\
        .filter(RecommendationHistory.workplace_id == workplace_id)\
        .order_by(RecommendationHistory.created_at.desc())\
        .first()
    
    if not latest:
        raise HTTPException(status_code=404, detail="No hay recomendaciones guardadas. Genera una primero.")
    
    results = json.loads(latest.results)
    
    # Actualizar is_favorite ya que el cache puede estar viejo
    fav_ids = set(row[0] for row in db.query(Favorite.property_id).filter(Favorite.user_id == current_user.id).all())
    for r in results:
        r["property"]["is_favorite"] = r["property"]["id"] in fav_ids

    return {"results": results, "total": len(results), "message": None, "min_price_in_area": None}


@router.get(
    "/workplaces/{workplace_id}/history",
    summary="Historial de recomendaciones",
    response_description="Todas las sesiones de recomendación generadas para el workplace",
    responses={404: {"description": "Workplace no encontrado"}},
)
def get_recommendation_history(
    workplace_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Devuelve todas las sesiones de recomendación generadas para un workplace, ordenadas de más reciente a más antigua."""
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
@router.get(
    "/workplaces/{workplace_id}",
    response_model=RecommendationPageResponse,
    summary="[Deprecated] Recomendaciones directas sin historial",
    response_description="Recomendaciones generadas (no se guardan)",
    deprecated=True,
    responses={
        400: {"description": "Sin preferencias configuradas para el workplace"},
        404: {"description": "Workplace no encontrado"},
    },
)
def recommend_for_logged_user(workplace_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    **Deprecado.** Ejecuta XGBoost sin guardar en historial.

    Usar `POST /recommend/workplaces/{workplace_id}/generate` en su lugar.
    """
    work = db.query(Workplace).filter(Workplace.id == workplace_id, Workplace.user_id == current_user.id).first()
    if not work:
        raise HTTPException(status_code=404, detail="Lugar de trabajo no encontrado")
        
    pref = db.query(RecommendationPreference).filter(RecommendationPreference.workplace_id == workplace_id).first()
    if not pref:
        raise HTTPException(status_code=400, detail="Faltan preferencias de recomendación para este lugar de trabajo")
        
    return generar_recomendacion(
        work.work_lat, 
        work.work_lon, 
        pref.budget, 
        pref.preferred_transportation, 
        db,
        user_home_lat=current_user.home_lat,
        user_home_lon=current_user.home_lon
    )
