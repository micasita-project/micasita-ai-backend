import os
import sys
from sqlalchemy import text

# Agregamos la ruta principal al path para que pueda importar módulos de 'app'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine

def add_features_column():
    print("Intentando agregar columna 'features' a la tabla 'properties'...")
    try:
        with engine.connect() as conn:
            # SQL para agregar la columna si no existe (PostgreSQL)
            conn.execute(text("ALTER TABLE properties ADD COLUMN IF NOT EXISTS features VARCHAR[] DEFAULT '{}';"))
            conn.commit()
            print("Columna 'features' agregada correctamente (o ya existía).")
            
    except Exception as e:
        print(f"Error al actualizar la base de datos: {e}")

if __name__ == "__main__":
    add_features_column()
