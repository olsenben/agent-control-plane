"""Authorization evaluation helpers (V6 T05)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from agent_control.config import Settings, get_settings
from agent_control.events import AgentEvent, append_event, deterministic_event_id
from agent_control.project_identity import canonical_project
from agent_control.project_registry import is_approval_authority
from agent_shared.models.authorization_decision import (
    AuthorizationDecision,
    evaluate_authorization,
)

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def check_user_repo_permission(
    project: str,
    username: str,
    *,
    need: str = "read",
    settings: Settings | None = None,
) -> bool:
    """Gitea collaborator/permission check — fail closed when API unavailable."""
    settings = settings or get_settings()
    if not settings.gitea_bot_token or not username:
        return False
    try:
        from agent_control.gitea_client import GiteaClient

        owner, repo = project.split("/", 1)
        client = GiteaClient(settings)
        return client.user_has_repo_permission(owner, repo, username, need=need)
    except Exception:
        logger.warning("repo_permission_check_failed project=%s user=%s need=%s", project, username, need)
        return False


def evaluate_command_authorization(
    *,
    command_kind: str,
    project: str,
    invoker_login: str,
    source_sha: str = "",
    policy_source_sha: str = "",
    policy_permits: bool = True,
    policy_reason: str = "",
    approval_valid: bool = True,
    approval_reason: str = "",
    approver_login: str | None = None,
    require_bot_write: bool = False,
    run_id: str | None = None,
    session_id: str | None = None,
    settings: Settings | None = None,
) -> AuthorizationDecision:
    settings = settings or get_settings()
    kind = (command_kind or "").lower()
    invoker_is_approver = is_approval_authority(invoker_login, project, settings=settings)
    invoker_can_read = check_user_repo_permission(project, invoker_login, need="read", settings=settings)
    acting = (settings.gitea_acting_identity or "agent-bot").strip() or "agent-bot"
    bot_can_write = True
    if require_bot_write:
        bot_can_write = check_user_repo_permission(project, acting, need="write", settings=settings)

    require_approver = kind in ("approve", "reject", "publish")
    effective_approver = approver_login or (invoker_login if kind in ("approve", "reject") else None)
    approver_is_authority = (
        is_approval_authority(effective_approver, project, settings=settings)
        if effective_approver
        else False
    )
    return evaluate_authorization(
        command_kind=kind,
        project=project,
        invoker_login=invoker_login,
        invoker_can_read=invoker_can_read,
        invoker_is_approver=invoker_is_approver,
        approver_login=effective_approver,
        acting_identity=acting,
        bot_can_write=bot_can_write,
        policy_permits=policy_permits,
        policy_reason=policy_reason,
        approval_valid=approval_valid,
        approval_reason=approval_reason,
        source_sha=source_sha,
        policy_source_sha=policy_source_sha,
        require_approver=require_approver,
        require_bot_write=require_bot_write,
        approver_is_authority=approver_is_authority,
        run_id=run_id,
        session_id=session_id,
    )


def append_authorization_decision(
    state_root: Path,
    decision: AuthorizationDecision,
) -> tuple[Path, bool]:
    delivery = (
        f"{decision.session_id or 'none'}:{decision.run_id or 'none'}:"
        f"{decision.command_kind}:{decision.decision}:{decision.checked_at}"
    )
    event_type = "agent.authorization_decision"
    event_id = deterministic_event_id("ct103", delivery, event_type)
    event = AgentEvent(
        event_id=event_id,
        type=event_type,
        raw_event_type=event_type,
        source="ct103",
        delivery_id=delivery,
        project=canonical_project(decision.project),
        payload=decision.model_dump(mode="json"),
        recorded_at=_now(),
    )
    return append_event(state_root, event)


def recheck_publish_authorization(
    *,
    project: str,
    invoker_login: str,
    approver_login: str | None,
    source_sha: str,
    policy_source_sha: str = "",
    approval_valid: bool,
    approval_reason: str = "",
    run_id: str | None = None,
    session_id: str | None = None,
    settings: Settings | None = None,
) -> AuthorizationDecision:
    """Mutation-critical recheck immediately before publish."""
    return evaluate_command_authorization(
        command_kind="publish",
        project=project,
        invoker_login=invoker_login,
        source_sha=source_sha,
        policy_source_sha=policy_source_sha,
        policy_permits=True,
        approval_valid=approval_valid,
        approval_reason=approval_reason,
        approver_login=approver_login,
        require_bot_write=True,
        run_id=run_id,
        session_id=session_id,
        settings=settings,
    )
