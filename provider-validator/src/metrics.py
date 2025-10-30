# src/metrics.py
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST



# HTTP metrics
HTTP_REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method','path','status'])
HTTP_REQUEST_LATENCY = Histogram('http_request_latency_seconds', 'HTTP request latency', ['method','path'])

# Batch metrics
BATCH_TASKS_QUEUED = Counter('batch_tasks_queued_total', 'Batch tasks queued')
BATCH_TASKS_SUCCESS = Counter('batch_tasks_success_total', 'Batch tasks succeeded')
BATCH_TASKS_FAILED = Counter('batch_tasks_failed_total', 'Batch tasks failed')

# Domain metrics
PROVIDERS_PROCESSED = Counter('providers_processed_total', 'Providers processed')
PROVIDERS_CONFIDENCE_SUM = Gauge('providers_confidence_sum', 'Sum of provider confidence values')

def metrics_response():
    return generate_latest(), CONTENT_TYPE_LATEST
