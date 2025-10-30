from celery import Celery
import logging
import asyncio
from prometheus_client import start_http_server
from src.logging_config import configure_logging
from opentelemetry import trace

# --- Setup Tracer ---
tracer = trace.get_tracer(__name__)

# --- Configure Celery ---
celery_app = Celery(
    "provider_validator",
    broker="redis://localhost:6379/0",     # Redis message broker
    backend="redis://localhost:6379/0"     # optional result backend
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
)

# --- Configure Logging ---
configure_logging()
logger = logging.getLogger("celery")
logger.setLevel(logging.INFO)


# -----------------------------------------------------------------------------
#  TASK 1 — Batch Validation Task with Tracing + Logging
# -----------------------------------------------------------------------------
@celery_app.task(bind=True)
def run_batch_task(self, limit=50, concurrency=6, request_id=None):
    """Run provider validation batch job with OpenTelemetry tracing."""
    from src.orchestrator import run_batch

    adapter = logging.LoggerAdapter(
        logger, {"request_id": request_id or self.request.id}
    )

    adapter.info("batch_task_start", extra={"task_id": self.request.id})

    # 🔹 Start OpenTelemetry span for tracing
    with tracer.start_as_current_span(
        "run_batch_task",
        attributes={
            "task.id": self.request.id,
            "request.id": request_id,
            "limit": limit,
            "concurrency": concurrency,
        },
    ):
        asyncio.run(run_batch("data/providers_sample.csv", concurrency))

    adapter.info("batch_task_complete", extra={"task_id": self.request.id})
    return {"status": "completed", "limit": limit, "concurrency": concurrency}


# -----------------------------------------------------------------------------
#  TASK 2 — Outreach Email Task with Tracing + Logging
# -----------------------------------------------------------------------------
@celery_app.task(bind=True)
def send_outreach_task(self, provider_payload, request_id=None):
    """Send outreach email and log with request_id context."""
    task_id = self.request.id
    adapter = logging.LoggerAdapter(
        logger, {"request_id": request_id or task_id}
    )

    with tracer.start_as_current_span(
        "send_outreach_task",
        attributes={
            "task.id": task_id,
            "request.id": request_id,
            "provider.id": provider_payload.get("id"),
        },
    ):
        adapter.info(
            "send_outreach_start",
            extra={"task_id": task_id, "provider_id": provider_payload.get("id")},
        )
        # --- your email sending logic goes here ---
        adapter.info(
            "send_outreach_complete",
            extra={"task_id": task_id, "status": "sent"},
        )


# -----------------------------------------------------------------------------
#  METRICS SERVER (Prometheus)
# -----------------------------------------------------------------------------
def start_metrics_server(port=8001):
    """Run Prometheus metrics server for Celery worker."""
    start_http_server(port)
    logger.info(f"Prometheus metrics available on port {port}")
