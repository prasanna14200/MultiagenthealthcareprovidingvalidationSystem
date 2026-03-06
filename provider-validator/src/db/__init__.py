# src/db/__init__.py
"""
CENTRAL DATABASE CONNECTION MODULE
===================================
All database access for the entire project goes through THIS file.

WHAT CHANGED FROM THE OLD CODE:
  OLD: sqlite3.connect("data/providers.db")  ← hardcoded SQLite everywhere
  NEW: SQLAlchemy engine built from DATABASE_URL in .env ← works for both
       SQLite (dev) and PostgreSQL (prod) with zero code changes

USAGE IN OTHER FILES:
  from src.db import fetch_all, init_db, insert_provider, get_engine

FILES THAT IMPORT FROM HERE:
  - src/api/app.py
  - src/dbutils.py
  - src/orchestrator.py
"""

import os
import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# ─────────────────────────────────────────────────────────────────────────────
# CRITICAL FIX: load_dotenv() MUST be called here, at the top of src/db,
# BEFORE os.getenv() reads DATABASE_URL.
#
# WHY THIS BUG OCCURS:
#   Python imports are executed when the module is first imported.
#   src/db/__init__.py is imported by orchestrator.py and app.py at startup.
#   If load_dotenv() is only called in gradio_app.py or main.py, it runs
#   AFTER src/db is already imported — so os.getenv("DATABASE_URL") returns
#   empty string, engine falls back to SQLite, and PostgreSQL is never used.
#
# FIX: Call load_dotenv() here so the .env file is always loaded before
#   the engine is built, regardless of import order.
# ─────────────────────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()   # ← loads .env before os.getenv() below

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 1. READ DATABASE URL FROM ENVIRONMENT
# ─────────────────────────────────────────────────────────────────────────────
#
# In your .env file set ONE of these:
#
#   PostgreSQL (production):
#     DATABASE_URL=postgresql+psycopg2://prasanna:yourpass@localhost:5432/provider_validator
#
#   SQLite (development/fallback — leave DATABASE_URL empty or commented out):
#     # DATABASE_URL=...
#
# ALSO REMOVE OR COMMENT OUT:
#     DB_PATH=data/providers.db   ← comment this out in .env, it is not needed
#     USE_POSTGRES=false          ← comment this out, it is ignored and confusing
#
DATABASE_URL = os.getenv("DATABASE_URL", "")
DB_PATH      = os.getenv("DB_PATH", "data/providers.db")   # only used as SQLite fallback

if DATABASE_URL:
    SQLALCHEMY_URL = DATABASE_URL
    IS_POSTGRES    = DATABASE_URL.startswith("postgresql")
    IS_SQLITE      = DATABASE_URL.startswith("sqlite")
else:
    # No DATABASE_URL set → fall back to SQLite
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", exist_ok=True)
    SQLALCHEMY_URL = f"sqlite:///{DB_PATH}"
    IS_POSTGRES    = False
    IS_SQLITE      = True

_display_url = SQLALCHEMY_URL.split("@")[-1] if "@" in SQLALCHEMY_URL else SQLALCHEMY_URL
print(f"[db] Connecting to: {_display_url}")

# ─────────────────────────────────────────────────────────────────────────────
# 2. CREATE ENGINE (different settings for Postgres vs SQLite)
# ─────────────────────────────────────────────────────────────────────────────
if IS_POSTGRES:
    engine = create_engine(
        SQLALCHEMY_URL,
        pool_size=10,        # keep 10 persistent connections
        max_overflow=20,     # allow 20 extra under burst load
        pool_pre_ping=True,  # test connection before using (auto-reconnect)
        pool_recycle=300,    # recycle connections every 5 min
    )
else:
    # SQLite must have check_same_thread=False for FastAPI (multi-threaded)
    engine = create_engine(
        SQLALCHEMY_URL,
        connect_args={"check_same_thread": False},
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_engine():
    """Return the SQLAlchemy engine. Use this anywhere you need a raw connection."""
    return engine


# ─────────────────────────────────────────────────────────────────────────────
# 3. INIT DB — creates all tables if they don't exist
# ─────────────────────────────────────────────────────────────────────────────
def init_db():
    """
    Create all tables using raw SQL so we don't depend on Alembic being run.
    Safe to call multiple times — uses CREATE TABLE IF NOT EXISTS.
    Called at FastAPI startup.
    """
    with engine.begin() as conn:
        if IS_POSTGRES:
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
                    source_json      TEXT    DEFAULT '{}',
                    confidence       FLOAT   DEFAULT 0.0,
                    final_confidence FLOAT   DEFAULT 0.0,
                    flags            TEXT    DEFAULT '[]',
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
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS outreach_logs (
                    id                   SERIAL PRIMARY KEY,
                    provider_id          INTEGER,
                    subject              TEXT,
                    body                 TEXT,
                    recipient_email      VARCHAR(255),
                    send_status          VARCHAR(50),
                    send_time            TEXT,
                    provider_response_id TEXT,
                    task_id              TEXT,
                    created_at           TIMESTAMPTZ DEFAULT NOW()
                )
            """))
        else:
            # SQLite DDL
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS providers (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id        INTEGER UNIQUE,
                    name             TEXT,
                    npi              TEXT,
                    phone            TEXT,
                    address          TEXT,
                    website          TEXT,
                    email            TEXT,
                    specialty        TEXT,
                    source_json      TEXT    DEFAULT '{}',
                    confidence       REAL    DEFAULT 0.0,
                    final_confidence REAL    DEFAULT 0.0,
                    flags            TEXT    DEFAULT '[]',
                    status           TEXT    DEFAULT 'pending',
                    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at       DATETIME
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS provider_reviews (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_id INTEGER,
                    reviewed_by TEXT,
                    status      TEXT,
                    notes       TEXT,
                    timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS outreach_logs (
                    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_id          INTEGER,
                    subject              TEXT,
                    body                 TEXT,
                    recipient_email      TEXT,
                    send_status          TEXT,
                    send_time            TEXT,
                    provider_response_id TEXT,
                    task_id              TEXT,
                    created_at           DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))

    print(f"[db] ✅ Tables verified OK  ({'PostgreSQL' if IS_POSTGRES else 'SQLite'})")


# ─────────────────────────────────────────────────────────────────────────────
# 4. fetch_all — raw SQL query → list of dicts
# ─────────────────────────────────────────────────────────────────────────────
def fetch_all(query: str, *params) -> List[Dict[str, Any]]:
    """
    Execute a raw SQL SELECT and return results as a list of dicts.

    IMPORTANT: Use SQLAlchemy :name style params, NOT sqlite3 ? style.
    This function auto-converts ? → :p0, :p1 etc. for compatibility.

    Examples:
        fetch_all("SELECT * FROM providers LIMIT ?", 50)
        fetch_all("SELECT * FROM providers WHERE status = ?", "confirmed")
        fetch_all("SELECT * FROM providers WHERE status = ? LIMIT ?", "confirmed", 50)
    """
    # Convert SQLite-style ? placeholders → SQLAlchemy :p0, :p1 ...
    param_dict = {}
    converted  = query
    if "?" in query and params:
        parts    = query.split("?")
        rebuilt  = parts[0]
        for i, part in enumerate(parts[1:]):
            key            = f"p{i}"
            param_dict[key] = params[i]
            rebuilt        += f":{key}" + part
        converted = rebuilt
    elif params:
        param_dict = {f"p{i}": v for i, v in enumerate(params)}

    try:
        with engine.connect() as conn:
            result  = conn.execute(text(converted), param_dict)
            cols    = list(result.keys())
            return [dict(zip(cols, row)) for row in result.fetchall()]
    except Exception as e:
        logger.error(f"[db] fetch_all error: {e}\nQuery: {converted}\nParams: {param_dict}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 5. insert_provider — UPSERT a provider record
# ─────────────────────────────────────────────────────────────────────────────
def insert_provider(row: Dict[str, Any]) -> Optional[int]:
    """
    Insert or UPDATE a provider record.

    KEY FEATURE — UPSERT on source_id:
      If a record with the same source_id already exists, it is UPDATED
      rather than creating a duplicate. This means re-running the
      orchestrator is safe — it refreshes data instead of duplicating it.

    This is the function called by src/orchestrator.py after processing
    each row through the agent pipeline.
    """
    flags_raw = row.get("flags", "[]")
    flags_str = flags_raw if isinstance(flags_raw, str) else json.dumps(flags_raw)

    params = {
        "source_id":        row.get("source_id"),
        "name":             str(row.get("name") or ""),
        "npi":              str(row.get("npi") or ""),
        "phone":            str(row.get("phone") or ""),
        "address":          str(row.get("address") or ""),
        "website":          str(row.get("website") or ""),
        "email":            str(row.get("email") or ""),
        "specialty":        str(row.get("specialty") or ""),
        "source_json":      row.get("source_json") or "{}",
        "confidence":       float(row.get("confidence") or 0.0),
        "final_confidence": float(row.get("final_confidence") or row.get("confidence") or 0.0),
        "flags":            flags_str,
        "status":           str(row.get("status") or "pending"),
    }

    try:
        with engine.begin() as conn:
            if IS_POSTGRES:
                result = conn.execute(text("""
                    INSERT INTO providers
                        (source_id, name, npi, phone, address, website, email,
                         specialty, source_json, confidence, final_confidence, flags, status)
                    VALUES
                        (:source_id, :name, :npi, :phone, :address, :website, :email,
                         :specialty, :source_json, :confidence, :final_confidence, :flags, :status)
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
                    RETURNING id
                """), params)
                return result.scalar()
            else:
                result = conn.execute(text("""
                    INSERT INTO providers
                        (source_id, name, npi, phone, address, website, email,
                         specialty, source_json, confidence, final_confidence, flags, status)
                    VALUES
                        (:source_id, :name, :npi, :phone, :address, :website, :email,
                         :specialty, :source_json, :confidence, :final_confidence, :flags, :status)
                    ON CONFLICT(source_id) DO UPDATE SET
                        name             = excluded.name,
                        npi              = excluded.npi,
                        phone            = excluded.phone,
                        address          = excluded.address,
                        website          = excluded.website,
                        email            = excluded.email,
                        specialty        = excluded.specialty,
                        source_json      = excluded.source_json,
                        confidence       = excluded.confidence,
                        final_confidence = excluded.final_confidence,
                        flags            = excluded.flags,
                        status           = excluded.status
                """), params)
                return result.lastrowid
    except Exception as e:
        logger.error(f"[db] insert_provider failed source_id={params.get('source_id')}: {e}")
        raise


# ─────────────────────────────────────────────────────────────────────────────
# 6. Convenience lookup functions
# ─────────────────────────────────────────────────────────────────────────────
def fetch_provider_by_id(provider_id: int) -> Optional[Dict[str, Any]]:
    rows = fetch_all(
        "SELECT * FROM providers WHERE id = ? OR source_id = ? LIMIT 1",
        provider_id, provider_id
    )
    return rows[0] if rows else None


def fetch_providers_by_specialty(specialty: str) -> List[Dict[str, Any]]:
    return fetch_all(
        "SELECT * FROM providers WHERE LOWER(specialty) = LOWER(?) LIMIT 100",
        specialty
    )