"""Parse and validate structured fix model output."""

from __future__ import annotations

from typing import Any

from agent_control.model_router import ResolvedEndpoint
from agent_shared.models.context_pack import ContextPack
from agent_shared.models.fix import FixResult
from agent_workers.rlm.model_output import StructuredParseFailure, validate_or_repair


class FixParseError(ValueError):
    """Raised when fix output cannot be parsed into FixResult."""


def parse_fix_output(
    raw: str,
    *,
    context_pack: ContextPack | None = None,
    run_id: str = "",
    repair_endpoint: ResolvedEndpoint | None = None,
    repair_timeout_seconds: float = 60.0,
    allowed_files: list[str] | None = None,
) -> FixResult:
    try:
        return validate_or_repair(
            "fix",
            raw,
            context_pack=context_pack,
            run_id=run_id,
            repair_endpoint=repair_endpoint,
            repair_timeout_seconds=repair_timeout_seconds,
            allowed_files=allowed_files,
        )
    except StructuredParseFailure as exc:
        raise FixParseError(str(exc)) from exc


def coerce_fix_changes(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    changes: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            changes.append(dict(item))
    return changes
