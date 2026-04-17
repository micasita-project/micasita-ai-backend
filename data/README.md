# Generación del Dataset de Entrenamiento

## Estructura

- `raw/` - Datos brutos: viviendas, usuarios, mapa de Perú (OSM)
- `processed/` - Dataset generado listo para entrenar modelos
- `images/` - Imágenes de viviendas descargadas

## Generar el Dataset

### Prerequisitos

- Docker instalado
- ~250 MB libres en disco (para datos OSM de Perú)
- Python 3.8+

### Pasos

#### 1. Descargar mapa de Perú

```bash
$url = "https://download.geofabrik.de/south-america/peru-latest.osm.pbf"
Invoke-WebRequest -Uri $url -OutFile "data/osrm/peru-latest.osm.pbf"
```

#### 2. Procesar con OSRM

Desde la carpeta raíz del proyecto:

```bash
# Extracción (3-5 min)
docker run -v ${PWD}/data/osrm:/data osrm/osrm-backend osrm-extract -p /opt/car.lua /data/peru-latest.osm.pbf

# Contracción (1-2 min)
docker run -v ${PWD}/data/osrm:/data osrm/osrm-backend osrm-contract /data/peru-latest.osrm
```

#### 3. Levantar servidor OSRM (en segundo plano)

```bash
docker run -d -p 5000:5000 -v ${PWD}/data/osrm:/data osrm/osrm-backend osrm-routed /data/peru-latest.osrm
```

#### 4. Generar dataset

```bash
python scripts/dataset_builder.py
```

**Output:** `data/processed/dataset_entrenamiento.csv`

Contiene 4520 filas (10 usuarios × 452 viviendas) con features:

- `vivienda_id`, `precio_alquiler`, `area_m2`, `presupuesto_usuario`, `modo_transporte`
- `distancia_km_simulada`, `tiempo_viaje_min` (calculados por OSRM)
- `source_ruta` (siempre "osrm" en esta versión)
- `afinidad_score` (etiqueta objetivo 0-100)

## Nota

Para reproducir: solo necesitas ejecutar los pasos 1-4 nuevamente.
