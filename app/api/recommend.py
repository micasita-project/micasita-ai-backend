from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
import json
from app.core.database import get_db
from app.models.user import User
from app.models.workplace import Workplace
from app.models.recommendation_preference import RecommendationPreference
from app.models.recommendation_history import RecommendationHistory
from app.models.favorite import Favorite
from app.core.security import get_current_user, get_current_user_optional
from app.schemas.recommend import RecommendationPageResponse, GuestRecommendRequest
from app.services.recommendation_service import generar_recomendacion, _serialize_results

router = APIRouter(prefix="/recommend", tags=["IA Recomendaciones"])


# ── Endpoints ────────────────────────────────────────────────────

@router.post(
    "/guest",
    response_model=RecommendationPageResponse,
    summary="Recomendaciones para visitante",
    response_description="Viviendas recomendadas con mensaje explicativo si el presupuesto no alcanza en la zona",
)
def recommend_for_guest(req: GuestRecommendRequest, current_user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    """
    Genera recomendaciones sin necesidad de cuenta registrada.

    Requiere pasar manualmente las coordenadas del trabajo, presupuesto y medio de transporte.
    Si se envía token JWT, el campo `is_favorite` refleja el estado real del usuario.
    Si se envían `home_lat`/`home_lon`, calcula el campo `time_saved_mins`.
    """
    return generar_recomendacion(
        req.work_lat, req.work_lon, req.budget, req.preferred_transportation, db,
        max_distance_km=req.max_distance_km,
        user_home_lat=req.home_lat,
        user_home_lon=req.home_lon,
        user_id=current_user.id if current_user else None
    )


@router.post(
    "/workplaces/{workplace_id}/generate",
    response_model=RecommendationPageResponse,
    summary="Generar recomendaciones (con historial)",
    response_description="Viviendas recomendadas por XGBoost, guardadas en historial",
    responses={
        400: {"description": "El workplace no tiene preferencias de recomendación configuradas"},
        404: {"description": "Workplace no encontrado"},
    },
)
def generate_recommendations(
    workplace_id: int,
    max_distance_km: float = 10.0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Ejecuta el modelo XGBoost usando las preferencias guardadas del workplace y almacena el resultado.

    Cada llamada crea una nueva entrada en el historial (no sobrescribe).
    El parámetro `max_distance_km` de query sobreescribe el valor de las preferencias si se envía explícitamente.
    Devuelve todos los resultados que cumplan presupuesto y distancia, sin límite artificial.
    Usar con moderación — cada llamada consulta OSRM por cada vivienda candidata.
    """
    work = db.query(Workplace).filter(Workplace.id == workplace_id, Workplace.user_id == current_user.id).first()
    if not work:
        raise HTTPException(status_code=404, detail="Lugar de trabajo no encontrado")

    pref = db.query(RecommendationPreference).filter(RecommendationPreference.workplace_id == workplace_id).first()
    if not pref:
        raise HTTPException(status_code=400, detail="Faltan preferencias de recomendación para este lugar de trabajo")

    # Usar max_distance_km de las preferencias si no se envía explícitamente por query
    dist = max_distance_km if max_distance_km != 10.0 else pref.max_distance_km

    # Ejecutar IA
    resultados = generar_recomendacion(
        work.work_lat, work.work_lon, pref.budget, pref.preferred_transportation, db,
        max_distance_km=dist,
        user_home_lat=current_user.home_lat,
        user_home_lon=current_user.home_lon,
        user_id=current_user.id
    )
    
    # Solo guardar en historial si hubo resultados
    if resultados["results"]:
        serialized = _serialize_results(resultados["results"])
        history_entry = RecommendationHistory(
            workplace_id=workplace_id,
            results=json.dumps(serialized)
        )
        db.add(history_entry)
        db.commit()

    return resultados


@router.get(
    "/workplaces/{workplace_id}/latest",
    response_model=RecommendationPageResponse,
    summary="Última recomendación (caché)",
    response_description="Última recomendación guardada con is_favorite actualizado en tiempo real",
    responses={
        404: {"description": "Workplace no encontrado o sin recomendaciones guardadas"},
    },
)
def get_latest_recommendations(
    workplace_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Devuelve la última recomendación guardada sin ejecutar el modelo XGBoost.

    El campo `is_favorite` se actualiza en tiempo real aunque el caché sea antiguo.
    Usar este endpoint para la carga inicial de la pantalla de resultados.
    """
    work = db.query(Workplace).filter(Workplace.id == workplace_id, Workplace.user_id == current_user.id).first()
    if not work:
        raise HTTPException(status_code=404, detail="Lugar de trabajo no encontrado")
    
    latest = db.query(RecommendationHistory)\
        .filter(RecommendationHistory.workplace_id == workplace_id)\
        .order_by(RecommendationHistory.created_at.desc())\
        .first()
    
    if not latest:
        raise HTTPException(status_code=404, detail="No hay recomendaciones guardadas. Genera una primero.")
    
    results = json.loads(latest.results)
    
    # Actualizar is_favorite ya que el cache puede estar viejo
    fav_ids = set(row[0] for row in db.query(Favorite.property_id).filter(Favorite.user_id == current_user.id).all())
    for r in results:
        r["property"]["is_favorite"] = r["property"]["id"] in fav_ids

    return {"results": results, "total": len(results), "message": None, "min_price_in_area": None}


@router.get(
    "/workplaces/{workplace_id}/history",
    summary="Historial de recomendaciones",
    response_description="Todas las sesiones de recomendación generadas para el workplace",
    responses={404: {"description": "Workplace no encontrado"}},
)
def get_recommendation_history(
    workplace_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Devuelve todas las sesiones de recomendación generadas para un workplace, ordenadas de más reciente a más antigua."""
    work = db.query(Workplace).filter(Workplace.id == workplace_id, Workplace.user_id == current_user.id).first()
    if not work:
        raise HTTPException(status_code=404, detail="Lugar de trabajo no encontrado")
    
    history = db.query(RecommendationHistory)\
        .filter(RecommendationHistory.workplace_id == workplace_id)\
        .order_by(RecommendationHistory.created_at.desc())\
        .all()
    
    return [
        {
            "id": h.id,
            "workplace_id": h.workplace_id,
            "results": json.loads(h.results),
            "created_at": h.created_at,
        }
        for h in history
    ]


# Mantener el endpoint viejo para compatibilidad (redirige a generate)
@router.get(
    "/workplaces/{workplace_id}",
    response_model=RecommendationPageResponse,
    summary="[Deprecated] Recomendaciones directas sin historial",
    response_description="Recomendaciones generadas (no se guardan)",
    deprecated=True,
    responses={
        400: {"description": "Sin preferencias configuradas para el workplace"},
        404: {"description": "Workplace no encontrado"},
    },
)
def recommend_for_logged_user(workplace_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    **Deprecado.** Ejecuta XGBoost sin guardar en historial.

    Usar `POST /recommend/workplaces/{workplace_id}/generate` en su lugar.
    """
    work = db.query(Workplace).filter(Workplace.id == workplace_id, Workplace.user_id == current_user.id).first()
    if not work:
        raise HTTPException(status_code=404, detail="Lugar de trabajo no encontrado")
        
    pref = db.query(RecommendationPreference).filter(RecommendationPreference.workplace_id == workplace_id).first()
    if not pref:
        raise HTTPException(status_code=400, detail="Faltan preferencias de recomendación para este lugar de trabajo")
        
    return generar_recomendacion(
        work.work_lat, 
        work.work_lon, 
        pref.budget, 
        pref.preferred_transportation, 
        db,
        user_home_lat=current_user.home_lat,
        user_home_lon=current_user.home_lon
    )
