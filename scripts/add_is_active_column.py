import os
import sys
from sqlalchemy import text

# Agregamos la ruta principal al path para que pueda importar módulos de 'app'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine

def add_is_active_column():
    print("Intentando agregar columna 'is_active' a la tabla 'users'...")
    try:
        with engine.connect() as conn:
            # PostgreSQL syntax to add column with default True
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;"))
            conn.commit()
            print("Columna 'is_active' agregada correctamente (o ya existía).")
            
    except Exception as e:
        print(f"Error al actualizar la base de datos: {e}")

if __name__ == "__main__":
    add_is_active_column()
