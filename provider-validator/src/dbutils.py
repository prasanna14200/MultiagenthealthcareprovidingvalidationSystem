import sqlite3
import os

def mark_provider_verified(provider_id: int, source: str = "manual"):
    """Mark provider as verified in outreach_logs table."""
    conn = sqlite3.connect(os.getenv("DB_PATH", "data/providers.db"))
    cur = conn.cursor()
    cur.execute("""
        UPDATE outreach_logs
        SET send_status = 'verified',
            provider_response_id = ?,
            send_time = CURRENT_TIMESTAMP
        WHERE provider_id = ?
        ORDER BY id DESC
        LIMIT 1
    """, (source, provider_id))
    conn.commit()
    conn.close()
    print(f"[INFO] Provider {provider_id} marked verified (source={source})")
