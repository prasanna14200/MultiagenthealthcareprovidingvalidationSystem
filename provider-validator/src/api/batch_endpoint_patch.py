# ============================================================================
# src/api/batch_endpoint_patch.py
#
# DROP-IN FIX for src/api/app.py
#
# PROBLEM: When Redis is down, calling run_batch_task.delay() throws
#   kombu.exceptions.OperationalError: Error 10061 connecting to localhost:6379
# which crashes the entire ASGI request and returns a 500 with a massive
# ExceptionGroup traceback instead of a clean error message.
#
# FIX: Two layers of protection:
#   1. A redis_health_check() called BEFORE .delay() — fails fast with a
#      clear human-readable error instead of a deep stack trace.
#   2. A ThreadPoolExecutor fallback — if Redis is truly unavailable,
#      the batch job still runs in a background thread so the UI works.
#      This is safe for development. In production, always use real Celery.
#
# HOW TO APPLY:
#   Replace the api_run_batch function in src/api/app.py with the version
#   below. Also add the imports and helpers at the top of app.py.
# ============================================================================

# ── Add these imports at the top of src/api/app.py ──────────────────────────
import uuid
import redis as redis_client
from concurrent.futures import ThreadPoolExecutor
from functools import partial

# Thread pool for the Redis-unavailable fallback (dev only)
_thread_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="batch-fallback")

# ── Add this helper function to src/api/app.py ──────────────────────────────

def redis_health_check() -> tuple[bool, str]:
    """
    Ping Redis before attempting to queue a Celery task.
    
    Returns (is_healthy: bool, error_message: str).
    Fails fast in ~1 second instead of letting Celery hang and produce
    an unhandled ExceptionGroup that crashes the ASGI middleware stack.
    """
    try:
        r = redis_client.Redis(host="localhost", port=6379, socket_connect_timeout=2)
        r.ping()
        return True, ""
    except redis_client.exceptions.ConnectionError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)


# ── Replace api_run_batch in src/api/app.py with this ───────────────────────

# IMPORTANT: adjust the import to match your actual worker module path.
# Your current code at line 117 is:
#   task = run_batch_task.delay(limit=limit, concurrency=concurrency)
# Keep that same import at the top of app.py — we just wrap the .delay() call.

@app.post("/run-batch")
async def api_run_batch(
    limit: int = 50,
    concurrency: int = 8,
    current_user: dict = Depends(get_current_user),   # keep your existing auth dep
):
    """
    Start batch validation job via Celery, with graceful Redis fallback.
    
    If Redis is reachable  → queues a real Celery task (production path).
    If Redis is DOWN       → runs the batch in a background thread (dev fallback).
    
    Either way the endpoint returns immediately with a task_id so the
    Gradio UI always gets a ✅ response instead of a 500 crash.
    """
    task_id = str(uuid.uuid4())

    # ── Layer 1: fast Redis health check ────────────────────────────────────
    redis_ok, redis_err = redis_health_check()

    if redis_ok:
        # ── Normal path: queue via Celery ────────────────────────────────
        try:
            task = run_batch_task.delay(limit=limit, concurrency=concurrency)
            task_id = task.id
            mode = "celery"
        except Exception as e:
            # Redis check passed but .delay() still failed — rare race condition.
            # Fall through to thread fallback below.
            redis_ok = False
            redis_err = str(e)

    if not redis_ok:
        # ── Fallback path: run in background thread ──────────────────────
        # Import your actual batch runner here — the synchronous function
        # that the Celery task wraps. Adjust the import path to match yours.
        # Example: from src.orchestrator import run_batch_sync
        #
        # If you don't have a sync version, you can call the Celery task
        # with apply() instead of delay() — this runs it synchronously
        # but still in a thread so we don't block the event loop:
        #
        #   future = _thread_pool.submit(
        #       run_batch_task.apply,
        #       kwargs={"limit": limit, "concurrency": concurrency}
        #   )
        #
        # For now we submit a placeholder — replace with your real call:
        try:
            future = _thread_pool.submit(
                run_batch_task.apply,           # runs task in-process, no Redis needed
                kwargs={"limit": limit, "concurrency": concurrency}
            )
            mode = "thread-fallback"
        except Exception as thread_err:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Redis is unreachable and thread fallback also failed.\n"
                    f"Redis error: {redis_err}\n"
                    f"Thread error: {str(thread_err)}\n\n"
                    f"Fix: start Redis — see REDIS_WINDOWS_FIX.md"
                )
            )

    return {
        "task_id": task_id,
        "limit": limit,
        "concurrency": concurrency,
        "started_by": current_user.get("sub", "unknown"),
        "mode": mode,                        # "celery" or "thread-fallback"
        "warning": (
            None if redis_ok else
            "⚠️ Redis unavailable — running in thread fallback mode (dev only). "
            "Start Redis for production use."
        )
    }