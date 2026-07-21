"""Repository data-egress policy for external model routes (V6 T04)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from agent_control.config import Settings, get_settings

ContentClassification = Literal[
    "homelab_only",
    "code_handling_allowed",
    "unclassified",
]


@dataclass(frozen=True)
class EgressDecision:
    allowed: bool
    reason: str
    data_left_homelab: bool
    provider: str
    content_classification: ContentClassification
    repo_policy: str


def repo_allows_external(project: str, settings: Settings | None = None) -> bool:
    """Return True when repo is on the external-processing allowlist.

    Empty allowlist means external egress is denied for all repos (fail closed).
    Use ``*`` or ``owner/*`` wildcards like GITEA_ALLOWED_REPOS.
    """
    settings = settings or get_settings()
    raw = (getattr(settings, "repo_external_model_policy", "") or "").strip()
    if not raw:
        return False
    project_l = project.strip().lower()
    for part in raw.split(","):
        pattern = part.strip().lower()
        if not pattern:
            continue
        if pattern == "*":
            return True
        if pattern.endswith("/*"):
            owner = pattern[:-2]
            if project_l.startswith(owner + "/"):
                return True
        if pattern == project_l:
            return True
    return False


def role_allows_external_code(role: str, settings: Settings | None = None) -> bool:
    """Fix/code roles require an explicit code-handling allowlist entry."""
    settings = settings or get_settings()
    code_roles = {
        r.strip().lower()
        for r in (getattr(settings, "model_code_handling_roles", "") or "").split(",")
        if r.strip()
    }
    if not code_roles:
        # Default: plan/review/judge/rlm may use external; fixer needs explicit allow.
        code_roles = {"fixer", "rlm"}
    if role.lower() not in {"fixer", "rlm"}:
        return True
    return role.lower() in code_roles


def evaluate_external_egress(
    *,
    project: str,
    role: str,
    provider: str,
    settings: Settings | None = None,
) -> EgressDecision:
    settings = settings or get_settings()
    if not settings.model_fallback_enabled:
        return EgressDecision(
            allowed=False,
            reason="MODEL_FALLBACK_ENABLED=false",
            data_left_homelab=False,
            provider=provider,
            content_classification="homelab_only",
            repo_policy=getattr(settings, "repo_external_model_policy", "") or "",
        )
    if not repo_allows_external(project, settings):
        return EgressDecision(
            allowed=False,
            reason="repo_external_model_policy denies external processing",
            data_left_homelab=False,
            provider=provider,
            content_classification="homelab_only",
            repo_policy=getattr(settings, "repo_external_model_policy", "") or "",
        )
    if not role_allows_external_code(role, settings):
        return EgressDecision(
            allowed=False,
            reason=f"role {role} not approved for external code handling",
            data_left_homelab=False,
            provider=provider,
            content_classification="homelab_only",
            repo_policy=getattr(settings, "repo_external_model_policy", "") or "",
        )
    return EgressDecision(
        allowed=True,
        reason="repo and role permit external processing",
        data_left_homelab=True,
        provider=provider,
        content_classification="code_handling_allowed",
        repo_policy=getattr(settings, "repo_external_model_policy", "") or "",
    )
