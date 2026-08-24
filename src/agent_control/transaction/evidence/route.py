"""Deterministic evidence-provider routing. No LLM / learned router."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from agent_shared.models.transaction.evidence import (
    EvidenceRoute,
    RouteRule,
    RoutedProvider,
    RouteWhen,
)

CHANGE_PRODUCTION = "PRODUCTION_SOURCE_CHANGE"
CHANGE_SECURITY_FINDING = "SECURITY_FINDING_TASK"
CHANGE_DEPENDENCY = "DEPENDENCY_MANIFEST_CHANGE"
CHANGE_SECURITY_SENSITIVE = "SECURITY_SENSITIVE_SYMBOL_OR_CONFIG"
CHANGE_PUBLIC_API = "PUBLIC_API_CHANGE"

REQUIRED = "REQUIRED_PROVIDER"
OPTIONAL = "OPTIONAL_PROVIDER"

DEPENDENCY_PATH_MARKERS = (
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "poetry.lock",
    "Pipfile",
    "go.mod",
    "Cargo.toml",
)

DEFAULT_ROUTE_RULES: tuple[dict[str, Any], ...] = (
    {
        "rule_id": "production_source_change",
        "when": {"change_class": CHANGE_PRODUCTION},
        "providers": [{"provider_id": "P1", "requirement_class": REQUIRED}],
    },
    {
        "rule_id": "security_finding_task",
        "when": {"change_class": CHANGE_SECURITY_FINDING},
        "providers": [
            {"provider_id": "P2", "requirement_class": REQUIRED},
            {"provider_id": "P3", "requirement_class": REQUIRED},
        ],
    },
    {
        "rule_id": "dependency_manifest_change",
        "when": {"change_class": CHANGE_DEPENDENCY},
        "providers": [
            {"provider_id": "dependency_if_configured", "requirement_class": OPTIONAL}
        ],
    },
    {
        "rule_id": "security_sensitive_symbol_or_config",
        "when": {"change_class": CHANGE_SECURITY_SENSITIVE},
        "providers": [{"provider_id": "P2", "requirement_class": REQUIRED}],
    },
    {
        "rule_id": "public_api_change",
        "when": {"change_class": CHANGE_PUBLIC_API},
        "providers": [{"provider_id": "P4", "requirement_class": REQUIRED}],
    },
)


def classify_change_classes(
    *,
    changed_files: Sequence[str],
    task_type: str | None = None,
    security_finding_ids: Sequence[str] | None = None,
    units: Sequence[Mapping[str, Any]] | None = None,
    authorized_change_classes: Sequence[str] | None = None,
) -> list[str]:
    classes: list[str] = []
    files = [path.replace("\\", "/") for path in changed_files]
    if any(path.startswith("src/") or path.endswith(".py") for path in files):
        classes.append(CHANGE_PRODUCTION)
    if task_type == "SECURITY_REMEDIATION" or security_finding_ids:
        classes.append(CHANGE_SECURITY_FINDING)
    if any(
        any(marker in path for marker in DEPENDENCY_PATH_MARKERS) for path in files
    ):
        classes.append(CHANGE_DEPENDENCY)
    if any(
        unit.get("privileged") or unit.get("side_effect_category") == "PRIVILEGED"
        for unit in (units or [])
    ) or any(path.endswith((".yml", ".yaml", ".ini", ".cfg", ".toml")) for path in files):
        if CHANGE_SECURITY_SENSITIVE not in classes:
            # config-only without privileged units still tags sensitive-config
            if any(unit.get("privileged") for unit in (units or [])) or any(
                "config" in path.lower() or path.endswith((".yml", ".yaml", ".ini", ".cfg"))
                for path in files
            ):
                classes.append(CHANGE_SECURITY_SENSITIVE)
    if any(
        "PUBLIC_API_CHANGE" in (unit.get("receipts") or []) for unit in (units or [])
    ) or task_type == "PUBLIC_API":
        classes.append(CHANGE_PUBLIC_API)
    for extra in authorized_change_classes or []:
        if extra in {
            CHANGE_PRODUCTION,
            CHANGE_SECURITY_FINDING,
            CHANGE_DEPENDENCY,
            CHANGE_SECURITY_SENSITIVE,
            CHANGE_PUBLIC_API,
        } and extra not in classes:
            classes.append(extra)
    if not classes:
        classes.append(CHANGE_PRODUCTION)
    return classes


def build_route(
    change_classes: Sequence[str],
    *,
    route_id: str = "default_deterministic_v1",
    tenant_id: str | None = None,
    org_id: str | None = None,
    repository: str | None = None,
    task_id: str | None = None,
    patch_digest: str | None = None,
    rules: Sequence[Mapping[str, Any]] | None = None,
) -> EvidenceRoute:
    selected: list[RouteRule] = []
    for raw in rules or DEFAULT_ROUTE_RULES:
        change = str(raw["when"]["change_class"])
        if change not in change_classes:
            continue
        selected.append(
            RouteRule(
                rule_id=str(raw["rule_id"]),
                when=RouteWhen(change_class=change),  # type: ignore[arg-type]
                providers=[
                    RoutedProvider(
                        provider_id=str(item["provider_id"]),
                        requirement_class=item["requirement_class"],  # type: ignore[arg-type]
                    )
                    for item in raw["providers"]
                ],
            )
        )
    if not selected:
        selected.append(
            RouteRule(
                rule_id="production_source_change",
                when=RouteWhen(change_class="PRODUCTION_SOURCE_CHANGE"),
                providers=[RoutedProvider(provider_id="P1", requirement_class="REQUIRED_PROVIDER")],
            )
        )
    return EvidenceRoute(
        route_id=route_id,
        tenant_id=tenant_id,
        org_id=org_id,
        repository=repository,
        task_id=task_id,
        patch_digest=patch_digest,
        rules=selected,
    )


def routed_providers(route: EvidenceRoute) -> list[RoutedProvider]:
    """Union of providers; REQUIRED wins over OPTIONAL for the same id."""
    by_id: dict[str, RoutedProvider] = {}
    for rule in route.rules:
        for provider in rule.providers:
            existing = by_id.get(provider.provider_id)
            if existing is None or provider.requirement_class == REQUIRED:
                by_id[provider.provider_id] = provider
    return list(by_id.values())
