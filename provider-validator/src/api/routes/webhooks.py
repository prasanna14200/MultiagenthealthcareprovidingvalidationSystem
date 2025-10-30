# src/api/webhooks.py
from fastapi import APIRouter, Request, HTTPException
from datetime import datetime
import json
import sqlite3

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

DB_PATH = "data/providers.db"  # change if using Postgres later

@router.post("/sendgrid")
async def sendgrid_webhook(request: Request):
    """
    Handle SendGrid Event Webhooks.
    SendGrid posts a list of JSON events to this endpoint.
    """
    try:
        events = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    if not isinstance(events, list):
        raise HTTPException(status_code=400, detail="Expected a list of events")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    for e in events:
        email = e.get("email")
        event = e.get("event")
        timestamp = e.get("timestamp")
        sg_message_id = e.get("sg_message_id")

        send_time = datetime.fromtimestamp(timestamp).isoformat() if timestamp else None

        # Log the event (optional: update outreach_logs table)
        cur.execute(
            """
            INSERT INTO outreach_logs (recipient_email, send_status, send_time, provider_response_id)
            VALUES (?, ?, ?, ?)
            """,
            (email, event, send_time, sg_message_id),
        )

        # Optional: mark verification if link clicked
        if event == "click":
            # Here you could mark the provider as verified in DB
            print(f"[INFO] Provider email {email} clicked verification link")

    conn.commit()
    conn.close()

    return {"status": "ok", "received": len(events)}
