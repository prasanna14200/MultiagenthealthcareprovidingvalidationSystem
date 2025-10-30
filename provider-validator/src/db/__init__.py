# src/db/__init__.py
import os
import sqlite3
from typing import Any, Dict, List

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from src.db.models import Base, Provider

load_dotenv()

# ------------------------------
# Database configuration
# ------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/providers.db")
DB_PATH = "data/providers.db"

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
# Legacy SQLite helpers (for old imports)
# ------------------------------
def fetch_all(limit: int = 100) -> List[Dict[str, Any]]:
    """Fetch all providers (legacy sqlite3 helper)."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Use SELECT * to get all available columns dynamically
    cur.execute("SELECT * FROM providers LIMIT ?", (limit,))
    rows = cur.fetchall()
    
    # Get column names dynamically from cursor description
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