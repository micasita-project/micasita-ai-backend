from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, Token
from app.core.security import get_password_hash, verify_password, create_access_token, get_current_user
from app.core.geo import is_within_lima, LIMA_LOCATION_ERROR
from app.core.config import settings
from datetime import timedelta
from fastapi.security import OAuth2PasswordRequestForm

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post(
    "/register",
    response_model=UserResponse,
    summary="Registrar usuario",
    response_description="Usuario creado exitosamente",
    responses={400: {"description": "El email ya está registrado"}},
)
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    """
    Crea una nueva cuenta de usuario con rol `user` por defecto.

    - **email**: debe ser único en el sistema
    - **password**: se hashea con bcrypt antes de almacenarse
    """
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="El email ya está registrado")
    
    hashed_password = get_password_hash(user.password)
    new_user = User(
        email=user.email,
        hashed_password=hashed_password,
        role="user",
        name=user.name,
        last_name=user.last_name
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.post(
    "/login",
    response_model=Token,
    summary="Iniciar sesión",
    response_description="Token JWT Bearer",
    responses={
        401: {"description": "Email o contraseña incorrectos"},
        403: {"description": "Cuenta bloqueada o suspendida"},
    },
)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta cuenta ha sido bloqueada o suspendida por un administrador.",
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

from app.schemas.user import UserHomeUpdate, UserProfileUpdate

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Obtener perfil propio",
    response_description="Perfil del usuario autenticado",
)
def get_me(current_user: User = Depends(get_current_user)):
    """Devuelve el perfil completo del usuario autenticado, incluyendo ubicación de su casa actual."""
    return current_user

@router.patch(
    "/me",
    response_model=UserResponse,
    summary="Actualizar perfil",
    response_description="Perfil actualizado",
)
def update_profile(profile_data: UserProfileUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Actualiza el nombre y/o apellido del usuario. Solo los campos enviados se modifican."""
    if profile_data.name is not None:
        current_user.name = profile_data.name
    if profile_data.last_name is not None:
        current_user.last_name = profile_data.last_name
        
    db.commit()
    db.refresh(current_user)
    return current_user

@router.put(
    "/me/home",
    response_model=UserResponse,
    summary="Actualizar ubicación de casa actual",
    response_description="Perfil con nueva ubicación de casa",
)
def update_user_home(home_data: UserHomeUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Guarda la ubicación de la vivienda actual del usuario.

    Esta coordenada se usa para calcular el campo `time_saved_mins` en las recomendaciones
    (diferencia entre el tiempo de viaje actual y el de la nueva vivienda propuesta).
    """
    if not is_within_lima(home_data.home_lat, home_data.home_lon):
        raise HTTPException(status_code=400, detail=LIMA_LOCATION_ERROR)

    current_user.home_lat = home_data.home_lat
    current_user.home_lon = home_data.home_lon
    current_user.home_address = home_data.home_address
    db.commit()
    db.refresh(current_user)
    return current_user

