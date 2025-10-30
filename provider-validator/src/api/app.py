# src/api/app.py
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Body, Request, Response, status, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
import os, csv, json, math, copy, uuid, time, sqlite3, logging
from typing import List, Dict, Any, Optional

# Internal imports
from src.tasks import send_outreach_task
from src.db import fetch_all, init_db, fetch_provider_by_id, fetch_providers_by_specialty
from src.orchestrator import run_batch
from src.agents.outreach_agent import OutreachAgent
from src.reports.pdf_generator import create_report
from src.auth import router as auth_router, get_current_active_user
from src.celery_app import run_batch_task
from src.metrics import HTTP_REQUEST_COUNT, HTTP_REQUEST_LATENCY, metrics_response
from src.logging_config import configure_logging
from src.tracing import init_tracing

# -------------------------------------------------------------------------
# 🧠 App Initialization
# -------------------------------------------------------------------------
app = FastAPI(title="Provider Validator API")
init_tracing(app)
configure_logging()
logger = logging.getLogger(__name__)
app.include_router(auth_router)

# Allow CORS (for Gradio or local testing)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------------------
# 🌱 Global Providers Cache
# -------------------------------------------------------------------------
providers_list: List[Dict[str, Any]] = []
outreach_agent = OutreachAgent(name="outreach_agent")

def load_providers_from_csv(path: str = "data/validated_providers.csv") -> List[Dict[str, Any]]:
    rows = []
    if not os.path.isfile(path):
        return rows
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                r["id"] = int(r.get("id") or 0)
            except Exception:
                pass
            rows.append(r)
    return rows

providers_list = load_providers_from_csv()

# -------------------------------------------------------------------------
# 🚀 Startup (DB initialization + Review Table creation)
# -------------------------------------------------------------------------
@app.on_event("startup")
def startup_event():
    init_db()
    DB_PATH = os.getenv("DB_PATH", "data/providers.db")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # ✅ Ensure review log table exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS provider_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_id INTEGER,
            reviewed_by TEXT,
            status TEXT,
            notes TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

# -------------------------------------------------------------------------
# 🌐 Base Endpoints
# -------------------------------------------------------------------------
@app.get("/")
async def root():
    return {
        "status": "API is running",
        "endpoints": [
            "/providers",
            "/providers/{provider_id}",
            "/providers/specialty/{specialty_name}",
            "/providers/export",
            "/providers/flags",
            "/providers/pending",
            "/providers/{id}/review",
            "/providers/{id}/history",
            "/send-outreach",
            "/reports/pdf",
            "/run-batch",
        ],
    }

# -------------------------------------------------------------------------
# ⚙️ Batch Orchestration (Celery)
# -------------------------------------------------------------------------
@app.post("/run-batch")
async def api_run_batch(
    background_tasks: BackgroundTasks,
    limit: int = 50,
    concurrency: int = 6,
    current_user=Depends(get_current_active_user)
):
    if current_user.role not in ("admin", "runner"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient privileges")
    task = run_batch_task.delay(limit=limit, concurrency=concurrency)
    return {"status": "queued", "task_id": task.id, "limit": limit, "concurrency": concurrency, "started_by": current_user.username}

# -------------------------------------------------------------------------
# 📋 Provider Listing / Export / Specialty
# -------------------------------------------------------------------------
@app.get("/providers")
def api_providers(limit: int = 100):
    rows = fetch_all(limit)
    return {"count": len(rows), "providers": rows}

@app.get("/providers/export")
def export_providers():
    path = os.path.abspath("data/validated_providers.csv")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="CSV file not found. Run /run-batch first.")
    return FileResponse(path, media_type="text/csv", filename="validated_providers.csv")

@app.get("/providers/specialty/{specialty_name}")
def get_by_specialty(specialty_name: str):
    global providers_list
    if not providers_list:
        providers_list = load_providers_from_csv()
    results = [p for p in providers_list if p.get("specialty", "").lower() == specialty_name.lower()]
    if not results:
        try:
            results = fetch_providers_by_specialty(specialty_name)
        except Exception as e:
            logger.warning(f"DB fetch failed: {e}")
    if not results:
        raise HTTPException(status_code=404, detail=f"No providers found for specialty: {specialty_name}")
    return {"count": len(results), "providers": results}

# -------------------------------------------------------------------------
# 🚩 Flags / Pending / Single Provider
# -------------------------------------------------------------------------
@app.get("/providers/flags")
async def get_flagged_providers(
    confidence_below: Optional[float] = Query(0.6),
    flag_contains: Optional[str] = Query(None)
):
    global providers_list
    if not providers_list:
        providers_list = load_providers_from_csv()
    flagged = []
    for p in providers_list:
        try:
            conf = float(p.get("final_confidence", p.get("confidence", 1.0)))
            flags = p.get("flags")
            if isinstance(flags, str):
                flags = json.loads(flags) if flags.strip().startswith("[") else [flags]
            if conf < confidence_below or flags:
                if flag_contains:
                    if any(flag_contains.lower() in f.lower() for f in flags):
                        flagged.append(p)
                else:
                    flagged.append(p)
        except Exception:
            continue
    return {"count": len(flagged), "providers": flagged}

@app.get("/providers/pending")
async def get_pending_providers(confidence_below: float = 0.6, current_user=Depends(get_current_active_user)):
    query = f"""
        SELECT * FROM providers
        WHERE COALESCE(final_confidence, confidence, 1.0) < {confidence_below}
           OR (flags IS NOT NULL AND jsonb_array_length(flags) > 0)
    """
    rows = fetch_all(query)
    return {
        "count": len(rows),
        "providers": rows,
        "filters": {"confidence_below": confidence_below}
    }

@app.get("/providers/{id}")
async def get_provider_details(id: int):
    global providers_list
    if not providers_list:
        providers_list = load_providers_from_csv()
    provider = next((p for p in providers_list if int(p.get("id", -1)) == id), None)
    if not provider:
        try:
            provider = fetch_provider_by_id(id)
        except Exception as e:
            logger.warning(f"DB lookup failed for provider {id}: {e}")
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider {id} not found")
    return provider

# -------------------------------------------------------------------------
# 🩺 Review + History Endpoints
# -------------------------------------------------------------------------
@app.patch("/providers/{id}/review")
async def review_provider(id: int, body: Dict[str, Any] = Body(...), current_user=Depends(get_current_active_user)):
    DB_PATH = os.getenv("DB_PATH", "data/providers.db")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id FROM providers WHERE id=?", (id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Provider not found")
    status_val = body.get("status", "needs_update")
    notes = body.get("notes", "")
    updated_fields = body.get("updated_fields", {})
    if updated_fields:
        set_clause = ", ".join([f"{k}=?" for k in updated_fields.keys()])
        cur.execute(f"UPDATE providers SET {set_clause} WHERE id=?", [*updated_fields.values(), id])
    cur.execute("""
        INSERT INTO provider_reviews (provider_id, reviewed_by, status, notes, timestamp)
        VALUES (?, ?, ?, ?, datetime('now'))
    """, (id, current_user.username, status_val, notes))
    conn.commit()
    conn.close()
    return {"status": "review_saved", "provider_id": id, "reviewed_by": current_user.username, "new_status": status_val, "notes": notes}

@app.get("/providers/{id}/history")
async def provider_history(id: int):
    DB_PATH = os.getenv("DB_PATH", "data/providers.db")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT reviewed_by, status, notes, timestamp FROM provider_reviews
        WHERE provider_id=? ORDER BY timestamp DESC
    """, (id,))
    rows = cur.fetchall()
    conn.close()
    history = [{"reviewed_by": r[0], "status": r[1], "notes": r[2], "timestamp": r[3]} for r in rows]
    if not history:
        raise HTTPException(status_code=404, detail=f"No history found for provider {id}")
    return {"provider_id": id, "history_count": len(history), "history": history}

# -------------------------------------------------------------------------
# 📬 Outreach + Verify + Reports
# -------------------------------------------------------------------------
@app.post("/send-outreach")
async def send_outreach():
    global providers_list
    if not providers_list:
        providers_list = load_providers_from_csv()
    results = []
    for p in providers_list:
        try:
            final_confidence = float(p.get("final_confidence", p.get("confidence", 0) or 0))
        except Exception:
            final_confidence = 0.0
        flags = p.get("flags")
        if isinstance(flags, str):
            try:
                flags = json.loads(flags)
            except Exception:
                flags = []
        if final_confidence < 0.6 or flags:
            try:
                email = await outreach_agent.run(p)
            except TypeError:
                email = outreach_agent.run(p)
            if email:
                results.append({"id": p.get("id"), **email})
    return {"emails_generated": len(results), "details": results}

@app.get("/reports/pdf")
def generate_pdf_report():
    os.makedirs("data/reports", exist_ok=True)
    pdf_path = create_report(providers_list)
    if not os.path.isfile(pdf_path):
        raise HTTPException(status_code=500, detail="PDF generation failed")
    return FileResponse(pdf_path, media_type="application/pdf", filename="provider_report.pdf")

@app.get("/verify")
async def verify(provider_id: int):
    conn = sqlite3.connect(os.getenv("DB_PATH", "data/providers.db"))
    cur = conn.cursor()
    cur.execute("""
      UPDATE outreach_logs SET send_status='verified'
      WHERE provider_id=? ORDER BY id DESC LIMIT 1
    """, (provider_id,))
    conn.commit()
    conn.close()
    return {"status": "verified", "provider_id": provider_id}

# -------------------------------------------------------------------------
# 📈 Metrics + Observability
# -------------------------------------------------------------------------
@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start_ts = time.time()
    path_label = request.scope.get("route").path if request.scope.get("route") else request.url.path
    logger.info(f"request_start {path_label}")
    response = await call_next(request)
    latency = time.time() - start_ts
    HTTP_REQUEST_COUNT.labels(method=request.method, path=path_label, status=str(response.status_code)).inc()
    HTTP_REQUEST_LATENCY.labels(method=request.method, path=path_label).observe(latency)
    logger.info(f"request_end {path_label} {round(latency, 4)}s")
    return response

@app.get("/metrics")
async def metrics():
    data, content_type = metrics_response()
    return Response(content=data, media_type=content_type)
