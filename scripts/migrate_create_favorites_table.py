import os
import sys
from sqlalchemy import text

# Agregamos la ruta principal al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine

def run_migration():
    print("Iniciando migración: Creando tabla 'favorites'...")
    
    query = text("""
        CREATE TABLE IF NOT EXISTS favorites (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, property_id)
        );
    """)
    
    try:
        with engine.connect() as connection:
            with connection.begin():
                connection.execute(query)
        print("¡Tabla 'favorites' creada exitosamente!")
    except Exception as e:
        print(f"Error durante la migración: {e}")

if __name__ == "__main__":
    run_migration()
