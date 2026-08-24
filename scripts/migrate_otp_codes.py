"""
Migration: create otp_codes table (persistent OTP store).

Run once:
    python scripts/migrate_otp_codes.py

Against production (overriding the DB URL):
    DATABASE_URL="<EXTERNAL_DATABASE_URL>" python scripts/migrate_otp_codes.py

Idempotent: uses CREATE TABLE / CREATE INDEX IF NOT EXISTS.
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import engine

STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS otp_codes (
        id SERIAL PRIMARY KEY,
        email VARCHAR NOT NULL,
        purpose VARCHAR NOT NULL,
        code VARCHAR NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0
    )
    """,
    # Por si la tabla ya existía de una corrida anterior de este script, de antes
    # de que se agregara el límite de intentos (app/core/otp.py).
    "ALTER TABLE otp_codes ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0",
    "CREATE INDEX IF NOT EXISTS ix_otp_codes_email ON otp_codes (email)",
    "CREATE INDEX IF NOT EXISTS ix_otp_codes_email_purpose ON otp_codes (email, purpose)",
]

if __name__ == "__main__":
    with engine.connect() as conn:
        for stmt in STATEMENTS:
            conn.execute(text(stmt))
        conn.commit()
    print("Migration complete: otp_codes table created.")
