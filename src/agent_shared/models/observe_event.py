"""Observation event display-safe contract (V9 T01).

``observe_event.v1`` is the schema every raw ledger event is normalized into
before it may reach any Agent Observatory display surface (API JSON, SSE
stream, or server-rendered UI). It is the single choke point enforcing the
project's H1 hard gate: *safe-display before store/stream/UI*.

Every payload field on a ledger event is classified into exactly one of four
tiers (see :data:`FieldClassification`) before its value is allowed anywhere
near a display surface:

``allowlisted``
    Curated, structurally-typed field (id, hash, enum, short label,
    timestamp, count). Safe to render verbatim, subject to a defensive
    length cap applied by the normalizer.

``redacted``
    Field is known to sometimes carry free-text narrative content produced
    by our own control-plane logic (for example an exception-derived
    ``reason`` string). Rendered as a fixed placeholder; the raw value never
    reaches the display surface.

``metadata_only``
    Field may carry an opaque blob (dict/list) or untrusted excerpt (for
    example an injection-scanner matched-region snippet). Rendered as a
    structural descriptor only (``present`` / ``count``); the raw value
    never reaches the display surface.

``prohibited``
    Field must never reach a display surface, not even as a placeholder.
    Only the field *name* is retained (for audit/debug visibility into how
    much was withheld); its value is dropped entirely. This is also the
    default outcome for every field on an event whose ``type`` is not
    present in the classification registry (see
    ``agent_control.observe.safe_display``) -- unknown event types are
    display-safe by construction: none of their payload field *values* are
    ever exposed, only field names.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

FieldClassification = Literal["allowlisted", "redacted", "metadata_only", "prohibited"]

FIELD_CLASSIFICATIONS: tuple[FieldClassification, ...] = (
    "allowlisted",
    "redacted",
    "metadata_only",
    "prohibited",
)


class ObserveEventV1(BaseModel):
    """Display-safe rendering of one ledger event for the Agent Observatory.

    Never carries a raw ``payload`` field. ``display_fields`` only ever
    contains values that passed ``allowlisted`` classification (verbatim, capped)
    or structural descriptors for ``metadata_only`` fields, or the fixed
    ``"<redacted>"`` placeholder for ``redacted`` fields.
    """

    schema_version: str = "observe_event.v1"
    event_id: str | None = None
    type: str
    sequence: int = 0
    ledger_sequence: int | None = None
    recorded_at: str | None = None
    project: str | None = None
    source: str | None = None
    known_type: bool = False
    summary: str = ""
    display_fields: dict[str, Any] = Field(default_factory=dict)
    metadata_only_field_names: list[str] = Field(default_factory=list)
    redacted_field_names: list[str] = Field(default_factory=list)
    prohibited_field_names: list[str] = Field(default_factory=list)
