from fastapi import APIRouter, Query
from typing import List, Optional
import requests
import threading
import time
from pydantic import BaseModel

router = APIRouter(prefix="/geocode", tags=["Geocodificacion"])

NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org"
HEADERS = {"User-Agent": "MiCasitaApp/1.0 (micasita.pe; contacto@micasita.pe)"}

# Caché manual que solo guarda resultados exitosos
_search_cache: dict = {}
_reverse_cache: dict = {}

# Throttle: Nominatim exige máximo 1 req/segundo
_nominatim_lock = threading.Lock()
_last_nominatim_call: float = 0.0
_MIN_INTERVAL = 1.1  # segundos entre llamadas a Nominatim


def _nominatim_get(url: str, params: dict) -> requests.Response:
    """Hace GET a Nominatim respetando el rate limit de 1 req/seg."""
    global _last_nominatim_call
    with _nominatim_lock:
        wait = _MIN_INTERVAL - (time.monotonic() - _last_nominatim_call)
        if wait > 0:
            time.sleep(wait)
        _last_nominatim_call = time.monotonic()
        return requests.get(url, params=params, headers=HEADERS, timeout=10)


def _fetch_search(q: str, limit: int) -> list:
    key = (q, limit)
    if key in _search_cache:
        return _search_cache[key]
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
        for attempt in range(3):
            response = _nominatim_get(f"{NOMINATIM_BASE_URL}/search", params)
            if response.status_code == 429:
                print(f"Nominatim 429 en /search, intento {attempt + 1}/3")
                time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            result = response.json()
            if result:
                _search_cache[key] = result
            return result
    except Exception as e:
        print(f"Error al consultar Nominatim /search: {e}")
    return []


def _fetch_reverse(lat: float, lon: float) -> dict:
    key = (lat, lon)
    if key in _reverse_cache:
        return _reverse_cache[key]
    params = {"lat": lat, "lon": lon, "format": "json", "addressdetails": 1}
    try:
        for attempt in range(3):
            response = _nominatim_get(f"{NOMINATIM_BASE_URL}/reverse", params)
            if response.status_code == 429:
                print(f"Nominatim 429 en /reverse, intento {attempt + 1}/3")
                time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            result = response.json()
            if result.get("display_name"):
                _reverse_cache[key] = result
            return result
    except Exception as e:
        print(f"Error reverse geocoding: {e}")
    return {}


class GeocodeSuggestion(BaseModel):
    display_name: str
    latitude: float
    longitude: float
    place_type: str
    district: Optional[str] = None


@router.get("/search", response_model=List[GeocodeSuggestion])
def search_address(
    q: str = Query(..., min_length=3, description="Texto de busqueda, ej: 'avenida javier prado'"),
    limit: int = Query(5, ge=1, le=10, description="Numero maximo de resultados"),
):
    """
    Proxy de Nominatim (OpenStreetMap) para autocompletado de direcciones.
    Limitado a Lima, Peru. Throttled a 1 req/seg y hasta 3 reintentos en 429.
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
