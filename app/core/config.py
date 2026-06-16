from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Micasita AI Backend"
    
    # Base de Datos PostgreSQL
    DATABASE_URL: str
    
    # JWT Auth
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080 # 7 días de sesión
    
    # Cloudinary
    CLOUDINARY_CLOUD_NAME: str
    CLOUDINARY_API_KEY: str
    CLOUDINARY_API_SECRET: str

    # Resend
    RESEND_API_KEY: str
    RESEND_EMAIL_SENDER: str

    model_config = {
        "env_file": ".env",
        "case_sensitive": True
    }

settings = Settings()
