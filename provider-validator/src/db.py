# src/db.py
import sqlite3
from typing import Any, Dict, List

DB_PATH = "data/providers.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS providers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id INTEGER,
        name TEXT,
        npi TEXT,
        phone TEXT,
        address TEXT,
        website TEXT,
        specialty TEXT,
        source_json TEXT,
        confidence REAL,
        flags TEXT,
        status TEXT
    )
    """)
    conn.commit()
    conn.close()

def insert_provider(row: Dict[str, Any]):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
      INSERT INTO providers (source_id, name, npi, phone, address, website, specialty, source_json, confidence, flags, status)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (row.get("source_id"), row.get("name"), row.get("npi"), row.get("phone"), row.get("address"),
          row.get("website"), row.get("specialty"), row.get("source_json", "{}"),
          row.get("confidence", 0.0), row.get("flags", "[]"), row.get("status", "pending")))
    conn.commit()
    conn.close()

def fetch_all(limit: int = 100) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT rowid, source_id, name, npi, phone, address, website, specialty, source_json, confidence, flags, status FROM providers LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    keys = ["rowid","source_id","name","npi","phone","address","website","specialty","source_json","confidence","flags","status"]
    return [dict(zip(keys, r)) for r in rows]



def fetch_provider_by_id(provider_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM providers WHERE id=?", (provider_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def fetch_providers_by_specialty(specialty):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM providers WHERE specialty LIKE ?", (f"%{specialty}%",))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]
