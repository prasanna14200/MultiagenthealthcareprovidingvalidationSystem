# scripts/sqlite_to_postgres.py
# Migrates all records from SQLite → PostgreSQL
# Run ONCE after setting up PostgreSQL:
#   python scripts/sqlite_to_postgres.py

import sqlite3
import os
import json
from sqlalchemy import create_engine, text

# ── Config ────────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://pvuser:pvpass@localhost:5432/provider_validator"
)
SQLITE_DB = os.getenv("SQLITE_DB", "data/providers.db")

# ── Connect ───────────────────────────────────────────────────────────────────
print(f"[migrate] SQLite source : {SQLITE_DB}")
print(f"[migrate] PostgreSQL target: {DATABASE_URL.split('@')[-1]}")

if not os.path.isfile(SQLITE_DB):
    print(f"[migrate] ❌ SQLite file not found: {SQLITE_DB}")
    exit(1)

pg_engine = create_engine(DATABASE_URL, pool_pre_ping=True)
sq_conn   = sqlite3.connect(SQLITE_DB)
sq_conn.row_factory = sqlite3.Row
sq_cur    = sq_conn.cursor()

# ── Read all rows from SQLite ─────────────────────────────────────────────────
rows = sq_cur.execute("SELECT * FROM providers").fetchall()
print(f"[migrate] Found {len(rows)} rows in SQLite")

if not rows:
    print("[migrate] Nothing to migrate.")
    sq_conn.close()
    exit(0)

# ── Ensure table exists in PostgreSQL ─────────────────────────────────────────
with pg_engine.begin() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS providers (
            id               SERIAL PRIMARY KEY,
            source_id        INTEGER UNIQUE,
            name             TEXT,
            npi              VARCHAR(20),
            phone            VARCHAR(50),
            address          TEXT,
            website          TEXT,
            email            TEXT,
            specialty        VARCHAR(200),
            source_json      TEXT DEFAULT '{}',
            confidence       FLOAT DEFAULT 0.0,
            final_confidence FLOAT DEFAULT 0.0,
            flags            TEXT DEFAULT '[]',
            status           VARCHAR(50) DEFAULT 'pending',
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            updated_at       TIMESTAMPTZ
        )
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS provider_reviews (
            id          SERIAL PRIMARY KEY,
            provider_id INTEGER,
            reviewed_by TEXT,
            status      TEXT,
            notes       TEXT,
            timestamp   TIMESTAMPTZ DEFAULT NOW()
        )
    """))
print("[migrate] ✅ Tables verified in PostgreSQL")

# ── Migrate rows ──────────────────────────────────────────────────────────────
inserted = 0
skipped  = 0
errors   = 0

with pg_engine.begin() as conn:
    for r in rows:
        row = dict(r)
        try:
            conn.execute(text("""
                INSERT INTO providers
                    (source_id, name, npi, phone, address, website, email,
                     specialty, source_json, confidence, final_confidence,
                     flags, status)
                VALUES
                    (:source_id, :name, :npi, :phone, :address, :website, :email,
                     :specialty, :source_json, :confidence, :final_confidence,
                     :flags, :status)
                ON CONFLICT (source_id) DO UPDATE SET
                    name             = EXCLUDED.name,
                    npi              = EXCLUDED.npi,
                    phone            = EXCLUDED.phone,
                    address          = EXCLUDED.address,
                    website          = EXCLUDED.website,
                    email            = EXCLUDED.email,
                    specialty        = EXCLUDED.specialty,
                    source_json      = EXCLUDED.source_json,
                    confidence       = EXCLUDED.confidence,
                    final_confidence = EXCLUDED.final_confidence,
                    flags            = EXCLUDED.flags,
                    status           = EXCLUDED.status,
                    updated_at       = NOW()
            """), {
                "source_id":        row.get("source_id") or row.get("id"),
                "name":             row.get("name"),
                "npi":              str(row.get("npi") or ""),
                "phone":            str(row.get("phone") or ""),
                "address":          str(row.get("address") or ""),
                "website":          str(row.get("website") or ""),
                "email":            str(row.get("email") or ""),
                "specialty":        str(row.get("specialty") or ""),
                "source_json":      row.get("source_json") or "{}",
                "confidence":       float(row.get("confidence") or 0.0),
                "final_confidence": float(row.get("final_confidence") or row.get("confidence") or 0.0),
                "flags":            row.get("flags") or "[]",
                "status":           row.get("status") or "pending",
            })
            inserted += 1
        except Exception as e:
            print(f"[migrate] ⚠️  Row source_id={row.get('source_id')} error: {e}")
            errors += 1

sq_conn.close()

print(f"\n[migrate] ✅ Done!")
print(f"  Inserted/updated : {inserted}")
print(f"  Errors           : {errors}")

# ── Verify ────────────────────────────────────────────────────────────────────
with pg_engine.connect() as conn:
    count = conn.execute(text("SELECT COUNT(*) FROM providers")).scalar()
    print(f"  PostgreSQL total : {count} records")