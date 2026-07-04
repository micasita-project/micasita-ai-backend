import json
import random
import csv
import os
from functools import lru_cache
from urllib import request

def get_osrm_profile(mode):
    """Retorna el modo tal cual (ya viene en inglés desde users.json)."""
    return mode.lower()

# OSRM local multi-perfil: una instancia por modo (driving=car, cycling=bike, walking=foot).
# El perfil real lo define la instancia, no el path. Configurable vía variables de entorno.
OSRM_BASE_URLS = {
    "driving": os.getenv("OSRM_DRIVING_URL", "http://localhost:5003/route/v1/driving"),
    "cycling": os.getenv("OSRM_CYCLING_URL", "http://localhost:5001/route/v1/driving"),
    "walking": os.getenv("OSRM_WALKING_URL", "http://localhost:5002/route/v1/driving"),
}

@lru_cache(maxsize=4096)
def get_route_metrics(lat1, lon1, lat2, lon2, mode):
    profile = get_osrm_profile(mode)
    base_url = OSRM_BASE_URLS.get(profile, OSRM_BASE_URLS["driving"])
    url = (
        f"{base_url}/"
        f"{lon1},{lat1};{lon2},{lat2}?overview=false&steps=false"
    )

    try:
        with request.urlopen(url, timeout=15) as response:
            payload = json.loads(response.read().decode('utf-8'))

        routes = payload.get('routes') or []
        if routes:
            route = routes[0]
            distance_km = round(route.get('distance', 0) / 1000, 2)
            duration_min = round(route.get('duration', 0) / 60)
            return distance_km, duration_min, 'osrm'
    except (TimeoutError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError('OSRM no respondió o devolvió una respuesta inválida') from exc

    raise RuntimeError('OSRM no devolvió rutas para las coordenadas dadas')

def build_dataset(viviendas_path, usuarios_path, output_csv_path):
    print(f"Cargando viviendas desde {viviendas_path}...")
    with open(viviendas_path, 'r', encoding='utf-8') as f:
        viviendas = json.load(f)
        
    print(f"Cargando perfiles desde {usuarios_path}...")
    with open(usuarios_path, 'r', encoding='utf-8') as f:
        usuarios = json.load(f)
    
    viviendas_limpias = []
    for v in viviendas:
        if v.get('property_type') in ['Departamento', 'Casa','Proyecto'] and v.get('price') is not None:
            price = float(v['price'])
            if 0 < price < 10000:
                viviendas_limpias.append(v)
    
    print(f"Viviendas filtradas aptas para alquiler: {len(viviendas_limpias)}")
    
    dataset = []
    print(f"Calculando rutas e interacciones para {len(usuarios)} usuarios...")
    
    from concurrent.futures import ThreadPoolExecutor
    
    def process_pair(u, v):
        precio = float(v.get('price', 0))
        area = float(v.get('total_area_sqm') or v.get('covered_area_sqm') or 0)
        
        english_mode = get_osrm_profile(u['preferred_transport'])
        
        try:
            dist_km, tiempo_viaje, source = get_route_metrics(
                u['work_lat'], u['work_lon'],
                v['latitude'], v['longitude'],
                english_mode
            )
        except Exception:
            # Fallback Haversine si falla el thread
            source = 'haversine'
            from math import radians, sin, cos, sqrt, atan2
            lat1, lon1 = radians(u['work_lat']), radians(u['work_lon'])
            lat2, lon2 = radians(v['latitude']), radians(v['longitude'])
            dlon = lon2 - lon1
            dlat = lat2 - lat1
            a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
            c = 2 * atan2(sqrt(a), sqrt(1 - a))
            dist_km = 6371.0 * c
            tiempo_viaje = (dist_km * 1.4 / (4.5 if 'walk' in english_mode else 12.0 if 'cycl' in english_mode else 15.0)) * 60

        score = 40.0

        # 1. TIEMPO DE VIAJE — factor principal (hasta +45 pts)
        # Curva lineal continua: 0 min → +45, 45 min → 0, >45 penaliza.
        if tiempo_viaje <= 45:
            score += 45 * (1 - tiempo_viaje / 45)
        else:
            score -= min(20, ((tiempo_viaje - 45) / 15) * 10)

        # 2. DISTANCIA AL TRABAJO — complementario al tiempo (hasta +3 pts)
        if dist_km <= 2:
            score += 3
        elif dist_km <= 5:
            score += 1
        elif dist_km <= 15:
            pass
        else:
            score -= 3

        # 3. PRESUPUESTO — curva suave sin acantilado (hasta +20 pts)
        ratio = precio / u['budget'] if u['budget'] > 0 else 2.0
        if ratio <= 1.0:
            score += (1 - ratio) * 20
        else:
            score -= min(35, (ratio - 1) * 60)

        # 4. ÁREA — ajuste menor (hasta +5 pts)
        if area >= 40:
            score += 5
        elif area >= 25:
            score += 3
        elif area >= 15:
            score += 1
        elif 0 < area < 15:
            score -= 2

        score += random.uniform(-2, 2)
        score = max(0, min(100, score))
        
        precio_ratio = precio / u['budget'] if u['budget'] > 0 else 1.0

        return {
            'vivienda_id': v['id'],
            'precio_ratio': round(precio_ratio, 4),
            'area_m2': area,
            'modo_transporte': english_mode,
            'distancia_km_simulada': dist_km,
            'tiempo_viaje_min': tiempo_viaje,
            'source_ruta': source,
            'afinidad_score': score
        }

    tasks = []
    for u in usuarios:
        for v in viviendas_limpias:
            tasks.append((u, v))
            
    print(f"Total de tareas a procesar: {len(tasks)}")
    
    results = []
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = [executor.submit(process_pair, u, v) for u, v in tasks]
        for i, future in enumerate(futures):
            results.append(future.result())
            if (i + 1) % 500 == 0:
                print(f"Progreso: {i + 1}/{len(tasks)} procesados...")
    
    dataset = results

    if dataset:
        headers = dataset[0].keys()
        
        # Crear la carpeta de destino si no existe
        os.makedirs(os.path.dirname(output_csv_path), exist_ok=True)

        with open(output_csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(dataset)
        
        print(f"¡Éxito! Dataset generado con {len(dataset)} interacciones en: {output_csv_path}")

if __name__ == "__main__":
    # Las rutas asumen que ejecutas el script desde la raíz: `python scripts/dataset_builder.py`
    build_dataset(
        viviendas_path='data/raw/housing.json',
        usuarios_path='data/raw/users.json',
        output_csv_path='data/processed/training_dataset.csv'
    )
