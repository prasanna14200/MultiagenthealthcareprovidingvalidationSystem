# src/email_sender.py
import os, datetime, sqlite3
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from dotenv import load_dotenv
load_dotenv()

DB_PATH = os.getenv("DB_PATH", "data/providers.db")

def log_outreach(data):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO outreach_logs
        (provider_id, subject, body, recipient_email, send_status, send_time, task_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (data.get("provider_id"), data.get("subject"), data.get("body"),
          data.get("recipient_email"), data.get("send_status"),
          data.get("send_time"), data.get("task_id")))
    conn.commit()
    conn.close()

def send_email_sendgrid(draft, task_id=None):
    sg_key = os.getenv("SENDGRID_API_KEY")
    if not sg_key:
        raise RuntimeError("SENDGRID_API_KEY missing")

    message = Mail(
        from_email="noreply@yourdomain.com",
        to_emails=draft["recipient"],
        subject=draft["subject"],
        html_content=draft["body"]
    )

    try:
        sg = SendGridAPIClient(sg_key)
        resp = sg.send(message)
        status = "sent" if 200 <= resp.status_code < 300 else f"failed:{resp.status_code}"
    except Exception as e:
        status = f"error:{e}"

    log_outreach({
        "provider_id": draft.get("provider_id"),
        "subject": draft.get("subject"),
        "body": draft.get("body"),
        "recipient_email": draft.get("recipient"),
        "send_status": status,
        "send_time": datetime.datetime.utcnow().isoformat(),
        "task_id": task_id
    })
    return {"status": status}
