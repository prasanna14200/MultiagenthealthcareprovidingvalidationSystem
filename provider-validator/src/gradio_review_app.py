# src/gradio_review_app.py
import os
import requests
import gradio as gr
from dotenv import load_dotenv

load_dotenv()
API_URL = os.environ.get("API_URL", "http://localhost:8000")
API_TOKEN = os.environ.get("API_TOKEN", "")
HEADERS = {"Authorization": f"Bearer {API_TOKEN}"} if API_TOKEN else {}

# -----------------------------
# Backend helpers
# -----------------------------
def fetch_pending(page: int = 1, page_size: int = 20, q: str = "", status: str = "Pending"):
    params = {"page": page, "page_size": page_size}
    if q:
        params["q"] = q
    # your backend currently ignores 'status' param but we keep it for future
    try:
        r = requests.get(f"{API_URL}/providers/pending", headers=HEADERS, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        items = data.get("providers") or data.get("data") or []
        # ensure list
        return items if isinstance(items, list) else []
    except Exception as e:
        return {"error": str(e)}

def fetch_provider(provider_id):
    try:
        r = requests.get(f"{API_URL}/providers/{provider_id}", headers=HEADERS, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def fetch_history(provider_id):
    try:
        r = requests.get(f"{API_URL}/providers/{provider_id}/history", headers=HEADERS, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def submit_review(provider_id, edited_fields: dict, action: str, note: str = ""):
    payload = {"edited_fields": edited_fields, "action": action, "note": note}
    try:
        r = requests.patch(f"{API_URL}/providers/{provider_id}/review", json=payload, headers=HEADERS, timeout=10)
        r.raise_for_status()
        return {"ok": True, "result": r.json()}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# -----------------------------
# Gradio callbacks
# -----------------------------
def load_pending(page=1, q="", status="Pending"):
    """
    Returns three outputs: search_value_update, dropdown_update, status_message
    Use gr.update(...) to update components so Gradio preprocessing won't reject values.
    """
    resp = fetch_pending(page=page, page_size=50, q=q, status=status)
    if isinstance(resp, dict) and "error" in resp:
        return gr.update(value=q), gr.update(choices=[], value=None), f"⚠️ Error loading providers: {resp['error']}"

    items = resp  # should be a list
    options = [f"{p['id']} | {p.get('name','-')} | {p.get('specialty','-')}" for p in items]

    if not options:
        return gr.update(value=q), gr.update(choices=[], value=None), "ℹ️ No pending providers found."

    # Update dropdown choices and set value to None (no selection) to avoid preprocess rejection
    return gr.update(value=q), gr.update(choices=options, value=None), f"✅ Loaded {len(options)} pending providers."

def on_select_provider(selection):
    # defensive: selection may be list or str
    if not selection:
        return {}, "", "⚠️ No provider selected.", []
    if isinstance(selection, list):
        selection = selection[0] if selection else ""
    if not selection or "|" not in selection:
        return {}, "", "⚠️ Invalid selection.", []
    provider_id = selection.split("|")[0].strip()
    if not provider_id.isdigit():
        return {}, "", "⚠️ Invalid provider id.", []

    data = fetch_provider(provider_id)
    if isinstance(data, dict) and "error" in data:
        return {}, "", f"⚠️ Error fetching provider: {data['error']}", []

    # Build editable fields
    fields = {
        "id": data.get("id"),
        "name": data.get("name", ""),
        "phone": data.get("phone", ""),
        "email": data.get("email", ""),
        "address": data.get("address", ""),
        "specialty": data.get("specialty", ""),
        "confidence": data.get("final_confidence", None),
        "flags": data.get("flags", []),
    }

    history = fetch_history(provider_id)
    history_text = history if isinstance(history, dict) else {"history": history}

    return fields, f"👤 Provider ID: {provider_id}", "", history_text

def save_edits(fields, note):
    pid = fields.get("id") if isinstance(fields, dict) else None
    if not pid:
        return "⚠️ No provider selected."
    edited = {k: fields[k] for k in ("phone", "email", "address", "specialty") if fields.get(k)}
    res = submit_review(pid, edited, action="save", note=note or "")
    return "💾 Saved successfully!" if res.get("ok") else f"❌ Error: {res.get('error')}"

def approve_provider(fields, note):
    pid = fields.get("id") if isinstance(fields, dict) else None
    if not pid:
        return "⚠️ No provider selected."
    res = submit_review(pid, {}, "approve", note or "")
    return "✅ Provider approved." if res.get("ok") else f"❌ Error: {res.get('error')}"

def reject_provider(fields, note):
    pid = fields.get("id") if isinstance(fields, dict) else None
    if not pid:
        return "⚠️ No provider selected."
    res = submit_review(pid, {}, "reject", note or "")
    return "🚫 Provider rejected." if res.get("ok") else f"❌ Error: {res.get('error')}"

def send_outreach(fields, note):
    pid = fields.get("id") if isinstance(fields, dict) else None
    if not pid:
        return "⚠️ No provider selected."
    res = submit_review(pid, {}, "outreach", note or "")
    return "📧 Outreach queued." if res.get("ok") else f"❌ Error: {res.get('error')}"

# -----------------------------
# Gradio UI
# -----------------------------
with gr.Blocks(
    title="Provider Review Dashboard",
    theme=gr.themes.Soft(primary_hue="indigo", secondary_hue="blue", neutral_hue="slate"),
    css="""
    #status {font-weight: bold; color: #1E40AF;}
    .gr-button {border-radius: 10px !important; font-weight: 600;}
    .gr-textbox, .gr-dropdown, .gr-number {border-radius: 8px !important;}
    body {background: linear-gradient(135deg, #eef2ff, #ffffff);}
    """
) as demo:
    gr.Markdown("# 🌈 Provider Manual Review Dashboard")
    gr.Markdown("Review, edit and approve flagged or low-confidence providers.")

    with gr.Row():
        with gr.Column(scale=1):
            search = gr.Textbox(label="🔍 Search", placeholder="Name, specialty or NPI...")
            review_choices = ["Pending", "Flagged", "Low Confidence", "All"]
            status_dropdown = gr.Dropdown(label="Filter by Status", choices=review_choices, value="Pending", allow_custom_value=False)
            load_btn = gr.Button("🔄 Load Providers", variant="primary")
            pending_list = gr.Dropdown(label="Select Provider", choices=[], interactive=True, multiselect=False, allow_custom_value=True)
            status = gr.Markdown("", elem_id="status")

        with gr.Column(scale=2):
            provider_info = gr.JSON(value={}, label="Provider Record (editable)")
            name_field = gr.Textbox(label="Name")
            phone_field = gr.Textbox(label="Phone")
            email_field = gr.Textbox(label="Email")
            address_field = gr.Textbox(label="Address")
            specialty_field = gr.Textbox(label="Specialty")
            confidence_field = gr.Number(label="Final Confidence", interactive=False)
            note_field = gr.Textbox(label="Reviewer Note", lines=3)
            with gr.Row():
                btn_save = gr.Button("💾 Save", variant="secondary")
                btn_approve = gr.Button("✅ Approve", variant="primary")
                btn_reject = gr.Button("🚫 Reject", variant="stop")
                btn_outreach = gr.Button("📧 Outreach", variant="secondary")
            result_area = gr.Textbox(label="Result", interactive=False)

        with gr.Column(scale=1):
            history_area = gr.JSON(value={}, label="📜 Change History / Flags")

    # Bind actions
    load_btn.click(fn=load_pending, inputs=[gr.Number(value=1, visible=False), search, status_dropdown], outputs=[search, pending_list, status])
    pending_list.change(fn=on_select_provider, inputs=[pending_list], outputs=[provider_info, status, result_area, history_area])
    btn_save.click(save_edits, inputs=[provider_info, note_field], outputs=[result_area])
    btn_approve.click(approve_provider, inputs=[provider_info, note_field], outputs=[result_area])
    btn_reject.click(reject_provider, inputs=[provider_info, note_field], outputs=[result_area])
    btn_outreach.click(send_outreach, inputs=[provider_info, note_field], outputs=[result_area])

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)
