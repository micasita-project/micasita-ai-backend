from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Micasita AI Backend"
    
    # Base de Datos PostgreSQL
    DATABASE_URL: str
    
    # JWT Auth
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080 # 7 días de sesión
    
    # Azure Blob Storage
    AZURE_STORAGE_CONNECTION_STRING: str
    AZURE_CONTAINER_NAME: str

    model_config = {
        "env_file": ".env",
        "case_sensitive": True
    }

settings = Settings()
