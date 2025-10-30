# src/api/app.py
from fastapi import FastAPI, HTTPException, BackgroundTasks,Depends
from fastapi.responses import FileResponse
import csv
import os
from typing import List, Dict, Any
from src.tasks import send_outreach_task
from src.db import fetch_all, init_db,fetch_provider_by_id,fetch_providers_by_specialty
from src.orchestrator import run_batch
from src.agents.outreach_agent import OutreachAgent
from src.reports.pdf_generator import create_report  # absolute import
from src.auth import router as auth_router, get_current_active_user
import sqlite3, os
from src.api.routes.webhooks import router as webhook_router
from src.api.routes.verify import verify as verify
from src.logging_config import configure_logging
import logging
import uuid
from fastapi import Request
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from src.metrics import HTTP_REQUEST_COUNT, HTTP_REQUEST_LATENCY, metrics_response


app = FastAPI(title="Provider Validator API")

from src.tracing import init_tracing
init_tracing(app)


configure_logging()
logger = logging.getLogger(__name__)
app.include_router(auth_router)  # mounts /token
#app.include_router(webhook_router)
#app.include_router(verify.router)
#app.include_router(webhooks.router)





# Global cache of providers loaded from CSV
providers_list: List[Dict[str, Any]] = []
outreach_agent = OutreachAgent(name="outreach_agent")





def load_providers_from_csv(path: str = "data/validated_providers.csv") -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not os.path.isfile(path):
        return rows
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                r["id"] = int(r.get("id") or 0)
            except Exception:
                r["id"] = r.get("id")
            rows.append(r)
    return rows


# Load providers on module import (safe fallback)
providers_list = load_providers_from_csv()


@app.on_event("startup")
def startup_event():
    init_db()


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
            "/send-outreach",
            "/reports/pdf",
            "/run-batch"
        ],
    }

# @app.post("/run-batch")
# async def api_run_batch(background_tasks: BackgroundTasks, limit: int = 50, concurrency: int = 6,current_user = Depends(get_current_active_user)):
#     """
#     Kick off the batch run in the background.
#     Query params:
#       - limit: how many rows to process (default 50)
#       - concurrency: concurrency level for run_batch
#     """
#      # optionally check role:
#     if current_user.role not in ("admin", "runner"):
#         # only admins or runner roles allowed to start batch
#         from fastapi import HTTPException, status
#         raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient privileges")
#     # run_batch will write validated_providers.csv when done
#     background_tasks.add_task(run_batch, "data/providers_sample.csv",6,concurrency=concurrency, limit=limit)
#     return {"status": "started", "limit": limit, "concurrency": concurrency,"started_by": current_user.username}



 # instaed In your src/api/app.py, update the /run-batch endpoint so it triggers Celery instead of FastAPI BackgroundTasks

from fastapi import BackgroundTasks, Depends, HTTPException, status
from src.auth import get_current_active_user
from src.celery_app import run_batch_task

@app.post("/run-batch")
async def api_run_batch(
    background_tasks: BackgroundTasks,
    limit: int = 50,
    concurrency: int = 6,
    current_user = Depends(get_current_active_user)
):
    if current_user.role not in ("admin", "runner"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient privileges"
        )
    
    # ✅ Proper Celery call
    task = run_batch_task.delay(limit=limit, concurrency=concurrency)

    # ✅ Always return response immediately
    return {
        "status": "queued",
        "task_id": task.id,
        "limit": limit,
        "concurrency": concurrency,
        "started_by": current_user.username
    }



@app.get("/providers")
def api_providers(limit: int = 100):
    rows = fetch_all(limit)
    return {"count": len(rows), "providers": rows}


@app.get("/providers/export")
def export_providers():
    export_path = os.path.abspath("data/validated_providers.csv")
    if not os.path.isfile(export_path):
        raise HTTPException(status_code=404, detail="CSV file not found. Run /run-batch first.")
    return FileResponse(export_path, media_type="text/csv", filename="validated_providers.csv")




from typing import Optional
from fastapi import Query, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
import json, math, copy

@app.get("/providers/flags")
async def get_flagged_providers(
    confidence_below: Optional[float] = Query(default=None, description="Filter providers below this confidence score"),
    flag_contains: Optional[str] = Query(default=None, description="Filter providers containing this flag keyword")
):
    """
    Return all providers that have flags or low confidence.
    Fully sanitizes all records to avoid 422 Unprocessable Entity.
    """
    global providers_list

    # Default value manually (because Query(None) default can't be float)
    if confidence_below is None:
        confidence_below = 0.6

    if not providers_list:
        providers_list = load_providers_from_csv()
    # ✅ FIX: If CSV doesn't exist, try to load from database
    if not providers_list:
        try:
            db_rows = fetch_all(limit=1000)
            if db_rows:
                providers_list = db_rows
        except Exception as e:
            logger.warning(f"Could not fetch from database: {e}")
    
    # ✅ FIX: Return informative message if no data available
    if not providers_list:
        return JSONResponse(
            status_code=200,
            content={
                "count": 0,
                "providers": [],
                "filters": {"confidence_below": confidence_below, "flag_contains": flag_contains},
                "message": "No provider data available. Please run /run-batch first or add providers to the database."
            }
        )

    flagged = []

    for raw_p in providers_list:
        try:
            p = copy.deepcopy(raw_p)

            # Parse confidence safely
            conf_val = p.get("final_confidence") or p.get("confidence") or 1.0
            try:
                conf_val = float(conf_val)
                if math.isnan(conf_val):
                    conf_val = 1.0
            except Exception:
                conf_val = 1.0
            p["final_confidence"] = round(conf_val, 3)

            # Parse flags safely
            flags = p.get("flags")
            if isinstance(flags, str):
                try:
                    flags = json.loads(flags)
                except Exception:
                    flags = [flags.strip()] if flags.strip() else []
            if not isinstance(flags, list):
                flags = [str(flags)] if flags else []
            p["flags"] = [str(f) for f in flags if f]

            # Apply filters
            low_conf = conf_val < confidence_below
            has_flag = bool(flags)

            if has_flag or low_conf:
                if flag_contains:
                    if any(flag_contains.lower() in f.lower() for f in flags):
                        flagged.append(p)
                else:
                    flagged.append(p)

        except Exception as e:
            print(f"[WARN] Skipping bad row: {e}")
            continue

    # JSON-safe cleanup
    clean_flagged = []
    for p in flagged:
        safe_p = {k: (v if isinstance(v, (float, int, str, bool)) or v is None else str(v)) for k, v in p.items()}
        clean_flagged.append(safe_p)

    result = {
        "count": len(clean_flagged),
        "providers": clean_flagged,
        "filters": {"confidence_below": confidence_below, "flag_contains": flag_contains},
    }

    return JSONResponse(content=jsonable_encoder(result))



@app.get("/providers/{provider_id}")
def get_provider(provider_id: int):
    """Get a single provider by ID - tries CSV cache first, then database."""
    global providers_list
    
    # ✅ FIX: Try CSV cache first
    if not providers_list:
        providers_list = load_providers_from_csv()
    
    provider = next((p for p in providers_list if int(p.get("id", -1)) == provider_id), None)
    
    # ✅ FIX: If not found in CSV, try database
    if not provider:
        try:
            provider = fetch_provider_by_id(provider_id)
        except Exception as e:
            logger.warning(f"Database fetch failed: {e}")
    
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider


@app.post("/providers/{provider_id}/send-outreach")
async def send_outreach(provider_id: int, current_user=Depends(get_current_active_user)):
    DB_PATH = os.getenv("DB_PATH", "data/providers.db")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, name, phone, email, address FROM providers WHERE id=?", (provider_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Provider not found")

    payload = {"id": row[0], "name": row[1], "phone": row[2], "email": row[3], "address": row[4]}
    task = send_outreach_task.delay(payload)
    return {"status": "queued", "task_id": task.id}


@app.get("/providers/specialty/{specialty_name}")
def get_by_specialty(specialty_name: str):
    """Get providers by specialty - tries CSV cache first, then database."""
    global providers_list
    
    # ✅ FIX: Try CSV cache first
    if not providers_list:
        providers_list = load_providers_from_csv()
    
    results = [p for p in providers_list if p.get("specialty", "").lower() == specialty_name.lower()]
    
    # ✅ FIX: If not found in CSV, try database
    if not results:
        try:
            results = fetch_providers_by_specialty(specialty_name)
        except Exception as e:
            logger.warning(f"Database fetch failed: {e}")
    
    if not results:
        raise HTTPException(status_code=404, detail=f"No providers found for specialty: {specialty_name}")
    return {"count": len(results), "providers": results}




@app.post("/send-outreach")
async def send_outreach():
    """
    Generate outreach emails for flagged/low-confidence providers.
    Returns generated email drafts (does not actually send).
    """
    global providers_list
    if not providers_list:
        providers_list = load_providers_from_csv()

    results = []
    for p in providers_list:
        # parse final_confidence and flags robustly
        try:
            final_confidence = float(p.get("final_confidence", p.get("confidence", 0) or 0))
        except Exception:
            final_confidence = 0.0
        flags = p.get("flags")
        if isinstance(flags, str):
            try:
                import json
                flags = json.loads(flags)
            except Exception:
                flags = []

        if final_confidence < 0.6 or flags:
            # outreach_agent.run is async and should return an object (subject/body/email) or None
            try:
                email = await outreach_agent.run(p)
            except TypeError:
                # some older outreach_agent implementations may expose a sync method; support both
                email = outreach_agent.run(p)
            if email:
                results.append({"id": p.get("id"), **email})

    return {"emails_generated": len(results), "details": results}

@app.get("/reports/pdf")
def generate_pdf_report():
    """Generate a PDF report of validated providers."""
    from src.reports.pdf_generator import create_report

    os.makedirs("data/reports", exist_ok=True)
    pdf_path = create_report(providers_list)

    if not os.path.isfile(pdf_path):
        raise HTTPException(status_code=500, detail="PDF report generation failed")

    return FileResponse(pdf_path, media_type="application/pdf", filename="provider_report.pdf")



@app.get("/verify")
async def verify(provider_id: int):
    conn = sqlite3.connect(os.getenv("DB_PATH", "data/providers.db"))
    cur = conn.cursor()
    cur.execute("""
      UPDATE outreach_logs
      SET send_status='verified'
      WHERE provider_id=?
      ORDER BY id DESC
      LIMIT 1
    """, (provider_id,))
    conn.commit()
    conn.close()
    return {"status": "verified", "provider_id": provider_id}




import time
import uuid
import logging
from fastapi import Request, Response
from src.metrics import HTTP_REQUEST_COUNT, HTTP_REQUEST_LATENCY
from src.logging_config import configure_logging

# ensure logger configured (call once at app startup)
configure_logging()
logger = logging.getLogger(__name__)

def _get_route_template(request: Request) -> str:
    # Try to use route template if available to avoid high cardinality (e.g. /providers/{id})
    route = request.scope.get("route")
    if route is not None and hasattr(route, "path"):
        return route.path
    return request.url.path

@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    # 1) request id
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    # 2) create a LoggerAdapter so later logs include request_id if you use adapter
    adapter = logging.LoggerAdapter(logger, {"request_id": request_id})

    # 3) start timer
    start_ts = time.time()

    # 4) log request start
    path_label = _get_route_template(request)
    adapter.info("request_start", extra={"method": request.method, "path": path_label})

    
        # 5) call downstream handler
    response: Response = await call_next(request)

        # 6) compute latency
    latency = time.time() - start_ts

        # 7) increment metrics (use response status as string)
    status_str = str(response.status_code)
    HTTP_REQUEST_COUNT.labels(method=request.method, path=path_label, status=status_str).inc()
    HTTP_REQUEST_LATENCY.labels(method=request.method, path=path_label).observe(latency)

        # 8) log request end
    adapter.info(
        "request_end",
        extra={
            "status_code": response.status_code,
            "latency_seconds": round(latency, 4),
            "path": path_label,
        },
    )

    return response

    



@app.get("/metrics")
async def metrics():
    data, content_type = metrics_response()
    return Response(content=data, media_type=content_type)