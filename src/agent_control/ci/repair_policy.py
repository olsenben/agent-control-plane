"""Central repair repository + class decision (V4.1.1 PR4).

Empty allowlist denies all. No wildcards. Invalid entries fail Settings startup.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

# First ACP self-repair envelope: lint/format family only when allowlisted.
DEFAULT_REPAIR_ALLOWED_CLASSES = ("lint_failure",)

# Demo-only intentional-fail heuristic repos (never ACP).
DEMO_INTENTIONAL_FAIL_REPOS = frozenset({"ai-sdlc-lab/demo-app"})

# Paths never eligible for automatic repair (trust-boundary / infra).
_PROHIBITED_PATH_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"(^|/)\.agent(/|$)"),
    re.compile(r"(^|/)config/command_registry\.ya?ml$"),
    re.compile(r"(^|/)\.gitea/workflows(/|$)"),
    re.compile(r"(^|/).github/workflows(/|$)"),
    re.compile(r"(^|/)sandbox(/|$)"),
    re.compile(r"(^|/)publish"),
    re.compile(r"(^|/)broker"),
    re.compile(r"(^|/)policy_loader"),
    re.compile(r"(^|/)command_runner"),
    re.compile(r"(^|/)docker-compose"),
    re.compile(r"(^|/)\.env"),
    re.compile(r"(^|/)Dockerfile"),
    re.compile(r"(^|/)docs/adr(/|$)"),
)

_REPO_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")


@dataclass
class RepairRepoDecision:
    """Structured result from the single repair allowlist decision function."""

    allowed: bool
    reason_code: str
    normalized_repository: str
    matched_allowlist_entry: str | None = None
    repair_class: str | None = None
    effective_policy_hash: str = ""
    messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason_code": self.reason_code,
            "normalized_repository": self.normalized_repository,
            "matched_allowlist_entry": self.matched_allowlist_entry,
            "repair_class": self.repair_class,
            "effective_policy_hash": self.effective_policy_hash,
            "messages": list(self.messages),
        }


def normalize_repository(full_name: str) -> str:
    """Canonical owner/repo: trim whitespace, fixed case (lower)."""
    return (full_name or "").strip().lower()


def parse_repair_allowlist(raw: str) -> list[str]:
    """Parse comma-separated exact repos. No wildcards. Invalid → ValueError."""
    entries: list[str] = []
    for part in (raw or "").split(","):
        item = part.strip()
        if not item:
            continue
        if "*" in item or "?" in item:
            raise ValueError(f"repair_allowlist_wildcards_forbidden:{item}")
        if not _REPO_RE.match(item):
            raise ValueError(f"repair_allowlist_invalid_entry:{item}")
        entries.append(normalize_repository(item))
    # Preserve order, unique
    seen: set[str] = set()
    out: list[str] = []
    for e in entries:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out


def parse_repair_classes(raw: str) -> frozenset[str]:
    items = [c.strip() for c in (raw or "").split(",") if c.strip()]
    if not items:
        return frozenset(DEFAULT_REPAIR_ALLOWED_CLASSES)
    return frozenset(items)


def decision_policy_hash(
    *,
    allowlist: list[str],
    allowed_classes: frozenset[str],
    publish_enabled: bool,
) -> str:
    blob = json.dumps(
        {
            "schema": "repair_repo_policy.v1",
            "allowlist": allowlist,
            "allowed_classes": sorted(allowed_classes),
            "publish_enabled": publish_enabled,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def decide_repair_repository(
    repository: str,
    *,
    failure_class: str | None = None,
    allowlist_raw: str = "",
    allowed_classes_raw: str = "lint_failure",
    publish_enabled: bool = False,
    for_publish: bool = False,
) -> RepairRepoDecision:
    """Single decision function for repair enqueue / execution / publish.

    Empty allowlist → deny all. Exact match only (no wildcards).
    """
    normalized = normalize_repository(repository)
    allowlist = parse_repair_allowlist(allowlist_raw)
    classes = parse_repair_classes(allowed_classes_raw)
    pol_hash = decision_policy_hash(
        allowlist=allowlist,
        allowed_classes=classes,
        publish_enabled=publish_enabled,
    )

    if not normalized or "/" not in normalized:
        return RepairRepoDecision(
            allowed=False,
            reason_code="repository_invalid",
            normalized_repository=normalized,
            effective_policy_hash=pol_hash,
        )

    if not allowlist:
        return RepairRepoDecision(
            allowed=False,
            reason_code="repair_allowlist_empty",
            normalized_repository=normalized,
            repair_class=failure_class,
            effective_policy_hash=pol_hash,
        )

    matched = normalized if normalized in allowlist else None
    if matched is None:
        return RepairRepoDecision(
            allowed=False,
            reason_code="repository_not_allowlisted",
            normalized_repository=normalized,
            repair_class=failure_class,
            effective_policy_hash=pol_hash,
        )

    if failure_class is not None:
        if failure_class not in classes:
            return RepairRepoDecision(
                allowed=False,
                reason_code=f"failure_class_not_enabled:{failure_class}",
                normalized_repository=normalized,
                matched_allowlist_entry=matched,
                repair_class=failure_class,
                effective_policy_hash=pol_hash,
            )

    if for_publish and not publish_enabled:
        return RepairRepoDecision(
            allowed=False,
            reason_code="repair_publish_disabled",
            normalized_repository=normalized,
            matched_allowlist_entry=matched,
            repair_class=failure_class,
            effective_policy_hash=pol_hash,
            messages=["staged enablement: observe/repair-no-publish before publish"],
        )

    return RepairRepoDecision(
        allowed=True,
        reason_code="ok",
        normalized_repository=normalized,
        matched_allowlist_entry=matched,
        repair_class=failure_class,
        effective_policy_hash=pol_hash,
    )


def path_prohibited_for_repair(path: str) -> bool:
    """True if path is outside the ACP self-repair envelope."""
    norm = path.replace("\\", "/")
    while norm.startswith("./"):
        norm = norm[2:]
    norm = norm.lstrip("/")
    return any(p.search(norm) for p in _PROHIBITED_PATH_RES)


def filter_repair_allowed_files(paths: list[str]) -> tuple[list[str], list[str]]:
    """Return (kept, rejected) after path envelope filter."""
    kept: list[str] = []
    rejected: list[str] = []
    for p in paths:
        if path_prohibited_for_repair(p):
            rejected.append(p)
        else:
            kept.append(p)
    return kept, rejected


def intentional_fail_heuristic_allowed(repository: str) -> bool:
    """Demo intentional-fail stub removal is hard-gated off ACP."""
    return normalize_repository(repository) in DEMO_INTENTIONAL_FAIL_REPOS
