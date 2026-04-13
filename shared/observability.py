"""
Shared observability setup — import this in every service's main.py.

Provides:
  - Structured JSON logging via structlog
  - Prometheus metrics via prometheus-fastapi-instrumentator
  - OpenTelemetry tracing (OTLP export when collector is available)
  - /health and /metrics endpoints
"""

import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from typing import Callable

import structlog
from fastapi import FastAPI, Request, Response
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from prometheus_fastapi_instrumentator import Instrumentator

SERVICE_NAME = os.getenv("SERVICE_NAME", "unknown-service")
OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")


# ── Logging ────────────────────────────────────────────────────────────────────

def setup_logging() -> None:
    """Configure structlog to emit JSON lines to stdout."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
    )

    # Also redirect stdlib logging into structlog so third-party libs log as JSON
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )


def get_logger(name: str = SERVICE_NAME) -> structlog.BoundLogger:
    return structlog.get_logger(name)


# ── Tracing ────────────────────────────────────────────────────────────────────

class _NoOpExporter(SpanExporter):
    """Silent exporter used when no OTLP endpoint is configured."""
    def export(self, spans): return SpanExportResult.SUCCESS
    def shutdown(self): pass


def setup_tracing() -> None:
    """
    Configure OpenTelemetry. Exports to OTLP when OTEL_EXPORTER_OTLP_ENDPOINT
    is set (e.g. when Tempo/Jaeger is running), otherwise traces are collected
    but silently dropped — no stdout noise.
    """
    resource = Resource.create({"service.name": SERVICE_NAME})
    provider = TracerProvider(resource=resource)

    exporter = (
        OTLPSpanExporter(endpoint=f"{OTEL_ENDPOINT}/v1/traces")
        if OTEL_ENDPOINT
        else _NoOpExporter()
    )

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Instrument outbound HTTP calls automatically
    HTTPXClientInstrumentor().instrument()


# ── Request ID + trace context middleware ──────────────────────────────────────

async def request_context_middleware(request: Request, call_next: Callable) -> Response:
    """
    Injects request_id and trace_id into structlog context so every log line
    emitted during a request automatically includes them.
    """
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    span = trace.get_current_span()
    trace_id = format(span.get_span_context().trace_id, "032x") if span else ""

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        service=SERVICE_NAME,
        request_id=request_id,
        trace_id=trace_id,
    )

    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


# ── App factory ────────────────────────────────────────────────────────────────

def create_app(title: str, version: str = "0.1.0", **kwargs) -> FastAPI:
    """
    Creates a FastAPI app pre-wired with:
      - Structured logging
      - OpenTelemetry tracing
      - Prometheus /metrics endpoint
      - /health endpoint
      - Request ID middleware
    """
    setup_logging()
    setup_tracing()

    app = FastAPI(title=title, version=version, **kwargs)

    # Prometheus metrics — exposes /metrics automatically
    Instrumentator().instrument(app).expose(app)

    # OTEL FastAPI instrumentation
    FastAPIInstrumentor.instrument_app(app)

    # Request context middleware (request_id + trace_id in all logs)
    app.middleware("http")(request_context_middleware)

    @app.get("/health", tags=["ops"])
    async def health():
        return {"status": "ok", "service": SERVICE_NAME}

    @app.get("/ready", tags=["ops"])
    async def ready():
        return {"status": "ready", "service": SERVICE_NAME}

    return app
