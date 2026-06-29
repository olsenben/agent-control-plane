"""Capture repo base SHA at approval time (Slice 6D)."""

from __future__ import annotations

from agent_control.config import Settings, get_settings
from agent_control.gitea_client import GiteaClient
from agent_control.project_registry import resolve_project
from agent_shared.project_ids import split_project


def resolve_approval_base_refs(
    project: str,
    *,
    settings: Settings | None = None,
) -> tuple[str, str | None]:
    """Return (approved_base_ref, approved_base_sha) for the primary/default branch tip."""
    settings = settings or get_settings()
    cfg = resolve_project(project, settings=settings)
    approved_base_ref = cfg.default_branch or "main"
    client = GiteaClient(settings)
    owner, repo = split_project(project)
    sha: str | None = None
    try:
        sha = client.get_branch_sha(owner, repo, approved_base_ref)
    except Exception:
        sha = None
    return approved_base_ref, sha
