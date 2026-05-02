from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.models.recommendation_preference import RecommendationPreference
from app.models.workplace import Workplace
from app.models.user import User
from app.schemas.recommendation_preference import RecommendationPreferenceCreate, RecommendationPreferenceUpdate, RecommendationPreferenceResponse
from app.core.security import get_current_user

router = APIRouter(prefix="/recommendation_preferences", tags=["Preferencias de Recomendación"])

@router.post("/", response_model=RecommendationPreferenceResponse)
def create_preference(pref_data: RecommendationPreferenceCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Crear preferencias de recomendación para un lugar de trabajo"""
    # Verificar que el workplace pertenece al usuario
    work = db.query(Workplace).filter(Workplace.id == pref_data.workplace_id, Workplace.user_id == current_user.id).first()
    if not work:
        raise HTTPException(status_code=404, detail="Lugar de trabajo no encontrado o no autorizado")
        
    # Verificar si ya existe una preferencia
    existing_pref = db.query(RecommendationPreference).filter(RecommendationPreference.workplace_id == pref_data.workplace_id).first()
    if existing_pref:
        raise HTTPException(status_code=400, detail="Ya existen preferencias para este lugar de trabajo. Usa PATCH para actualizar.")

    new_pref = RecommendationPreference(**pref_data.model_dump(), user_id=current_user.id)
    db.add(new_pref)
    db.commit()
    db.refresh(new_pref)
    return new_pref

@router.get("/", response_model=List[RecommendationPreferenceResponse])
def get_preferences(workplace_id: Optional[int] = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Obtener preferencias (todas las del usuario o filtradas por workplace_id)"""
    query = db.query(RecommendationPreference).filter(RecommendationPreference.user_id == current_user.id)
    
    if workplace_id is not None:
        query = query.filter(RecommendationPreference.workplace_id == workplace_id)
        
    return query.all()

@router.patch("/{pref_id}", response_model=RecommendationPreferenceResponse)
def update_preference(pref_id: int, pref_data: RecommendationPreferenceUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Actualizar preferencias de recomendación"""
    pref = db.query(RecommendationPreference).filter(RecommendationPreference.id == pref_id, RecommendationPreference.user_id == current_user.id).first()
    if not pref:
        raise HTTPException(status_code=404, detail="Preferencias no encontradas")
        
    update_data = pref_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(pref, key, value)
        
    db.commit()
    db.refresh(pref)
    return pref
