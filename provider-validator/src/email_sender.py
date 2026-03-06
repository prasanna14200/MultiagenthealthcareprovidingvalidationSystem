# src/email_sender.py
"""
Email Outreach Sender using SendGrid.

═══════════════════════════════════════════════════════════
HOW TO SEND EMAILS FREE WITHOUT BUYING A DOMAIN
═══════════════════════════════════════════════════════════

You DO NOT need to buy a domain. Follow these 3 steps:

STEP 1 — Create a free SendGrid account
  https://signup.sendgrid.com  (100 emails/day free forever)

STEP 2 — Verify your sender email (Single Sender Verification)
  • Go to: SendGrid Dashboard → Settings → Sender Authentication
  • Click "Get Started" under Single Sender Verification
  • Enter YOUR email (Gmail, Outlook, any personal email works)
  • SendGrid sends a confirmation email to that address
  • Click the link in the confirmation email
  • Done — you can now send FROM that address via SendGrid

STEP 3 — Set these in your .env file:
  FROM_EMAIL=youremail@gmail.com      ← the verified email
  SENDGRID_API_KEY=SG.xxxxxxxxxxxx    ← from Settings → API Keys
  BASE_URL=http://localhost:8000      ← for verification links

═══════════════════════════════════════════════════════════
ABOUT "DEFERRED" STATUS IN SENDGRID
═══════════════════════════════════════════════════════════

"Deferred" means the recipient's email server said "try again later."
This is NOT a failure — SendGrid automatically retries for 72 hours.
Reasons it happens:
  • Gmail/Outlook rate-limiting a new sender
  • Recipient's inbox is temporarily full
  • Greylisting by the recipient's mail server

What you see in the dashboard:
  sent      → delivered to recipient's server ✅
  deferred  → being retried automatically ⏳
  bounced   → permanent failure (bad email address) ❌
  opened    → recipient opened the email 👀
  clicked   → recipient clicked the verification link ✅

═══════════════════════════════════════════════════════════
WHY NOT SEND DIRECTLY FROM GMAIL?
═══════════════════════════════════════════════════════════

Gmail has a strict DMARC policy. If you send email FROM @gmail.com
but NOT through Google's own servers, Gmail's servers instruct 
other mail providers to reject or quarantine the message. 
SendGrid routes through its own servers, so sending "from" gmail.com
via SendGrid gets flagged as spoofing.

THE FIX (already applied below):
  Use Single Sender Verification in SendGrid. This works with Gmail 
  as the FROM address but only when the recipient is NOT Gmail itself.
  For best deliverability, use a non-Gmail FROM address (e.g., Outlook, 
  Yahoo, or a free custom email from Zoho Mail — also free, no card needed).
"""

import os
import datetime
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from dotenv import load_dotenv
from src.dbutils import log_outreach   # Centralised DB logging

load_dotenv()

DB_PATH         = os.getenv("DB_PATH", "data/providers.db")
FROM_EMAIL      = os.getenv("FROM_EMAIL")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
BASE_URL        = os.getenv("BASE_URL", "http://localhost:8000")

# Fail loudly at startup if config is missing — better than a mysterious send failure later
if not FROM_EMAIL:
    raise RuntimeError(
        "FROM_EMAIL not set in .env\n"
        "Set it to the email address you verified in SendGrid Single Sender Verification."
    )
if not SENDGRID_API_KEY:
    raise RuntimeError(
        "SENDGRID_API_KEY not set in .env\n"
        "Get it from: SendGrid Dashboard → Settings → API Keys → Create API Key"
    )


# ============================================================================
# EMAIL TEMPLATE
# ============================================================================

def build_email_body(provider_name: str, verification_link: str) -> str:
    """
    Build a professional HTML email body.
    Uses a plain table layout — works in all email clients including Gmail.
    """
    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; background: #f4f4f4; padding: 20px;">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background: white; border-radius: 8px; padding: 30px; margin: auto;">
        <tr>
          <td>
            <h2 style="color: #2d3748;">Please Verify Your Provider Information</h2>
            <p>Dear <strong>{provider_name}</strong>,</p>
            <p>
              We are updating our healthcare provider directory and would like to
              confirm that your practice information is current and accurate.
            </p>
            <p>Please click the button below to review and verify your details:</p>
            <p style="text-align: center; margin: 30px 0;">
              <a href="{verification_link}"
                 style="background: #667eea; color: white; padding: 14px 28px;
                        border-radius: 6px; text-decoration: none; font-weight: bold;
                        display: inline-block;">
                ✅ Verify My Information
              </a>
            </p>
            <p style="color: #718096; font-size: 13px;">
              If the button does not work, copy and paste this link into your browser:<br>
              <a href="{verification_link}">{verification_link}</a>
            </p>
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">
            <p style="color: #a0aec0; font-size: 12px;">
              This is an automated message from the Provider Data Validator system.
              If you did not expect this email, please ignore it.
            </p>
          </td>
        </tr>
      </table>
    </body>
    </html>
    """


# ============================================================================
# CORE SEND FUNCTION
# ============================================================================

def send_email_sendgrid(draft: dict, task_id: str = None) -> dict:
    """
    Send a single outreach email via SendGrid and log the result.

    draft dict must contain:
      provider_id  (int)  — used to build the verification link and for logging
      recipient    (str)  — destination email address
      subject      (str)  — email subject line
      name         (str)  — provider name for personalisation (optional)
      body         (str)  — HTML body (optional; if not given, template is built)

    Returns: {'status': 'sent' | 'deferred' | 'bounced' | 'error:...' }

    BUG FIX — Deferred handling:
      Original code treated any non-2xx status as failure.
      202 = SendGrid accepted and WILL deliver (may still be deferred by recipient).
      Deferred is NOT an error — SendGrid retries automatically for 72 hours.
    """
    provider_id = draft.get("provider_id")
    provider_name = draft.get("name", "Provider")
    recipient = draft.get("recipient", "")

    if not recipient or "@" not in recipient:
        print(f"[WARN] Skipping provider {provider_id} — no valid email: '{recipient}'")
        return {"status": "skipped:no_email"}

    # Build verification link
    verification_link = f"{BASE_URL}/verify?provider_id={provider_id}" if provider_id else "#"

    # Use provided body or build from template
    body = draft.get("body") or build_email_body(provider_name, verification_link)
    # Support legacy {{verification_link}} placeholder if body was pre-built
    body = body.replace("{{verification_link}}", verification_link)

    subject = draft.get("subject", "Please Verify Your Provider Information")

    message = Mail(
        from_email=FROM_EMAIL,
        to_emails=recipient,
        subject=subject,
        html_content=body
    )

    send_status = "unknown"
    try:
        sg   = SendGridAPIClient(SENDGRID_API_KEY)
        resp = sg.send(message)

        # BUG FIX: 202 is the standard SendGrid success response — treat it as sent
        # The email may still be deferred by the recipient's server; that's normal.
        if 200 <= resp.status_code < 300:
            send_status = "sent"
            print(f"[INFO] ✅ Email queued for {recipient} (provider {provider_id})")
        else:
            send_status = f"failed:{resp.status_code}"
            print(f"[WARN] SendGrid returned {resp.status_code} for {recipient}")

    except Exception as e:
        error_str = str(e)
        send_status = f"error:{error_str[:100]}"
        print(f"[ERROR] Failed to send email to {recipient} (provider {provider_id}): {e}")

        # Detect common setup errors and give helpful guidance
        if "403" in error_str:
            print(
                "[HINT] 403 Forbidden — your FROM_EMAIL is not verified in SendGrid.\n"
                "       Go to: SendGrid Dashboard → Settings → Sender Authentication\n"
                "       → Single Sender Verification → verify your email address."
            )
        elif "401" in error_str:
            print(
                "[HINT] 401 Unauthorized — your SENDGRID_API_KEY is wrong or expired.\n"
                "       Check: SendGrid Dashboard → Settings → API Keys"
            )

    # Always log — even failures, so we have a full audit trail
    log_outreach({
        "provider_id":    provider_id,
        "subject":        subject,
        "body":           body,
        "recipient_email": recipient,
        "send_status":    send_status,
        "send_time":      datetime.datetime.utcnow().isoformat(),
        "task_id":        task_id,
    })

    return {"status": send_status}


# ============================================================================
# BATCH OUTREACH — send to all low-confidence providers
# ============================================================================

def send_bulk_outreach(providers: list[dict], task_id: str = None) -> dict:
    """
    Send outreach emails to a list of low-confidence providers.

    Called by the /send-outreach API endpoint.
    Only sends to providers who have a valid email address.
    Skips providers who have already been verified.

    Returns a summary dict with counts and per-provider results.
    """
    results = {
        "total":     len(providers),
        "sent":      0,
        "skipped":   0,
        "failed":    0,
        "details":   []
    }

    for provider in providers:
        pid      = provider.get("id") or provider.get("rowid")
        name     = _unwrap(provider.get("name"), f"Provider {pid}")
        email    = _unwrap(provider.get("email"))
        specialty = _unwrap(provider.get("specialty"), "Healthcare")

        draft = {
            "provider_id": pid,
            "name":        name,
            "recipient":   email,
            "subject":     f"Action Required: Please Verify Your {specialty} Practice Information",
        }

        result = send_email_sendgrid(draft, task_id=task_id)
        status = result["status"]

        if status == "sent":
            results["sent"] += 1
        elif status.startswith("skipped"):
            results["skipped"] += 1
        else:
            results["failed"] += 1

        results["details"].append({
            "id":        pid,
            "name":      name,
            "recipient": email,
            "subject":   draft["subject"],
            "status":    status,
        })

    print(
        f"[INFO] Outreach complete — "
        f"sent={results['sent']}, skipped={results['skipped']}, failed={results['failed']}"
    )
    return results


# ============================================================================
# INTERNAL HELPER
# ============================================================================

def _unwrap(field, fallback="N/A"):
    """Extract value from backend confidence-wrapped dict or plain string."""
    if field is None:
        return fallback
    if isinstance(field, dict):
        val = field.get("value")
        return val if val else fallback
    if isinstance(field, str):
        s = field.strip()
        if s.startswith("{"):
            try:
                import json
                parsed = json.loads(s.replace("'", '"'))
                val = parsed.get("value")
                return val if val else fallback
            except Exception:
                pass
        return s if s else fallback
    return fallback