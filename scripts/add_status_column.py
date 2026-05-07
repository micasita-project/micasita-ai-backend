import os
import sys
from sqlalchemy import text

# Agregamos la ruta principal al path para que pueda importar módulos de 'app'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine

def add_status_column():
    print("Intentando agregar columna 'status' a la tabla 'properties'...")
    try:
        with engine.connect() as conn:
            # SQL para agregar la columna si no existe
            conn.execute(text("ALTER TABLE properties ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'pending';"))
            conn.commit()
            print("Columna 'status' agregada correctamente (o ya existía).")
            
            # Opcional: Marcar todas las existentes como aprobadas para que no desaparezcan del feed
            print("Marcando propiedades existentes como 'approved'...")
            conn.execute(text("UPDATE properties SET status = 'approved' WHERE status IS NULL OR status = 'pending';"))
            conn.commit()
            print("Propiedades actualizadas.")
            
    except Exception as e:
        print(f"Error al actualizar la base de datos: {e}")

if __name__ == "__main__":
    add_status_column()
