"""Modular prompt-injection scanner — shadow mode only (V6 T06).

LlamaFirewall-style modular detectors without a hard dependency on the
upstream package. Blocking mode requires a separate ADR + operator approval.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from agent_shared.models.injection_assessment import (
    InjectionAssessment,
    InjectionRisk,
    MatchedRegion,
    RecommendedAction,
)
from agent_shared.models.trust import TRUSTED_AUTHORITY_CLASSES, TrustClass


@dataclass(frozen=True)
class _Hit:
    category: str
    start: int
    end: int
    snippet: str
    risk: InjectionRisk


Detector = Callable[[str], list[_Hit]]

_RISK_RANK: dict[str, int] = {"none": 0, "low": 1, "medium": 2, "high": 3}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_patterns(text: str, category: str, patterns: list[str], risk: InjectionRisk) -> list[_Hit]:
    hits: list[_Hit] = []
    for pat in patterns:
        for m in re.finditer(pat, text, flags=re.IGNORECASE | re.MULTILINE):
            snippet = text[m.start() : m.end()][:120]
            hits.append(
                _Hit(
                    category=category,
                    start=m.start(),
                    end=m.end(),
                    snippet=snippet,
                    risk=risk,
                )
            )
    return hits


def detect_ignore_instructions(text: str) -> list[_Hit]:
    return _find_patterns(
        text,
        "ignore_prior_instructions",
        [
            r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
            r"disregard\s+(the\s+)?system\s+prompt",
            r"forget\s+(everything|your\s+rules)",
        ],
        "high",
    )


def detect_role_override(text: str) -> list[_Hit]:
    return _find_patterns(
        text,
        "role_override",
        [
            r"you\s+are\s+now\s+(?:dan|unrestricted|admin)",
            r"act\s+as\s+(?:system|root|developer\s+mode)",
            r"jailbreak",
        ],
        "high",
    )


def detect_exfiltration(text: str) -> list[_Hit]:
    return _find_patterns(
        text,
        "data_exfiltration",
        [
            r"(?:exfiltrate|leak|dump)\s+(?:the\s+)?(?:secrets?|tokens?|env|credentials?)",
            r"send\s+(?:all\s+)?(?:api[_-]?keys?|secrets?)\s+to\s+https?://",
            r"print\s+(?:GITEA_|OPENAI_|AWS_)[A-Z0-9_]+",
        ],
        "high",
    )


def detect_tool_abuse(text: str) -> list[_Hit]:
    return _find_patterns(
        text,
        "tool_policy_bypass",
        [
            r"(?:run|execute)\s+(?:rm\s+-rf|curl\s+.*\|\s*sh)",
            r"disable\s+(?:tool\s+)?(?:policy|sandbox|allowlist)",
            r"push\s+(?:directly\s+)?to\s+(?:main|master)\s+without\s+approval",
        ],
        "medium",
    )


DEFAULT_DETECTORS: tuple[Detector, ...] = (
    detect_ignore_instructions,
    detect_role_override,
    detect_exfiltration,
    detect_tool_abuse,
)


def _max_risk(hits: list[_Hit]) -> InjectionRisk:
    if not hits:
        return "none"
    best = max(hits, key=lambda h: _RISK_RANK[h.risk])
    return best.risk


def _recommend(risk: InjectionRisk) -> RecommendedAction:
    if risk == "high":
        return "exclude"
    if risk == "medium":
        return "flag"
    if risk == "low":
        return "flag"
    return "allow"


def assess_text_shadow(
    text: str,
    *,
    content_ref: str = "content",
    project: str = "",
    run_id: str | None = None,
    session_id: str | None = None,
    detectors: tuple[Detector, ...] | None = None,
) -> InjectionAssessment:
    """Run modular detectors in shadow mode. Never sets authority_granted."""
    body = text or ""
    hits: list[_Hit] = []
    for det in detectors or DEFAULT_DETECTORS:
        hits.extend(det(body))
    risk = _max_risk(hits)
    categories = sorted({h.category for h in hits})
    regions = [
        MatchedRegion(start=h.start, end=h.end, snippet=h.snippet, category=h.category)
        for h in hits
    ]
    return InjectionAssessment(
        risk=risk,
        categories=categories,
        matched_regions=regions,
        recommended_action=_recommend(risk),
        authority_granted=False,
        content_ref=content_ref,
        detail={"hit_count": len(hits), "mode": "shadow"},
        assessed_at=_now(),
        run_id=run_id,
        session_id=session_id,
        project=project,
    )


def scanner_cannot_grant_authority(assessment: InjectionAssessment) -> bool:
    """Invariant: shadow scanner never upgrades trust / grants authority."""
    return assessment.authority_granted is False and assessment.mode == "shadow"


def apply_shadow_to_trust(
    *,
    current_trust: TrustClass | str,
    assessment: InjectionAssessment,
) -> TrustClass | str:
    """High-risk may flag content as untrusted; never upgrade to trusted_*."""
    assert scanner_cannot_grant_authority(assessment)
    if current_trust in TRUSTED_AUTHORITY_CLASSES:
        return current_trust
    if assessment.risk in ("high", "medium") and assessment.recommended_action in (
        "flag",
        "exclude",
    ):
        if current_trust in ("untrusted_issue_content", "untrusted_comment", "untrusted_log"):
            return current_trust
        return "untrusted_comment"
    return current_trust
