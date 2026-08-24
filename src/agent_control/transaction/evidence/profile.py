"""verification_profile.v1 load and required-workflow resolution.

Durability closeout gap: register_pending_ci defaulted required_workflows=[].
Profiles supply a required workflow identity without weakening exact-SHA bind.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from agent_control.project_identity import canonical_project
from agent_shared.models.ci import RequiredWorkflow
from agent_shared.models.verification_profile import VerificationProfile, VerificationProfileCatalog

_CONFIG_CANDIDATES = (
    Path(__file__).resolve().parents[4] / "config" / "verification_profiles.yaml",
    Path("/opt/ai-sdlc-lab/agent-control-plane/config/verification_profiles.yaml"),
    Path("/app/config/verification_profiles.yaml"),
    Path.cwd() / "config" / "verification_profiles.yaml",
)


class VerificationProfileError(ValueError):
    """Invalid or missing verification profile catalog."""


def default_catalog_path() -> Path:
    for candidate in _CONFIG_CANDIDATES:
        if candidate.is_file():
            return candidate
    return _CONFIG_CANDIDATES[0]


def load_verification_profile_catalog(path: Path | None = None) -> VerificationProfileCatalog:
    cfg = path or default_catalog_path()
    if not cfg.is_file():
        raise VerificationProfileError(f"verification profile catalog missing: {cfg}")
    raw = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise VerificationProfileError("VERIFICATION_PROFILE_NOT_A_MAPPING")
    try:
        return VerificationProfileCatalog.model_validate(raw)
    except Exception as exc:  # noqa: BLE001 - fail closed on schema
        raise VerificationProfileError(f"VERIFICATION_PROFILE_SCHEMA_INVALID:{exc}") from exc


def profile_for_repository(
    repository: str,
    *,
    catalog: VerificationProfileCatalog | None = None,
    path: Path | None = None,
) -> VerificationProfile | None:
    try:
        repo = canonical_project(repository)
    except ValueError:
        return None
    loaded = catalog or load_verification_profile_catalog(path)
    for profile in loaded.profiles:
        if profile.repository == repo:
            return profile
    return None


def required_workflows_for_repository(
    repository: str,
    *,
    catalog: VerificationProfileCatalog | None = None,
    path: Path | None = None,
) -> list[RequiredWorkflow]:
    """Return profile workflows, or [] when no profile exists (fail-closed matrix)."""
    try:
        profile = profile_for_repository(repository, catalog=catalog, path=path)
    except VerificationProfileError:
        return []
    if profile is None:
        return []
    return [
        RequiredWorkflow(
            workflow_id=item.workflow_id,
            path=item.path,
            display_name=item.display_name or item.workflow_id or item.path,
            source=item.source,
        )
        for item in profile.required_workflows
    ]


def profile_as_dict(profile: VerificationProfile) -> dict[str, Any]:
    return profile.model_dump(mode="json")
