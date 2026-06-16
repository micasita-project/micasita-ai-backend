from fastapi import APIRouter, Query
from typing import List, Optional
from functools import lru_cache
import requests
from pydantic import BaseModel

router = APIRouter(prefix="/geocode", tags=["Geocodificacion"])

NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org"
HEADERS = {"User-Agent": "MiCasitaApp/1.0 (micasita.pe; contacto@micasita.pe)"}


class GeocodeSuggestion(BaseModel):
    display_name: str
    latitude: float
    longitude: float
    place_type: str
    district: Optional[str] = None


@lru_cache(maxsize=512)
def _fetch_search(q: str, limit: int) -> list:
    params = {
        "q": q,
        "format": "json",
        "addressdetails": 1,
        "limit": limit,
        "countrycodes": "pe",
        "viewbox": "-77.2,-11.8,-76.7,-12.3",
        "bounded": 1,
    }
    try:
        response = requests.get(f"{NOMINATIM_BASE_URL}/search", params=params, headers=HEADERS, timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error al consultar Nominatim: {e}")
        return []


@lru_cache(maxsize=512)
def _fetch_reverse(lat: float, lon: float) -> dict:
    params = {"lat": lat, "lon": lon, "format": "json", "addressdetails": 1}
    try:
        response = requests.get(f"{NOMINATIM_BASE_URL}/reverse", params=params, headers=HEADERS, timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error reverse geocoding: {e}")
        return {}


@router.get("/search", response_model=List[GeocodeSuggestion])
def search_address(
    q: str = Query(..., min_length=3, description="Texto de busqueda, ej: 'avenida javier prado'"),
    limit: int = Query(5, ge=1, le=10, description="Numero maximo de resultados"),
):
    """
    Proxy de Nominatim (OpenStreetMap) para autocompletado de direcciones.
    Limitado a Lima, Peru. Resultados cacheados en memoria para respetar el rate limit.
    """
    data = _fetch_search(q.strip().lower(), limit)
    suggestions = []
    for item in data:
        address = item.get("address", {})
        district = address.get("suburb") or address.get("city_district") or address.get("town")
        suggestions.append(GeocodeSuggestion(
            display_name=item.get("display_name", ""),
            latitude=float(item.get("lat", 0)),
            longitude=float(item.get("lon", 0)),
            place_type=item.get("type", "unknown"),
            district=district,
        ))
    return suggestions


@router.get("/reverse", response_model=GeocodeSuggestion)
def reverse_address(lat: float, lon: float):
    """
    Proxy de Nominatim para reverse geocoding.
    Las coordenadas se redondean a 4 decimales para maximizar el caché.
    """
    lat_r = round(lat, 4)
    lon_r = round(lon, 4)
    data = _fetch_reverse(lat_r, lon_r)

    if not data:
        return GeocodeSuggestion(
            display_name="Ubicación seleccionada en el mapa",
            latitude=lat, longitude=lon,
            place_type="unknown", district=None,
        )

    address = data.get("address", {})
    district = address.get("suburb") or address.get("city_district") or address.get("town")
    return GeocodeSuggestion(
        display_name=data.get("display_name", "Ubicación seleccionada"),
        latitude=lat, longitude=lon,
        place_type=data.get("type", "unknown"),
        district=district,
    )
