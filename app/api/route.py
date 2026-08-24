from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import List

from app.services.recommendation_service import (
    get_osrm_route_with_geometry, corregir_tiempos, simulate_commute_time, haversine,
)

router = APIRouter(prefix="/route", tags=["Ruteo"])


class Waypoint(BaseModel):
    latitude: float
    longitude: float


class RouteResponse(BaseModel):
    distance_km: float
    duration_min: float
    waypoints: List[Waypoint]
    from_osrm: bool  # False si OSRM falló y se usó la aproximación de Haversine


@router.get(
    "",
    response_model=RouteResponse,
    summary="Ruta punto a punto con geometría",
    response_description="Distancia, tiempo (corregido con el mismo modelo de tráfico "
                          "que usa la recomendación) y geometría para dibujar en el mapa",
)
def get_route(
    origin_lat: float = Query(...),
    origin_lon: float = Query(...),
    dest_lat: float = Query(...),
    dest_lon: float = Query(...),
    mode: str = Query(..., pattern="^(driving|cycling|walking)$"),
):
    """
    Único punto de entrada del front para ruteo. El front NUNCA debe llamar a
    OSRM directamente — ni para el tiempo ni para la geometría del mapa.

    Si OSRM falla, degrada a una aproximación en línea recta (Haversine) en
    vez de fallar la petición: `from_osrm=False` avisa al front de que el
    tiempo mostrado es una estimación, no una ruta real.
    """
    try:
        dist_km, duration_osrm, waypoints = get_osrm_route_with_geometry(
            origin_lat, origin_lon, dest_lat, dest_lon, mode
        )
        corregidos = corregir_tiempos([{
            "osrm_min": duration_osrm, "osrm_dist_km": dist_km,
            "modo": mode.lower(),
            "lat_a": origin_lat, "lon_a": origin_lon,
            "lat_b": dest_lat, "lon_b": dest_lon,
        }])
        return RouteResponse(
            distance_km=round(dist_km, 2),
            duration_min=round(corregidos[0], 1),
            waypoints=[Waypoint(**w) for w in waypoints],
            from_osrm=True,
        )
    except Exception:
        dist_km = haversine(origin_lat, origin_lon, dest_lat, dest_lon)
        duration_min = simulate_commute_time(dist_km, mode)
        return RouteResponse(
            distance_km=round(dist_km, 2),
            duration_min=round(duration_min, 1),
            waypoints=[
                Waypoint(latitude=origin_lat, longitude=origin_lon),
                Waypoint(latitude=dest_lat, longitude=dest_lon),
            ],
            from_osrm=False,
        )
