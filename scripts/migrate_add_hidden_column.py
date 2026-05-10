import os
import sys
from sqlalchemy import text

# Agregamos la ruta principal al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine

def run_migration():
    print("Iniciando migración manual: Añadiendo columna 'hidden_by_user_block' a 'properties'...")
    
    query = text("ALTER TABLE properties ADD COLUMN IF NOT EXISTS hidden_by_user_block BOOLEAN DEFAULT FALSE NOT NULL;")
    
    try:
        with engine.connect() as connection:
            with connection.begin():
                connection.execute(query)
        print("¡Migración completada exitosamente!")
    except Exception as e:
        print(f"Error durante la migración: {e}")

if __name__ == "__main__":
    run_migration()
