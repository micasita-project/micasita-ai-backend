import json
import random
import math
import csv
import os

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
    
    base_time = (distance_km / speed) * 60
    return round(base_time * random.uniform(0.9, 1.2))

def build_dataset(viviendas_path, usuarios_path, output_csv_path):
    print(f"Cargando viviendas desde {viviendas_path}...")
    with open(viviendas_path, 'r', encoding='utf-8') as f:
        viviendas = json.load(f)
        
    print(f"Cargando perfiles desde {usuarios_path}...")
    with open(usuarios_path, 'r', encoding='utf-8') as f:
        usuarios = json.load(f)
    
    viviendas_limpias = []
    for v in viviendas:
        if v.get('property_type') in ['Departamento', 'Casa'] and v.get('price') is not None:
            price = float(v['price'])
            if 0 < price < 10000:
                viviendas_limpias.append(v)
    
    print(f"Viviendas filtradas aptas para alquiler: {len(viviendas_limpias)}")
    
    dataset = []
    for u in usuarios:
        for v in viviendas_limpias:
            precio = float(v.get('price', 0))
            area = float(v.get('total_area_sqm') or v.get('covered_area_sqm') or 0)
            
            dist_km = haversine(u['trabajo_lat'], u['trabajo_lon'], v['latitude'], v['longitude'])
            dist_km = round(dist_km, 2)
            tiempo_viaje = simulate_commute_time(dist_km, u['transporte_fav'])
            
            score = 50.0
            
            if precio > u['presupuesto']:
                score -= 40
            else:
                ahorro = u['presupuesto'] - precio
                score += (ahorro / u['presupuesto']) * 20
                
            if tiempo_viaje <= 15:
                score += 30
            elif 15 < tiempo_viaje <= 45:
                score -= 10
            else:
                score -= 30
                
            if u['importa_tamano'] and area > 60:
                score += 15
                
            ruido = random.uniform(-10, 10)
            score += ruido
            
            score = max(0, min(100, round(score)))
            
            fila = {
                'vivienda_id': v['id'],
                'precio_alquiler': precio,
                'area_m2': area,
                'presupuesto_usuario': u['presupuesto'],
                'modo_transporte': u['transporte_fav'],
                'distancia_km_simulada': dist_km,
                'tiempo_viaje_min': tiempo_viaje,
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
        viviendas_path='data/raw/viviendas_300.json', 
        usuarios_path='data/raw/usuarios.json', 
        output_csv_path='data/processed/dataset_entrenamiento.csv'
    )
