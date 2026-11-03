import os
import sys
from sqlalchemy import text

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine


def run_migration():
    print("Añadiendo columnas de consentimiento a 'users'...")
    queries = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS consent_accepted_at TIMESTAMP NULL;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS consent_version VARCHAR(20) NULL;",
    ]
    try:
        with engine.connect() as connection:
            with connection.begin():
                for q in queries:
                    connection.execute(text(q))
        print("¡Migración completada exitosamente!")
    except Exception as e:
        print(f"Error durante la migración: {e}")


if __name__ == "__main__":
    run_migration()
