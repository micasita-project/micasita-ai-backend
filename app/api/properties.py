from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session
from typing import List
import cloudinary
import cloudinary.uploader
from app.core.database import get_db
from app.models.property import Property
from app.models.user import User
from app.schemas.property import PropertyCreate, PropertyResponse, ImageUploadResponse
from app.core.security import get_current_user
from app.core.config import settings

router = APIRouter(prefix="/properties", tags=["Properties (Viviendas)"])

# Configuración obligatoria de Cloudinary
cloudinary.config( 
  cloud_name = settings.CLOUDINARY_CLOUD_NAME, 
  api_key = settings.CLOUDINARY_API_KEY, 
  api_secret = settings.CLOUDINARY_API_SECRET 
)

@router.post("/upload_image", response_model=ImageUploadResponse)
def upload_image(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    """Sube un archivo a Cloudinary y devuelve el URL web estático. Ideal para la App Móvil antes de publicar la casa."""
    if not settings.CLOUDINARY_API_KEY:
        raise HTTPException(status_code=500, detail="Falta configurar Cloudinary en el archivo .env")
    try:
        resultado = cloudinary.uploader.upload(file.file)
        return {"url": resultado.get("secure_url")}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error subiendo a Cloudinary: {str(e)}")

@router.post("/", response_model=PropertyResponse)
def create_property(property_data: PropertyCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Solo usuarios registrados publican casas"""
    new_property = Property(**property_data.model_dump(), publisher_id=current_user.id)
    db.add(new_property)
    db.commit()
    db.refresh(new_property)
    return new_property

@router.get("/", response_model=List[PropertyResponse])
def get_all_properties(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Público para cualquier visitante. Endpoint útil para el feed principal de Micasita."""
    casas = db.query(Property).offset(skip).limit(limit).all()
    return casas

@router.delete("/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_property(property_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Solo el dueño original o admin puede borrar su publicacion"""
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Vivienda no encontrada")
    
    if prop.publisher_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="No tienes permisos para borrar esta propiedad")
        
    db.delete(prop)
    db.commit()
    return None
