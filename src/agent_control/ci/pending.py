"""Pending CI index — repo + exact head_commit_sha correlation (Slice 6E.1)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from agent_control.project_identity import canonical_project, sanitize_path_segment
from agent_shared.models.ci import PendingCiRecord, RequiredWorkflow
from agent_shared.repo_identity import split_repo_full_name


def pending_ci_dir(state_root: Path, project: str) -> Path:
    repo_full = canonical_project(project)
    owner, repo = split_repo_full_name(repo_full)
    return (
        state_root
        / "projects"
        / sanitize_path_segment(owner)
        / sanitize_path_segment(repo)
        / "pending_ci"
    )


def pending_ci_path(state_root: Path, project: str, fix_run_id: str) -> Path:
    return pending_ci_dir(state_root, project) / f"{sanitize_path_segment(fix_run_id)}.json"


def sha_index_path(state_root: Path, project: str, head_sha: str) -> Path:
    """Secondary index: exact SHA → fix_run_id (supports supersession lookups)."""
    return pending_ci_dir(state_root, project) / "by_sha" / f"{sanitize_path_segment(head_sha)}.json"


def save_pending_ci(state_root: Path, record: PendingCiRecord) -> Path:
    path = pending_ci_path(state_root, record.repository, record.fix_run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = record.model_dump_json(indent=2)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)

    idx = sha_index_path(state_root, record.repository, record.expected_head_commit_sha)
    idx.parent.mkdir(parents=True, exist_ok=True)
    idx_body = json.dumps(
        {
            "fix_run_id": record.fix_run_id,
            "expected_head_commit_sha": record.expected_head_commit_sha,
            "current_verdict": record.current_verdict,
        },
        indent=2,
    )
    idx_tmp = idx.with_suffix(".json.tmp")
    idx_tmp.write_text(idx_body, encoding="utf-8")
    os.replace(idx_tmp, idx)
    return path


def load_pending_ci(state_root: Path, project: str, fix_run_id: str) -> PendingCiRecord | None:
    path = pending_ci_path(state_root, project, fix_run_id)
    if not path.is_file():
        return None
    try:
        return PendingCiRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValueError):
        return None


def find_pending_by_repo_sha(
    state_root: Path,
    repository: str,
    head_sha: str,
) -> PendingCiRecord | None:
    """Exact-SHA correlate. Wrong SHA → None. Same SHA other repo → None."""
    if not head_sha or not repository:
        return None

    def _scan_fallback() -> PendingCiRecord | None:
        for record in list_pending_ci(state_root, repository, include_terminal=True):
            if (
                record.expected_head_commit_sha == head_sha
                and record.current_verdict not in ("superseded", "expired")
            ):
                return record
        return None

    idx = sha_index_path(state_root, repository, head_sha)
    if not idx.is_file():
        return _scan_fallback()
    try:
        data = json.loads(idx.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _scan_fallback()
    run_id = data.get("fix_run_id")
    if not run_id:
        return _scan_fallback()
    record = load_pending_ci(state_root, repository, str(run_id))
    if record is None:
        return _scan_fallback()
    if record.expected_head_commit_sha != head_sha:
        return None
    if record.repository != canonical_project(repository):
        return None
    return record


def list_pending_ci(
    state_root: Path,
    project: str | None = None,
    *,
    include_terminal: bool = False,
) -> list[PendingCiRecord]:
    roots: list[Path] = []
    if project:
        roots.append(pending_ci_dir(state_root, project))
    else:
        projects = state_root / "projects"
        if projects.is_dir():
            for owner_dir in projects.iterdir():
                if not owner_dir.is_dir():
                    continue
                for repo_dir in owner_dir.iterdir():
                    pending = repo_dir / "pending_ci"
                    if pending.is_dir():
                        roots.append(pending)

    items: list[PendingCiRecord] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.json")):
            if path.name.endswith(".tmp") or path.parent.name == "by_sha":
                continue
            try:
                record = PendingCiRecord.model_validate(
                    json.loads(path.read_text(encoding="utf-8"))
                )
            except (json.JSONDecodeError, ValueError):
                continue
            if not include_terminal and record.current_verdict in (
                "verified",
                "superseded",
                "expired",
            ):
                continue
            items.append(record)
    return items


def register_pending_ci(
    state_root: Path,
    *,
    fix_run_id: str,
    repository: str,
    expected_head_commit_sha: str,
    opened_pr_number: int | None = None,
    issue_id: int | None = None,
    agent_branch: str | None = None,
    required_workflows: list[RequiredWorkflow] | None = None,
    artifact_root: str | None = None,
) -> PendingCiRecord:
    """Register pending fix for CI observation. Supersedes older pending with same PR/repo."""
    repo = canonical_project(repository)
    now = datetime.now(timezone.utc).isoformat()
    workflows = list(required_workflows or [])
    if not workflows:
        from agent_control.transaction.evidence.profile import required_workflows_for_repository

        workflows = required_workflows_for_repository(repo)

    # Supersede older pending records for same PR when SHA advances
    if opened_pr_number is not None:
        for existing in list_pending_ci(state_root, repo, include_terminal=True):
            if (
                existing.opened_pr_number == opened_pr_number
                and existing.expected_head_commit_sha != expected_head_commit_sha
                and existing.current_verdict == "pending"
            ):
                existing.current_verdict = "superseded"
                existing.superseded_by_sha = expected_head_commit_sha
                save_pending_ci(state_root, existing)

    record = PendingCiRecord(
        fix_run_id=fix_run_id,
        repository=repo,
        expected_head_commit_sha=expected_head_commit_sha,
        opened_pr_number=opened_pr_number,
        issue_id=issue_id,
        agent_branch=agent_branch,
        required_workflows=list(workflows),
        created_at=now,
        current_verdict="pending",
        artifact_root=artifact_root,
    )
    save_pending_ci(state_root, record)
    _project_waiting_for_ci(state_root, record)
    return record


def _project_waiting_for_ci(state_root: Path, record: PendingCiRecord) -> None:
    """Drive session comment → WaitingForCI when CI is registered (QA F-10)."""
    try:
        from agent_control.observe.comment_projection import project_session_comment
        from agent_control.session.storage import load_session_by_run

        session = load_session_by_run(state_root, record.repository, record.fix_run_id)
        if session is None:
            return
        # Mark reason so display_status_from_session can map running→waiting_for_ci.
        code = (session.terminal_reason_code or "").lower()
        if "ci" not in code:
            session = session.model_copy(
                update={
                    "terminal_reason_code": "waiting_for_ci",
                    "terminal_reason": session.terminal_reason or "Waiting for CT102 CI",
                }
            )
        project_session_comment(
            state_root,
            session,
            run_id=record.fix_run_id,
            command=session.command_kind or "fix",
            display_status="waiting_for_ci",
            issue_number=record.issue_id or session.subject_number,
        )
    except Exception:
        import logging

        logging.getLogger(__name__).exception(
            "waiting_for_ci_projection_failed run=%s", record.fix_run_id
        )
