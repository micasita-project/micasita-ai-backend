import json
import random
import csv
import os
from functools import lru_cache
from urllib import request

def get_osrm_profile(mode):
    if mode == 'Caminando':
        return 'walking'
    if mode == 'Bicicleta':
        return 'cycling'
    return 'driving'

@lru_cache(maxsize=4096)
def get_route_metrics(lat1, lon1, lat2, lon2, mode):
    profile = get_osrm_profile(mode)
    url = (
        f"http://localhost:5000/route/v1/{profile}/"
        f"{lon1},{lat1};{lon2},{lat2}?overview=false&steps=false"
    )

    try:
        with request.urlopen(url, timeout=10) as response:
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
    for u in usuarios:
        for v in viviendas_limpias:
            precio = float(v.get('price', 0))
            area = float(v.get('total_area_sqm') or v.get('covered_area_sqm') or 0)
            
            dist_km, tiempo_viaje, route_source = get_route_metrics(
                u['work_lat'],
                u['work_lon'],
                v['latitude'],
                v['longitude'],
                u['preferred_transport']
            )
            
            score = 50.0
            
            if precio > u['budget']:
                score -= 40
            else:
                ahorro = u['budget'] - precio
                score += (ahorro / u['budget']) * 20
                
            if tiempo_viaje <= 15:
                score += 30
            elif 15 < tiempo_viaje <= 45:
                score -= 10
            else:
                score -= 30
                
            if u['size_matters'] and area > 60:
                score += 15
                
            ruido = random.uniform(-10, 10)
            score += ruido
            
            score = max(0, min(100, round(score)))
            
            fila = {
                'vivienda_id': v['id'],
                'precio_alquiler': precio,
                'area_m2': area,
                'presupuesto_usuario': u['budget'],
                'modo_transporte': u['preferred_transport'],
                'distancia_km_simulada': dist_km,
                'tiempo_viaje_min': tiempo_viaje,
                'source_ruta': route_source,
                'afinidad_score': score
            }
            dataset.append(fila)

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
