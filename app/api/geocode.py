from fastapi import APIRouter, Query
from typing import List
import requests
from pydantic import BaseModel

router = APIRouter(prefix="/geocode", tags=["Geocodificacion"])

NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org"


class GeocodeSuggestion(BaseModel):
    display_name: str       # "Av. Javier Prado Este 4600, San Borja, Lima, Peru"
    latitude: float
    longitude: float
    place_type: str         # "road", "building", "amenity", etc.


@router.get("/search", response_model=List[GeocodeSuggestion])
def search_address(
    q: str = Query(..., min_length=3, description="Texto de busqueda, ej: 'avenida javier prado'"),
    limit: int = Query(5, ge=1, le=10, description="Numero maximo de resultados"),
):
    """
    Proxy de Nominatim (OpenStreetMap) para autocompletado de direcciones.
    Limitado a Lima, Peru para mayor precision.
    """
    params = {
        "q": q,
        "format": "json",
        "addressdetails": 1,
        "limit": limit,
        "countrycodes": "pe",           # Solo Peru
        "viewbox": "-77.2,-11.8,-76.7,-12.3",  # Bounding box de Lima metropolitana
        "bounded": 1,                   # Forzar resultados dentro del viewbox
    }
    
    headers = {
        # Nominatim requiere un User-Agent personalizado (politica de uso)
        "User-Agent": "MiCasitaApp/1.0 (micasita.pe; contacto@micasita.pe)"
    }
    
    try:
        response = requests.get(
            f"{NOMINATIM_BASE_URL}/search",
            params=params,
            headers=headers,
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Error al consultar Nominatim: {e}")
        return []
    
    suggestions = []
    for item in data:
        suggestions.append(GeocodeSuggestion(
            display_name=item.get("display_name", ""),
            latitude=float(item.get("lat", 0)),
            longitude=float(item.get("lon", 0)),
            place_type=item.get("type", "unknown"),
        ))
    
    return suggestions

@router.get("/reverse", response_model=GeocodeSuggestion)
def reverse_address(lat: float, lon: float):
    """
    Proxy de Nominatim para reverse geocoding (obtener dirección desde lat/lon).
    """
    params = {
        "lat": lat,
        "lon": lon,
        "format": "json",
    }
    headers = {
        "User-Agent": "MiCasitaApp/1.0 (micasita.pe; contacto@micasita.pe)"
    }
    try:
        response = requests.get(
            f"{NOMINATIM_BASE_URL}/reverse",
            params=params,
            headers=headers,
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        return GeocodeSuggestion(
            display_name=data.get("display_name", "Ubicación seleccionada"),
            latitude=lat,
            longitude=lon,
            place_type=data.get("type", "unknown"),
        )
    except Exception as e:
        print(f"Error reverse geocoding: {e}")
        return GeocodeSuggestion(
            display_name="Ubicación seleccionada en el mapa",
            latitude=lat,
            longitude=lon,
            place_type="unknown",
        )
