from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.models.workplace import Workplace
from app.models.user import User
from app.schemas.workplace import WorkplaceCreate, WorkplaceResponse
from app.core.security import get_current_user

router = APIRouter(prefix="/workplaces", tags=["Trabajos (Workplaces)"])

@router.post("/", response_model=WorkplaceResponse)
def create_workplace(work_data: WorkplaceCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Crear un nuevo lugar de trabajo/estudio para el motor IA"""
    new_work = Workplace(**work_data.model_dump(), user_id=current_user.id)
    db.add(new_work)
    db.commit()
    db.refresh(new_work)
    return new_work

@router.get("/", response_model=List[WorkplaceResponse])
def get_workplaces(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Devuelve la lista de todos los trabajos guardados por el usuario logueado"""
    return db.query(Workplace).filter(Workplace.user_id == current_user.id).all()

@router.delete("/{workplace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workplace(workplace_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Borrar un trabajo"""
    work = db.query(Workplace).filter(Workplace.id == workplace_id, Workplace.user_id == current_user.id).first()
    if not work:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    
    db.delete(work)
    db.commit()
    return None
