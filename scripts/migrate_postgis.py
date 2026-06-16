"""
Migración única: agrega la columna PostGIS 'location' a la tabla properties,
la puebla desde latitude/longitude y crea el índice GIST para consultas espaciales.

Ejecutar una sola vez:
    python scripts/migrate_postgis.py
"""
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import engine


def run():
    with engine.begin() as conn:
        print("1/3 Agregando columna location (GEOGRAPHY POINT)...")
        conn.execute(text("""
            ALTER TABLE properties
            ADD COLUMN IF NOT EXISTS location GEOGRAPHY(POINT, 4326);
        """))

        print("2/3 Poblando location desde latitude/longitude...")
        result = conn.execute(text("""
            UPDATE properties
            SET location = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography
            WHERE location IS NULL
              AND latitude IS NOT NULL
              AND longitude IS NOT NULL;
        """))
        print(f"    {result.rowcount} filas actualizadas.")

        print("3/3 Creando índice GIST sobre location...")
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_properties_location
            ON properties USING GIST(location);
        """))

    print("¡Migración PostGIS completada exitosamente!")


if __name__ == "__main__":
    run()
