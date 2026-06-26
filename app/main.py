from fastapi import FastAPI
from sqlalchemy import text
from app.core.database import Base, engine
from app.api import auth, properties, recommend, workplaces, geocode, recommendation_preferences, admin

# Importar todos los modelos para que SQLAlchemy los registre
from app.models import user, property, workplace, recommendation_history, recommendation_preference, otp_code

# Habilitar PostGIS y crear tablas al arrancar
print("Sincronizando Base de Datos PostgreSQL...")
with engine.connect() as conn:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    conn.commit()
Base.metadata.create_all(bind=engine)

# Limpieza de OTP vencidos al arrancar (cubre periodos de inactividad)
from app.core.otp import purge_expired_otps
try:
    purgados = purge_expired_otps()
    if purgados:
        print(f"OTP vencidos purgados al inicio: {purgados}")
except Exception as e:
    print(f"No se pudo purgar OTP al inicio: {e}")

app = FastAPI(
    title="Micasita AI-Backend API",
    description="Backend oficial con PostgreSQL, Autenticacion y Machine Learning para Micasita",
    version="1.0.0"
)

# Registramos los endpoints creados
app.include_router(auth.router)
app.include_router(properties.router)
app.include_router(recommend.router)
app.include_router(workplaces.router)
app.include_router(recommendation_preferences.router)
app.include_router(geocode.router)
app.include_router(admin.router)

@app.get("/")
@app.head("/")
def read_root():
    return {"message": "Servidor Micasita AI Operativo! Ve a /docs para interactuar con la API."}

