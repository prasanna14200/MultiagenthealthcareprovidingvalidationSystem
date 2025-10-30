# scripts/sqlite_to_postgres.py
import sqlite3
import os
from sqlalchemy import create_engine, text

# read env or hardcode
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://pvuser:pvpass@localhost:5432/providerdb")
SQLITE_DB = "data/providers.db"

pg = create_engine(DATABASE_URL)

# make sure target table exists (run alembic upgrade first)
# connect to sqlite
sconn = sqlite3.connect(SQLITE_DB)
sconn.row_factory = sqlite3.Row
scur = sconn.cursor()
rows = scur.execute("SELECT * FROM providers").fetchall()

with pg.begin() as conn:
    for r in rows:
        row = dict(r)
        # map fields - adjust to your SQLAlchemy model column names
        conn.execute(
            text("""
                INSERT INTO providers (source_id, name, npi, phone, address, website, specialty, source_json, confidence, flags, status)
                VALUES (:source_id, :name, :npi, :phone, :address, :website, :specialty, :source_json, :confidence, :flags, :status)
            """),
            **{
                "source_id": row.get("source_id"),
                "name": row.get("name"),
                "npi": row.get("npi"),
                "phone": row.get("phone"),
                "address": row.get("address"),
                "website": row.get("website"),
                "specialty": row.get("specialty"),
                "source_json": row.get("source_json") or "{}",
                "confidence": row.get("confidence") or 0.0,
                "flags": row.get("flags") or "[]",
                "status": row.get("status") or "pending"
            }
        )
sconn.close()
print("Migration finished")
