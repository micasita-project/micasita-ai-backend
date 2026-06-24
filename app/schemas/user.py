from pydantic import BaseModel, EmailStr, Field
from typing import Optional

# 1. Esquemas de Creación/Registro
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None
    last_name: Optional[str] = None

# 2. Respuesta que devuelve la API (Ocultando la contraseña)
class UserResponse(BaseModel):
    id: int
    email: EmailStr
    role: str
    is_active: bool
    email_verified: bool
    name: Optional[str] = None
    last_name: Optional[str] = None
    home_lat: Optional[float] = None
    home_lon: Optional[float] = None
    home_address: Optional[str] = None

    class Config:
        from_attributes = True

class UserStatusUpdate(BaseModel):
    is_active: bool

# 3. Actualizar Perfil General
class UserProfileUpdate(BaseModel):
    name: Optional[str] = None
    last_name: Optional[str] = None

# 4. Actualizar Casa
class UserHomeUpdate(BaseModel):
    home_lat: float
    home_lon: float
    home_address: str

# 5. JWT Token
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

# 6. Auth OTP flows
class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    new_password: str = Field(min_length=8)

class VerifyEmailRequest(BaseModel):
    email: EmailStr
    otp: str

class ResendVerificationRequest(BaseModel):
    email: EmailStr

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)
