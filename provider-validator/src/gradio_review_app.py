# gradio_review_app.py
import os
import time
import requests
from dotenv import load_dotenv
import gradio as gr

load_dotenv()
API_URL = os.environ.get("API_URL", "http://localhost:8000")
API_TOKEN = os.environ.get("API_TOKEN", "")

HEADERS = {"Authorization": f"Bearer {API_TOKEN}"} if API_TOKEN else {}

# Helper: fetch pending providers (paginated)
def fetch_pending(page: int=1, page_size: int=20, q: str=""):
    params = {"page": page, "page_size": page_size}
    if q:
        params["q"] = q
    try:
        r = requests.get(f"{API_URL}/providers/pending", headers=HEADERS, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e), "data": []}

# Helper: fetch single provider
def fetch_provider(provider_id):
    try:
        r = requests.get(f"{API_URL}/providers/{provider_id}", headers=HEADERS, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}

# Helper: fetch provider history
def fetch_history(provider_id):
    try:
        r = requests.get(f"{API_URL}/providers/{provider_id}/history", headers=HEADERS, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}

# Helper: patch review (edits + action)
def submit_review(provider_id, edited_fields: dict, action: str, note: str=""):
    payload = {
        "edited_fields": edited_fields,
        "action": action,   # "approve", "reject", "save" (or "outreach")
        "note": note
    }
    try:
        r = requests.patch(f"{API_URL}/providers/{provider_id}/review", json=payload, headers=HEADERS, timeout=10)
        r.raise_for_status()
        return {"ok": True, "result": r.json()}
    except Exception as e:
        return {"ok": False, "error": str(e), "status_code": getattr(e, "response", None)}

# Gradio callbacks
def load_pending(page=1, q=""):
    resp = fetch_pending(page=page, q=q)
    if "error" in resp:
        return gr.update(value=""), [], "Error: " + resp["error"]
    items = resp.get("data", [])
    # show simple list entries: "ID - name - specialty"
    options = [f"{it['id']} | {it.get('name','-')} | {it.get('specialty','-')}" for it in items]
    return gr.update(value=""), options, f"Page {page} — {len(options)} items"

def on_select_provider(selection):
    if not selection:
        return {}, "", "", []
    provider_id = selection.split("|")[0].strip()
    data = fetch_provider(provider_id)
    if "error" in data:
        return {}, "", f"Error: {data['error']}", []
    # Populate editable form fields
    fields = {
        "id": data.get("id"),
        "name": data.get("name",""),
        "phone": data.get("phone",""),
        "email": data.get("email",""),
        "address": data.get("address",""),
        "specialty": data.get("specialty",""),
        "confidence": data.get("final_confidence", None),
        "validation": data.get("validation_results", {})
    }
    history = fetch_history(provider_id)
    history_text = history if isinstance(history, dict) else {"history": history}
    return fields, f"Provider ID: {provider_id}", "", history_text

def save_edits(fields, note):
    # fields is a dict (Gradio sends it as JSON-like)
    provider_id = fields.get("id")
    edited = {k: fields[k] for k in ("phone","email","address","specialty") if k in fields}
    res = submit_review(provider_id, edited, action="save", note=note or "")
    if res.get("ok"):
        return "Saved successfully."
    return f"Error saving: {res.get('error')}"

def approve_provider(fields, note):
    provider_id = fields.get("id")
    res = submit_review(provider_id, {}, action="approve", note=note or "")
    if res.get("ok"):
        return "Provider approved."
    return f"Error approving: {res.get('error')}"

def reject_provider(fields, note):
    provider_id = fields.get("id")
    res = submit_review(provider_id, {}, action="reject", note=note or "")
    if res.get("ok"):
        return "Provider rejected."
    return f"Error rejecting: {res.get('error')}"

def send_outreach(fields, note):
    provider_id = fields.get("id")
    res = submit_review(provider_id, {}, action="outreach", note=note or "")
    if res.get("ok"):
        return "Outreach queued."
    return f"Error queueing outreach: {res.get('error')}"

# Build Gradio interface
with gr.Blocks(title="Provider Manual Review") as demo:
    gr.Markdown("## Provider Manual Review Dashboard")
    with gr.Row():
        with gr.Column(scale=1):
            search = gr.Textbox(label="Search (name, specialty, NPI...)", placeholder="type and press Load")
            load_btn = gr.Button("Load Pending")
            pending_list = gr.Dropdown(label="Pending providers", choices=[], interactive=True)
            status = gr.Markdown("")
        with gr.Column(scale=2):
            provider_info = gr.JSON(value={}, label="Provider (editable) - edit fields below then Save/Approve")
            # Individual editable fields for nicer UX
            name_field = gr.Textbox(label="Name")
            phone_field = gr.Textbox(label="Phone")
            email_field = gr.Textbox(label="Email")
            address_field = gr.Textbox(label="Address")
            specialty_field = gr.Textbox(label="Specialty")
            confidence_field = gr.Number(label="Confidence", interactive=False)
            note_field = gr.Textbox(label="Reviewer note", lines=3, placeholder="Optional note for history")
            btn_save = gr.Button("Save edits")
            btn_approve = gr.Button("Approve")
            btn_reject = gr.Button("Reject")
            btn_outreach = gr.Button("Send Outreach")
            result_area = gr.Textbox(label="Result", interactive=False)
        with gr.Column(scale=1):
            history_area = gr.JSON(value={}, label="Change History / Validation Results")

    # Wire actions
    load_btn.click(load_pending, inputs=[gr.Number(value=1, visible=False), search], outputs=[search, pending_list, status])
    pending_list.change(on_select_provider, inputs=[pending_list], outputs=[provider_info, status, result_area, history_area])

    # Map JSON provider_info to individual form fields on select
    def map_json_to_fields(js):
        return js.get("name",""), js.get("phone",""), js.get("email",""), js.get("address",""), js.get("specialty",""), js.get("confidence",None)
    provider_info.change(lambda js: map_json_to_fields(js), inputs=[provider_info],
                         outputs=[name_field, phone_field, email_field, address_field, specialty_field, confidence_field])

    # Map field edits back to provider_info JSON
    def collect_to_json(name, phone, email, address, specialty, confidence, old_json):
        new = old_json.copy() if isinstance(old_json, dict) else {}
        new.update({"name": name, "phone": phone, "email": email, "address": address, "specialty": specialty, "final_confidence": confidence})
        return new

    name_field.change(collect_to_json, inputs=[name_field, phone_field, email_field, address_field, specialty_field, confidence_field, provider_info], outputs=[provider_info])
    phone_field.change(collect_to_json, inputs=[name_field, phone_field, email_field, address_field, specialty_field, confidence_field, provider_info], outputs=[provider_info])
    email_field.change(collect_to_json, inputs=[name_field, phone_field, email_field, address_field, specialty_field, confidence_field, provider_info], outputs=[provider_info])
    address_field.change(collect_to_json, inputs=[name_field, phone_field, email_field, address_field, specialty_field, confidence_field, provider_info], outputs=[provider_info])
    specialty_field.change(collect_to_json, inputs=[name_field, phone_field, email_field, address_field, specialty_field, confidence_field, provider_info], outputs=[provider_info])

    btn_save.click(save_edits, inputs=[provider_info, note_field], outputs=[result_area])
    btn_approve.click(approve_provider, inputs=[provider_info, note_field], outputs=[result_area])
    btn_reject.click(reject_provider, inputs=[provider_info, note_field], outputs=[result_area])
    btn_outreach.click(send_outreach, inputs=[provider_info, note_field], outputs=[result_area])

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)
