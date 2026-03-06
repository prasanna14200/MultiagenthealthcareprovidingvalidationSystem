# src/gradio_app.py - Complete Provider Validator Dashboard
import os
import json
import gradio as gr
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
GRADIO_PORT = int(os.getenv("GRADIO_PORT", "7860"))
GRADIO_HOST = os.getenv("GRADIO_HOST", "127.0.0.1")

# Global state for authentication
class AppState:
    token = None
    username = None
    role = None

state = AppState()

# ============================================================================
# HELPER: UNWRAP BACKEND FIELD VALUES
# ============================================================================
# BUG FIX #2 — The backend stores each field as a dict like:
#   {'value': None, 'confidence': 0.95, 'sources': ['validation', 'enrichment', 'ocr']}
# instead of a plain string. This helper safely extracts the real value from that structure.
# When value is None it returns a fallback string so the UI never shows "None" or a raw dict.

def unwrap(field, fallback="N/A"):
    """
    Extract plain value from a backend confidence-wrapped field.
    
    Backend enrichment pipeline stores fields like:
        {'value': 'Dr. John Smith', 'confidence': 0.92, 'sources': [...]}
    
    This unwraps to: 'Dr. John Smith'
    If the value inside is None/empty, returns the fallback string.
    If the field is already a plain string/number, returns it directly.
    """
    if field is None:
        return fallback

    # Already a plain primitive
    if isinstance(field, (int, float, bool)):
        return field

    # It's a dict from the enrichment pipeline
    if isinstance(field, dict):
        val = field.get("value")
        if val is None or val == "":
            return fallback
        return val

    # It might be a JSON string that looks like a dict
    if isinstance(field, str):
        stripped = field.strip()
        if stripped.startswith("{"):
            try:
                parsed = json.loads(stripped.replace("'", '"'))  # Handle single-quote dicts
                val = parsed.get("value")
                if val is None or val == "":
                    return fallback
                return val
            except Exception:
                pass
        # Plain string — return as-is unless empty
        return stripped if stripped else fallback

    return fallback


def unwrap_confidence(field):
    """
    Extract a numeric confidence score (0.0–1.0) from a field or a confidence-wrapped dict.
    Returns float. Falls back to 0.0 if not found.
    """
    if field is None:
        return 0.0
    if isinstance(field, (int, float)):
        return float(field)
    if isinstance(field, str):
        try:
            return float(field)
        except ValueError:
            pass
        # Might be a stringified dict
        stripped = field.strip()
        if stripped.startswith("{"):
            try:
                parsed = json.loads(stripped.replace("'", '"'))
                conf = parsed.get("confidence", 0.0)
                return float(conf)
            except Exception:
                return 0.0
    if isinstance(field, dict):
        try:
            return float(field.get("confidence", 0.0))
        except Exception:
            return 0.0
    return 0.0


# ============================================================================
# AUTHENTICATION FUNCTIONS
# ============================================================================

def login(username, password):
    """Authenticate user and store token"""
    try:
        response = requests.post(
            f"{API_BASE_URL}/token",
            data={"username": username, "password": password},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            state.token = data["access_token"]
            state.username = username
            state.role = "admin"  # Placeholder — decode from JWT if needed
            
            return (
                gr.update(visible=False),  # Hide login
                gr.update(visible=True),   # Show main app
                f"✅ Welcome, {username}!",
                gr.update(value=f"👤 {username}", visible=True)
            )
        else:
            error = response.json().get("detail", "Login failed")
            return gr.update(visible=True), gr.update(visible=False), f"❌ {error}", gr.update(visible=False)
            
    except Exception as e:
        return gr.update(visible=True), gr.update(visible=False), f"❌ Connection error: {str(e)}", gr.update(visible=False)


def logout():
    """Clear authentication"""
    state.token = None
    state.username = None
    state.role = None
    return (
        gr.update(visible=True),   # Show login
        gr.update(visible=False),  # Hide main app
        "",
        gr.update(visible=False)
    )


def get_headers():
    """Get authorization headers"""
    if state.token:
        return {"Authorization": f"Bearer {state.token}"}
    return {}


# ============================================================================
# API FUNCTIONS — BATCH PROCESSING
# ============================================================================

def run_batch_validation(limit, concurrency):
    """
    Start batch validation job.

    This triggers the background Celery worker to:
      1. Read providers from the source database
      2. Run OCR on any attached scanned PDFs
      3. Scrape provider websites for contact info
      4. Reconcile all data sources and compute confidence scores
      5. Flag records that need manual review

    BUG FIX #4 — Original timeout was 10s which is too short.
    The /run-batch endpoint itself responds quickly (it just queues a task),
    but network latency + worker spin-up can exceed 10s. Raised to 30s.
    """
    if not state.token:
        return "❌ Please login first!"
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/run-batch",
            params={"limit": int(limit), "concurrency": int(concurrency)},
            headers=get_headers(),
            timeout=30  # BUG FIX #4: was 10, raised to 30
        )
        
        if response.status_code == 200:
            data = response.json()
            return f"""✅ **Batch Processing Started!**

**Task ID:** `{data.get('task_id', 'N/A')}`
**Records to Process:** {data.get('limit', 0)}
**Concurrency Level:** {data.get('concurrency', 0)}
**Started By:** {data.get('started_by', state.username)}

⏳ Processing runs in the background via Celery workers.  
Switch to the **"View Providers"** tab and click **Refresh** to see results as they complete."""
        else:
            error = response.json().get("detail", "Unknown error")
            return f"❌ **Error:** {error}"
            
    except requests.exceptions.ReadTimeout:
        # The task was likely queued successfully even if we timed out waiting
        return (
            "⚠️ **Request timed out — but the batch job may still be running!**\n\n"
            "The Celery worker processes records in the background. "
            "Switch to **View Providers → Refresh** in 30–60 seconds to check results.\n\n"
            "If you see no new records after a minute, check that Celery + Redis are running:\n"
            "```\ncelery -A src.worker worker --loglevel=info\n```"
        )
    except Exception as e:
        return f"❌ **Connection Error:** {str(e)}"


# ============================================================================
# API FUNCTIONS — PROVIDERS
# ============================================================================

def fetch_providers(limit):
    """
    Get list of validated providers.

    BUG FIX #2 — Applied unwrap() to name and specialty fields so the UI
    shows real values instead of raw dicts like {'value': None, ...}.
    BUG FIX #3 — Confidence now reads final_confidence (the correct field).
    BUG FIX #6 — Added missing headers=get_headers() and token guard.
    Without the auth header, every request returned 401 silently, so the
    provider table never populated after batch processing completed.
    """
    # BUG FIX #6: Guard added — same pattern as run_batch_validation.
    # Previously this function had no token check and no auth header,
    # so it hit a protected endpoint anonymously → always got 401 → showed nothing.
    if not state.token:
        return "❌ Please login first!"

    try:
        response = requests.get(
            f"{API_BASE_URL}/providers",
            params={"limit": int(limit)},
            headers=get_headers(),  # BUG FIX #6: was missing entirely
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            providers = data.get("providers", [])
            
            if not providers:
                return "ℹ️ No providers found. Run batch processing first."
            
            output = f"### 📊 Provider Records ({data.get('count', 0)} total)\n\n"
            output += "| ID | Name | Specialty | Confidence | Status |\n"
            output += "|---|---|---|---|---|\n"
            
            for p in providers[:20]:
                pid       = p.get('source_id', p.get('rowid', p.get('id', 'N/A')))
                # BUG FIX #2: unwrap dict-wrapped name/specialty
                name      = str(unwrap(p.get('name'), 'Unknown'))[:30]
                specialty = str(unwrap(p.get('specialty'), 'N/A'))
                # BUG FIX #3: use final_confidence, fall back to confidence
                raw_conf  = p.get('final_confidence', p.get('confidence', 0))
                confidence = unwrap_confidence(raw_conf)
                # BUG FIX #5: derive readable status from confidence
                if confidence >= 0.8:
                    status = "✅ Validated"
                elif confidence >= 0.5:
                    status = "⚠️ Review"
                else:
                    status = "❌ Flagged"
                
                conf_emoji = "🟢" if confidence >= 0.8 else "🟡" if confidence >= 0.5 else "🔴"
                output += f"| {pid} | {name} | {specialty} | {conf_emoji} {confidence:.2f} | {status} |\n"
            
            return output
        else:
            return f"❌ Error: {response.status_code} — {response.text[:200]}"
            
    except Exception as e:
        return f"❌ Connection Error: {str(e)}"


def search_provider_by_id(provider_id):
    """
    Get single provider details.

    BUG FIX #2 — All fields are passed through unwrap() so dict-wrapped
    values like {'value': None, 'confidence': 0.95} are shown as clean text.
    BUG FIX #3 — Confidence reads final_confidence correctly.
    BUG FIX #5 — Status is derived from confidence instead of missing field.
    BUG FIX #6 — Added missing headers=get_headers() and token guard.
    Without auth header this always returned 401 → detail panel stayed blank
    and confidence scores / flags were never rendered.
    """
    # BUG FIX #6: Guard added
    if not state.token:
        return "❌ Please login first!", ""

    try:
        response = requests.get(
            f"{API_BASE_URL}/providers/{int(provider_id)}",
            headers=get_headers(),  # BUG FIX #6: was missing entirely
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()

            # BUG FIX #2: unwrap all fields
            name      = unwrap(data.get('name'))
            npi       = unwrap(data.get('npi'))
            phone     = unwrap(data.get('phone'))
            email     = unwrap(data.get('email'))
            address   = unwrap(data.get('address'))
            specialty = unwrap(data.get('specialty'))
            website   = unwrap(data.get('website'))

            # BUG FIX #3: correct confidence field
            raw_conf   = data.get('final_confidence', data.get('confidence', 0))
            confidence = unwrap_confidence(raw_conf)

            # BUG FIX #5: derive status from confidence score
            if confidence >= 0.8:
                status = "✅ Validated — High Confidence"
            elif confidence >= 0.5:
                status = "⚠️ Needs Review — Medium Confidence"
            else:
                status = "❌ Flagged — Low Confidence"

            flags = data.get('flags', [])
            if isinstance(flags, str):
                try:
                    flags = json.loads(flags)
                except Exception:
                    flags = [flags] if flags else []

            output = f"""### 👤 Provider Details

**ID:** {data.get('id', 'N/A')}
**Name:** {name}
**NPI:** {npi}
**Phone:** {phone}
**Email:** {email}
**Address:** {address}
**Specialty:** {specialty}
**Website:** {website}

**Confidence Score:** {confidence:.2f} / 1.00
**Status:** {status}
**Flags:** {', '.join(flags) if flags else 'None — record is clean'}
"""
            return output, json.dumps(data, indent=2)
        else:
            return f"❌ Provider not found (ID: {provider_id})", ""
            
    except Exception as e:
        return f"❌ Error: {str(e)}", ""


def fetch_providers_by_specialty(specialty):
    """
    Filter providers by specialty.
    BUG FIX #2 — unwrap() applied to name field in listing.
    BUG FIX #6 — Added missing headers=get_headers() and token guard.
    """
    # BUG FIX #6: Guard added
    if not state.token:
        return "❌ Please login first!"

    try:
        response = requests.get(
            f"{API_BASE_URL}/providers/specialty/{specialty}",
            headers=get_headers(),  # BUG FIX #6: was missing entirely
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            providers = data.get("providers", [])
            
            if not providers:
                return f"ℹ️ No providers found for specialty: {specialty}"
            
            output = f"### 🏥 {specialty} Providers ({data.get('count', 0)} found)\n\n"
            for p in providers[:15]:
                # BUG FIX #2: unwrap name
                name    = unwrap(p.get('name'), 'Unknown Provider')
                pid     = p.get('id', 'N/A')
                phone   = unwrap(p.get('phone'), 'N/A')
                address = str(unwrap(p.get('address'), 'N/A'))[:40]
                output += f"**{name}** (ID: {pid})\n"
                output += f"  📞 {phone} | 📍 {address}...\n\n"
            
            return output
        else:
            return f"❌ No providers found for: {specialty}"
            
    except Exception as e:
        return f"❌ Error: {str(e)}"


# ============================================================================
# API FUNCTIONS — FLAGGED PROVIDERS (MANUAL REVIEW)
# ============================================================================

def fetch_flagged_providers(confidence_threshold, flag_keyword):
    """
    Get providers needing manual review.

    WHY MANUAL REVIEW EXISTS:
    The AI enrichment pipeline scores every field 0.0–1.0.
    When a record scores BELOW the threshold (default 0.6), it means
    the system could not confidently verify the provider's data —
    e.g., the phone number found on the website doesn't match the PDF,
    or the address appears invalid. A human reviewer then:
      - Calls the provider directly to confirm details
      - Looks up the NPI registry manually
      - Marks the record as verified or removes it
    This prevents bad data from reaching the final directory.

    BUG FIX #6 — Added missing headers=get_headers() and token guard.
    This was why confidence scores and flags never appeared in the Manual
    Review tab — the unauthenticated request returned 401, so providers
    was always an empty list or an error.
    """
    # BUG FIX #6: Guard added
    if not state.token:
        return "❌ Please login first!"

    try:
        params = {"confidence_below": confidence_threshold}
        if flag_keyword:
            params["flag_contains"] = flag_keyword
        
        response = requests.get(
            f"{API_BASE_URL}/providers/flags",
            params=params,
            headers=get_headers(),  # BUG FIX #6: was missing entirely
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            providers = data.get("providers", [])
            
            if not providers:
                return (
                    f"✅ **No providers below confidence {confidence_threshold}!**\n\n"
                    "All records meet the quality threshold — no manual review needed right now."
                )
            
            output = f"### 🚩 Flagged Providers for Manual Review ({data.get('count', 0)} total)\n\n"
            output += f"*Showing records with confidence below **{confidence_threshold}***\n\n"
            
            for p in providers[:15]:
                pid  = p.get('id', 'N/A')
                # BUG FIX #2: unwrap name/specialty
                name      = unwrap(p.get('name'), 'Unknown Provider')
                specialty = unwrap(p.get('specialty'), 'N/A')
                phone     = unwrap(p.get('phone'), 'N/A')

                raw_conf = p.get('final_confidence', p.get('confidence', 0))
                conf     = unwrap_confidence(raw_conf)

                flags = p.get('flags', [])
                if isinstance(flags, str):
                    try:
                        flags = json.loads(flags)
                    except Exception:
                        flags = [flags] if flags else []
                
                output += f"#### 🔴 {name} (ID: {pid})\n"
                output += f"- **Confidence Score:** {conf:.2f} / 1.00\n"
                output += f"- **Why Flagged:** {', '.join(flags) if flags else 'Below threshold'}\n"
                output += f"- **Phone:** {phone}\n"
                output += f"- **Specialty:** {specialty}\n\n"
            
            return output
        else:
            return f"❌ Error: {response.status_code} — {response.text[:200]}"
            
    except Exception as e:
        return f"❌ Error: {str(e)}"


# ============================================================================
# API FUNCTIONS — OUTREACH
# ============================================================================

def send_outreach_emails():
    """
    Generate and queue outreach emails.

    USE CASE: When a provider record has a low confidence score or missing
    fields (e.g., no email, unverified phone), the system automatically
    drafts a professional email to the provider asking them to verify/update
    their directory information. This is sent via SendGrid. The email contains
    a unique verification link so we can track responses.
    """
    if not state.token:
        return "❌ Please login first!"
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/send-outreach",
            headers=get_headers(),
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            emails_count = data.get("emails_generated", 0)
            
            output = f"### 📧 Outreach Emails Generated\n\n"
            output += f"**Total Emails Queued:** {emails_count}\n\n"
            
            if emails_count == 0:
                output += "ℹ️ No providers need outreach — all records are above the confidence threshold."
            else:
                output += "**Email Preview (first 5):**\n\n"
                details = data.get("details", [])[:5]
                
                for email in details:
                    output += f"---\n"
                    output += f"**Provider ID:** {email.get('id', 'N/A')}\n"
                    output += f"**Subject:** {email.get('subject', 'N/A')}\n"
                    output += f"**Recipient:** {email.get('recipient', 'N/A')}\n\n"
            
            return output
        else:
            return f"❌ Error: {response.json().get('detail', 'Unknown error')}"
            
    except Exception as e:
        return f"❌ Error: {str(e)}"


# ============================================================================
# API FUNCTIONS — REPORTS
# ============================================================================

def generate_pdf_report():
    """
    Generate and download PDF report.

    BUG FIX #1 — The original code wrote:
        [Download via API: http://127.0.0.1:8000/reports/pdf]
    which is NOT a valid markdown link (missing the (url) part).
    Markdown renders the ] as a literal character, then URL-encodes it → %5D.
    Fixed to proper markdown link syntax: [text](url)

    BUG FIX #6 — Added missing headers=get_headers().
    Without auth header the report endpoint returned 401 → download always failed.
    """
    if not state.token:
        return "❌ Please login first!", None

    try:
        response = requests.get(
            f"{API_BASE_URL}/reports/pdf",
            headers=get_headers(),  # BUG FIX #6: was missing entirely
            timeout=30
        )
        
        if response.status_code == 200:
            os.makedirs("downloads", exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"downloads/provider_report_{timestamp}.pdf"
            
            with open(filename, "wb") as f:
                f.write(response.content)
            
            # BUG FIX #1: proper markdown link [text](url) — no %5D
            return (
                f"✅ **PDF Report Generated!**\n\n"
                f"Saved to: `{filename}`\n\n"
                f"[📥 Download directly from API]({API_BASE_URL}/reports/pdf)",
                filename
            )
        else:
            return f"❌ Error generating PDF: {response.status_code}", None
            
    except Exception as e:
        return f"❌ Error: {str(e)}", None


def export_csv():
    """
    Export validated providers to CSV.

    BUG FIX #1 — Same broken markdown link issue as PDF. Fixed here too.
    BUG FIX #6 — Added missing headers=get_headers().
    Without auth header the export endpoint returned 401 → CSV always failed silently.
    """
    if not state.token:
        return "❌ Please login first!", None

    try:
        response = requests.get(
            f"{API_BASE_URL}/providers/export",
            headers=get_headers(),  # BUG FIX #6: was missing entirely
            timeout=30
        )
        
        if response.status_code == 200:
            os.makedirs("downloads", exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"downloads/validated_providers_{timestamp}.csv"
            
            with open(filename, "wb") as f:
                f.write(response.content)
            
            # BUG FIX #1: proper markdown link [text](url) — no %5D
            return (
                f"✅ **CSV Export Complete!**\n\n"
                f"Saved to: `{filename}`\n\n"
                f"[📥 Download directly from API]({API_BASE_URL}/providers/export)",
                filename
            )
        else:
            return f"❌ Error: {response.status_code}", None
            
    except Exception as e:
        return f"❌ Error: {str(e)}", None


# ============================================================================
# API FUNCTIONS — MONITORING
# ============================================================================

def fetch_metrics():
    """
    Get Prometheus metrics from the backend.
    BUG FIX #6 — Added headers=get_headers() defensively (endpoint may be protected).
    """
    try:
        response = requests.get(
            f"{API_BASE_URL}/metrics",
            headers=get_headers(),  # BUG FIX #6: added defensively
            timeout=10
        )
        
        if response.status_code == 200:
            metrics_text = response.text
            lines = metrics_text.split("\n")
            output = "### 📈 System Metrics\n\n"
            output += "```\n"
            
            for line in lines[:30]:
                if line and not line.startswith("#"):
                    output += line + "\n"
            
            output += "```\n\n"
            output += f"**Full metrics endpoint:** [{API_BASE_URL}/metrics]({API_BASE_URL}/metrics)"
            
            return output
        else:
            return "❌ Metrics endpoint not available"
            
    except Exception as e:
        return f"❌ Error: {str(e)}"


def check_api_health():
    """Check API health status — public endpoint, no auth needed."""
    try:
        response = requests.get(f"{API_BASE_URL}/", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            return f"""✅ **API Health: ONLINE**

**Status:** {data.get('status', 'Unknown')}
**Endpoint:** {API_BASE_URL}
**Available Endpoints:** {len(data.get('endpoints', []))}

**API Docs:** [Swagger UI]({API_BASE_URL}/docs) | [ReDoc]({API_BASE_URL}/redoc)
"""
        else:
            return f"⚠️ **API responded with status:** {response.status_code}"
            
    except Exception as e:
        return (
            f"❌ **API is DOWN**\n\n"
            f"Error: {str(e)}\n\n"
            f"Make sure FastAPI is running:\n"
            f"```\nuvicorn src.api.app:app --reload --port 8000\n```"
        )


# ============================================================================
# GRADIO UI — MAIN APPLICATION
# ============================================================================

custom_css = """
#login-container {
    max-width: 500px;
    margin: 100px auto;
    padding: 30px;
    border-radius: 15px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    box-shadow: 0 10px 40px rgba(0,0,0,0.2);
}
#main-app {
    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
}
.gradio-container {
    max-width: 1400px !important;
    margin: auto !important;
}
.tab-nav button {
    font-weight: 600 !important;
    font-size: 16px !important;
}
#status-text {
    font-size: 18px;
    font-weight: bold;
    color: #2d3748;
}
"""

with gr.Blocks(title="🏥 Provider Validator Dashboard", theme=gr.themes.Soft(), css=custom_css) as app:

    # ========================================================================
    # LOGIN SCREEN
    # ========================================================================
    with gr.Column(visible=True, elem_id="login-container") as login_screen:
        gr.Markdown("""
        # 🏥 Provider Data Validator
        ### AI-Powered Healthcare Directory Management
        """)
        
        login_username = gr.Textbox(label="👤 Username", placeholder="admin")
        login_password = gr.Textbox(label="🔒 Password", placeholder="Enter password", type="password")
        login_btn      = gr.Button("🚀 Login", variant="primary", size="lg")
        login_status   = gr.Markdown("")
        
        gr.Markdown("""
        ---
        **Default Credentials:**  
        Username: `admin` | Password: `admin123`

        **API Endpoint:** `http://127.0.0.1:8000`
        """)

    # ========================================================================
    # MAIN APPLICATION (Hidden until login)
    # ========================================================================
    with gr.Column(visible=False, elem_id="main-app") as main_app:

        with gr.Row():
            gr.Markdown("# 🏥 Provider Data Validator Dashboard")
            user_badge  = gr.Markdown("", visible=False)
            logout_btn  = gr.Button("🚪 Logout", size="sm", variant="secondary")
        
        gr.Markdown("### AI-powered validation, enrichment, and management system")

        # ====================================================================
        # TAB 1: BATCH PROCESSING
        # ====================================================================
        with gr.Tab("⚙️ Batch Processing"):
            gr.Markdown("""
            ## Start Provider Validation Batch

            This kicks off background workers that:
            1. Read raw provider records from the database
            2. Run **OCR** on scanned PDF files to extract text
            3. **Scrape** provider websites for phone/email/address
            4. Reconcile all sources and compute a **confidence score (0–1)**
            5. Flag low-confidence records for manual review

            Adjust the sliders and click **Start**.
            """)
            
            with gr.Row():
                batch_limit = gr.Slider(
                    minimum=10, maximum=200, value=50, step=10,
                    label="📊 Number of Records to Process"
                )
                batch_concurrency = gr.Slider(
                    minimum=1, maximum=20, value=8, step=1,
                    label="⚡ Concurrency Level (parallel workers)"
                )
            
            batch_start_btn = gr.Button("🚀 Start Batch Processing", variant="primary", size="lg")
            batch_output    = gr.Markdown("")

        # ====================================================================
        # TAB 2: VIEW PROVIDERS
        # ====================================================================
        with gr.Tab("👥 View Providers"):
            gr.Markdown("## Browse Validated Providers")
            
            with gr.Row():
                provider_limit = gr.Slider(10, 100, value=20, step=10, label="Records to Display")
                refresh_btn    = gr.Button("🔄 Refresh", variant="secondary")
            
            providers_output = gr.Markdown("")
            
            gr.Markdown("""
            ---
            ### 🔍 Search by Provider ID

            Enter a numeric provider ID to see full enriched details, 
            confidence breakdown, and any quality flags.
            """)
            with gr.Row():
                provider_id_input = gr.Number(label="Provider ID", precision=0)
                search_btn        = gr.Button("Search", variant="primary")
            
            provider_detail_output = gr.Markdown("")
            provider_json_output   = gr.Code(label="Raw JSON from API", language="json")
            
            gr.Markdown("""
            ---
            ### 🏥 Filter by Specialty

            Type a specialty (e.g., `Cardiology`, `Orthopedics`) to list all 
            matching validated providers.
            """)
            with gr.Row():
                specialty_input      = gr.Textbox(label="Specialty", placeholder="e.g., Cardiology")
                specialty_search_btn = gr.Button("Search", variant="primary")
            
            specialty_output = gr.Markdown("")

        # ====================================================================
        # TAB 3: MANUAL REVIEW (FLAGGED PROVIDERS)
        # ====================================================================
        with gr.Tab("🚩 Manual Review"):
            gr.Markdown("""
            ## Flagged Providers Needing Human Review

            **Why does this exist?**  
            The AI pipeline cannot always verify every field with high confidence.
            For example:
            - The phone number on the website doesn't match the scanned PDF
            - The provider's address appears invalid or incomplete
            - The NPI number could not be verified against the registry

            Records falling below the confidence threshold are shown here so 
            a human reviewer can manually verify and correct the data.

            **What to do:** Contact the provider directly, confirm their details, 
            and update the record accordingly.
            """)
            
            with gr.Row():
                confidence_threshold = gr.Slider(
                    0.1, 0.9, value=0.6, step=0.1,
                    label="Confidence Threshold — show records BELOW this score"
                )
                flag_keyword = gr.Textbox(
                    label="Filter by Flag Keyword (optional)",
                    placeholder="e.g., phone, address, name"
                )
            
            flagged_btn    = gr.Button("🔍 Get Flagged Providers", variant="primary")
            flagged_output = gr.Markdown("")

        # ====================================================================
        # TAB 4: OUTREACH EMAILS
        # ====================================================================
        with gr.Tab("📧 Outreach"):
            gr.Markdown("""
            ## Generate Verification Outreach Emails

            **What this does:**  
            For every provider with a low confidence score or missing fields,
            the system drafts a professional email asking them to verify their
            directory information. Each email contains a unique secure link.

            **Delivery:** Emails are sent via SendGrid and tracked for responses.
            When a provider clicks the link and confirms their details, the 
            confidence score is updated automatically.
            """)
            
            outreach_btn    = gr.Button("📨 Generate & Queue Outreach Emails", variant="primary", size="lg")
            outreach_output = gr.Markdown("")

        # ====================================================================
        # TAB 5: REPORTS & EXPORTS
        # ====================================================================
        with gr.Tab("📊 Reports & Export"):
            gr.Markdown("""
            ## Generate Reports & Export Data

            - **PDF Report** — Full summary of validation results, confidence 
              statistics, and flagged records. Ready to share with stakeholders.
            - **CSV Export** — All validated provider records in spreadsheet format 
              for use in CRM, billing, or directory publishing systems.
            """)
            
            with gr.Row():
                pdf_btn = gr.Button("📄 Generate PDF Report", variant="primary")
                csv_btn = gr.Button("📁 Export CSV", variant="secondary")
            
            report_output = gr.Markdown("")
            download_file = gr.File(label="⬇️ Download File")

        # ====================================================================
        # TAB 6: MONITORING & METRICS
        # ====================================================================
        with gr.Tab("📈 Monitoring"):
            gr.Markdown("## System Health & Metrics")
            
            with gr.Row():
                health_btn  = gr.Button("🏥 Check API Health", variant="primary")
                metrics_btn = gr.Button("📊 Fetch Prometheus Metrics", variant="secondary")
            
            monitoring_output = gr.Markdown("")

        # ====================================================================
        # TAB 7: SYSTEM INFO
        # ====================================================================
        with gr.Tab("ℹ️ Info"):
            gr.Markdown(f"""
            ## 🏥 Provider Data Validator — System Guide

            ---

            ### What is the Confidence Score?

            Every provider record gets a **confidence score from 0.0 to 1.0** based on
            how well the AI was able to verify and reconcile data across multiple sources:

            | Score | Meaning | Action |
            |---|---|---|
            | 🟢 0.8 – 1.0 | High confidence — data verified across sources | Auto-publish |
            | 🟡 0.5 – 0.79 | Medium confidence — some fields uncertain | Flag for review |
            | 🔴 0.0 – 0.49 | Low confidence — significant data problems | Manual review + outreach |

            The score is computed per-field (name, phone, address, NPI, etc.) and the
            final score is the **weighted average** stored as `final_confidence`.

            ---

            ### What do the Sources Mean?

            Each field in the raw API response shows its sources:
            ```
            'sources': ['validation', 'enrichment', 'ocr']
            ```
            - **ocr** — extracted from a scanned PDF using Tesseract OCR
            - **enrichment** — scraped from the provider's website
            - **validation** — cross-checked against NPI registry or reference data

            ---

            ### Architecture

            **Backend:** FastAPI + SQLAlchemy  
            **Database:** SQLite (dev) / PostgreSQL (prod)  
            **Queue:** Celery + Redis  
            **OCR:** Tesseract + pdf2image  
            **Email:** SendGrid API  
            **Monitoring:** Prometheus metrics  

            ---

            ### API Documentation

            📖 [Swagger UI — Interactive API Docs]({API_BASE_URL}/docs)  
            📖 [ReDoc — Reference Docs]({API_BASE_URL}/redoc)

            **API Endpoint:** `{API_BASE_URL}`  
            **Gradio Port:** `{GRADIO_PORT}`  
            **Version:** 1.0.0  
            """)

    # ========================================================================
    # EVENT HANDLERS
    # ========================================================================

    login_btn.click(
        fn=login,
        inputs=[login_username, login_password],
        outputs=[login_screen, main_app, login_status, user_badge]
    )

    logout_btn.click(
        fn=logout,
        outputs=[login_screen, main_app, login_status, user_badge]
    )

    batch_start_btn.click(
        fn=run_batch_validation,
        inputs=[batch_limit, batch_concurrency],
        outputs=batch_output
    )

    refresh_btn.click(
        fn=fetch_providers,
        inputs=[provider_limit],
        outputs=providers_output
    )

    search_btn.click(
        fn=search_provider_by_id,
        inputs=[provider_id_input],
        outputs=[provider_detail_output, provider_json_output]
    )

    specialty_search_btn.click(
        fn=fetch_providers_by_specialty,
        inputs=[specialty_input],
        outputs=specialty_output
    )

    flagged_btn.click(
        fn=fetch_flagged_providers,
        inputs=[confidence_threshold, flag_keyword],
        outputs=flagged_output
    )

    outreach_btn.click(
        fn=send_outreach_emails,
        outputs=outreach_output
    )

    pdf_btn.click(
        fn=generate_pdf_report,
        outputs=[report_output, download_file]
    )

    csv_btn.click(
        fn=export_csv,
        outputs=[report_output, download_file]
    )

    health_btn.click(
        fn=check_api_health,
        outputs=monitoring_output
    )

    metrics_btn.click(
        fn=fetch_metrics,
        outputs=monitoring_output
    )


# ============================================================================
# LAUNCH APPLICATION
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("🏥 PROVIDER DATA VALIDATOR - GRADIO DASHBOARD")
    print("=" * 70)
    print(f"🌐 API Endpoint: {API_BASE_URL}")
    print(f"🎨 Gradio Host: {GRADIO_HOST}:{GRADIO_PORT}")
    print("=" * 70)
    print("\n⚠️  Make sure FastAPI is running before using this interface!")
    print("   Start with: uvicorn src.api.app:app --reload --port 8000\n")
    print("⚠️  Make sure Celery + Redis are running for batch processing!")
    print("   Start with: celery -A src.worker worker --loglevel=info\n")

    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
        favicon_path=None
    )