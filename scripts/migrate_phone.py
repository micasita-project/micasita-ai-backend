"""Completar teléfonos por source_url; los IDs del JSON no son IDs de la BD.

Vista previa: python scripts/migrate_phone.py --env-file .env.production.local
Aplicar:     python scripts/migrate_phone.py --env-file .env.production.local --apply
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]


def plan_updates(dataset, properties):
    contacts = {}
    for row in dataset:
        source = row.get("source_url")
        phone = str(row.get("phone") or "").strip()
        if not source or not phone:
            continue
        if source in contacts and contacts[source] != phone:
            raise ValueError("El JSON contiene teléfonos contradictorios para un mismo source_url")
        contacts[source] = phone
    changes = []
    counts = Counter()
    matched = set()
    for row in properties:
        source = row["source_url"]
        if source not in contacts:
            counts["sin_coincidencia"] += 1
            continue
        matched.add(source)
        previous = row["phone"]
        phone = contacts[source]
        if previous is not None and str(previous).strip():
            counts["telefono_existente_conservado"] += 1
            continue
        changes.append(dict(id=row["id"], source_url=source, previous_phone=previous, phone=phone))
    counts["por_actualizar"] = len(changes)
    counts["fuentes_con_telefono"] = len(contacts)
    counts["fuentes_sin_fila_en_bd"] = len(set(contacts) - matched)
    return changes, dict(counts)


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/raw/housing.json")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    config = dotenv_values(args.env_file) if args.env_file else {}
    database_url = config.get("DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("Falta DATABASE_URL: indica --env-file o la variable de entorno")
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        parser.error("La migración requiere PostgreSQL")
    print(f"Destino: {url.host}:{url.port or 5432}/{url.database}")
    dataset = json.loads(args.dataset.read_text())
    connect_args = {"connect_timeout": 15}
    if url.host not in {"localhost", "127.0.0.1", "::1"}:
        connect_args["sslmode"] = "require"
    engine = create_engine(url, connect_args=connect_args)
    try:
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL statement_timeout = '60s'"))
            conn.execute(text("SET LOCAL lock_timeout = '10s'"))
            properties = conn.execute(text("SELECT id, source_url, phone FROM properties")).mappings().all()
            changes, counts = plan_updates(dataset, properties)
            print(json.dumps(counts, ensure_ascii=False))
            if not args.apply:
                print("Vista previa: no se modificó ningún registro.")
                return
            if not changes:
                print("No hay teléfonos pendientes de completar.")
                return
            backup = args.backup or ROOT / "data/processed/respaldos" / (
                "phones-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f") + ".json")
            backup.parent.mkdir(parents=True, exist_ok=True)
            snapshot = dict(created_at=datetime.now(timezone.utc).isoformat(), host=url.host,
                            database=url.database, changes=changes)
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as stream:
                json.dump(snapshot, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            print(f"Respaldo previo: {backup}")
            query = text("""UPDATE properties AS p SET phone = c.phone
                FROM jsonb_to_recordset(CAST(:changes AS jsonb))
                    AS c(id integer, source_url text, previous_phone text, phone text)
                WHERE p.id = c.id AND p.source_url = c.source_url
                AND p.phone IS NOT DISTINCT FROM c.previous_phone""")
            if conn.execute(query, {"changes": json.dumps(changes)}).rowcount != len(changes):
                raise RuntimeError("Un registro cambió durante la migración; se revierten todos los cambios")
        print(f"Actualizados y confirmados: {len(changes)}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    run()
