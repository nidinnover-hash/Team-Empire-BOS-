"""
Optional OpenTelemetry instrumentation.

Activated only when OTEL_EXPORTER_OTLP_ENDPOINT is set in the environment.
Requires optional packages (not in requirements.txt by default):

  pip install \
    opentelemetry-api \
    opentelemetry-sdk \
    opentelemetry-instrumentation-fastapi \
    opentelemetry-instrumentation-sqlalchemy \
    opentelemetry-exporter-otlp-proto-http

If the packages are not installed, setup() is a safe no-op.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_otel_initialized = False


def setup(app=None) -> bool:
    """
    Initialise OpenTelemetry tracing.

    Returns True if instrumentation was activated, False if skipped (no
    OTLP endpoint configured) or if the packages are not installed.

    Call once from the FastAPI lifespan *before* the app handles requests.
    """
    global _otel_initialized
    if _otel_initialized:
        return True

    try:
        from app.core.config import settings
        endpoint = (settings.OTEL_EXPORTER_OTLP_ENDPOINT or "").strip()
        service_name = settings.OTEL_SERVICE_NAME
    except Exception:
        return False

    if not endpoint:
        # No exporter configured — stay silent (common in dev/test)
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.info(
            "OpenTelemetry packages not installed — tracing disabled. "
            "Install with: pip install opentelemetry-api opentelemetry-sdk "
            "opentelemetry-exporter-otlp-proto-http"
        )
        return False

    try:
        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)

        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(provider)

        # Instrument FastAPI if app instance provided
        if app is not None:
            try:
                from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
                FastAPIInstrumentor.instrument_app(app)
                logger.debug("OpenTelemetry FastAPI instrumentation enabled")
            except ImportError:
                logger.debug(
                    "opentelemetry-instrumentation-fastapi not installed — skipping FastAPI auto-instrumentation"
                )

        # Instrument SQLAlchemy
        try:
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
            SQLAlchemyInstrumentor().instrument()
            logger.debug("OpenTelemetry SQLAlchemy instrumentation enabled")
        except ImportError:
            logger.debug(
                "opentelemetry-instrumentation-sqlalchemy not installed — skipping SQLAlchemy auto-instrumentation"
            )

        _otel_initialized = True
        logger.info(
            "OpenTelemetry tracing enabled (service=%s, endpoint=%s)",
            service_name,
            endpoint,
        )
        return True

    except Exception as exc:
        logger.warning("OpenTelemetry setup failed: %s — tracing disabled", type(exc).__name__)
        return False


def get_tracer(name: str = "app"):
    """Return an OTel tracer (or a no-op tracer if OTel is not active)."""
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return _NoOpTracer()


class _NoOpTracer:
    """Minimal no-op tracer used when opentelemetry-api is not installed."""

    def start_as_current_span(self, name: str, **_kwargs):
        from contextlib import contextmanager

        @contextmanager
        def _noop():
            yield None

        return _noop()
