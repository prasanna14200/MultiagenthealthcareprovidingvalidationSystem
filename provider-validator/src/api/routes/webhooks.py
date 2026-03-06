# src/api/webhooks.py
"""
SendGrid Event Webhook Handler.

═══════════════════════════════════════════════════════════
HOW SENDGRID WEBHOOKS WORK
═══════════════════════════════════════════════════════════

After you send an email via SendGrid, SendGrid tracks what happens to it
and POSTs real-time event notifications to THIS endpoint:

  Event         Meaning
  ─────────     ────────────────────────────────────────────
  processed     SendGrid accepted the email for sending
  deferred      Recipient's server said "try again later" — SendGrid is retrying
  delivered     Recipient's server confirmed receipt ✅
  open          Recipient opened the email 👀
  click         Recipient clicked a link in the email ✅✅
  bounce        Permanent delivery failure (bad email address) ❌
  spamreport    Recipient marked as spam ⚠️
  unsubscribe   Recipient unsubscribed ⚠️

TO ENABLE WEBHOOKS IN SENDGRID:
  1. Go to SendGrid Dashboard → Settings → Mail Settings → Event Webhook
  2. Set HTTP Post URL to: https://your-server.com/webhooks/sendgrid
     (For local testing use ngrok: ngrok http 8000, then use the ngrok URL)
  3. Check these events: Delivered, Open, Click, Bounce, Deferred
  4. Save

BUG FIX: Original code used column 'provider_response_id' in the INSERT
which may not exist in the outreach_logs schema. Fixed to use correct columns.
Also added safe handling for missing/null event fields.
"""

from fastapi import APIRouter, Request, HTTPException
from datetime import datetime
import sqlite3
import os

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

DB_PATH = os.getenv("DB_PATH", "data/providers.db")


@router.post("/sendgrid")
async def sendgrid_webhook(request: Request):
    """
    Receive and process SendGrid event webhook POST.

    SendGrid sends a JSON array of event objects.
    We log each event and update the outreach_logs table accordingly.
    If the event is a 'click' on a verification link, we mark the provider verified.
    """
    try:
        events = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON body: {e}")

    if not isinstance(events, list):
        # SendGrid sometimes sends a single object instead of a list
        events = [events]

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()

    processed = 0
    for event in events:
        email        = event.get("email", "")
        event_type   = event.get("event", "unknown")
        timestamp    = event.get("timestamp")
        sg_msg_id    = event.get("sg_message_id", "")
        url_clicked  = event.get("url", "")     # Only present on 'click' events

        # Convert Unix timestamp → ISO string
        event_time = (
            datetime.fromtimestamp(timestamp).isoformat()
            if timestamp else datetime.utcnow().isoformat()
        )

        # BUG FIX: Use correct columns that exist in outreach_logs schema.
        # Original used 'provider_response_id' which may not be in schema.
        # We UPDATE existing log rows by matching recipient_email,
        # or INSERT a new row for webhook-only events.
        try:
            # Try to update an existing outreach log entry for this email
            cur.execute("""
                UPDATE outreach_logs
                SET send_status = ?,
                    send_time   = ?
                WHERE id = (
                    SELECT id FROM outreach_logs
                    WHERE recipient_email = ?
                    ORDER BY id DESC
                    LIMIT 1
                )
            """, (event_type, event_time, email))

            if cur.rowcount == 0:
                # No existing row — insert a new webhook event log
                cur.execute("""
                    INSERT INTO outreach_logs
                    (recipient_email, send_status, send_time, task_id)
                    VALUES (?, ?, ?, ?)
                """, (email, event_type, event_time, sg_msg_id[:100] if sg_msg_id else None))

        except Exception as db_err:
            print(f"[ERROR] DB write failed for webhook event: {db_err}")
            continue

        # ── Special handling for specific event types ──────────────────────

        if event_type == "click" and "verify" in url_clicked:
            # Provider clicked the verification link in the email
            # Extract provider_id from the URL query string if possible
            provider_id = _extract_provider_id_from_url(url_clicked)
            if provider_id:
                from src.dbutils import mark_provider_verified
                mark_provider_verified(provider_id, source="email_link_click")
                print(f"[INFO] ✅ Provider {provider_id} auto-verified via email click")
            else:
                print(f"[INFO] Click event on verify URL (no provider_id extracted): {url_clicked}")

        elif event_type == "bounce":
            print(f"[WARN] ❌ Bounce for {email} — permanent delivery failure. Check the address.")

        elif event_type == "deferred":
            # This is normal — SendGrid is retrying. No action needed.
            print(f"[INFO] ⏳ Deferred for {email} — SendGrid will retry automatically.")

        elif event_type == "spamreport":
            print(f"[WARN] ⚠️ Spam report from {email} — consider suppressing this address.")

        processed += 1

    conn.commit()
    conn.close()

    return {"status": "ok", "received": len(events), "processed": processed}


def _extract_provider_id_from_url(url: str) -> int | None:
    """
    Extract the provider_id query parameter from a URL like:
      http://localhost:8000/verify?provider_id=42
    Returns the integer id, or None if not found.
    """
    try:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        pid_list = params.get("provider_id", [])
        if pid_list:
            return int(pid_list[0])
    except Exception:
        pass
    return None