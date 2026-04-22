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

    class Config:
        from_attributes = True

# 3. JWT Token
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
