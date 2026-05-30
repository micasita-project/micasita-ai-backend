from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional
from app.core.database import get_db
from app.models.property import Property
from app.models.user import User
from app.schemas.property import PropertyResponse, PropertyStatusUpdate
from app.schemas.user import UserResponse, UserStatusUpdate
from app.core.security import get_current_admin
from app.core.email import email_service
from app.core.email_templates import get_block_notification_template, get_property_status_template

router = APIRouter(prefix="/admin", tags=["Admin (Moderación)"])

@router.get(
    "/properties/pending",
    response_model=List[PropertyResponse],
    summary="Viviendas pendientes de revisión",
    response_description="Lista de viviendas en estado pending",
    responses={403: {"description": "El usuario no tiene rol admin"}},
)
def get_pending_properties(
    skip: int = 0,
    limit: int = 100,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Lista todas las viviendas en estado `pending` que esperan aprobación o rechazo."""
    return db.query(Property).filter(Property.status == "pending").offset(skip).limit(limit).all()

@router.patch(
    "/properties/{property_id}/status",
    response_model=PropertyResponse,
    summary="Aprobar o rechazar vivienda",
    response_description="Vivienda con estado actualizado",
    responses={
        400: {"description": "Estado inválido o rejection_reason faltante al rechazar"},
        403: {"description": "El usuario no tiene rol admin"},
        404: {"description": "Vivienda no encontrada"},
    },
)
def update_property_status(
    property_id: int,
    status_data: PropertyStatusUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Cambia el estado de una vivienda a `approved`, `rejected` o `pending`.

    - Al rechazar (`rejected`), el campo `rejection_reason` es obligatorio.
    - Se envía una notificación por email al propietario al cambiar el estado.
    """
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Vivienda no encontrada")
    
    if status_data.status not in ["approved", "rejected", "pending"]:
        raise HTTPException(status_code=400, detail="Estado no válido")
        
    prop.status = status_data.status
    if status_data.status == "rejected":
        if not status_data.rejection_reason or not status_data.rejection_reason.strip():
            raise HTTPException(status_code=400, detail="El motivo de rechazo (rejection_reason) es obligatorio al rechazar una vivienda")
        prop.rejection_reason = status_data.rejection_reason
    else:
        prop.rejection_reason = None # Limpiamos el motivo si es aprobada o pendiente
        
    db.commit()
    db.refresh(prop)
    
    propietario = db.query(User).filter(User.id == prop.publisher_id).first()
    if propietario:
        subject = f"Actualización de tu propiedad: {prop.status.capitalize()}"
        html_content = get_property_status_template(
            user_name=propietario.name,
            property_title=prop.title,
            status=prop.status,
            reason=prop.rejection_reason
        )
        email_service.send_email(propietario.email, subject, html_content)
            
    return prop

@router.get(
    "/users",
    response_model=List[UserResponse],
    summary="Listar usuarios",
    response_description="Lista de usuarios registrados en el sistema",
    responses={403: {"description": "El usuario no tiene rol admin"}},
)
def get_all_users(
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Lista todos los usuarios del sistema. El parámetro `search` filtra por email, nombre o apellido (búsqueda parcial)."""
    query = db.query(User)
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                User.email.ilike(search_term),
                User.name.ilike(search_term),
                User.last_name.ilike(search_term)
            )
        )
        
    return query.offset(skip).limit(limit).all()

@router.patch(
    "/users/{user_id}/status",
    response_model=UserResponse,
    summary="Activar o bloquear usuario",
    response_description="Usuario con estado actualizado",
    responses={
        400: {"description": "Un admin no puede bloquearse a sí mismo"},
        403: {"description": "El usuario no tiene rol admin"},
        404: {"description": "Usuario no encontrado"},
    },
)
def update_user_status(
    user_id: int,
    status_data: UserStatusUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Activa o bloquea la cuenta de un usuario (`is_active: true/false`).

    - Al bloquear, todas sus viviendas se ocultan automáticamente del feed público.
    - Al reactivar, sus viviendas vuelven a ser visibles.
    - Se envía una notificación por email al usuario afectado.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    if user.role == "admin" and user.id == admin.id:
        raise HTTPException(status_code=400, detail="No puedes bloquearte a ti mismo")
        
    user.is_active = status_data.is_active
    
    # Ocultar o mostrar todas las propiedades del usuario automáticamente
    # Si is_active es False, hidden_by_user_block debe ser True
    db.query(Property).filter(Property.publisher_id == user.id).update(
        {"hidden_by_user_block": not status_data.is_active}
    )
    
    db.commit()
    db.refresh(user)
    
    # Enviar notificación por correo
    subject = "Actualización importante de tu cuenta - MiCasita"
    html_content = get_block_notification_template(user.name, user.is_active)
    email_service.send_email(user.email, subject, html_content)
    
    return user
