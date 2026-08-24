"""
@layer services
Servicio de dominio de recomendaciones.

Orquesta el pipeline: pre-filtro espacial PostGIS → ruteo OSRM por modo con
Circuit Breaker (fallback Haversine) → corrección del tiempo con XGBoost (vía
`ml_pipeline.predictor_travel_time`, entrenado contra tráfico real de TomTom)
→ cálculo de `time_saved` y ranking por `match_score`.

`match_score` ya NO es un modelo de ML: es una función de utilidad explícita
(cercanía + presupuesto + área) documentada más abajo. El modelo de ML predice
el tiempo de viaje, que es lo único que de verdad hacía falta aprender —
cercanía y presupuesto se pueden calcular con una fórmula, el tiempo con
tráfico no.

Consumido por `app/api/recommend.py` (capa de routers).
"""

import math
import requests
from geoalchemy2.functions import ST_DWithin, ST_Distance

from app.core.config import settings
from app.models.property import Property
from app.models.favorite import Favorite
from ml_pipeline.predictor_travel_time import predictor_travel_time


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
    "driving": settings.OSRM_DRIVING_URL,
    "cycling": settings.OSRM_CYCLING_URL,
    "walking": settings.OSRM_WALKING_URL,
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


def get_osrm_route_with_geometry(lat1, lon1, lat2, lon2, mode):
    """
    Igual que get_osrm_route pero además devuelve la geometría de la ruta.

    Es la única función que pide geometría a OSRM. El front NUNCA debe llamar
    a OSRM directamente — la consume vía el endpoint de ruta de la API
    (app/api/recommend.py), que a su vez llama a esto.
    """
    profile = mode.lower()
    base_url = OSRM_BASE_URLS.get(profile, OSRM_BASE_URLS["driving"])
    url = f"{base_url}/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"

    response = requests.get(url, timeout=8)
    response.raise_for_status()

    data = response.json()
    if data.get('code') != 'Ok' or not data.get('routes'):
        raise ValueError("No route found")

    route = data['routes'][0]
    distance_km = route['distance'] / 1000.0
    duration_min = route['duration'] / 60.0
    # GeoJSON viene como [lon, lat]; el front espera {latitude, longitude}.
    waypoints = [{"latitude": lat, "longitude": lon}
                for lon, lat in route['geometry']['coordinates']]

    return distance_km, duration_min, waypoints


# Mismos hosts que OSRM_BASE_URLS, pidiendo el servicio /table en vez de
# /route: una sola llamada resuelve la matriz completa origen -> N destinos,
# en vez de N llamadas secuenciales. El segmento final ("driving") no cambia
# de significado: sigue sin definir el perfil (lo define la instancia), solo
# selecciona el servicio correcto en el servidor público multi-perfil.
OSRM_TABLE_URLS = {k: v.replace("/route/v1/", "/table/v1/") for k, v in OSRM_BASE_URLS.items()}


def get_osrm_table(work_lat, work_lon, destinos, mode):
    """
    Distancia y tiempo de flujo libre desde (work_lat, work_lon) hacia cada
    punto de `destinos` (lista de (lat, lon)), en una sola petición a OSRM.

    Devuelve una lista de (dist_km, duration_min) en el mismo orden que
    `destinos`, o None si la petición falla completa (el llamador decide el
    fallback — no hay "circuit breaker" por candidata porque ya es una sola
    llamada para todas).
    """
    if not destinos:
        return []

    profile = mode.lower()
    base_url = OSRM_TABLE_URLS.get(profile, OSRM_TABLE_URLS["driving"])

    coords = [f"{work_lon},{work_lat}"] + [f"{lon},{lat}" for lat, lon in destinos]
    destinos_idx = ";".join(str(i) for i in range(1, len(destinos) + 1))
    url = (f"{base_url}/{';'.join(coords)}"
           f"?sources=0&destinations={destinos_idx}&annotations=duration,distance")

    response = requests.get(url, timeout=15)
    response.raise_for_status()

    data = response.json()
    if data.get('code') != 'Ok':
        raise ValueError(f"OSRM table devolvió: {data.get('code')}")

    duraciones = data['durations'][0]
    distancias = data['distances'][0]
    return [
        (d / 1000.0, t / 60.0) if t is not None and d is not None else None
        for d, t in zip(distancias, duraciones)
    ]


BUDGET_TOLERANCE = 1.15  # Mostrar casas hasta un 15% sobre el presupuesto declarado
USD_TO_PEN = settings.USD_TO_PEN


def _to_pen(price: float, currency: str | None) -> float:
    """Convierte price a soles. Si currency es USD multiplica por el tipo de cambio."""
    if currency and currency.upper() == "USD":
        return price * USD_TO_PEN
    return price


# --- Corrección del tiempo de viaje con el modelo de tráfico ---
#
# Mismo centro de referencia que scripts/collect_traffic_data.py, para que las
# distancias "al centro" que ve el modelo en inferencia sean comparables a las
# de entrenamiento.
LIMA_CENTER = (-12.0464, -77.0428)

# El modelo se entrenó con una sola fecha de referencia (martes) y tres horas
# fijas. dia_semana fue CONSTANTE en todo el entrenamiento (siempre 1, martes):
# el modelo no aprendió variación por día de semana, así que en inferencia se
# le da ese mismo valor — es el único que conoce, no una elección arbitraria.
DIA_SEMANA_INFERENCIA = 1  # martes, el único valor visto en entrenamiento

# La app no le pregunta al usuario a qué hora sale de casa. Se asume la punta
# de la mañana (llegar al trabajo), que es el caso de uso central del producto
# y la franja con más error de OSRM sin corregir. Limitación documentada: el
# tiempo mostrado corresponde a esa franja, no a la hora real de cada usuario.
HORA_INFERENCIA = 7  # 7:00 am, punta de la mañana


def _geo_relativa(lat, lon):
    """Distancia (km) de un punto al centro de Lima, misma métrica que en el
    dataset de entrenamiento."""
    return haversine(lat, lon, *LIMA_CENTER)


def corregir_tiempos(filas_osrm: list[dict]) -> list[float]:
    """
    Corrige una lista de tiempos de OSRM (flujo libre) al tiempo real esperado
    con tráfico, usando el modelo entrenado contra TomTom.

    Cada fila necesita: osrm_min, osrm_dist_km, modo, lat/lon de los dos
    extremos del trayecto (para la geografía relativa a Lima).
    """
    entradas = []
    for f in filas_osrm:
        centro_a = _geo_relativa(f["lat_a"], f["lon_a"])
        centro_b = _geo_relativa(f["lat_b"], f["lon_b"])
        entradas.append({
            "osrm_min": f["osrm_min"],
            "osrm_dist_km": f["osrm_dist_km"],
            "modo": f["modo"],
            "hora": HORA_INFERENCIA,
            "dia_semana": DIA_SEMANA_INFERENCIA,
            "work_dist_centro_km": centro_a,
            "prop_dist_centro_km": centro_b,
            "hacia_el_centro": int(centro_a < centro_b),
        })
    corregidos = predictor_travel_time.predict_minutes(entradas)
    # Si esto no calzara, el zip() del llamador recortaría en silencio y
    # dejaría algunas filas con el tiempo sin corregir sin ningún aviso.
    assert len(corregidos) == len(filas_osrm), (
        f"predict_minutes devolvió {len(corregidos)} valores para "
        f"{len(filas_osrm)} filas de entrada"
    )
    return corregidos


# --- match_score: función de utilidad explícita, no un modelo de ML ---
#
# Combina cercanía (a partir del tiempo YA CORREGIDO por el modelo de tráfico),
# ajuste al presupuesto y área. Los pesos y tramos son los mismos que usaba
# scripts/dataset_builder.py para generar la etiqueta sintética del modelo
# viejo — se conservan porque son una heurística de dominio razonable, pero
# ahora se declaran como lo que son: una regla de negocio explícita, no algo
# "aprendido". Sin ruido aleatorio: aquí el puntaje debe ser determinista.
def calcular_match_score(tiempo_min: float, dist_km: float, precio_ratio: float,
                         area_m2: float) -> float:
    score = 40.0

    # Tiempo de viaje — factor principal (hasta +45 pts)
    if tiempo_min <= 45:
        score += 45 * (1 - tiempo_min / 45)
    else:
        score -= min(20, ((tiempo_min - 45) / 15) * 10)

    # Distancia — complementario al tiempo (hasta +3 pts)
    if dist_km <= 2:
        score += 3
    elif dist_km <= 5:
        score += 1
    elif dist_km <= 15:
        pass
    else:
        score -= 3

    # Presupuesto (hasta +20 pts)
    if precio_ratio <= 1.0:
        score += (1 - precio_ratio) * 20
    else:
        score -= min(35, (precio_ratio - 1) * 60)

    # Área — ajuste menor (hasta +5 pts)
    if area_m2 >= 40:
        score += 5
    elif area_m2 >= 25:
        score += 3
    elif area_m2 >= 15:
        score += 1
    elif 0 < area_m2 < 15:
        score -= 2

    return max(0.0, min(100.0, score))


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
            home_dist_km, current_commute_time = get_osrm_route(
                user_home_lat, user_home_lon, work_lat, work_lon, mode)
            # Corregir con el modelo solo si el tiempo vino de OSRM real: el
            # modelo se entrenó sobre salidas de OSRM, no sobre la aproximación
            # de Haversine del bloque except de abajo.
            corregidos = corregir_tiempos([{
                "osrm_min": current_commute_time, "osrm_dist_km": home_dist_km,
                "modo": mode.lower(),
                "lat_a": work_lat, "lon_a": work_lon,
                "lat_b": user_home_lat, "lon_b": user_home_lon,
            }])
            current_commute_time = corregidos[0]
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

    mode_english = mode.lower()

    # Una sola llamada a OSRM /table resuelve distancia y tiempo hacia TODAS
    # las candidatas. Reemplaza al bucle secuencial de N llamadas a /route
    # (hasta 271 candidatas x ~150ms + 50ms de cortesía = 46-95 s por
    # recomendación). Ya no hace falta circuit breaker por candidata: o la
    # llamada completa funciona, o se cae entera a Haversine para el lote.
    try:
        resultado_tabla = get_osrm_table(
            work_lat, work_lon,
            [(c.latitude, c.longitude) for _, c in casas_candidatas],
            mode,
        )
    except Exception:
        resultado_tabla = None

    lista_casas = []
    for idx, (straight_dist, c) in enumerate(casas_candidatas):
        fila_tabla = resultado_tabla[idx] if resultado_tabla else None
        if fila_tabla is not None:
            de_osrm = True
            dist_km, tiempo_osrm = fila_tabla
        else:
            # Toda la tabla falló, o esta celda vino null (sin ruta a ese punto)
            de_osrm = False
            dist_km = straight_dist
            tiempo_osrm = simulate_commute_time(dist_km, mode)

        precio_pen = _to_pen(c.price, c.currency)
        precio_ratio = precio_pen / budget if budget > 0 else 1.0

        lista_casas.append({
            "prop": c, "dist_km": dist_km, "tiempo_osrm": tiempo_osrm,
            "de_osrm": de_osrm, "precio_ratio": precio_ratio,
            "area_m2": float(c.total_area_sqm),
        })

    # Corregir el tiempo con el modelo de tráfico — solo para las que sí vinieron
    # de OSRM real. Las que cayeron al fallback de Haversine se quedan con esa
    # estimación tal cual: el modelo se entrenó con salidas de OSRM, meterle una
    # aproximación en línea recta sería extrapolar fuera de lo que aprendió.
    indices_osrm = [i for i, d in enumerate(lista_casas) if d["de_osrm"]]
    if indices_osrm:
        filas = [{
            "osrm_min": lista_casas[i]["tiempo_osrm"],
            "osrm_dist_km": lista_casas[i]["dist_km"],
            "modo": mode_english,
            "lat_a": work_lat, "lon_a": work_lon,
            "lat_b": lista_casas[i]["prop"].latitude, "lon_b": lista_casas[i]["prop"].longitude,
        } for i in indices_osrm]
        corregidos = corregir_tiempos(filas)
        for i, tiempo_corregido in zip(indices_osrm, corregidos):
            lista_casas[i]["tiempo"] = tiempo_corregido
    for d in lista_casas:
        d.setdefault("tiempo", d["tiempo_osrm"])  # las de fallback no se tocaron arriba

    # Obtener favoritos del usuario si está logueado
    fav_ids = set()
    if user_id:
        fav_ids = set(row[0] for row in db.query(Favorite.property_id).filter(Favorite.user_id == user_id).all())

    # match_score: función de utilidad explícita (ver calcular_match_score), no
    # una inferencia de modelo. Se calcula con el tiempo YA corregido.
    resultados = []
    for d in lista_casas:
        tiempo = d["tiempo"]
        time_saved = current_commute_time - tiempo if current_commute_time is not None else None
        score = calcular_match_score(tiempo, d["dist_km"], d["precio_ratio"], d["area_m2"])

        prop = d["prop"]
        prop.is_favorite = prop.id in fav_ids

        resultados.append({
            "property": prop,
            "predicted_time_min": round(tiempo),
            "match_score": round(score, 1),
            "time_saved_mins": round(time_saved) if time_saved is not None else None,
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
                "status": prop.status,
                "phone": prop.phone,
            },
            "match_score": r["match_score"],
            "predicted_time_min": r["predicted_time_min"],
            "time_saved_mins": r.get("time_saved_mins"),
        })
    return serialized
