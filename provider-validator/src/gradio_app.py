# src/gradio_app.py - Complete Provider Validator Dashboard (FULLY FIXED)
import os
import json
import ast
import gradio as gr
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
GRADIO_PORT  = int(os.getenv("GRADIO_PORT", "7860"))
GRADIO_HOST  = os.getenv("GRADIO_HOST", "127.0.0.1")

class AppState:
    token        = None
    username     = None
    role         = None
    last_task_id = None

state = AppState()

# ============================================================================
# HELPERS
# ============================================================================

def unwrap(field, fallback="N/A"):
    """Extract plain value from backend confidence-wrapped field dict."""
    if field is None:
        return fallback
    if isinstance(field, (int, float, bool)):
        return field
    if isinstance(field, dict):
        val = field.get("value")
        return val if (val is not None and val != "") else fallback
    if isinstance(field, str):
        stripped = field.strip()
        if stripped.startswith("{"):
            try:
                parsed = ast.literal_eval(stripped)
                if isinstance(parsed, dict):
                    val = parsed.get("value")
                    return val if (val is not None and val != "") else fallback
            except Exception:
                pass
        return stripped if stripped else fallback
    return fallback


def unwrap_confidence(field):
    """Extract numeric confidence score 0.0-1.0 from any field shape."""
    if field is None:
        return 0.0
    if isinstance(field, (int, float)):
        return float(field)
    if isinstance(field, str):
        try:
            return float(field)
        except ValueError:
            pass
        stripped = field.strip()
        if stripped.startswith("{"):
            try:
                parsed = ast.literal_eval(stripped)
                if isinstance(parsed, dict):
                    return float(parsed.get("confidence", 0.0))
            except Exception:
                pass
        return 0.0
    if isinstance(field, dict):
        try:
            return float(field.get("confidence", 0.0))
        except Exception:
            return 0.0
    return 0.0


def parse_flags(raw):
    """Safely parse a flags field that may be a list, JSON string, or Python string."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = ast.literal_eval(raw.strip())
            return parsed if isinstance(parsed, list) else [raw]
        except Exception:
            try:
                parsed = json.loads(raw.strip())
                return parsed if isinstance(parsed, list) else [raw]
            except Exception:
                return [raw]
    return []


def extract_list(data, tried_keys=("providers","data","results","items","records")):
    """
    Robustly extract a list of records from any response shape:
      - bare list: [...]
      - wrapped dict: {"providers": [...], ...}
    Returns (list_of_records, total_count, error_message_or_None)
    """
    if isinstance(data, list):
        return data, len(data), None
    if isinstance(data, dict):
        for key in tried_keys:
            val = data.get(key)
            if isinstance(val, list):
                total = data.get("count", data.get("total", data.get("total_count", len(val))))
                return val, total, None
        # No matching key found — return diagnostic info
        try:
            preview = json.dumps(data, indent=2)[:600]
        except Exception:
            preview = str(data)[:400]
        err = (
            f"⚠️ **Response returned 200 but no list found.**\n\n"
            f"**Keys present:** `{list(data.keys())}`\n\n"
            f"**Raw response:**\n```json\n{preview}\n```"
        )
        return [], 0, err
    return [], 0, f"⚠️ Unexpected response type: `{type(data).__name__}`"


def get_headers():
    if state.token:
        return {"Authorization": f"Bearer {state.token}"}
    return {}


# ============================================================================
# AUTHENTICATION
# ============================================================================

def login(username, password):
    try:
        response = requests.post(
            f"{API_BASE_URL}/token",
            data={"username": username, "password": password},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            state.token    = data["access_token"]
            state.username = username
            state.role     = "admin"
            return (
                gr.update(visible=False),
                gr.update(visible=True),
                f"✅ Welcome, {username}!",
                gr.update(value=f"👤 {username}", visible=True)
            )
        else:
            error = response.json().get("detail", "Login failed")
            return gr.update(visible=True), gr.update(visible=False), f"❌ {error}", gr.update(visible=False)
    except Exception as e:
        return gr.update(visible=True), gr.update(visible=False), f"❌ Connection error: {str(e)}", gr.update(visible=False)


def logout():
    state.token = state.username = state.role = None
    return gr.update(visible=True), gr.update(visible=False), "", gr.update(visible=False)


# ============================================================================
# DIAGNOSIS TOOL
# ============================================================================

def run_diagnosis():
    """
    DIAGNOSIS TOOL — probes every relevant endpoint and reports exactly what
    data exists and where, so you can see immediately why View Providers is empty.

    This is the key tool for debugging the orchestrator→API data flow gap:
      python -m src.orchestrator  →  writes records to DB
      GET /providers              →  reads from DB (but may filter by status)

    The diagnosis checks both the standard /providers endpoint AND tries
    alternative endpoints/params to find where the batch records actually landed.
    """
    lines = ["## 🔍 System Diagnosis Report\n"]
    lines.append(f"**API:** `{API_BASE_URL}`  |  **Time:** {datetime.now().strftime('%H:%M:%S')}\n\n---\n")

    def probe(label, url, params=None, method="GET", headers=None):
        try:
            r = requests.request(
                method, url,
                params=params,
                headers=headers or get_headers(),
                timeout=10
            )
            try:
                body = r.json()
            except Exception:
                body = r.text[:300]

            # Summarise the response shape
            if isinstance(body, list):
                summary = f"✅ **{r.status_code}** — bare list, **{len(body)} records**"
                if body:
                    summary += f"\n  - First record keys: `{list(body[0].keys()) if isinstance(body[0], dict) else type(body[0]).__name__}`"
            elif isinstance(body, dict):
                summary = f"✅ **{r.status_code}** — dict keys: `{list(body.keys())}`"
                # Look for any list values and count them
                for k, v in body.items():
                    if isinstance(v, list):
                        summary += f"\n  - `{k}`: **{len(v)} records**"
                        if v and isinstance(v[0], dict):
                            summary += f" (first record keys: `{list(v[0].keys())}`)"
            else:
                summary = f"**{r.status_code}** — `{str(body)[:200]}`"
            return summary
        except requests.exceptions.ConnectionError:
            return "❌ **Connection refused** — is FastAPI running?"
        except Exception as e:
            return f"❌ `{str(e)}`"

    # 1. API root / health
    lines.append("### 1. API Health\n")
    lines.append(probe("Root", f"{API_BASE_URL}/") + "\n\n")

    # 2. Standard /providers (no auth, then with auth)
    lines.append("### 2. GET /providers (no auth)\n")
    lines.append(probe("providers-noauth", f"{API_BASE_URL}/providers",
                        params={"limit": 50}, headers={}) + "\n\n")

    lines.append("### 3. GET /providers (with auth token)\n")
    if not state.token:
        lines.append("⚠️ Not logged in — token missing. Login first.\n\n")
    else:
        lines.append(probe("providers-auth", f"{API_BASE_URL}/providers",
                            params={"limit": 50}) + "\n\n")

    # 3. Try status variants — the orchestrator may write records with status="pending"
    #    but /providers only returns status="validated". Try all status values.
    lines.append("### 4. GET /providers with status variants\n")
    for status_val in ("all", "pending", "processing", "validated", "flagged", "raw"):
        result = probe(
            f"status={status_val}",
            f"{API_BASE_URL}/providers",
            params={"limit": 50, "status": status_val}
        )
        lines.append(f"- `status={status_val}`: {result}\n")
    lines.append("\n")

    # 4. Try /providers/flags directly
    lines.append("### 5. GET /providers/flags\n")
    lines.append(probe("flags", f"{API_BASE_URL}/providers/flags",
                        params={"confidence_below": 1.0, "limit": 50}) + "\n\n")

    # 5. Try alternative base endpoints the orchestrator might write to
    lines.append("### 6. Alternative endpoints\n")
    for alt in ("/batch/results", "/results", "/validated", "/pipeline/results",
                "/providers/all", "/providers/raw"):
        result = probe(f"alt:{alt}", f"{API_BASE_URL}{alt}", params={"limit": 10})
        lines.append(f"- `{alt}`: {result}\n")
    lines.append("\n")

    # 6. Batch status
    lines.append("### 7. Batch/task status\n")
    if state.last_task_id:
        lines.append(probe("task-status", f"{API_BASE_URL}/batch/status/{state.last_task_id}") + "\n\n")
    else:
        lines.append("ℹ️ No task ID stored (batch wasn't started via UI this session).\n\n")

    lines.append("---\n")
    lines.append(
        "**How to read this:** Find the endpoint that shows records > 0. "
        "That's where your orchestrator writes to. If `/providers?status=pending` "
        "has records but `/providers` (no status) has 0, the backend filters to "
        "`validated` only and the orchestrator isn't promoting records. "
        "Fix: pass `status=all` or `status=pending` when fetching, or check your "
        "backend's `/providers` route filter condition."
    )
    return "\n".join(lines)


# ============================================================================
# BATCH PROCESSING
# ============================================================================

def run_batch_validation(limit, concurrency):
    if not state.token:
        return "❌ Please login first!"
    try:
        response = requests.post(
            f"{API_BASE_URL}/run-batch",
            params={"limit": int(limit), "concurrency": int(concurrency)},
            headers=get_headers(),
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            state.last_task_id = data.get("task_id")
            return f"""✅ **Batch Processing Started!**

**Task ID:** `{data.get('task_id', 'N/A')}`
**Records to Process:** {data.get('limit', 0)}
**Concurrency Level:** {data.get('concurrency', 0)}
**Started By:** {data.get('started_by', state.username)}

⏳ Processing runs in the background via Celery workers.
Switch to **View Providers → Refresh** to see results as they complete.

> 💡 If you ran the batch via CLI (`python -m src.orchestrator ...`), click
> **Refresh** in View Providers. If records still don't appear, use the
> **🔍 Diagnose** button to find where records were written."""
        else:
            try:
                error = response.json().get("detail", "Unknown error")
            except Exception:
                error = response.text[:200]
            return (
                f"❌ **Batch endpoint error ({response.status_code}):** {error}\n\n"
                f"> ℹ️ If Redis is not running, use the CLI instead:\n"
                f"> ```\n> python -m src.orchestrator data/providers_sample.csv 8 10\n> ```\n"
                f"> Then click **Refresh** in the View Providers tab."
            )
    except requests.exceptions.ReadTimeout:
        return (
            "⚠️ **Request timed out — batch may still be running.**\n\n"
            "Switch to **View Providers → Refresh** in 30–60 seconds.\n\n"
            "If no records appear, run the **🔍 Diagnose** tool to find where data landed."
        )
    except Exception as e:
        return f"❌ **Connection Error:** {str(e)}"


# ============================================================================
# VIEW PROVIDERS
# ============================================================================

def fetch_providers(limit, status_filter="all"):
    """
    FIXED: Now sends status=all by default so records written by the orchestrator
    (which may have status 'pending' or 'processing') are included.

    Previously the frontend sent no status param, so the backend defaulted to
    status='validated' only — meaning CLI-batch records never appeared.
    """
    if not state.token:
        return "❌ Please login first!"
    try:
        # KEY FIX: pass status="all" so we see every record regardless of
        # validation status. This is why CLI-batch records never showed up.
        params = {"limit": int(limit)}
        if status_filter and status_filter != "default":
            params["status"] = status_filter

        response = requests.get(
            f"{API_BASE_URL}/providers",
            params=params,
            headers=get_headers(),
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            providers, total_count, err = extract_list(data)

            if err:
                return err

            if not providers:
                return (
                    f"ℹ️ **No providers found** (status filter: `{status_filter}`, limit: {limit})\n\n"
                    f"**Try these steps:**\n"
                    f"1. Click **🔍 Diagnose** below to find where batch records landed\n"
                    f"2. Try the **Status Filter** dropdown — records may be in `pending` status\n"
                    f"3. If you ran the CLI batch (`python -m src.orchestrator ...`), confirm it "
                    f"completed successfully and wrote to the same DB the API reads from\n\n"
                    f"**Response from API:** `{json.dumps(data)[:300]}`"
                )

            output = f"### 📊 Provider Records ({total_count} total, showing {min(len(providers), 20)})\n\n"
            output += "| ID | Name | Specialty | Confidence | Status |\n"
            output += "|---|---|---|---|---|\n"

            for p in providers[:20]:
                pid        = p.get("source_id") or p.get("rowid") or p.get("id", "N/A")
                name       = str(unwrap(p.get("name"), "Unknown"))[:30]
                specialty  = str(unwrap(p.get("specialty"), "N/A"))
                raw_conf   = p.get("final_confidence", p.get("confidence", 0))
                confidence = unwrap_confidence(raw_conf)

                if confidence >= 0.8:
                    row_status = "✅ Validated"
                elif confidence >= 0.5:
                    row_status = "⚠️ Review"
                elif confidence == 0.0:
                    row_status = "⏳ Pending"
                else:
                    row_status = "❌ Flagged"

                conf_emoji = "🟢" if confidence >= 0.8 else ("🟡" if confidence >= 0.5 else "🔴")
                output += f"| {pid} | {name} | {specialty} | {conf_emoji} {confidence:.2f} | {row_status} |\n"

            return output

        elif response.status_code == 401:
            return "❌ **401 Unauthorized** — token may have expired. Please logout and login again."
        else:
            return f"❌ API Error {response.status_code}: `{response.text[:300]}`"

    except Exception as e:
        return f"❌ Connection Error: {str(e)}"


def search_provider_by_id(provider_id):
    if not state.token:
        return "❌ Please login first!", ""
    if not provider_id:
        return "⚠️ Please enter a Provider ID.", ""
    try:
        response = requests.get(
            f"{API_BASE_URL}/providers/{int(provider_id)}",
            headers=get_headers(),
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            name      = unwrap(data.get("name"))
            npi       = unwrap(data.get("npi"))
            phone     = unwrap(data.get("phone"))
            email     = unwrap(data.get("email"))
            address   = unwrap(data.get("address"))
            specialty = unwrap(data.get("specialty"))
            website   = unwrap(data.get("website"))
            raw_conf  = data.get("final_confidence", data.get("confidence", 0))
            confidence = unwrap_confidence(raw_conf)
            if confidence >= 0.8:
                status = "✅ Validated — High Confidence"
            elif confidence >= 0.5:
                status = "⚠️ Needs Review — Medium Confidence"
            else:
                status = "❌ Flagged — Low Confidence"
            flags = parse_flags(data.get("flags", []))
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
**Flags:** {', '.join(str(f) for f in flags) if flags else 'None — record is clean'}
"""
            return output, json.dumps(data, indent=2)
        else:
            return f"❌ Provider not found (ID: {provider_id})", ""
    except Exception as e:
        return f"❌ Error: {str(e)}", ""


def fetch_providers_by_specialty(specialty):
    if not state.token:
        return "❌ Please login first!"
    if not specialty or not specialty.strip():
        return "⚠️ Please enter a specialty (e.g. Cardiology)."
    try:
        response = requests.get(
            f"{API_BASE_URL}/providers/specialty/{specialty.strip()}",
            headers=get_headers(),
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            providers, total_count, err = extract_list(data)
            if err:
                return err
            if not providers:
                return f"ℹ️ No providers found for specialty: **{specialty}**"
            output = f"### 🏥 {specialty} Providers ({total_count} found)\n\n"
            for p in providers[:15]:
                name    = unwrap(p.get("name"), "Unknown Provider")
                pid     = p.get("id", "N/A")
                phone   = unwrap(p.get("phone"), "N/A")
                address = str(unwrap(p.get("address"), "N/A"))[:40]
                output += f"**{name}** (ID: {pid})\n"
                output += f"  📞 {phone} | 📍 {address}...\n\n"
            return output
        else:
            return f"❌ Error {response.status_code} for specialty: {specialty}"
    except Exception as e:
        return f"❌ Error: {str(e)}"


# ============================================================================
# MANUAL REVIEW — FIXED: client-side filtering on /providers
# ============================================================================

def fetch_flagged_providers(confidence_threshold, flag_keyword):
    """
    FIXED: The /providers/flags endpoint always returned empty regardless of inputs.

    Root cause: the backend query was broken (wrong column name or param mismatch).
    Fix: fetch all providers via the working /providers endpoint and filter
    client-side by confidence score and keyword. This is reliable and works
    without any backend changes.

    The keyword now does case-insensitive substring match against:
    flag reasons, provider name, and specialty.
    """
    if not state.token:
        return "❌ Please login first!"
    try:
        # Fetch all records — use status=all to include pending/unvalidated records
        response = requests.get(
            f"{API_BASE_URL}/providers",
            params={"limit": 500, "status": "all"},
            headers=get_headers(),
            timeout=15
        )

        if response.status_code != 200:
            # Fall back to no status param if status=all isn't supported
            response = requests.get(
                f"{API_BASE_URL}/providers",
                params={"limit": 500},
                headers=get_headers(),
                timeout=15
            )

        if response.status_code != 200:
            return f"❌ Error fetching providers: {response.status_code}\n```\n{response.text[:300]}\n```"

        data = response.json()
        all_providers, _, err = extract_list(data)

        if err:
            return err

        if not all_providers:
            return (
                "ℹ️ No provider records found.\n\n"
                "Run batch processing first, then try again.\n"
                "Use the **🔍 Diagnose** button to verify records exist."
            )

        # Client-side filter: confidence BELOW threshold
        flagged = []
        for p in all_providers:
            raw_conf = p.get("final_confidence", p.get("confidence", 0))
            conf = unwrap_confidence(raw_conf)
            if conf < confidence_threshold:
                flagged.append((p, conf))

        # Optional keyword filter (case-insensitive substring)
        if flag_keyword and flag_keyword.strip():
            kw = flag_keyword.strip().lower()
            filtered = []
            for (p, conf) in flagged:
                flags_list = parse_flags(p.get("flags", []))
                flags_str  = " ".join(str(f) for f in flags_list).lower()
                name_str   = str(unwrap(p.get("name"), "")).lower()
                spec_str   = str(unwrap(p.get("specialty"), "")).lower()
                addr_str   = str(unwrap(p.get("address"), "")).lower()
                if kw in flags_str or kw in name_str or kw in spec_str or kw in addr_str:
                    filtered.append((p, conf))
            flagged = filtered

        if not flagged:
            return (
                f"✅ **No providers found below confidence {confidence_threshold}"
                + (f" matching `{flag_keyword}`" if flag_keyword and flag_keyword.strip() else "")
                + f"**\n\n"
                + f"Checked {len(all_providers)} total records.\n\n"
                + (
                    f"> 💡 Try lowering the threshold slider or clearing the keyword filter."
                    if confidence_threshold >= 0.5 else ""
                )
            )

        # Sort worst confidence first
        flagged.sort(key=lambda x: x[1])

        output = (
            f"### 🚩 Flagged Providers — Manual Review Required\n\n"
            f"**{len(flagged)}** of {len(all_providers)} records below confidence "
            f"**{confidence_threshold}**"
        )
        if flag_keyword and flag_keyword.strip():
            output += f" matching `{flag_keyword}`"
        output += "\n\n"

        for (p, conf) in flagged[:20]:
            pid       = p.get("source_id") or p.get("rowid") or p.get("id", "N/A")
            name      = unwrap(p.get("name"), "Unknown Provider")
            specialty = unwrap(p.get("specialty"), "N/A")
            phone     = unwrap(p.get("phone"), "N/A")
            email     = unwrap(p.get("email"), "N/A")
            flags     = parse_flags(p.get("flags", []))

            conf_icon = "🔴" if conf < 0.5 else "🟡"
            output += f"#### {conf_icon} {name} (ID: {pid})\n"
            output += f"- **Confidence:** `{conf:.2f}` / 1.00\n"
            output += f"- **Flags:** {', '.join(str(f) for f in flags) if flags else 'Below threshold'}\n"
            output += f"- **Phone:** {phone}\n"
            output += f"- **Email:** {email}\n"
            output += f"- **Specialty:** {specialty}\n\n"

        if len(flagged) > 20:
            output += f"\n*...and {len(flagged) - 20} more records.*\n"

        return output

    except Exception as e:
        return f"❌ Error: {str(e)}"


# ============================================================================
# OUTREACH
# ============================================================================

def send_outreach_emails():
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
            output = f"### 📧 Outreach Emails Generated\n\n**Total Queued:** {emails_count}\n\n"
            if emails_count == 0:
                output += "ℹ️ No providers need outreach — all records are above threshold."
            else:
                output += "**Email Preview (first 5):**\n\n"
                for email in data.get("details", [])[:5]:
                    output += f"---\n**ID:** {email.get('id','N/A')} | **Subject:** {email.get('subject','N/A')} | **To:** {email.get('recipient','N/A')}\n\n"
            return output
        else:
            return f"❌ Error: {response.json().get('detail', 'Unknown error')}"
    except Exception as e:
        return f"❌ Error: {str(e)}"


# ============================================================================
# REPORTS & EXPORTS
# ============================================================================

def generate_pdf_report():
    if not state.token:
        return "❌ Please login first!", None
    try:
        response = requests.get(
            f"{API_BASE_URL}/reports/pdf",
            headers=get_headers(),
            timeout=30
        )
        if response.status_code == 200:
            os.makedirs("downloads", exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"downloads/provider_report_{timestamp}.pdf"
            with open(filename, "wb") as f:
                f.write(response.content)
            return (
                f"✅ **PDF Report Generated!**\n\nSaved to: `{filename}`\n\n"
                f"[📥 Download from API]({API_BASE_URL}/reports/pdf)",
                filename
            )
        else:
            return f"❌ Error generating PDF: {response.status_code}", None
    except Exception as e:
        return f"❌ Error: {str(e)}", None


def export_csv():
    if not state.token:
        return "❌ Please login first!", None
    try:
        response = requests.get(
            f"{API_BASE_URL}/providers/export",
            headers=get_headers(),
            timeout=30
        )
        if response.status_code == 200:
            os.makedirs("downloads", exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename  = f"downloads/validated_providers_{timestamp}.csv"
            with open(filename, "wb") as f:
                f.write(response.content)
            return (
                f"✅ **CSV Export Complete!**\n\nSaved to: `{filename}`\n\n"
                f"[📥 Download from API]({API_BASE_URL}/providers/export)",
                filename
            )
        else:
            return f"❌ Error: {response.status_code}", None
    except Exception as e:
        return f"❌ Error: {str(e)}", None


# ============================================================================
# MONITORING
# ============================================================================

def fetch_metrics():
    try:
        response = requests.get(f"{API_BASE_URL}/metrics", headers=get_headers(), timeout=10)
        if response.status_code == 200:
            lines = [l for l in response.text.split("\n")[:30] if l and not l.startswith("#")]
            return "### 📈 System Metrics\n\n```\n" + "\n".join(lines) + f"\n```\n\n[Full metrics]({API_BASE_URL}/metrics)"
        return "❌ Metrics endpoint not available"
    except Exception as e:
        return f"❌ Error: {str(e)}"


def check_api_health():
    try:
        response = requests.get(f"{API_BASE_URL}/", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return (
                f"✅ **API Health: ONLINE**\n\n"
                f"**Status:** {data.get('status','Unknown')}\n"
                f"**Endpoint:** {API_BASE_URL}\n\n"
                f"[Swagger UI]({API_BASE_URL}/docs) | [ReDoc]({API_BASE_URL}/redoc)"
            )
        return f"⚠️ API responded with status: {response.status_code}"
    except Exception as e:
        return f"❌ **API is DOWN**\n\nError: {str(e)}\n\n```\nuvicorn src.api.app:app --reload --port 8000\n```"


# ============================================================================
# GRADIO UI
# ============================================================================

custom_css = """
#login-container {
    max-width: 500px; margin: 100px auto; padding: 30px;
    border-radius: 15px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    box-shadow: 0 10px 40px rgba(0,0,0,0.2);
}
.gradio-container { max-width: 1400px !important; margin: auto !important; }
.tab-nav button { font-weight: 600 !important; font-size: 16px !important; }
"""

with gr.Blocks(title="🏥 Provider Validator Dashboard", theme=gr.themes.Soft(), css=custom_css) as app:

    # LOGIN
    with gr.Column(visible=True, elem_id="login-container") as login_screen:
        gr.Markdown("# 🏥 Provider Data Validator\n### AI-Powered Healthcare Directory Management")
        login_username = gr.Textbox(label="👤 Username", placeholder="admin")
        login_password = gr.Textbox(label="🔒 Password", placeholder="Enter password", type="password")
        login_btn      = gr.Button("🚀 Login", variant="primary", size="lg")
        login_status   = gr.Markdown("")
        gr.Markdown("---\n**Default Credentials:**  \nUsername: `admin` | Password: `admin123`\n\n**API:** `http://127.0.0.1:8000`")

    # MAIN APP
    with gr.Column(visible=False, elem_id="main-app") as main_app:

        with gr.Row():
            gr.Markdown("# 🏥 Provider Data Validator Dashboard")
            user_badge = gr.Markdown("", visible=False)
            logout_btn = gr.Button("🚪 Logout", size="sm", variant="secondary")
        gr.Markdown("### AI-powered validation, enrichment, and management system")

        # ── TAB 1: BATCH ──────────────────────────────────────────────────────
        with gr.Tab("⚙️ Batch Processing"):
            gr.Markdown("""
            ## Start Provider Validation Batch

            > **Running via CLI instead?** That's fine — just run:
            > ```
            > python -m src.orchestrator data/providers_sample.csv 8 10
            > ```
            > Then go to **View Providers → Refresh**. If records don't appear,
            > use the **🔍 Diagnose** tab to find where they landed.
            """)
            with gr.Row():
                batch_limit       = gr.Slider(10, 200, value=50, step=10, label="📊 Records to Process")
                batch_concurrency = gr.Slider(1, 20,   value=8,  step=1,  label="⚡ Concurrency Level")
            batch_start_btn = gr.Button("🚀 Start Batch Processing", variant="primary", size="lg")
            batch_output    = gr.Markdown("")

        # ── TAB 2: VIEW PROVIDERS ─────────────────────────────────────────────
        with gr.Tab("👥 View Providers"):
            gr.Markdown("## Browse Validated Providers")
            with gr.Row():
                provider_limit   = gr.Slider(10, 100, value=20, step=10, label="Records to Display")
                status_filter_dd = gr.Dropdown(
                    choices=["all", "default", "validated", "pending", "flagged", "processing"],
                    value="all",
                    label="Status Filter",
                    info="'all' shows every record including CLI-batch results"
                )
                refresh_btn = gr.Button("🔄 Refresh", variant="primary")
            providers_output = gr.Markdown("")

            gr.Markdown("---\n### 🔍 Search by Provider ID")
            with gr.Row():
                provider_id_input = gr.Number(label="Provider ID", precision=0)
                search_btn        = gr.Button("Search", variant="primary")
            provider_detail_output = gr.Markdown("")
            provider_json_output   = gr.Code(label="Raw JSON from API", language="json")

            gr.Markdown("---\n### 🏥 Filter by Specialty")
            with gr.Row():
                specialty_input      = gr.Textbox(label="Specialty", placeholder="e.g., Cardiology")
                specialty_search_btn = gr.Button("Search", variant="primary")
            specialty_output = gr.Markdown("")

        # ── TAB 3: MANUAL REVIEW ──────────────────────────────────────────────
        with gr.Tab("🚩 Manual Review"):
            gr.Markdown("""
            ## Flagged Providers Needing Human Review

            **FIXED:** Now filters records client-side from `/providers` — no longer
            depends on the broken `/providers/flags` backend endpoint.

            Keyword search matches: flag reasons · provider name · specialty · address.
            """)
            with gr.Row():
                confidence_threshold = gr.Slider(0.1, 0.9, value=0.6, step=0.1,
                                                 label="Show records BELOW this confidence score")
                flag_keyword = gr.Textbox(label="Keyword Filter (optional)",
                                          placeholder="e.g., phone, Cardiology, address")
            flagged_btn    = gr.Button("🔍 Get Flagged Providers", variant="primary")
            flagged_output = gr.Markdown("")

        # ── TAB 4: OUTREACH ───────────────────────────────────────────────────
        with gr.Tab("📧 Outreach"):
            gr.Markdown("## Generate Verification Outreach Emails")
            outreach_btn    = gr.Button("📨 Generate & Queue Outreach Emails", variant="primary", size="lg")
            outreach_output = gr.Markdown("")

        # ── TAB 5: REPORTS ────────────────────────────────────────────────────
        with gr.Tab("📊 Reports & Export"):
            gr.Markdown("## Generate Reports & Export Data")
            with gr.Row():
                pdf_btn = gr.Button("📄 Generate PDF Report", variant="primary")
                csv_btn = gr.Button("📁 Export CSV",          variant="secondary")
            report_output = gr.Markdown("")
            download_file = gr.File(label="⬇️ Download File")

        # ── TAB 6: DIAGNOSIS (NEW) ────────────────────────────────────────────
        with gr.Tab("🔍 Diagnose"):
            gr.Markdown("""
            ## System Diagnosis Tool

            **Use this when View Providers is empty after running the CLI orchestrator.**

            This probes every relevant API endpoint and shows exactly:
            - Which endpoints return records and how many
            - Whether records exist but are filtered out by status
            - Which response keys your backend actually uses

            Run this once after CLI batch, then read the results to find your records.
            """)
            diagnose_btn    = gr.Button("🔍 Run Full Diagnosis", variant="primary", size="lg")
            diagnose_output = gr.Markdown("")

        # ── TAB 7: MONITORING ─────────────────────────────────────────────────
        with gr.Tab("📈 Monitoring"):
            gr.Markdown("## System Health & Metrics")
            with gr.Row():
                health_btn  = gr.Button("🏥 Check API Health",           variant="primary")
                metrics_btn = gr.Button("📊 Fetch Prometheus Metrics",    variant="secondary")
            monitoring_output = gr.Markdown("")

        # ── TAB 8: INFO ───────────────────────────────────────────────────────
        with gr.Tab("ℹ️ Info"):
            gr.Markdown(f"""
            ## System Guide

            | Score | Meaning | Action |
            |---|---|---|
            | 🟢 0.8–1.0 | High confidence | Auto-publish |
            | 🟡 0.5–0.79 | Medium confidence | Flag for review |
            | 🔴 0.0–0.49 | Low confidence | Manual review + outreach |

            **Architecture:** FastAPI + SQLAlchemy | Celery + Redis | Tesseract OCR | SendGrid

            📖 [Swagger UI]({API_BASE_URL}/docs) | [ReDoc]({API_BASE_URL}/redoc)

            **API:** `{API_BASE_URL}` | **Gradio Port:** `{GRADIO_PORT}`
            """)

    # ── EVENT HANDLERS ────────────────────────────────────────────────────────
    login_btn.click(fn=login, inputs=[login_username, login_password],
                    outputs=[login_screen, main_app, login_status, user_badge])
    logout_btn.click(fn=logout, outputs=[login_screen, main_app, login_status, user_badge])
    batch_start_btn.click(fn=run_batch_validation, inputs=[batch_limit, batch_concurrency], outputs=batch_output)
    refresh_btn.click(fn=fetch_providers, inputs=[provider_limit, status_filter_dd], outputs=providers_output)
    search_btn.click(fn=search_provider_by_id, inputs=[provider_id_input],
                     outputs=[provider_detail_output, provider_json_output])
    specialty_search_btn.click(fn=fetch_providers_by_specialty, inputs=[specialty_input], outputs=specialty_output)
    flagged_btn.click(fn=fetch_flagged_providers, inputs=[confidence_threshold, flag_keyword], outputs=flagged_output)
    outreach_btn.click(fn=send_outreach_emails, outputs=outreach_output)
    pdf_btn.click(fn=generate_pdf_report, outputs=[report_output, download_file])
    csv_btn.click(fn=export_csv, outputs=[report_output, download_file])
    health_btn.click(fn=check_api_health, outputs=monitoring_output)
    metrics_btn.click(fn=fetch_metrics, outputs=monitoring_output)
    diagnose_btn.click(fn=run_diagnosis, outputs=diagnose_output)


# ============================================================================
# LAUNCH
# ============================================================================
if __name__ == "__main__":
    print("=" * 70)
    print("🏥 PROVIDER DATA VALIDATOR - GRADIO DASHBOARD")
    print("=" * 70)
    print(f"🌐 API Endpoint: {API_BASE_URL}")
    print(f"🎨 Gradio: {GRADIO_HOST}:{GRADIO_PORT}")
    print("=" * 70)
    print("\n⚠️  FastAPI must be running:  uvicorn src.api.app:app --reload --port 8000")
    print("⚠️  For UI batch: Redis + Celery must be running")
    print("⚠️  CLI batch:    python -m src.orchestrator data/providers_sample.csv 8 10")
    print("     → Then View Providers → Status Filter: 'all' → Refresh\n")
    app.launch(server_name="0.0.0.0", server_port=7860, share=False, show_error=True)