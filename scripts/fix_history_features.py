import os
import sys
import json
from sqlalchemy import text

# Agregamos la ruta principal al path para que pueda importar módulos de 'app'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine

def fix_history_features():
    print("Intentando corregir el historial de recomendaciones (RecommendationHistory) agregando 'features'...")
    try:
        with engine.connect() as conn:
            # Obtener todos los registros del historial
            result = conn.execute(text("SELECT id, results FROM recommendation_history;"))
            history_rows = result.fetchall()
            
            for row_id, results_str in history_rows:
                try:
                    results = json.loads(results_str)
                    modified = False
                    
                    for r in results:
                        # Si la propiedad en el resultado no tiene features, se lo agregamos
                        if "property" in r and "features" not in r["property"]:
                            r["property"]["features"] = [] # Default vacio
                            modified = True
                    
                    if modified:
                        new_results_str = json.dumps(results)
                        conn.execute(
                            text("UPDATE recommendation_history SET results = :results WHERE id = :id"),
                            {"results": new_results_str, "id": row_id}
                        )
                        print(f"Registro ID {row_id} actualizado con features vacíos.")
                except Exception as e:
                    print(f"Error procesando registro {row_id}: {e}")
            
            conn.commit()
            print("Corrección de historial completada.")
            
    except Exception as e:
        print(f"Error al conectar con la base de datos: {e}")

if __name__ == "__main__":
    fix_history_features()
