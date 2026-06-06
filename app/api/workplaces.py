from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.models.workplace import Workplace
from app.models.user import User
from app.schemas.workplace import WorkplaceCreate, WorkplaceResponse, WorkplaceUpdate
from app.core.security import get_current_user
from app.core.geo import is_within_lima, LIMA_LOCATION_ERROR

router = APIRouter(prefix="/workplaces", tags=["Trabajos (Workplaces)"])

@router.post(
    "/",
    response_model=WorkplaceResponse,
    summary="Registrar lugar de trabajo",
    response_description="Workplace creado con su ID asignado",
)
def create_workplace(work_data: WorkplaceCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Registra un lugar de trabajo o estudio del usuario.

    Las coordenadas (`work_lat`, `work_lon`) son el punto de origen desde el cual
    el motor de IA calculará el tiempo de viaje a cada vivienda.
    Solo se aceptan coordenadas dentro de Lima Metropolitana.
    """
    if not is_within_lima(work_data.work_lat, work_data.work_lon):
        raise HTTPException(status_code=400, detail=LIMA_LOCATION_ERROR)

    new_work = Workplace(**work_data.model_dump(), user_id=current_user.id)
    db.add(new_work)
    db.commit()
    db.refresh(new_work)
    return new_work

@router.get(
    "/",
    response_model=List[WorkplaceResponse],
    summary="Listar lugares de trabajo",
    response_description="Todos los workplaces del usuario autenticado",
)
def get_workplaces(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Devuelve todos los lugares de trabajo registrados por el usuario autenticado."""
    return db.query(Workplace).filter(Workplace.user_id == current_user.id).all()

@router.patch(
    "/{workplace_id}",
    response_model=WorkplaceResponse,
    summary="Actualizar lugar de trabajo",
    response_description="Workplace con datos actualizados",
    responses={404: {"description": "Workplace no encontrado"}},
)
def update_workplace(workplace_id: int, work_data: WorkplaceUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Actualiza la dirección o coordenadas de un lugar de trabajo. Solo se modifican los campos enviados."""
    work = db.query(Workplace).filter(Workplace.id == workplace_id, Workplace.user_id == current_user.id).first()
    if not work:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
        
    update_data = work_data.model_dump(exclude_unset=True)

    if 'work_lat' in update_data or 'work_lon' in update_data:
        lat = update_data.get('work_lat', work.work_lat)
        lon = update_data.get('work_lon', work.work_lon)
        if not is_within_lima(lat, lon):
            raise HTTPException(status_code=400, detail=LIMA_LOCATION_ERROR)

    for key, value in update_data.items():
        setattr(work, key, value)
        
    db.commit()
    db.refresh(work)
    return work

@router.delete(
    "/{workplace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar lugar de trabajo",
    responses={404: {"description": "Workplace no encontrado"}},
)
def delete_workplace(workplace_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Elimina un lugar de trabajo del usuario. Solo el dueño puede eliminarlo."""
    work = db.query(Workplace).filter(Workplace.id == workplace_id, Workplace.user_id == current_user.id).first()
    if not work:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    
    db.delete(work)
    db.commit()
    return None
