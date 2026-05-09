import os
import sys
from sqlalchemy import text

# Agregamos la ruta principal al path para que pueda importar módulos de 'app'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine

def add_rejection_reason_column():
    print("Intentando agregar columna 'rejection_reason' a la tabla 'properties'...")
    try:
        with engine.connect() as conn:
            # PostgreSQL syntax to add column
            conn.execute(text("ALTER TABLE properties ADD COLUMN IF NOT EXISTS rejection_reason VARCHAR;"))
            conn.commit()
            print("Columna 'rejection_reason' agregada correctamente (o ya existía).")
            
    except Exception as e:
        print(f"Error al actualizar la base de datos: {e}")

if __name__ == "__main__":
    add_rejection_reason_column()
