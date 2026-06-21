"""Approval target and plan alias identifiers (Slice 6A plan-scoped handles)."""

from __future__ import annotations

import re

_PLAN_ALIAS = re.compile(r"^PLAN-run-(?P<suffix>[a-f0-9]{8,})$", re.IGNORECASE)
_APPROVAL_TARGET = re.compile(
    r"^WI-(?P<issue>\d{4,})-(?P<suffix>[a-f0-9]{8,})$",
    re.IGNORECASE,
)


def derive_approval_target_id(*, issue_id: int, plan_run_id: str) -> str:
    suffix = plan_run_id[-8:] if len(plan_run_id) >= 8 else plan_run_id
    return f"WI-{issue_id:04d}-{suffix.lower()}"


def derive_plan_alias(plan_run_id: str) -> str:
    suffix = plan_run_id[-8:] if len(plan_run_id) >= 8 else plan_run_id
    return f"PLAN-run-{suffix.lower()}"


def parse_approval_target(raw: str) -> tuple[str, int | None, str] | None:
    """Return (kind, issue_id, suffix) where kind is 'wi' or 'plan'."""
    text = raw.strip()
    wi = _APPROVAL_TARGET.match(text)
    if wi:
        return ("wi", int(wi.group("issue")), wi.group("suffix").lower())
    plan = _PLAN_ALIAS.match(text)
    if plan:
        return ("plan", None, plan.group("suffix").lower())
    return None
