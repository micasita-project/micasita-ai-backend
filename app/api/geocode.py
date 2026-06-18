from fastapi import APIRouter, Query
from typing import List, Optional
import requests
import threading
import time
from pydantic import BaseModel

router = APIRouter(prefix="/geocode", tags=["Geocodificacion"])

NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org"
PHOTON_BASE_URL = "https://photon.komoot.io"
HEADERS = {"User-Agent": "MiCasitaApp/1.0 (micasita.pe; jhersastu@gmail.com)"}

# Caché manual — solo guarda resultados exitosos
_search_cache: dict = {}
_reverse_cache: dict = {}

# Throttle global: Nominatim exige máximo 1 req/segundo
_nominatim_lock = threading.Lock()
_last_nominatim_call: float = 0.0
_MIN_INTERVAL = 1.1


def _nominatim_get(url: str, params: dict) -> Optional[requests.Response]:
    """Llama a Nominatim con throttle. Retorna None en 429."""
    global _last_nominatim_call
    with _nominatim_lock:
        wait = _MIN_INTERVAL - (time.monotonic() - _last_nominatim_call)
        if wait > 0:
            time.sleep(wait)
        _last_nominatim_call = time.monotonic()
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=8)
            if resp.status_code == 429:
                print("Nominatim 429 — usando Photon como fallback")
                return None
            resp.raise_for_status()
            return resp
        except Exception as e:
            print(f"Error Nominatim: {e}")
            return None


# ── Photon fallback ──────────────────────────────────────────────────────────

def _photon_reverse(lat: float, lon: float) -> dict:
    try:
        resp = requests.get(f"{PHOTON_BASE_URL}/reverse",
                            params={"lat": lat, "lon": lon}, headers=HEADERS, timeout=8)
        resp.raise_for_status()
        features = resp.json().get("features", [])
        if features:
            return features[0].get("properties", {})
    except Exception as e:
        print(f"Error Photon reverse: {e}")
    return {}


def _photon_search(q: str, limit: int) -> list:
    try:
        resp = requests.get(
            f"{PHOTON_BASE_URL}/api/",
            params={"q": q, "limit": limit * 3, "lat": -12.05,
                    "lon": -77.03, "bbox": "-77.3,-12.6,-76.6,-11.7"},
            headers=HEADERS,
            timeout=8,
        )
        resp.raise_for_status()
        features = resp.json().get("features", [])
        return [f for f in features if f.get("properties", {}).get("countrycode", "").upper() == "PE"][:limit]
    except Exception as e:
        print(f"Error Photon search: {e}")
    return []


def _photon_display_name(props: dict) -> str:
    parts = [props.get(k) for k in (
        "name", "street", "housenumber", "district", "city") if props.get(k)]
    return ", ".join(dict.fromkeys(parts)) if parts else "Ubicación encontrada"


# ── Capa de caché + lógica principal ─────────────────────────────────────────

class GeocodeSuggestion(BaseModel):
    display_name: str
    latitude: float
    longitude: float
    place_type: str
    district: Optional[str] = None


def _fetch_search(q: str, limit: int) -> list:
    key = (q, limit)
    if key in _search_cache:
        return _search_cache[key]

    params = {
        "q": q, "format": "json", "addressdetails": 1,
        "limit": limit, "countrycodes": "pe",
        "viewbox": "-77.2,-11.8,-76.7,-12.3", "bounded": 1,
    }
    resp = _nominatim_get(f"{NOMINATIM_BASE_URL}/search", params)

    if resp is not None:
        result = resp.json()
        if result:
            _search_cache[key] = result
        return result

    # Fallback a Photon
    features = _photon_search(q, limit)
    if features:
        _search_cache[key] = features
    return features


def _fetch_reverse(lat: float, lon: float) -> dict:
    key = (lat, lon)
    if key in _reverse_cache:
        return _reverse_cache[key]

    params = {"lat": lat, "lon": lon, "format": "json", "addressdetails": 1}
    resp = _nominatim_get(f"{NOMINATIM_BASE_URL}/reverse", params)

    if resp is not None:
        result = resp.json()
        if result.get("display_name"):
            _reverse_cache[key] = result
        return result

    # Fallback a Photon
    props = _photon_reverse(lat, lon)
    if props:
        _reverse_cache[key] = props
    return props


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/search", response_model=List[GeocodeSuggestion])
def search_address(
    q: str = Query(..., min_length=3),
    limit: int = Query(5, ge=1, le=10),
):
    data = _fetch_search(q.strip().lower(), limit)
    suggestions = []
    for item in data:
        # Nominatim devuelve dict con "address", Photon devuelve Feature con "properties"
        if "properties" in item:
            props = item["properties"]
            coords = item.get("geometry", {}).get("coordinates", [0, 0])
            district = props.get("district") or props.get("city")
            suggestions.append(GeocodeSuggestion(
                display_name=_photon_display_name(props),
                latitude=coords[1], longitude=coords[0],
                place_type=props.get("type", "unknown"),
                district=district,
            ))
        else:
            address = item.get("address", {})
            district = address.get("suburb") or address.get(
                "city_district") or address.get("town")
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
    lat_r = round(lat, 4)
    lon_r = round(lon, 4)
    data = _fetch_reverse(lat_r, lon_r)

    if not data:
        return GeocodeSuggestion(
            display_name="Ubicación seleccionada en el mapa",
            latitude=lat, longitude=lon,
            place_type="unknown", district=None,
        )

    # Nominatim tiene "display_name", Photon tiene "name"/"street"/etc
    if "display_name" in data:
        address = data.get("address", {})
        district = address.get("suburb") or address.get(
            "city_district") or address.get("town")
        return GeocodeSuggestion(
            display_name=data["display_name"],
            latitude=lat, longitude=lon,
            place_type=data.get("type", "unknown"),
            district=district,
        )
    else:
        district = data.get("district") or data.get("city")
        return GeocodeSuggestion(
            display_name=_photon_display_name(data),
            latitude=lat, longitude=lon,
            place_type=data.get("type", "unknown"),
            district=district,
        )
