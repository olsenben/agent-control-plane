"""Nonblocking OpenTelemetry stub (V6 T01).

Ledger remains canonical. Telemetry export failure never blocks agent sessions.
When opentelemetry is not installed, all helpers no-op safely.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

logger = logging.getLogger(__name__)

# Pin adopted GenAI semantic convention reference version for operators.
GENAI_SEMCONV_REFERENCE = "gen_ai/1.36.0"

_ATTR_NAMESPACE = "agent"


@dataclass
class TelemetryStats:
    spans_started: int = 0
    spans_dropped: int = 0
    export_failures: int = 0


_stats = TelemetryStats()
_initialized = False
_otel_available = False


def telemetry_stats() -> TelemetryStats:
    return _stats


def init_telemetry(*, service_name: str = "agent-control-plane") -> None:
    global _initialized, _otel_available
    if _initialized:
        return
    _initialized = True
    if os.environ.get("OTEL_SDK_DISABLED", "").lower() in ("1", "true", "yes"):
        logger.info("telemetry disabled via OTEL_SDK_DISABLED")
        return
    try:
        from opentelemetry import trace  # noqa: F401
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
        if endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
            provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        _otel_available = True
        logger.info("telemetry initialized service=%s otlp=%s", service_name, bool(endpoint))
    except ImportError:
        logger.info("opentelemetry not installed; telemetry no-op")
    except Exception as exc:
        _stats.export_failures += 1
        logger.warning("telemetry init failed (nonblocking): %s", exc)


def _agent_attributes(
    *,
    trace_id: str | None = None,
    run_id: str | None = None,
    session_id: str | None = None,
    policy_source_sha: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    if trace_id:
        attrs[f"{_ATTR_NAMESPACE}.trace_id"] = trace_id
    if run_id:
        attrs[f"{_ATTR_NAMESPACE}.run_id"] = run_id
    if session_id:
        attrs[f"{_ATTR_NAMESPACE}.session_id"] = session_id
    if policy_source_sha:
        attrs[f"{_ATTR_NAMESPACE}.policy_source_sha"] = policy_source_sha
    if extra:
        attrs.update(extra)
    return attrs


@contextmanager
def short_span(
    name: str,
    *,
    trace_id: str | None = None,
    run_id: str | None = None,
    session_id: str | None = None,
    policy_source_sha: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> Iterator[None]:
    """Start a short-lived span; never hold open across human/CI waits."""
    _stats.spans_started += 1
    if not _otel_available:
        yield
        return
    try:
        from opentelemetry import trace

        tracer = trace.get_tracer("agent-control-plane")
        attrs = _agent_attributes(
            trace_id=trace_id,
            run_id=run_id,
            session_id=session_id,
            policy_source_sha=policy_source_sha,
            extra=attributes,
        )
        with tracer.start_as_current_span(name, attributes=attrs):
            yield
    except Exception as exc:
        _stats.spans_dropped += 1
        _stats.export_failures += 1
        logger.debug("span %s dropped (nonblocking): %s", name, exc)
        yield


def record_span_link(name: str, *, linked_trace_id: str, attributes: dict[str, Any] | None = None) -> None:
    """Record intent to link async boundary (ledger event is durable source)."""
    _stats.spans_started += 1
    if not _otel_available:
        return
    try:
        with short_span(name, trace_id=linked_trace_id, attributes=attributes or {}):
            pass
    except Exception:
        _stats.spans_dropped += 1
