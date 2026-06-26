"""
@layer services
Servicio de dominio de recomendaciones.

Orquesta el pipeline: pre-filtro espacial PostGIS → ruteo OSRM por modo con
Circuit Breaker (fallback Haversine) → inferencia XGBoost (vía
`ml_pipeline.predictor`) → cálculo de `time_saved` y ranking por `match_score`.

Consumido por `app/api/recommend.py` (capa de routers).
"""

import os
import math
import time
import requests
from geoalchemy2.functions import ST_DWithin, ST_Distance

from app.models.property import Property
from app.models.favorite import Favorite
from ml_pipeline.predictor import predictor


# --- Funciones auxiliares geométricas ---
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
        speed = 4.5  # km/h
    elif mode_lower == 'cycling' or mode_lower == 'bicicleta':
        speed = 12.0  # km/h
    else:
        speed = 15.0  # km/h (Promedio real en Lima con tráfico)

    return (real_dist / speed) * 60


# routing.openstreetmap.de corre una instancia OSRM por perfil (mismo servicio que usa el frontend).
# El perfil real lo define la instancia (routed-car/bike/foot), no el path (siempre /route/v1/driving).
# Configurable vía .env; los defaults apuntan al servicio público por perfil.
OSRM_BASE_URLS = {
    "driving": os.getenv("OSRM_DRIVING_URL", "https://routing.openstreetmap.de/routed-car/route/v1/driving"),
    "cycling": os.getenv("OSRM_CYCLING_URL", "https://routing.openstreetmap.de/routed-bike/route/v1/driving"),
    "walking": os.getenv("OSRM_WALKING_URL", "https://routing.openstreetmap.de/routed-foot/route/v1/driving"),
}


def get_osrm_route(lat1, lon1, lat2, lon2, mode):
    # Ya viene en inglés (driving, walking, cycling)
    profile = mode.lower()

    # Cada modo usa su propia instancia OSRM con el perfil correcto
    base_url = OSRM_BASE_URLS.get(profile, OSRM_BASE_URLS["driving"])
    url = f"{base_url}/{lon1},{lat1};{lon2},{lat2}?overview=false"

    response = requests.get(url, timeout=5)
    response.raise_for_status()

    data = response.json()
    if data.get('code') != 'Ok' or not data.get('routes'):
        raise ValueError("No route found")

    route = data['routes'][0]
    distance_km = route['distance'] / 1000.0
    duration_min = route['duration'] / 60.0

    return distance_km, duration_min


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
    # Calcular tiempo de viaje actual si tiene casa guardada (para field time_saved_mins)
    current_commute_time = None
    if user_home_lat is not None and user_home_lon is not None:
        try:
            _, current_commute_time = get_osrm_route(user_home_lat, user_home_lon, work_lat, work_lon, mode)
        except Exception:
            dist = haversine(user_home_lat, user_home_lon, work_lat, work_lon)
            current_commute_time = simulate_commute_time(dist, mode)

    budget_limit = budget * BUDGET_TOLERANCE

    # PostGIS hace filtro de radio + distancia + orden en una sola consulta indexada (GIST).
    # ST_Distance sobre geography devuelve metros → lo convertimos a km.
    # casas_en_radio: todas en el radio sin filtro de presupuesto → para calcular min_price_in_area
    work_wkt = f'SRID=4326;POINT({work_lon} {work_lat})'
    dist_km_col = (ST_Distance(Property.location, work_wkt) / 1000.0).label("dist_km")

    query = db.query(Property, dist_km_col).filter(
        Property.status == "approved",
        Property.location.isnot(None),
    )
    if max_distance_km is not None:
        query = query.filter(ST_DWithin(Property.location, work_wkt, max_distance_km * 1000))

    # Ordenado por distancia ascendente: OSRM procesa primero las más cercanas
    # y el circuit breaker actúa sobre las más lejanas si hay problemas.
    casas_en_radio = query.order_by(dist_km_col).all()  # [(Property, dist_km), ...]

    if not casas_en_radio:
        if max_distance_km:
            msg = f"No encontramos viviendas disponibles en un radio de {int(max_distance_km)} km."
        else:
            msg = "No hay viviendas disponibles en el sistema."
        return {"results": [], "total": 0, "message": msg, "min_price_in_area": None}

    # casas_candidatas: en radio Y dentro del presupuesto → las que evalúa XGBoost.
    # La distancia (dist_km) ya viene calculada y ordenada desde PostGIS.
    casas_candidatas = []
    for c, dist_km in casas_en_radio:
        if not c.price:
            continue
        if _to_pen(c.price, c.currency) <= budget_limit:
            casas_candidatas.append((dist_km, c))

    if not casas_candidatas:
        min_price = round(min(_to_pen(c.price, c.currency) for c, _ in casas_en_radio), 2)
        return {
            "results": [], "total": 0,
            "message": f"Ninguna vivienda en esta zona entra en tu presupuesto. Las más económicas parten desde S/ {min_price:,.0f}.",
            "min_price_in_area": min_price,
        }

    # (Ya vienen ordenadas por distancia desde la consulta PostGIS)

    # Armar features exactamente como el dataset de entrenamiento
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

    # Inferencia centralizada en ml_pipeline.predictor
    predicciones = predictor.predict_scores(datos_dict)

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
