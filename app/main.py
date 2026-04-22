from fastapi import FastAPI
from app.core.database import Base, engine
from app.api import auth, properties, recommend, workplaces

# Creamos las tablas de la base de datos automáticamente si no existen
print("Sincronizando Base de Datos PostgreSQL...")
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Micasita AI-Backend API",
    description="Backend oficial con PostgreSQL, Autenticación y Machine Learning para Micasita",
    version="1.0.0"
)

# Registramos los endpoints creados
app.include_router(auth.router)
app.include_router(properties.router)
app.include_router(recommend.router)
app.include_router(workplaces.router)

@app.get("/")
def read_root():
    return {"message": "¡Servidor Micasita AI Operativo! Ve a /docs para interactuar con la API."}
