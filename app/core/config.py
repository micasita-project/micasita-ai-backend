from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Micasita AI Backend"
    
    # Base de Datos PostgreSQL
    # URL default asume puerto estandar y un usuario/bd local comun. Puedes cambiarlo luego en tu archivo .env
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/micasita_db"
    
    # JWT Auth
    SECRET_KEY: str = "TesisMicasitaSuperSecretKey2026_CambiarEnProduccion"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7 # 7 días de sesión
    
    # Cloudinary
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    class Config:
        env_file = ".env"

settings = Settings()
