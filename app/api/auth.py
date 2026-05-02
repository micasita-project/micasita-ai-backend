from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, Token
from app.core.security import get_password_hash, verify_password, create_access_token, get_current_user
from app.core.config import settings
from datetime import timedelta
from fastapi.security import OAuth2PasswordRequestForm

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=UserResponse)
def register_user(user: UserCreate, db: Session = Depends(get_db)):
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

@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

from app.schemas.user import UserHomeUpdate

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Obtiene el perfil del usuario logueado"""
    return current_user

@router.put("/me/home", response_model=UserResponse)
def update_user_home(home_data: UserHomeUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Actualiza la ubicación de la casa actual del usuario"""
    current_user.home_lat = home_data.home_lat
    current_user.home_lon = home_data.home_lon
    current_user.home_address = home_data.home_address
    db.commit()
    db.refresh(current_user)
    return current_user

