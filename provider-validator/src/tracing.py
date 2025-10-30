# src/tracing.py
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
RequestsInstrumentor().instrument()


def init_tracing(app):
    resource = Resource.create({"service.name": "provider-validator-api"})
    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)
    # Console exporter for local debugging
    console_exporter = ConsoleSpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(console_exporter))
    # instrument FastAPI
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
