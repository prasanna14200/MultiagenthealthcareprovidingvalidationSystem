
import os
import sqlite3
from typing import Any, Dict, List

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from src.db.models import Base, Provider

load_dotenv()

# ------------------------------
# Database configuration
# ------------------------------
DB_PATH = "data/providers.db"
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set in environment. Please check your .env file.")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ------------------------------
# ORM setup
# ------------------------------
def init_db():
    """Create all tables using SQLAlchemy models."""
    Base.metadata.create_all(bind=engine)


def insert_provider(provider_data: dict):
    """Insert a new provider via SQLAlchemy."""
    db = SessionLocal()
    try:
        provider = Provider(**provider_data)
        db.add(provider)
        db.commit()
        db.refresh(provider)
        return provider
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


# ------------------------------
# Hybrid fetch_all (auto-detect engine)
# ------------------------------
def fetch_all(query: str = None, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Unified fetch_all that works for both SQLite and PostgreSQL.
    If a custom SQL query is provided, it runs that directly.
    Otherwise, it defaults to SELECT * FROM providers LIMIT {limit}.
    """
    # If DATABASE_URL starts with postgres — use SQLAlchemy
    if DATABASE_URL.startswith("postgres"):
        with engine.connect() as conn:
            sql = text(query or f"SELECT * FROM providers LIMIT {limit}")
            result = conn.execute(sql)
            rows = [dict(row._mapping) for row in result]
            return rows

    # Otherwise, fallback to legacy SQLite
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    sql = query or "SELECT * FROM providers LIMIT ?"
    params = (limit,) if "?" in sql else ()
    cur.execute(sql, params)
    rows = cur.fetchall()
    keys = [desc[0] for desc in cur.description] if cur.description else []
    conn.close()
    return [dict(zip(keys, r)) for r in rows]

    
def fetch_provider_by_id(provider_id: int) -> Dict[str, Any]:
    """Fetch a single provider by ID (legacy sqlite3 helper)."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM providers WHERE id=?", (provider_id,))
    row = cur.fetchone()
    keys = [desc[0] for desc in cur.description] if row and cur.description else []
    conn.close()
    return dict(zip(keys, row)) if row else None


def fetch_providers_by_specialty(specialty: str) -> List[Dict[str, Any]]:
    """Fetch providers by specialty (legacy sqlite3 helper)."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM providers WHERE specialty LIKE ?", (f"%{specialty}%",))
    rows = cur.fetchall()
    keys = [desc[0] for desc in cur.description] if cur.description else []
    conn.close()
    return [dict(zip(keys, r)) for r in rows]