from pydantic import BaseModel, EmailStr
from typing import Optional

# 1. Esquemas de Creación/Registro
class UserCreate(BaseModel):
    email: EmailStr
    password: str

# 2. Respuesta que devuelve la API (Ocultando la contraseña)
class UserResponse(BaseModel):
    id: int
    email: EmailStr
    role: str
    home_lat: Optional[float] = None
    home_lon: Optional[float] = None
    home_address: Optional[str] = None

    class Config:
        from_attributes = True

# 3. Actualizar Casa
class UserHomeUpdate(BaseModel):
    home_lat: float
    home_lon: float
    home_address: str

# 4. JWT Token
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
