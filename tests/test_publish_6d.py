"""Slice 6D publish tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_control.approval.dispatch_fix import build_fix_authorization_binding
from agent_control.approval.service import reserve_approval_for_fix
from agent_control.results_ingest import ingest_result_file
from agent_shared.constants import FIX_STATUS_BRANCH_PUBLISHED_PR_FAILED, FIX_STATUS_PR_OPENED_PENDING_CI
from agent_shared.models.approval import FixAuthorizationBinding, WorkItemApproval
from agent_shared.models.fix import FixResult
from agent_shared.models.jobs import RLMJob
from agent_workers.publish.formatters import build_commit_message
from agent_workers.publish.remote import (
    PublishError,
    _stage_allowed_files,
    _validate_push_destination,
    _validate_remote_url,
    publish_fix_branch_and_pr,
    verify_workspace_base_equals_approved,
)
from agent_workers.settings import WorkerSettings
from conftest import sample_plan, seed_plan_completed
from agent_control.approval.service import grant_approval


def _init_git_repo(path: Path, readme: str = "# Demo\n") -> str:
    path.mkdir(parents=True, exist_ok=True)
    (path / "README.md").write_text(readme, encoding="utf-8")
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def _worker_settings(tmp_path: Path) -> WorkerSettings:
    return WorkerSettings(
        redis_url="redis://localhost:6379/0",
        agent_runs_dir=tmp_path / "runs",
        agent_cache_dir=tmp_path / "cache",
        agent_state_root=tmp_path / "state",
        gitea_base_url="http://gitea.local",
        gitea_agent_token="",
        gitea_bot_token="token",
        gitea_agent_comment_enabled=False,
        git_ro_key_path=None,
        model_policy="fake",
        fix_remote_publish_enabled=True,
    )


def _binding() -> FixAuthorizationBinding:
    return FixAuthorizationBinding(
        approval_id="appr-1",
        approval_target_id="WI-0004-abcd1234",
        plan_run_id="run-plan-1",
        plan_hash="planhash",
        blast_radius_hash="brhash",
        allowed_files=["README.md"],
        approved_base_sha="abc123",
        approved_base_ref="main",
    )


def test_publish_stale_base_blocks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    head = _init_git_repo(repo)
    with pytest.raises(PublishError) as exc:
        verify_workspace_base_equals_approved(repo, "deadbeef" * 5)
    assert exc.value.stage == "stale_approval_base"
    verify_workspace_base_equals_approved(repo, head)


def test_publish_commit_trailers() -> None:
    msg = build_commit_message(
        run_id="run-fix-1",
        binding=_binding(),
        approved_base_sha="abc123",
    )
    assert "Agent-Run-ID: run-fix-1" in msg
    assert "Approval-ID: appr-1" in msg
    assert "Blast-Radius-Hash: brhash" in msg
    assert "Approved-Base-SHA: abc123" in msg


def test_publish_dry_run_writes_plan(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    head = _init_git_repo(repo)
    (repo / "README.md").write_text("# Changed\n", encoding="utf-8")
    artifact = tmp_path / "art"
    artifact.mkdir()
    binding = _binding().model_copy(update={"approved_base_sha": head})
    job = RLMJob.model_validate(
        {
            "run_id": "run-dry",
            "job_id": "j1",
            "workflow_id": "run-dry",
            "session_id": "run-dry",
            "workflow_definition": "developer/v1",
            "flow_config_id": "developer",
            "flow_version": "0.1.0",
            "flow_config_schema_version": "v1",
            "project": "ai-sdlc-lab/demo",
            "owner": "ai-sdlc-lab",
            "repo": "demo",
            "repo_url": "http://gitea.local/ai-sdlc-lab/demo.git",
            "primary_branch": "main",
            "policy_ref": "main",
            "base_ref": "main",
            "target_sha": None,
            "task_ref": "main",
            "proposed_agent_branch": "agent/run-dry",
            "trigger_event_id": "t1",
            "trigger_delivery_id": None,
            "trigger_type": "manual",
            "trigger_context": {"event_type": "manual"},
            "flow": "developer",
            "agent": "developer",
            "risk_class": "write_patch",
            "command_intent": {"kind": "fix"},
            "reporting": {},
            "limits": {},
            "safety": {"allow_push": True},
            "model_policy": "fake",
            "state_path": str(tmp_path / "v.json"),
            "fix_authorization": binding.model_dump(mode="json"),
        }
    )
    fix = FixResult.model_validate(
        {
            "schema_version": "fix_result.v1",
            "scope_summary": "test",
            "files_changed": ["README.md"],
            "changes": [
                {"path": "README.md", "edit_kind": "replace", "content": "# Changed\n"},
            ],
            "confidence": "high",
        }
    )
    with patch("agent_workers.publish.remote.run_closed_world_diff_gate") as mock_gate:
        mock_gate.return_value = MagicMock(passed=True, model_dump=lambda mode="json": {"passed": True})
        result = publish_fix_branch_and_pr(
            repo_workspace=repo,
            policy_workspace=repo,
            artifact_root=artifact,
            job=job,
            fix_result=fix,
            settings=_worker_settings(tmp_path),
            dry_run=True,
            gitea_client=MagicMock(),
        )
    assert result.dry_run is True
    assert result.publish_state == "dry_run_passed"
    assert (artifact / "remote_publish_plan.json").is_file()


def test_approval_reservation_on_enqueue(tmp_path: Path) -> None:
    target = seed_plan_completed(tmp_path)
    approval, _, _ = grant_approval(
        tmp_path,
        project="ai-sdlc-lab/agent-control-plane",
        issue_id=4,
        target=target,
        approver_login="owner",
        author_is_owner=True,
    )
    assert approval is not None
    reserved = reserve_approval_for_fix(tmp_path, approval, fix_run_id="run-r1")
    assert reserved.status == "reserved"
    assert reserved.reserved_by_fix_run_id == "run-r1"


def test_ingest_consumes_on_pr_opened(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    target = seed_plan_completed(state)
    approval, _, _ = grant_approval(
        state,
        project="ai-sdlc-lab/agent-control-plane",
        issue_id=4,
        target=target,
        approver_login="owner",
        author_is_owner=True,
    )
    assert approval is not None
    reserve_approval_for_fix(state, approval, fix_run_id="run-ingest-1")
    inbox_dir = state / "inbox" / "ct104-results"
    inbox_dir.mkdir(parents=True)
    payload = {
        "schema_version": "agent_run_completed.v1",
        "run_id": "run-ingest-1",
        "job_id": "j1",
        "workflow_id": "run-ingest-1",
        "session_id": "run-ingest-1",
        "trigger_event_id": "t1",
        "project": "ai-sdlc-lab/agent-control-plane",
        "flow": "developer",
        "agent": "developer",
        "risk_class": "write_patch",
        "status": "completed",
        "terminal_status": "completed",
        "summary": "published",
        "artifact_root": "/tmp",
        "command_kind": "fix",
        "issue_id": 4,
        "approval_id": approval.approval_id,
        "approval_target_id": approval.approval_target_id,
        "fix_status": FIX_STATUS_PR_OPENED_PENDING_CI,
        "opened_pr_number": 42,
        "agent_branch": "agent/run-ingest-1",
    }
    inbox = inbox_dir / "run-ingest-1.json"
    inbox.write_text(json.dumps(payload), encoding="utf-8")
    ingest_result_file(state, inbox)
    from agent_control.approval.storage import load_approval

    stored = load_approval(state, "ai-sdlc-lab/agent-control-plane", target)
    assert stored is not None
    assert stored.status == "consumed"


def test_publish_status_names_not_verified() -> None:
    from agent_workers.formatters.fix_comment import render_fix_published_comment
    from agent_shared.models.publish import RemotePublishResult

    fix = FixResult.model_validate(
        {
            "schema_version": "fix_result.v1",
            "scope_summary": "s",
            "files_changed": ["README.md"],
            "changes": [],
            "confidence": "high",
        }
    )
    pub = RemotePublishResult(
        publish_state="pr_opened",
        agent_branch="agent/run-x",
        base_ref="main",
        opened_pr_number=1,
        opened_pr_url="http://gitea/pr/1",
    )
    text = render_fix_published_comment(fix, publish=pub)
    assert "Not verified" in text
    assert "ci_verified" not in text.lower() or "pending" in text.lower()


def _fix_job(tmp_path: Path, *, head: str, run_id: str = "run-pub") -> RLMJob:
    binding = _binding().model_copy(update={"approved_base_sha": head})
    return RLMJob.model_validate(
        {
            "run_id": run_id,
            "job_id": "j1",
            "workflow_id": run_id,
            "session_id": run_id,
            "workflow_definition": "developer/v1",
            "flow_config_id": "developer",
            "flow_version": "0.1.0",
            "flow_config_schema_version": "v1",
            "project": "ai-sdlc-lab/demo",
            "owner": "ai-sdlc-lab",
            "repo": "demo",
            "repo_url": "http://gitea.local/ai-sdlc-lab/demo.git",
            "primary_branch": "main",
            "policy_ref": "main",
            "base_ref": "main",
            "target_sha": None,
            "task_ref": "main",
            "proposed_agent_branch": f"agent/{run_id}",
            "trigger_event_id": "t1",
            "trigger_delivery_id": None,
            "trigger_type": "manual",
            "trigger_context": {"event_type": "manual"},
            "flow": "developer",
            "agent": "developer",
            "risk_class": "write_patch",
            "command_intent": {"kind": "fix"},
            "reporting": {},
            "limits": {},
            "safety": {"allow_push": True},
            "model_policy": "fake",
            "state_path": str(tmp_path / "v.json"),
            "fix_authorization": binding.model_dump(mode="json"),
        }
    )


def _fix_result() -> FixResult:
    return FixResult.model_validate(
        {
            "schema_version": "fix_result.v1",
            "scope_summary": "test",
            "files_changed": ["README.md"],
            "changes": [
                {"path": "README.md", "edit_kind": "replace", "content": "# Changed\n"},
            ],
            "confidence": "high",
        }
    )


def _mock_gitea_for_publish(*, head: str, agent_remote: str | None = None, main_tips: list[str] | None = None):
    tips = list(main_tips or [head])
    tip_idx = {"i": 0}

    def get_sha(_owner: str, _repo: str, branch: str) -> str | None:
        if branch == "main":
            idx = min(tip_idx["i"], len(tips) - 1)
            tip_idx["i"] += 1
            return tips[idx]
        if branch.startswith("agent/"):
            return agent_remote
        return None

    mock = MagicMock()
    mock.get_branch_sha.side_effect = get_sha
    mock.list_pull_requests.return_value = []
    return mock


def test_publish_branch_exists_different_head_blocks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    head = _init_git_repo(repo)
    (repo / "README.md").write_text("# Changed\n", encoding="utf-8")
    artifact = tmp_path / "art"
    artifact.mkdir()
    job = _fix_job(tmp_path, head=head, run_id="run-branch-clash")
    mock_client = _mock_gitea_for_publish(head=head, agent_remote="deadbeef" * 5)
    with patch("agent_workers.publish.remote.run_closed_world_diff_gate") as mock_gate:
        mock_gate.return_value = MagicMock(passed=True, model_dump=lambda mode="json": {"passed": True})
        with pytest.raises(PublishError) as exc:
            publish_fix_branch_and_pr(
                repo_workspace=repo,
                policy_workspace=repo,
                artifact_root=artifact,
                job=job,
                fix_result=_fix_result(),
                settings=_worker_settings(tmp_path),
                gitea_client=mock_client,
            )
    assert exc.value.stage == "branch_push"
    assert "exists at" in str(exc.value)


def test_publish_push_succeeds_pr_fails_partial_state(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    head = _init_git_repo(repo)
    (repo / "README.md").write_text("# Changed\n", encoding="utf-8")
    artifact = tmp_path / "art"
    artifact.mkdir()
    job = _fix_job(tmp_path, head=head, run_id="run-pr-fail")
    mock_client = _mock_gitea_for_publish(head=head)
    mock_client.create_pull_request.side_effect = RuntimeError("PR API down")

    import agent_workers.publish.remote as remote_mod

    real_git_run = remote_mod._git_run

    def fake_git_run(repo_root: Path, cmd: list[str], *, env: dict[str, str] | None = None):
        if len(cmd) >= 2 and cmd[0] == "git" and cmd[1] == "push":
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return real_git_run(repo_root, cmd, env=env)

    with patch("agent_workers.publish.remote.run_closed_world_diff_gate") as mock_gate:
        mock_gate.return_value = MagicMock(passed=True, model_dump=lambda mode="json": {"passed": True})
        with patch("agent_workers.publish.remote._git_run", side_effect=fake_git_run):
            with patch(
                "agent_workers.publish.remote.resolve_authenticated_repo_url",
                return_value="http://gitea.local/ai-sdlc-lab/demo.git",
            ):
                with pytest.raises(PublishError) as exc:
                    publish_fix_branch_and_pr(
                        repo_workspace=repo,
                        policy_workspace=repo,
                        artifact_root=artifact,
                        job=job,
                        fix_result=_fix_result(),
                        settings=_worker_settings(tmp_path),
                        gitea_client=mock_client,
                    )
    assert exc.value.stage == "pr_open"
    assert exc.value.partial is not None
    assert exc.value.partial.publish_state == "publish_failed_partial"
    partial_path = artifact / "remote_publish_result.json"
    assert partial_path.is_file()
    partial = json.loads(partial_path.read_text(encoding="utf-8"))
    assert partial["publish_state"] == "publish_failed_partial"

    state = tmp_path / "state"
    state.mkdir()
    target = seed_plan_completed(state)
    approval, _, _ = grant_approval(
        state,
        project="ai-sdlc-lab/agent-control-plane",
        issue_id=4,
        target=target,
        approver_login="owner",
        author_is_owner=True,
    )
    assert approval is not None
    reserve_approval_for_fix(state, approval, fix_run_id="run-pr-fail")
    inbox_dir = state / "inbox" / "ct104-results"
    inbox_dir.mkdir(parents=True)
    payload = {
        "schema_version": "agent_run_completed.v1",
        "run_id": "run-pr-fail",
        "job_id": "j1",
        "workflow_id": "run-pr-fail",
        "session_id": "run-pr-fail",
        "trigger_event_id": "t1",
        "project": "ai-sdlc-lab/agent-control-plane",
        "flow": "developer",
        "agent": "developer",
        "risk_class": "write_patch",
        "status": "completed",
        "terminal_status": "failed_publish_partial",
        "summary": "partial",
        "artifact_root": str(artifact),
        "command_kind": "fix",
        "issue_id": 4,
        "approval_id": approval.approval_id,
        "approval_target_id": approval.approval_target_id,
        "fix_status": FIX_STATUS_BRANCH_PUBLISHED_PR_FAILED,
        "agent_branch": "agent/run-pr-fail",
    }
    inbox = inbox_dir / "run-pr-fail.json"
    inbox.write_text(json.dumps(payload), encoding="utf-8")
    ingest_result_file(state, inbox)
    from agent_control.approval.storage import load_approval

    stored = load_approval(state, "ai-sdlc-lab/agent-control-plane", target)
    assert stored is not None
    assert stored.status == "reserved"


def test_publish_staged_files_subset(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / "README.md").write_text("# Changed\n", encoding="utf-8")
    staged = _stage_allowed_files(repo, ["README.md"])
    assert staged == ["README.md"]


def test_publish_unstaged_side_effect_blocks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / "README.md").write_text("# Changed\n", encoding="utf-8")
    (repo / "evil.txt").write_text("bad\n", encoding="utf-8")
    with pytest.raises(PublishError) as exc:
        _stage_allowed_files(repo, ["README.md"])
    assert "outside allowlist" in str(exc.value)


def test_publish_remote_host_guard() -> None:
    with pytest.raises(PublishError) as exc:
        _validate_remote_url("https://evil.example/repo.git", "http://gitea.local")
    assert exc.value.stage == "branch_push"
    _validate_remote_url("http://gitea.local/ai-sdlc-lab/demo.git", "http://gitea.local")
