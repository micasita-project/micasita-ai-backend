from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session
from typing import List, Optional
import cloudinary
import cloudinary.uploader
from app.core.database import get_db
from app.models.property import Property
from app.models.user import User
from app.schemas.property import PropertyCreate, PropertyUpdate, PropertyResponse, ImageUploadResponse, PaginatedPropertyResponse
from app.core.security import get_current_user, get_current_user_optional
from app.core.config import settings
from app.core.geo import is_within_lima, LIMA_LOCATION_ERROR
from app.models.favorite import Favorite

router = APIRouter(prefix="/properties", tags=["Properties (Viviendas)"])

cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True,
)


def populate_favorites(properties, user_id, db: Session):
    if not user_id:
        return properties

    fav_ids = set(
        row[0] for row in db.query(Favorite.property_id).filter(Favorite.user_id == user_id).all()
    )

    for p in properties:
        p.is_favorite = p.id in fav_ids
    return properties


@router.post(
    "/upload_image",
    response_model=ImageUploadResponse,
    summary="Subir imagen de vivienda",
    response_description="URL pública permanente de la imagen en Cloudinary",
    responses={
        400: {"description": "Error al subir el archivo a Cloudinary"},
    },
)
def upload_image(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    """
    Sube una imagen a Cloudinary y devuelve la URL pública segura.

    Usar este endpoint antes de crear una vivienda para obtener las URLs de las imágenes.
    """
    try:
        content = file.file.read()
        result = cloudinary.uploader.upload(content, resource_type="image", folder="micasita")
        return {"url": result["secure_url"]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error subiendo imagen: {str(e)}")


@router.post(
    "/",
    response_model=PropertyResponse,
    summary="Publicar vivienda",
    response_description="Vivienda creada en estado pendiente de revisión",
)
def create_property(property_data: PropertyCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Crea una nueva publicación de vivienda. El estado inicial siempre es `pending`.

    Un administrador debe aprobarla antes de que aparezca en el feed público.
    Incluir en `images` las URLs obtenidas previamente con `/upload_image`.
    """
    if not is_within_lima(property_data.latitude, property_data.longitude):
        raise HTTPException(status_code=400, detail=LIMA_LOCATION_ERROR)

    data = property_data.model_dump()
    new_property = Property(
        **data,
        publisher_id=current_user.id,
        status="pending",
        location=f'SRID=4326;POINT({data["longitude"]} {data["latitude"]})',
    )
    db.add(new_property)
    db.commit()
    db.refresh(new_property)
    return new_property


@router.patch(
    "/{property_id}",
    response_model=PropertyResponse,
    summary="Editar vivienda",
    response_description="Vivienda actualizada",
    responses={
        403: {"description": "Sin permisos o vivienda en estado pending"},
        404: {"description": "Vivienda no encontrada"},
    },
)
def update_property(property_id: int, property_data: PropertyUpdate, current_user: 
    User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Actualiza los campos de una vivienda. Solo el dueño o un admin pueden editar.

    - No se puede editar si la vivienda está en estado `pending`.
    - Al editar (sin ser admin), la vivienda vuelve automáticamente a `pending` para nueva revisión.
    """
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

    if 'latitude' in update_data or 'longitude' in update_data:
        new_lat = update_data.get('latitude', prop.latitude)
        new_lon = update_data.get('longitude', prop.longitude)
        if not is_within_lima(new_lat, new_lon):
            raise HTTPException(status_code=400, detail=LIMA_LOCATION_ERROR)

    for key, value in update_data.items():
        setattr(prop, key, value)

    # Sincronizar columna PostGIS si cambiaron las coordenadas
    if 'latitude' in update_data or 'longitude' in update_data:
        prop.location = f'SRID=4326;POINT({prop.longitude} {prop.latitude})'

    # Si el usuario NO es admin, forzamos que vuelva a revisión
    if current_user.role != "admin":
        prop.status = "pending"

    db.commit()
    db.refresh(prop)
    return prop


@router.get(
    "/mine",
    response_model=List[PropertyResponse],
    summary="Mis publicaciones",
    response_description="Lista de viviendas del usuario autenticado en cualquier estado",
)
def get_my_properties(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Devuelve todas las viviendas publicadas por el usuario (pending, approved y rejected). Para la sección 'Mis Publicaciones'."""
    casas = db.query(Property).filter(
        Property.publisher_id == current_user.id).all()
    
    # Popular favoritos
    populate_favorites(casas, current_user.id, db)
    
    return casas


@router.get(
    "/favorites",
    response_model=List[PropertyResponse],
    summary="Mis favoritos",
    response_description="Lista de viviendas marcadas como favoritas (is_favorite siempre true)",
)
def get_my_favorites(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Devuelve todas las viviendas que el usuario marcó como favoritas."""
    favorites = db.query(Property).join(
        Favorite, Favorite.property_id == Property.id
    ).filter(
        Favorite.user_id == current_user.id
    ).all()
    
    for f in favorites:
        f.is_favorite = True
        
    return favorites


@router.get(
    "/{property_id}",
    response_model=PropertyResponse,
    summary="Detalle de vivienda",
    response_description="Datos completos de la vivienda",
    responses={404: {"description": "Vivienda no encontrada"}},
)
def get_property(property_id: int, current_user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    """
    Obtiene el detalle de una vivienda por su ID. Si el usuario está autenticado,
    incluye `is_favorite`.

    Las viviendas que no están `approved` (pendientes o rechazadas) solo las puede
    ver su propio publicador o un admin — de lo contrario, cualquiera sin login
    podría enumerar IDs y leer avisos aún no revisados, con teléfono y motivo de
    rechazo incluidos. Se responde 404 igual que "no existe", para no confirmar
    que el ID es válido pero restringido.
    """
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Vivienda no encontrada")

    is_owner = current_user is not None and current_user.id == prop.publisher_id
    is_admin = current_user is not None and current_user.role == "admin"
    if prop.status != "approved" and not (is_owner or is_admin):
        raise HTTPException(status_code=404, detail="Vivienda no encontrada")

    if current_user:
        is_fav = db.query(Favorite).filter(
            Favorite.user_id == current_user.id,
            Favorite.property_id == property_id
        ).first() is not None
        prop.is_favorite = is_fav
        
    return prop


@router.get(
    "/",
    response_model=PaginatedPropertyResponse,
    summary="Listar viviendas (feed público)",
    response_description="Lista paginada de viviendas aprobadas con total de registros",
)
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
    """
    Lista las viviendas aprobadas con paginación y filtros opcionales.

    No muestra viviendas de usuarios bloqueados (`hidden_by_user_block=true`).
    Si se envía token JWT, el campo `is_favorite` refleja el estado real del usuario.
    """
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


@router.delete(
    "/{property_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar vivienda",
    responses={
        403: {"description": "Sin permisos para eliminar esta vivienda"},
        404: {"description": "Vivienda no encontrada"},
    },
)
def delete_property(property_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Elimina permanentemente una vivienda. Solo el dueño o un administrador pueden hacerlo."""
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Vivienda no encontrada")

    if prop.publisher_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=403, detail="No tienes permisos para borrar esta propiedad")

    db.delete(prop)
    db.commit()
    return None


@router.post(
    "/{property_id}/favorite",
    status_code=status.HTTP_201_CREATED,
    summary="Añadir a favoritos",
    response_description="Confirmación de favorito añadido",
    responses={404: {"description": "Vivienda no encontrada"}},
)
def add_to_favorites(property_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Marca una vivienda como favorita. Si ya estaba marcada, devuelve 200 sin error."""
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


@router.delete(
    "/{property_id}/favorite",
    summary="Quitar de favoritos",
    response_description="Confirmación de favorito eliminado",
    responses={404: {"description": "La vivienda no estaba en favoritos"}},
)
def remove_from_favorites(property_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Quita una vivienda de la lista de favoritos del usuario."""
    favorite = db.query(Favorite).filter(
        Favorite.user_id == current_user.id,
        Favorite.property_id == property_id
    ).first()

    if not favorite:
        raise HTTPException(status_code=404, detail="No se encontró en tus favoritos")

    db.delete(favorite)
    db.commit()
    return {"message": "Quitada de favoritos exitosamente"}
