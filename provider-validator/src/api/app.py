# src/api/app.py — FULLY CONVERTED: zero sqlite3 imports, all DB via src.db
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Body, Request, Response, status, Query
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os, csv, json, uuid, time, logging
from typing import List, Dict, Any, Optional

# ── Internal imports ──────────────────────────────────────────────────────────
from src.tasks import send_outreach_task
from src.db import fetch_all, init_db, fetch_provider_by_id, fetch_providers_by_specialty, engine, IS_POSTGRES
from src.orchestrator import run_batch
from src.agents.outreach_agent import OutreachAgent
from src.reports.pdf_generator import create_report
from src.auth import router as auth_router, get_current_active_user
from src.celery_app import run_batch_task
from src.metrics import HTTP_REQUEST_COUNT, HTTP_REQUEST_LATENCY, metrics_response
from src.logging_config import configure_logging
from src.tracing import init_tracing
from sqlalchemy import text   # for review/history/verify endpoints

# ─────────────────────────────────────────────────────────────────────────────
# App Initialization
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(title="Provider Validator API")
init_tracing(app)
configure_logging()
logger = logging.getLogger(__name__)
app.include_router(auth_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

outreach_agent = OutreachAgent(name="outreach_agent")


# ─────────────────────────────────────────────────────────────────────────────
# Data Helpers
# ─────────────────────────────────────────────────────────────────────────────

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


def get_providers_from_db(limit: int = 500, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Read providers from DB with optional status filtering.

    Status mapping (Gradio dropdown → DB WHERE clause):
      "all" / None  → no filter, return everything
      "validated"   → WHERE status = 'confirmed'
      "flagged"     → WHERE status = 'manual_review'
      "pending"     → WHERE confidence = 0 OR status = 'pending'
      "processing"  → WHERE status = 'processing'
    """
    try:
        if not status_filter or status_filter in ("all", "default"):
            return fetch_all("SELECT * FROM providers LIMIT ?", limit)

        elif status_filter == "validated":
            return fetch_all("SELECT * FROM providers WHERE status = 'confirmed' LIMIT ?", limit)

        elif status_filter == "flagged":
            return fetch_all("SELECT * FROM providers WHERE status = 'manual_review' LIMIT ?", limit)

        elif status_filter == "pending":
            return fetch_all("""
                SELECT * FROM providers
                WHERE status = 'pending'
                   OR CAST(COALESCE(confidence, 0) AS FLOAT) = 0
                LIMIT ?
            """, limit)

        elif status_filter == "processing":
            return fetch_all("SELECT * FROM providers WHERE status = 'processing' LIMIT ?", limit)

        else:
            return fetch_all("SELECT * FROM providers WHERE status = ? LIMIT ?", status_filter, limit)

    except Exception as e:
        logger.warning(f"DB fetch failed (status={status_filter}): {e}")
        return []


def get_all_providers_merged(limit: int = 500, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Primary source: DB (written by orchestrator via insert_provider).
    Fallback/merge: validated_providers.csv (written at end of orchestrator run).
    DB records take priority. When a status filter is active, only DB rows
    are returned (CSV has no status column).
    """
    db_rows  = get_providers_from_db(limit, status_filter)
    csv_rows = load_providers_from_csv()

    if not db_rows and not csv_rows:
        return []

    if status_filter and status_filter not in ("all", "default", None):
        return db_rows[:limit]

    merged: Dict[Any, Dict] = {}
    for p in csv_rows:
        key = p.get("id") or p.get("source_id") or p.get("npi") or id(p)
        merged[key] = p
    for p in db_rows:
        key = p.get("id") or p.get("source_id") or p.get("npi") or id(p)
        merged[key] = p

    return list(merged.values())[:limit]


def _status_label(s: Optional[str]) -> str:
    return {
        None: "All", "all": "All", "default": "All",
        "validated":  "Confirmed (status=confirmed)",
        "flagged":    "Flagged (status=manual_review)",
        "pending":    "Pending (confidence=0)",
        "processing": "Processing",
    }.get(s, f"status={s}")


def _status_breakdown() -> Dict[str, int]:
    try:
        rows = fetch_all("SELECT status, COUNT(*) as cnt FROM providers GROUP BY status")
        return {r.get("status", "null"): r.get("cnt", 0) for r in rows}
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Startup — init DB tables via SQLAlchemy (NOT sqlite3)
# ─────────────────────────────────────────────────────────────────────────────
@app.on_event("startup")
def startup_event():
    """
    FIX: Old code called sqlite3.connect(DB_PATH) here to create
    provider_reviews table. That only worked for SQLite and bypassed
    the shared connection pool.

    NEW: init_db() from src.db handles ALL table creation for both
    SQLite and PostgreSQL using the shared SQLAlchemy engine.
    """
    init_db()   # creates providers, provider_reviews, outreach_logs if missing

    try:
        count = fetch_all("SELECT COUNT(*) as cnt FROM providers")
        cnt   = count[0].get("cnt", 0) if count else 0
        print(f"[startup] ✅ providers: {cnt} records")
        for s, c in _status_breakdown().items():
            print(f"[startup]    '{s}': {c} records")
    except Exception as e:
        print(f"[startup] Warning: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Root
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {"status": "API is running", "db": "postgresql" if IS_POSTGRES else "sqlite"}


# ─────────────────────────────────────────────────────────────────────────────
# Batch
# ─────────────────────────────────────────────────────────────────────────────
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
    return {"status": "queued", "task_id": task.id, "limit": limit,
            "concurrency": concurrency, "started_by": current_user.username}


# ─────────────────────────────────────────────────────────────────────────────
# /providers — with status filter
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/providers")
def api_providers(
    limit: int = 100,
    status: Optional[str] = Query(default=None, description=(
        "Filter: all=everything, validated=confirmed, "
        "flagged=manual_review, pending=zero-confidence"
    ))
):
    providers = get_all_providers_merged(limit, status_filter=status)
    return {
        "count":          len(providers),
        "providers":      providers,
        "filter_applied": _status_label(status),
        "debug": {
            "db_total":         len(get_providers_from_db(limit)),
            "csv_total":        len(load_providers_from_csv()),
            "status_breakdown": _status_breakdown(),
            "is_postgres":      IS_POSTGRES,
            "csv_exists":       os.path.isfile("data/validated_providers.csv"),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/providers/export")
def export_providers():
    path = os.path.abspath("data/validated_providers.csv")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="CSV not found. Run batch first.")
    return FileResponse(path, media_type="text/csv", filename="validated_providers.csv")


# ─────────────────────────────────────────────────────────────────────────────
# Specialty
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/providers/specialty/{specialty_name}")
def get_by_specialty(specialty_name: str):
    results = [
        p for p in get_all_providers_merged(500)
        if str(p.get("specialty", "")).lower() == specialty_name.lower()
    ]
    if not results:
        try:
            results = fetch_providers_by_specialty(specialty_name)
        except Exception as e:
            logger.warning(f"Specialty fetch failed: {e}")
    if not results:
        raise HTTPException(status_code=404, detail=f"No providers for: {specialty_name}")
    return {"count": len(results), "providers": results}


# ─────────────────────────────────────────────────────────────────────────────
# Flags
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/providers/flags")
async def get_flagged_providers(
    confidence_below: Optional[float] = Query(0.6),
    flag_contains:    Optional[str]   = Query(None)
):
    flagged = []
    for p in get_all_providers_merged(500):
        try:
            raw  = p.get("final_confidence", p.get("confidence", 1.0))
            conf = float(raw) if raw not in (None, "", "None") else 1.0
        except Exception:
            conf = 1.0
        flags = p.get("flags")
        if isinstance(flags, str) and flags.strip():
            try:
                import ast as _ast; flags = _ast.literal_eval(flags)
            except Exception:
                try:    flags = json.loads(flags)
                except: flags = [flags]
        if not isinstance(flags, list):
            flags = []
        is_low  = conf < confidence_below
        has_flg = len(flags) > 0
        if not (is_low or has_flg):
            continue
        if flag_contains:
            kw = flag_contains.lower()
            if not any(kw in str(f).lower() for f in flags) and not is_low:
                continue
        flagged.append(p)
    return {"count": len(flagged), "providers": flagged}


# ─────────────────────────────────────────────────────────────────────────────
# Pending
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/providers/pending")
async def get_pending_providers(confidence_below: float = 0.6, current_user=Depends(get_current_active_user)):
    pending = []
    for p in get_all_providers_merged(500):
        try:
            raw  = p.get("final_confidence", p.get("confidence", 1.0))
            conf = float(raw) if raw not in (None, "", "None") else 1.0
        except Exception:
            conf = 1.0
        has_flags = bool(p.get("flags") and p.get("flags") not in ("[]", "null", "None", ""))
        if conf < confidence_below or has_flags:
            pending.append(p)
    return {"count": len(pending), "providers": pending, "filters": {"confidence_below": confidence_below}}


# ─────────────────────────────────────────────────────────────────────────────
# Single provider
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/providers/{id}")
async def get_provider_details(id: int):
    provider = next(
        (p for p in get_all_providers_merged(500)
         if int(p.get("id", -1)) == id or int(p.get("source_id", -1)) == id),
        None
    )
    if not provider:
        try:    provider = fetch_provider_by_id(id)
        except Exception as e: logger.warning(f"DB lookup failed for {id}: {e}")
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider {id} not found")
    return provider


# ─────────────────────────────────────────────────────────────────────────────
# Review + History
# FIX: was using sqlite3.connect(DB_PATH) directly — now uses SQLAlchemy engine
# ─────────────────────────────────────────────────────────────────────────────
@app.patch("/providers/{id}/review")
async def review_provider(id: int, body: Dict[str, Any] = Body(...), current_user=Depends(get_current_active_user)):
    """
    FIX: Old code used sqlite3.connect(DB_PATH) with ? placeholders.
    Now uses SQLAlchemy engine with :name params — works for both DBs.
    """
    with engine.begin() as conn:
        row = conn.execute(text("SELECT id FROM providers WHERE id = :id"), {"id": id}).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Provider not found")

        status_val     = body.get("status", "needs_update")
        notes          = body.get("notes", "")
        updated_fields = body.get("updated_fields", {})

        if updated_fields:
            set_clause = ", ".join([f"{k} = :{k}" for k in updated_fields.keys()])
            conn.execute(
                text(f"UPDATE providers SET {set_clause} WHERE id = :id"),
                {**updated_fields, "id": id}
            )

        conn.execute(text("""
            INSERT INTO provider_reviews (provider_id, reviewed_by, status, notes)
            VALUES (:pid, :by, :st, :notes)
        """), {"pid": id, "by": current_user.username, "st": status_val, "notes": notes})

    return {"status": "review_saved", "provider_id": id,
            "reviewed_by": current_user.username, "new_status": status_val, "notes": notes}


@app.get("/providers/{id}/history")
async def provider_history(id: int):
    """
    FIX: Old code used sqlite3.connect(DB_PATH). Now uses SQLAlchemy.
    """
    rows = fetch_all("""
        SELECT reviewed_by, status, notes, timestamp
        FROM provider_reviews WHERE provider_id = ?
        ORDER BY timestamp DESC
    """, id)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No history for provider {id}")
    return {"provider_id": id, "history_count": len(rows), "history": rows}


# ─────────────────────────────────────────────────────────────────────────────
# Outreach
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/send-outreach")
async def send_outreach():
    results = []
    for p in get_all_providers_merged(500):
        try:    fc = float(p.get("final_confidence", p.get("confidence", 0) or 0))
        except: fc = 0.0
        flags = p.get("flags")
        if isinstance(flags, str):
            try:    flags = json.loads(flags)
            except: flags = []
        if not isinstance(flags, list):
            flags = []
        if fc < 0.6 or flags:
            try:    email = await outreach_agent.run(p)
            except TypeError: email = outreach_agent.run(p)
            if email:
                results.append({"id": p.get("id"), **email})
    return {"emails_generated": len(results), "details": results}


# ─────────────────────────────────────────────────────────────────────────────
# PDF Report
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/reports/pdf")
def generate_pdf_report():
    os.makedirs("data/reports", exist_ok=True)
    pdf_path = create_report(get_all_providers_merged(500))
    if not os.path.isfile(pdf_path):
        raise HTTPException(status_code=500, detail="PDF generation failed")
    return FileResponse(pdf_path, media_type="application/pdf", filename="provider_report.pdf")


# ─────────────────────────────────────────────────────────────────────────────
# Verify
# FIX: Old code used sqlite3 with ORDER BY/LIMIT in UPDATE (not valid in SQLite)
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/verify")
async def verify(provider_id: int):
    """
    FIX: Old code: sqlite3 UPDATE ... ORDER BY ... LIMIT — crashes on SQLite.
    New code: uses dbutils.mark_provider_verified which does a safe subquery.
    Works on both PostgreSQL and SQLite.
    """
    from src.dbutils import mark_provider_verified
    success = mark_provider_verified(provider_id, source="email_link")
    return {"status": "verified" if success else "not_found", "provider_id": provider_id}


# ─────────────────────────────────────────────────────────────────────────────
# Metrics + Observability
# ─────────────────────────────────────────────────────────────────────────────
@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    start_ts   = time.time()
    path_label = request.scope.get("route").path if request.scope.get("route") else request.url.path
    response   = await call_next(request)
    latency    = time.time() - start_ts
    HTTP_REQUEST_COUNT.labels(method=request.method, path=path_label, status=str(response.status_code)).inc()
    HTTP_REQUEST_LATENCY.labels(method=request.method, path=path_label).observe(latency)
    return response


@app.get("/metrics")
async def metrics():
    data, content_type = metrics_response()
    return Response(content=data, media_type=content_type)