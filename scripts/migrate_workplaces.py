import os
import sys

# Agregar al path para importar modulos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine
from sqlalchemy import text

def migrate():
    print("Iniciando migración de Workplaces -> Recommendation Preferences...")
    
    with engine.begin() as conn:
        try:
            # 1. Crear nueva tabla
            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS recommendation_preferences (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                workplace_id INTEGER NOT NULL REFERENCES workplaces(id) ON DELETE CASCADE,
                budget FLOAT NOT NULL,
                preferred_transportation VARCHAR NOT NULL,
                max_distance_km FLOAT DEFAULT 10.0
            );
            """))
            print("Tabla recommendation_preferences creada.")
            
            # 2. Migrar datos existentes (ignorando los que ya fueron migrados si se corre dos veces)
            # Como puede haber multiples workplaces con budget, insertamos todos.
            conn.execute(text("""
            INSERT INTO recommendation_preferences (user_id, workplace_id, budget, preferred_transportation)
            SELECT user_id, id, budget, preferred_transportation FROM workplaces
            ON CONFLICT DO NOTHING;
            """))
            print("Datos migrados de workplaces a recommendation_preferences.")
            
            # 3. Renombrar alias a work_address (si todavia se llama alias)
            try:
                conn.execute(text("ALTER TABLE workplaces RENAME COLUMN alias TO work_address;"))
                print("Columna 'alias' renombrada a 'work_address'.")
            except Exception as e:
                print(f"Nota: Columna 'alias' ya no existe o error: {e}")
            
            # 4. Eliminar columnas budget y preferred_transportation
            try:
                conn.execute(text("ALTER TABLE workplaces DROP COLUMN budget;"))
                conn.execute(text("ALTER TABLE workplaces DROP COLUMN preferred_transportation;"))
                print("Columnas antiguas eliminadas de workplaces.")
            except Exception as e:
                print(f"Nota: Columnas antiguas ya fueron eliminadas o error: {e}")
                
            print("Migración completada exitosamente!")
        except Exception as e:
            print(f"Error crítico durante la migración: {e}")
            raise

if __name__ == "__main__":
    migrate()
