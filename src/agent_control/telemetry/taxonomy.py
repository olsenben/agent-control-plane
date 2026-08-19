"""Experience telemetry vocabulary helpers (VExp W0-D).

Registers the 17 epic event names and builds a safe common envelope. Does not
append to the NFS ledger and does not register Observatory display types.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_shared.models.experience_events import (
    EXPERIENCE_EVENT_NAME_SET,
    EXPERIENCE_EVENT_NAMES,
    ExperienceEventEnvelope,
    TreatmentExposure,
)

# Copied from agent_control.observe.safe_display._PROHIBITED_NAME_KEYWORDS.
# Observatory remains single-owner of that module; this list is a W0 pin.
PROHIBITED_FIELD_KEYWORDS: tuple[str, ...] = (
    "token",
    "secret",
    "password",
    "passwd",
    "credential",
    "authorization",
    "auth_header",
    "cookie",
    "api_key",
    "apikey",
    "private_key",
    "ssh_key",
    "ssh_",
    "access_key",
    "bearer",
    "header",
    "env",
    "prompt",
    "stdout",
    "stderr",
    "raw_output",
    "raw_log",
    "raw_payload",
    "payload_json",
    "args",
    "system_message",
)


class ProhibitedTelemetryFieldError(ValueError):
    """Raised when an envelope payload uses a prohibited field name."""


def is_prohibited_telemetry_field_name(name: str) -> bool:
    """Name-based prohibition matching Observatory keyword policy."""
    lname = name.lower()
    return any(keyword in lname for keyword in PROHIBITED_FIELD_KEYWORDS)


def build_experience_event_envelope(
    event_name: str,
    *,
    payload: Mapping[str, Any] | None = None,
    treatment: TreatmentExposure | None = None,
    event_id: str | None = None,
    recorded_at: str | None = None,
    correlation_id: str | None = None,
    trace_id: str | None = None,
    session_id: str | None = None,
    run_id: str | None = None,
) -> ExperienceEventEnvelope:
    """Validate vocabulary + safe-field policy and return an in-memory envelope."""
    if event_name not in EXPERIENCE_EVENT_NAME_SET:
        raise ValueError(f"unregistered experience event name: {event_name}")
    body = dict(payload or {})
    _reject_prohibited_keys(body)
    return ExperienceEventEnvelope(
        event_name=event_name,
        event_id=event_id,
        recorded_at=recorded_at,
        correlation_id=correlation_id,
        trace_id=trace_id,
        session_id=session_id,
        run_id=run_id,
        treatment=treatment,
        payload=body,
    )


def emit_experience_event(
    event_name: str,
    *,
    payload: Mapping[str, Any] | None = None,
    treatment: TreatmentExposure | None = None,
    event_id: str | None = None,
    recorded_at: str | None = None,
    correlation_id: str | None = None,
    trace_id: str | None = None,
    session_id: str | None = None,
    run_id: str | None = None,
) -> ExperienceEventEnvelope:
    """Return a safe envelope. Does not persist to the NFS ledger."""
    return build_experience_event_envelope(
        event_name,
        payload=payload,
        treatment=treatment,
        event_id=event_id,
        recorded_at=recorded_at,
        correlation_id=correlation_id,
        trace_id=trace_id,
        session_id=session_id,
        run_id=run_id,
    )


def _reject_prohibited_keys(value: Any, *, path: str = "") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            name = str(key)
            if is_prohibited_telemetry_field_name(name):
                location = f"{path}.{name}" if path else name
                raise ProhibitedTelemetryFieldError(
                    f"prohibited telemetry field name: {location}"
                )
            child_path = f"{path}.{name}" if path else name
            _reject_prohibited_keys(nested, path=child_path)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            child_path = f"{path}[{index}]" if path else f"[{index}]"
            _reject_prohibited_keys(item, path=child_path)


__all__ = [
    "EXPERIENCE_EVENT_NAMES",
    "EXPERIENCE_EVENT_NAME_SET",
    "PROHIBITED_FIELD_KEYWORDS",
    "ProhibitedTelemetryFieldError",
    "build_experience_event_envelope",
    "emit_experience_event",
    "is_prohibited_telemetry_field_name",
]
