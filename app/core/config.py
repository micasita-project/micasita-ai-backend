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

    # scripts/seed_db.py — usuario admin y workplace de arranque para una base
    # nueva. Antes estaban hardcodeados en el script: credenciales siempre
    # iguales (admin@micasita.ai / password123) y una dirección real de
    # alguien como "casa" del admin semilla. Sin valores en .env, se usan
    # defaults genéricos y sin dato personal — nunca la dirección real.
    SEED_ADMIN_EMAIL: str = "admin@micasita.local"
    SEED_ADMIN_PASSWORD: str = ""  # vacío = seed_db.py genera una al azar y la imprime una vez
    SEED_ADMIN_HOME_LAT: float = -12.0464
    SEED_ADMIN_HOME_LON: float = -77.0428
    SEED_ADMIN_HOME_ADDRESS: str = "Lima, Perú"
    SEED_WORKPLACE_ADDRESS: str = "Oficina Central"
    SEED_WORKPLACE_LAT: float = -12.0931
    SEED_WORKPLACE_LON: float = -77.0465

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "ignore"
    }

settings = Settings()
