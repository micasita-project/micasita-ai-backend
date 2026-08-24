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

    # SendGrid (email transaccional)
    SENDGRID_API_KEY: str
    SENDGRID_EMAIL_SENDER: str

    # TomTom: geocodificación de direcciones y tiempos de viaje con tráfico.
    # Solo se usa en scripts de preparación de datos, nunca en tiempo de request.
    TOMTOM_API_KEY: str = ""

    # Tipo de cambio USD → PEN. Estaba solo en .env y se leía con os.getenv en
    # recommendation_service, lo que dejaba dos mecanismos de configuración.
    USD_TO_PEN: float = 3.75

    # OSRM: por defecto el clúster público de demostración (routing.openstreetmap.de).
    # En local/producción con OSRM propio, se sobreescriben en .env — el segmento
    # final "/driving" es fijo en los 3, el perfil real lo define el grafo con el
    # que se levantó cada instancia, no la URL.
    OSRM_DRIVING_URL: str = "https://routing.openstreetmap.de/routed-car/route/v1/driving"
    OSRM_CYCLING_URL: str = "https://routing.openstreetmap.de/routed-bike/route/v1/driving"
    OSRM_WALKING_URL: str = "https://routing.openstreetmap.de/routed-foot/route/v1/driving"

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "ignore"
    }

settings = Settings()
