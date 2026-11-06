"""Reconstrucción y copia de las bases locales conocidas; nunca acepta un host remoto.

python scripts/local_database.py --rebuild-local --clone-e2e
python scripts/local_database.py --clone-e2e
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from app.core.config import settings

LOCAL_DB = "micasita_db"
E2E_DB = "micasita_e2e"
BACKUPS = ROOT / "data/local/backups"


def local_url(value):
    url = make_url(value)
    if url.get_backend_name() != "postgresql" or url.host not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Solo se permite PostgreSQL en localhost/127.0.0.1/::1")
    if url.database not in {LOCAL_DB, E2E_DB}:
        raise ValueError("Solo se permite micasita_db o micasita_e2e")
    # Evitar que parámetros libpq reemplacen el host/base ya validados.
    if url.query:
        raise ValueError("La conexión local no debe contener parámetros adicionales")
    return url


def pg_environment(url):
    return {**os.environ, "PGHOST": url.host, "PGPORT": str(url.port or 5432),
            "PGUSER": url.username or "", "PGPASSWORD": url.password or "",
            "PGCONNECT_TIMEOUT": "5"}


def pg_command(name, url, *args):
    executable = shutil.which(name)
    if not executable:
        raise RuntimeError(f"Falta {name} en PATH")
    subprocess.run([executable, *map(str, args)], env=pg_environment(url), check=True)


def backup_database(value, label):
    url = local_url(value)
    BACKUPS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = BACKUPS / f"{url.database}-{label}-{stamp}.dump"
    path.touch(mode=0o600, exist_ok=False)
    pg_command("pg_dump", url, "--format=custom", "--no-owner", "--no-privileges",
               "--file", path, "--dbname", url.database)
    path.chmod(0o600)
    return path


def recreate_database(value):
    url = local_url(value)
    maintenance = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT",
                                connect_args={"connect_timeout": 5})
    try:
        with maintenance.connect() as connection:
            # Los únicos identificadores posibles se validaron arriba.
            name = connection.dialect.identifier_preparer.quote_identifier(url.database)
            exists = connection.execute(text("SELECT 1 FROM pg_database WHERE datname=:name"),
                                        {"name": url.database}).scalar()
            old_backup = backup_database(url, "before-reset") if exists else None
            connection.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))
            connection.execute(text(f"CREATE DATABASE {name} TEMPLATE template0"))
            return old_backup
    finally:
        maintenance.dispose()


def clone_database(value):
    source = local_url(value)
    if source.database != LOCAL_DB:
        raise ValueError("La copia E2E debe partir de micasita_db")
    snapshot = backup_database(source, "seed-snapshot")
    destination = source.set(database=E2E_DB)
    previous = recreate_database(destination)
    pg_command("pg_restore", destination, "--exit-on-error", "--no-owner", "--no-privileges",
               "--dbname", E2E_DB, snapshot)
    return {"source": LOCAL_DB, "destination": E2E_DB, "snapshot": str(snapshot),
            "previous_e2e_backup": str(previous) if previous else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild-local", action="store_true")
    parser.add_argument("--clone-e2e", action="store_true")
    args = parser.parse_args()
    if not (args.rebuild_local or args.clone_e2e):
        parser.error("Indicar --rebuild-local y/o --clone-e2e")
    url = local_url(settings.DATABASE_URL)
    if url.database != LOCAL_DB:
        parser.error("DATABASE_URL debe apuntar a micasita_db local")
    result = {}
    if args.rebuild_local:
        if not settings.SEED_ADMIN_EMAIL:
            parser.error("Configurar SEED_ADMIN_EMAIL antes de reconstruir")
        backup = recreate_database(url)
        result["previous_local_backup"] = str(backup) if backup else None
        from scripts.seed_db import seed_database, engine
        try:
            seed_database()
            data = json.loads((ROOT / "data/raw/housing.json").read_text())
            expected = sum(row.get("price") is not None and float(row["price"]) != 0 for row in data)
            with engine.connect() as connection:
                actual = connection.execute(text("SELECT count(*) FROM properties")).scalar()
                users = connection.execute(text("SELECT count(*) FROM users")).scalar()
                if actual != expected or users != 1:
                    raise RuntimeError(f"Seed incompleto: {actual}/{expected} viviendas, {users} usuarios")
            result.update(properties=actual, users=users)
        finally:
            engine.dispose()
    if args.clone_e2e:
        result["clone"] = clone_database(url)
    BACKUPS.mkdir(parents=True, exist_ok=True)
    (BACKUPS / "last-setup.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
