"""Shared publish-candidate predicate for ingest and brokerage."""

from __future__ import annotations

from agent_shared.constants import (
    FIX_STATUS_PATCH_BUNDLE_READY,
    PRODUCER_PROTOCOL_PATCH_BUNDLE_V1,
)
from agent_shared.models.events import AgentRunCompletedEvent


def is_publish_candidate(
    event: AgentRunCompletedEvent,
    *,
    remote_publish_enabled: bool = True,
) -> bool:
    """True when worker produced a bundle the CT103 broker may publish."""
    if event.command_kind not in ("fix", "repair"):
        return False
    if event.producer_protocol != PRODUCER_PROTOCOL_PATCH_BUNDLE_V1:
        return False
    if event.fix_status != FIX_STATUS_PATCH_BUNDLE_READY:
        return False
    if not event.bundle_id:
        return False
    if event.command_kind == "fix" and not remote_publish_enabled:
        return False
    return True
