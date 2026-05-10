from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session
from typing import List, Optional
import uuid
from azure.storage.blob import BlobServiceClient
from app.core.database import get_db
from app.models.property import Property
from app.models.user import User
from app.schemas.property import PropertyCreate, PropertyUpdate, PropertyResponse, ImageUploadResponse, PaginatedPropertyResponse
from app.core.security import get_current_user, get_current_user_optional
from app.core.config import settings
from app.models.favorite import Favorite

router = APIRouter(prefix="/properties", tags=["Properties (Viviendas)"])

def populate_favorites(properties, user_id, db: Session):
    if not user_id:
        return properties
    
    # Obtener IDs de favoritos del usuario
    fav_ids = set(
        row[0] for row in db.query(Favorite.property_id).filter(Favorite.user_id == user_id).all()
    )
    
    for p in properties:
        p.is_favorite = p.id in fav_ids
    return properties

# Configuración inicial de Azure
blob_service_client = None
if settings.AZURE_STORAGE_CONNECTION_STRING:
    blob_service_client = BlobServiceClient.from_connection_string(
        settings.AZURE_STORAGE_CONNECTION_STRING)


@router.post("/upload_image", response_model=ImageUploadResponse)
def upload_image(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    """Sube un archivo a Azure Blob Storage y devuelve el URL web estático."""
    if not blob_service_client or not settings.AZURE_CONTAINER_NAME:
        raise HTTPException(
            status_code=500, detail="Falta configurar Azure en el archivo .env")

    try:
        # Generar un nombre de archivo único
        file_extension = file.filename.split(
            ".")[-1] if "." in file.filename else "jpg"
        unique_filename = f"{uuid.uuid4()}.{file_extension}"

        # Obtener el cliente del contenedor y el cliente del blob
        blob_client = blob_service_client.get_blob_client(
            container=settings.AZURE_CONTAINER_NAME,
            blob=unique_filename
        )

        # Subir el archivo
        # Importante: Leemos el contenido de UploadFile
        content = file.file.read()
        blob_client.upload_blob(content, overwrite=True)

        # Construir la URL pública (asumiendo que el contenedor tiene acceso público de lectura)
        public_url = blob_client.url

        return {"url": public_url}
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Error subiendo a Azure: {str(e)}")


@router.post("/", response_model=PropertyResponse)
def create_property(property_data: PropertyCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Solo usuarios registrados publican casas. Por defecto quedan 'en revisión'."""
    new_property = Property(
        **property_data.model_dump(),
        publisher_id=current_user.id,
        status="pending"  # Aseguramos que inicie en revisión
    )
    db.add(new_property)
    db.commit()
    db.refresh(new_property)
    return new_property


@router.patch("/{property_id}", response_model=PropertyResponse)
def update_property(property_id: int, property_data: PropertyUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Edita una propiedad siempre que no esté en estado 'pending'."""
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Vivienda no encontrada")

    if prop.publisher_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=403, detail="No tienes permisos para editar esta propiedad")

    if prop.status == "pending":
        raise HTTPException(
            status_code=403, detail="No se puede editar una vivienda en estado pending")

    update_data = property_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(prop, key, value)

    # Si el usuario NO es admin, forzamos que vuelva a revisión
    if current_user.role != "admin":
        prop.status = "pending"

    db.commit()
    db.refresh(prop)
    return prop


@router.get("/mine", response_model=List[PropertyResponse])
def get_my_properties(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Obtiene todas las propiedades creadas por el usuario autenticado (para la sección 'Mis Publicaciones')."""
    casas = db.query(Property).filter(
        Property.publisher_id == current_user.id).all()
    
    # Popular favoritos
    populate_favorites(casas, current_user.id, db)
    
    return casas


@router.get("/favorites", response_model=List[PropertyResponse])
def get_my_favorites(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Obtener la lista de viviendas marcadas como favoritas por el usuario."""
    favorites = db.query(Property).join(
        Favorite, Favorite.property_id == Property.id
    ).filter(
        Favorite.user_id == current_user.id
    ).all()
    
    for f in favorites:
        f.is_favorite = True
        
    return favorites


@router.get("/{property_id}", response_model=PropertyResponse)
def get_property(property_id: int, current_user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    """Obtiene el detalle de una propiedad por su ID."""
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Vivienda no encontrada")
    
    if current_user:
        is_fav = db.query(Favorite).filter(
            Favorite.user_id == current_user.id,
            Favorite.property_id == property_id
        ).first() is not None
        prop.is_favorite = is_fav
        
    return prop


@router.get("/", response_model=PaginatedPropertyResponse)
def list_properties(
    skip: int = 0,
    limit: int = 10,
    district: Optional[str] = None,
    bedrooms: Optional[int] = None,
    bathrooms: Optional[int] = None,
    parking: Optional[int] = None,
    min_area_sqm: Optional[float] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Lista propiedades aprobadas con paginación y filtros."""
    # Mostrar solo propiedades aprobadas y que no estén ocultas por bloqueo de usuario
    query = db.query(Property).filter(
        Property.status == "approved",
        Property.hidden_by_user_block == False,
    )

    if district:
        query = query.filter(Property.district.ilike(f"%{district}%"))
    if bedrooms is not None:
        query = query.filter(Property.bedrooms >= bedrooms)
    if bathrooms is not None:
        query = query.filter(Property.bathrooms >= bathrooms)
    if parking is not None:
        query = query.filter(Property.parking >= parking)
    if min_area_sqm is not None:
        query = query.filter(Property.total_area_sqm >= min_area_sqm)
    if min_price is not None:
        query = query.filter(Property.price >= min_price)
    if max_price is not None:
        query = query.filter(Property.price <= max_price)

    total = query.count()
    items = query.offset(skip).limit(limit).all()

    # Popular favoritos
    populate_favorites(items, current_user.id if current_user else None, db)

    return {"total": total, "items": items}


@router.delete("/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_property(property_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Solo el dueño original o admin puede borrar su publicacion"""
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Vivienda no encontrada")

    if prop.publisher_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=403, detail="No tienes permisos para borrar esta propiedad")

    db.delete(prop)
    db.commit()
    return None


@router.post("/{property_id}/favorite", status_code=status.HTTP_201_CREATED)
def add_to_favorites(property_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Añadir una propiedad a favoritos."""
    # Verificar que la propiedad exista
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Vivienda no encontrada")

    # Verificar si ya es favorita
    existing = db.query(Favorite).filter(
        Favorite.user_id == current_user.id,
        Favorite.property_id == property_id
    ).first()

    if existing:
        return {"message": "Ya está en tus favoritos"}

    new_favorite = Favorite(user_id=current_user.id, property_id=property_id)
    db.add(new_favorite)
    db.commit()
    return {"message": "Añadida a favoritos exitosamente"}


@router.delete("/{property_id}/favorite")
def remove_from_favorites(property_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Quitar una propiedad de favoritos."""
    favorite = db.query(Favorite).filter(
        Favorite.user_id == current_user.id,
        Favorite.property_id == property_id
    ).first()

    if not favorite:
        raise HTTPException(status_code=404, detail="No se encontró en tus favoritos")

    db.delete(favorite)
    db.commit()
    return {"message": "Quitada de favoritos exitosamente"}
