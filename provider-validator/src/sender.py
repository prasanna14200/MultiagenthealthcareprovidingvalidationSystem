# src/email_sender.py
import os
import datetime
import sqlite3
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "data/providers.db")
FROM_EMAIL = os.getenv("FROM_EMAIL")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")  # For verification links

if not FROM_EMAIL or not SENDGRID_API_KEY:
    raise RuntimeError("FROM_EMAIL or SENDGRID_API_KEY not set in environment variables")

def log_outreach(data: dict):
    """Log email sending events in outreach_logs table"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO outreach_logs
        (provider_id, subject, body, recipient_email, send_status, send_time, task_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("provider_id"),
        data.get("subject"),
        data.get("body"),
        data.get("recipient_email"),
        data.get("send_status"),
        data.get("send_time"),
        data.get("task_id")
    ))
    conn.commit()
    conn.close()


def send_email_sendgrid(draft: dict, task_id: str = None):
    """
    Send an email via SendGrid professionally.
    draft must include:
      - recipient (email)
      - subject
      - body (HTML content)
      - provider_id (for logging / verification links)
    """
    # Construct verification link dynamically if needed
    provider_id = draft.get("provider_id")
    verification_link = f"{BASE_URL}/verify?provider_id={provider_id}" if provider_id else "#"

    # Replace placeholder in body if exists
    body = draft.get("body", "")
    body = body.replace("{{verification_link}}", verification_link)

    message = Mail(
        from_email=draft.get("from_email", FROM_EMAIL),
        to_emails=draft["recipient"],
        subject=draft["subject"],
        html_content=body
    )

    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        resp = sg.send(message)
        status = "sent" if 200 <= resp.status_code < 300 else f"failed:{resp.status_code}"
        print(f"[INFO] Email to {draft['recipient']} status: {status}")
    except Exception as e:
        status = f"error:{e}"
        print(f"[ERROR] Failed to send email to {draft['recipient']}: {e}")

    # Log the email sending event
    log_outreach({
        "provider_id": provider_id,
        "subject": draft.get("subject"),
        "body": body,
        "recipient_email": draft.get("recipient"),
        "send_status": status,
        "send_time": datetime.datetime.utcnow().isoformat(),
        "task_id": task_id
    })

    return {"status": status}