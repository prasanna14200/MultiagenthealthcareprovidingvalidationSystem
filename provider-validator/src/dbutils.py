# src/dbutils.py
"""
Database utility functions shared across the application.

WHAT CHANGED:
  OLD: import sqlite3 / sqlite3.connect(DB_PATH)  ← direct SQLite only
  NEW: from src.db import engine, IS_POSTGRES      ← works for Postgres + SQLite

All raw sqlite3 calls replaced with SQLAlchemy text() queries via the
shared engine from src/db/__init__.py.
"""

import os
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from src.db import engine, IS_POSTGRES

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# mark_provider_verified
# ─────────────────────────────────────────────────────────────────────────────
def mark_provider_verified(provider_id: int, source: str = "manual") -> bool:
    """
    Mark the most recent outreach log entry for a provider as 'verified'.

    FIX vs old code:
      OLD used sqlite3 with ORDER BY ... LIMIT inside UPDATE — not supported.
      NEW uses a subquery to find the row id first, then updates by PK.
      Works identically on both SQLite and PostgreSQL.
    """
    try:
        with engine.begin() as conn:
            # Step 1: find the most recent log row id for this provider
            row = conn.execute(text("""
                SELECT id FROM outreach_logs
                WHERE provider_id = :pid
                ORDER BY id DESC
                LIMIT 1
            """), {"pid": provider_id}).fetchone()

            if not row:
                logger.warning(f"[dbutils] No outreach log found for provider {provider_id}")
                return False

            log_id = row[0]

            # Step 2: update only that specific row by PK
            conn.execute(text("""
                UPDATE outreach_logs
                SET send_status          = 'verified',
                    provider_response_id = :source,
                    send_time            = :ts
                WHERE id = :log_id
            """), {
                "source":  source,
                "ts":      datetime.utcnow().isoformat(),
                "log_id":  log_id,
            })

        logger.info(f"[dbutils] Provider {provider_id} verified via '{source}' (log_id={log_id})")
        return True

    except Exception as e:
        logger.error(f"[dbutils] mark_provider_verified failed for {provider_id}: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# get_provider_outreach_status
# ─────────────────────────────────────────────────────────────────────────────
def get_provider_outreach_status(provider_id: int) -> Optional[dict]:
    """
    Get the latest outreach status for a provider.
    Returns dict with send_status, send_time, recipient_email, subject
    or None if no outreach sent yet.
    """
    try:
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT send_status, send_time, recipient_email, subject
                FROM outreach_logs
                WHERE provider_id = :pid
                ORDER BY id DESC
                LIMIT 1
            """), {"pid": provider_id}).fetchone()
        if row:
            return {
                "send_status":      row[0],
                "send_time":        row[1],
                "recipient_email":  row[2],
                "subject":          row[3],
            }
        return None
    except Exception as e:
        logger.error(f"[dbutils] get_provider_outreach_status failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# get_all_unverified_providers
# ─────────────────────────────────────────────────────────────────────────────
def get_all_unverified_providers(confidence_threshold: float = 0.6) -> list:
    """
    Return all providers below the confidence threshold who have NOT yet
    been verified via email link.

    FIX vs old code:
      OLD queried 'validated_providers' table — doesn't exist.
      NEW queries 'providers' table with correct column names.
      CAST works identically in both SQLite and PostgreSQL.
    """
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT p.*
                FROM providers p
                WHERE CAST(COALESCE(p.final_confidence, p.confidence, 1.0) AS FLOAT) < :threshold
                  AND p.id NOT IN (
                      SELECT DISTINCT provider_id
                      FROM outreach_logs
                      WHERE send_status = 'verified'
                        AND provider_id IS NOT NULL
                  )
                ORDER BY CAST(COALESCE(p.final_confidence, p.confidence, 1.0) AS FLOAT) ASC
            """), {"threshold": confidence_threshold}).fetchall()
            cols = list(rows[0].keys()) if rows else []
            return [dict(zip(cols, r)) for r in rows]
    except Exception as e:
        logger.error(f"[dbutils] get_all_unverified_providers failed: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# log_outreach
# ─────────────────────────────────────────────────────────────────────────────
def log_outreach(data: dict) -> bool:
    """
    Insert a record into outreach_logs after sending (or attempting) an email.

    Expected keys in data:
      provider_id, subject, body, recipient_email,
      send_status, send_time, task_id
    """
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO outreach_logs
                    (provider_id, subject, body, recipient_email,
                     send_status, send_time, task_id)
                VALUES
                    (:provider_id, :subject, :body, :recipient_email,
                     :send_status, :send_time, :task_id)
            """), {
                "provider_id":    data.get("provider_id"),
                "subject":        data.get("subject"),
                "body":           data.get("body"),
                "recipient_email": data.get("recipient_email"),
                "send_status":    data.get("send_status"),
                "send_time":      data.get("send_time", datetime.utcnow().isoformat()),
                "task_id":        data.get("task_id"),
            })
        return True
    except Exception as e:
        logger.error(f"[dbutils] log_outreach failed: {e}")
        return False