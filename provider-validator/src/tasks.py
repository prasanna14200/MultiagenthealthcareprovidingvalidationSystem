from src.celery_app import celery_app
from src.orchestrator import run_batch
from src.agents.outreach_agent import OutreachAgent
from src.email_sender import send_email_sendgrid
import asyncio

@celery_app.task
def run_batch_task(limit=50, concurrency=6):
    import asyncio
    from src.orchestrator import run_batch
    asyncio.run(run_batch("data/providers_sample.csv", concurrency))
    print("[INFO] Completed batch task")
    return {"status": "completed", "limit": limit, "concurrency": concurrency}



@celery_app.task(name="send_outreach_task", bind=True, max_retries=3, default_retry_delay=60)
def send_outreach_task(self, provider_payload):
    try:
        agent = OutreachAgent("outreach")
        draft = asyncio.run(agent.run(provider_payload))
        if not draft.get("recipient"):
            return {"status": "no_valid_email"}
        return send_email_sendgrid(draft, task_id=self.request.id)
    except Exception as exc:
        raise self.retry(exc=exc)