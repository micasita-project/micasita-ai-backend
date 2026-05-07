from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.models.property import Property
from app.models.user import User
from app.schemas.property import PropertyResponse, PropertyStatusUpdate
from app.core.security import get_current_admin

router = APIRouter(prefix="/admin", tags=["Admin (Moderación)"])

@router.get("/properties/pending", response_model=List[PropertyResponse])
def get_pending_properties(
    skip: int = 0, 
    limit: int = 100, 
    admin: User = Depends(get_current_admin), 
    db: Session = Depends(get_db)
):
    """Listar todas las viviendas esperando aprobación. Solo accesible para administradores."""
    return db.query(Property).filter(Property.status == "pending").offset(skip).limit(limit).all()

@router.patch("/properties/{property_id}/status", response_model=PropertyResponse)
def update_property_status(
    property_id: int, 
    status_data: PropertyStatusUpdate, 
    admin: User = Depends(get_current_admin), 
    db: Session = Depends(get_db)
):
    """Aprobar o rechazar una vivienda. Solo accesible para administradores."""
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Vivienda no encontrada")
    
    if status_data.status not in ["approved", "rejected", "pending"]:
        raise HTTPException(status_code=400, detail="Estado no válido")
        
    prop.status = status_data.status
    db.commit()
    db.refresh(prop)
    return prop
