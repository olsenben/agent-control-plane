"""NL ``@agent`` intent extraction (V6 T07).

Deterministic heuristic is the default (homelab-safe). Instructor and Semantic
Router backends are optional and gated by ``NL_INTENT_BACKEND``.
"""

from __future__ import annotations

import os
import re

from agent_shared.models.invocation import AgentIntent

_AT_AGENT = re.compile(r"^\s*@agent\b(?:\s+(.*))?$", re.IGNORECASE | re.DOTALL)

_KIND_HINTS: list[tuple[str, list[str]]] = [
    ("explain", [r"\bexplain\b", r"\bwhy\b", r"\bwhat\s+happened\b"]),
    ("inspect", [r"\binspect\b", r"\blook\s+at\b", r"\bcheck\b"]),
    ("review", [r"\breview\b", r"\bpr\b", r"\bpull\s+request\b"]),
    ("plan", [r"\bplan\b", r"\bapproach\b", r"\bhowto\b", r"\bhow\s+to\b"]),
    ("verify", [r"\bverify\b", r"\bci\b", r"\btest\b"]),
    ("fix", [r"\bfix\b", r"\bpatch\b", r"\brepair\b"]),
]

_CONFIDENCE_AUTO = 0.7


def is_bare_at_agent(text: str) -> bool:
    """True for ``@agent …`` but not ``@agent-reviewer`` role mentions."""
    t = (text or "").strip()
    if re.match(r"^\s*@agent-", t, flags=re.IGNORECASE):
        return False
    return bool(_AT_AGENT.match(t))


def _heuristic_extract(task: str) -> AgentIntent:
    body = (task or "").strip()
    if not body:
        return AgentIntent(
            kind=None,
            natural_language_task="",
            confidence=0.0,
            clarification_question="Which command should I run (inspect, review, plan, explain, verify)?",
            extractor="heuristic",
        )
    scores: dict[str, int] = {}
    for kind, pats in _KIND_HINTS:
        for pat in pats:
            if re.search(pat, body, flags=re.IGNORECASE):
                scores[kind] = scores.get(kind, 0) + 1
    if not scores:
        return AgentIntent(
            kind=None,
            natural_language_task=body,
            confidence=0.2,
            clarification_question=(
                "I am not sure what to do. Reply with `/agent review|plan|explain|inspect …` "
                "or clarify the task."
            ),
            extractor="heuristic",
        )
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    best_kind, best_score = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0
    if best_score == second:
        return AgentIntent(
            kind=None,
            natural_language_task=body,
            confidence=0.4,
            clarification_question=(
                f"Ambiguous intent between {ranked[0][0]} and {ranked[1][0]}. "
                "Please use an explicit `/agent <kind> …` command."
            ),
            extractor="heuristic",
        )
    confidence = min(0.95, 0.55 + 0.15 * best_score)
    return AgentIntent(
        kind=best_kind,
        natural_language_task=body,
        confidence=confidence,
        clarification_question=None if confidence >= _CONFIDENCE_AUTO else (
            f"Did you want `/agent {best_kind}` for this? Reply with the slash command to confirm."
        ),
        extractor="heuristic",
    )


def _instructor_extract(task: str) -> AgentIntent | None:
    """Optional Instructor path; returns None if unavailable."""
    if os.environ.get("NL_INTENT_BACKEND", "heuristic").lower() != "instructor":
        return None
    try:
        from agent_workers.rlm.structured_output_client import StructuredOutputClient
    except Exception:
        return None
    # Homelab gate: do not call live models from the webhook path in T07 day-one.
    # Keep heuristic authoritative unless explicitly wired later.
    _ = StructuredOutputClient
    return None


def extract_agent_intent(text: str) -> AgentIntent:
    """Extract structured intent from ``@agent`` NL text (body after mention)."""
    m = _AT_AGENT.match((text or "").strip())
    if not m:
        return AgentIntent(confidence=0.0, extractor="none")
    task = (m.group(1) or "").strip()
    instructor = _instructor_extract(task)
    if instructor is not None:
        return instructor
    return _heuristic_extract(task)


def confidence_allows_dispatch(intent: AgentIntent) -> bool:
    return bool(intent.kind) and intent.confidence >= _CONFIDENCE_AUTO
