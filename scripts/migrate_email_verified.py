"""
Migration: add email_verified column to users table.

Run once:
    python scripts/migrate_email_verified.py

Existing users get email_verified = TRUE so they can still log in.
New registrations start with email_verified = FALSE (set by the app).
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import engine

SQL = """
ALTER TABLE users
ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT TRUE;
"""

if __name__ == "__main__":
    with engine.connect() as conn:
        conn.execute(text(SQL))
        conn.commit()
    print("Migration complete: email_verified column added (existing users set to TRUE).")
