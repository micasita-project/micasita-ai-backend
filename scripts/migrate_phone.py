"""
Migración: agrega columna 'phone' a properties y actualiza con valores de housing.json.

Uso:
    DATABASE_URL=<url_produccion> PYTHONPATH=. python scripts/migrate_phone.py
"""
import json, os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import SessionLocal, engine

JSON_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw", "housing.json")

def run():
    # 1. Agregar columna si no existe
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE properties ADD COLUMN IF NOT EXISTS phone VARCHAR;"))
        conn.commit()
    print("Columna 'phone' asegurada.")

    # 2. Cargar JSON
    with open(JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)

    phone_map = {str(p["id"]): str(p["phone"]) for p in data if p.get("phone")}
    print(f"Registros con phone en JSON: {len(phone_map)}")

    # 3. Actualizar con SQL directo (más rápido, no requiere cargar todos los modelos)
    with engine.connect() as conn:
        actualizados = 0
        sin_match = 0
        for entry in data:
            phone = entry.get("phone")
            if not phone:
                continue
            result = conn.execute(
                text("UPDATE properties SET phone = :phone WHERE id = :id"),
                {"phone": str(phone), "id": int(entry["id"])}
            )
            if result.rowcount > 0:
                actualizados += 1
            else:
                sin_match += 1
        conn.commit()
        print(f"Actualizados: {actualizados} | Sin coincidencia: {sin_match}")

    print("Migración completada.")

if __name__ == "__main__":
    run()
