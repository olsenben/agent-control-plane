"""Remote branch push + PR publish (Slice 6D)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from agent_control.git_auth import git_non_interactive_env, resolve_authenticated_repo_url
from agent_control.gitea_client import GiteaClient
from agent_shared.constants import (
    FIX_STATUS_BRANCH_PUBLISHED_PR_FAILED,
    FIX_STATUS_LOCAL_PATCH_PASSED,
    FIX_STATUS_PR_OPENED_PENDING_CI,
    FIX_STATUS_PUBLISH_FAILED,
)
from agent_shared.models.approval import FixAuthorizationBinding
from agent_shared.models.fix import FixResult
from agent_shared.models.jobs import RLMJob
from agent_shared.models.publish import RemotePublishResult
from agent_shared.project_ids import split_project
from agent_workers.gates.runner import collect_changed_files, run_closed_world_diff_gate
from agent_workers.publish.formatters import build_commit_message, build_pr_body
from agent_workers.publish.safe_write import redact_publish_text, write_redacted_json
from agent_workers.settings import WorkerSettings

_PROTECTED_BASES = frozenset({"main", "master"})


class PublishError(Exception):
    def __init__(self, stage: str, message: str, *, partial: RemotePublishResult | None = None):
        self.stage = stage
        self.partial = partial
        super().__init__(redact_publish_text(message))


def _git_run(repo_root: Path, cmd: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _git_head(repo_root: Path) -> str:
    proc = _git_run(repo_root, ["git", "rev-parse", "HEAD"])
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def verify_workspace_base_equals_approved(repo_root: Path, approved_base_sha: str | None) -> None:
    """Before publish commit: workspace HEAD must equal approved_base_sha exactly."""
    if not approved_base_sha:
        return
    head = _git_head(repo_root)
    if head != approved_base_sha:
        raise PublishError(
            "stale_approval_base",
            f"Workspace HEAD {head} does not equal approved base {approved_base_sha}",
        )


def verify_remote_base_unchanged(
    client: GiteaClient,
    owner: str,
    repo: str,
    approved_base_ref: str,
    approved_base_sha: str | None,
) -> None:
    """Before push and before PR open: remote primary branch tip must equal approved_base_sha."""
    if not approved_base_sha:
        return
    try:
        remote_tip = client.get_branch_sha(owner, repo, approved_base_ref)
    except Exception as exc:
        raise PublishError(
            "stale_approval_base",
            f"Cannot read remote {approved_base_ref}: {exc}",
        ) from exc
    if remote_tip != approved_base_sha:
        raise PublishError(
            "stale_approval_base",
            f"Remote {approved_base_ref} advanced from {approved_base_sha} to {remote_tip}",
        )


def _validate_remote_url(repo_url: str, allowed_host: str) -> None:
    parsed = urlparse(repo_url)
    host = (parsed.hostname or "").lower()
    allowed = urlparse(allowed_host if "://" in allowed_host else f"https://{allowed_host}")
    allowed_hostname = (allowed.hostname or "").lower()
    if host != allowed_hostname:
        raise PublishError("branch_push", f"Remote host {host!r} not allowed (expected {allowed_hostname!r})")


def _resolve_pr_base_ref(binding: FixAuthorizationBinding, job: RLMJob) -> str:
    configured = job.primary_branch or job.base_ref or "main"
    base_ref = binding.approved_base_ref or configured
    if base_ref != configured:
        raise PublishError(
            "branch_push",
            f"PR base {base_ref!r} must equal configured primary_branch {configured!r}",
        )
    return base_ref


def _validate_push_destination(agent_branch: str, base_ref: str) -> str:
    if not agent_branch.startswith("agent/"):
        raise PublishError("branch_push", f"Invalid agent branch: {agent_branch}")
    if agent_branch == base_ref or agent_branch in _PROTECTED_BASES:
        raise PublishError("branch_push", "Direct push to PR base or protected branch is forbidden")
    return f"refs/heads/{agent_branch}"


def _stage_allowed_files(repo_root: Path, allowed_files: list[str]) -> list[str]:
    changed = collect_changed_files(repo_root)
    to_stage = [p for p in changed if p in allowed_files]
    if not to_stage:
        raise PublishError("branch_push", "No allowed changed files to stage")
    cmd = ["git", "add", "-A", "--", *to_stage]
    proc = _git_run(repo_root, cmd)
    if proc.returncode != 0:
        raise PublishError("branch_push", redact_publish_text(proc.stderr or "git add failed"))
    staged_proc = _git_run(repo_root, ["git", "diff", "--cached", "--name-only"])
    staged = [line.strip() for line in staged_proc.stdout.splitlines() if line.strip()]
    allowed_set = set(allowed_files)
    extra_staged = [p for p in staged if p not in allowed_set]
    if extra_staged:
        raise PublishError("branch_push", f"Staged files outside allowlist: {extra_staged}")
    status_proc = _git_run(repo_root, ["git", "status", "--porcelain=v1"])
    for line in status_proc.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path not in allowed_set and path not in staged:
            raise PublishError("branch_push", f"Unstaged side effect outside allowlist: {path}")
    return staged


def _ensure_origin(repo_root: Path, repo_url: str, env: dict[str, str]) -> None:
    proc = _git_run(repo_root, ["git", "remote", "get-url", "origin"], env=env)
    if proc.returncode != 0:
        add = _git_run(repo_root, ["git", "remote", "add", "origin", repo_url], env=env)
        if add.returncode != 0:
            raise PublishError("branch_push", redact_publish_text(add.stderr or "git remote add failed"))
    else:
        set_url = _git_run(repo_root, ["git", "remote", "set-url", "origin", repo_url], env=env)
        if set_url.returncode != 0:
            raise PublishError("branch_push", redact_publish_text(set_url.stderr or "git remote set-url failed"))


def push_repair_fast_forward(
    *,
    repo_workspace: Path,
    agent_branch: str,
    expected_remote_sha: str,
    repository: str,
    repo_url: str,
    settings: WorkerSettings,
    gitea_client: GiteaClient | None = None,
) -> dict[str, str | bool | None | list[str]]:
    """Non-force push of a repair commit onto an existing agent/* branch.

    Requires remote tip == ``expected_remote_sha`` and local HEAD to be a
    fast-forward of that tip. Never force-pushes. On non-FF rejection returns
    ``stale=True`` with reason ``push_rejected`` / ``remote_head_changed``.
    """
    if not agent_branch.startswith("agent/"):
        return {"ok": False, "stale": False, "reason_codes": ["branch_policy"]}
    if agent_branch in _PROTECTED_BASES:
        return {"ok": False, "stale": False, "reason_codes": ["protected_branch"]}

    client = gitea_client or GiteaClient()
    try:
        owner, repo = split_project(repository)
    except Exception:
        return {"ok": False, "stale": False, "reason_codes": ["repo_identity_invalid"]}

    try:
        remote_tip = client.get_branch_sha(owner, repo, agent_branch)
    except Exception:
        return {"ok": False, "stale": False, "reason_codes": ["api_unavailable"]}

    if remote_tip != expected_remote_sha:
        return {
            "ok": False,
            "stale": True,
            "reason": "remote_head_changed",
            "observed_head": remote_tip,
        }

    local_head = _git_head(repo_workspace)
    if not local_head:
        return {"ok": False, "stale": False, "reason_codes": ["local_head_missing"]}

    ancestor = _git_run(
        repo_workspace,
        ["git", "merge-base", "--is-ancestor", expected_remote_sha, local_head],
    )
    if ancestor.returncode != 0:
        return {"ok": False, "stale": False, "reason_codes": ["not_fast_forward_local"]}

    if local_head == expected_remote_sha:
        return {"ok": True, "new_head_commit_sha": local_head, "skipped_identical": True}

    auth_url = resolve_authenticated_repo_url(repo_url)
    try:
        _validate_remote_url(auth_url, settings.gitea_base_url)
    except PublishError as exc:
        return {
            "ok": False,
            "stale": False,
            "reason_codes": ["remote_host_rejected"],
            "detail": str(exc),
        }

    env = git_non_interactive_env(repo_url=auth_url)
    try:
        _ensure_origin(repo_workspace, auth_url, env)
    except PublishError as exc:
        return {"ok": False, "stale": False, "reason_codes": ["origin_failed"], "detail": str(exc)}

    push_ref = f"refs/heads/{agent_branch}"
    push = _git_run(
        repo_workspace,
        ["git", "push", "origin", f"HEAD:{push_ref}"],
        env=env,
    )
    if push.returncode != 0:
        err = (push.stderr or push.stdout or "").lower()
        if "non-fast-forward" in err or "fetch first" in err or "rejected" in err:
            return {
                "ok": False,
                "stale": True,
                "reason": "push_rejected",
                "observed_head": None,
            }
        return {
            "ok": False,
            "stale": False,
            "reason_codes": ["push_failed"],
            "detail": redact_publish_text(push.stderr or "git push failed"),
        }

    return {"ok": True, "new_head_commit_sha": local_head}


def _write_publish_artifact(artifact_root: Path, result: RemotePublishResult) -> None:
    write_redacted_json(artifact_root / "remote_publish_result.json", result.model_dump(mode="json"))


def publish_fix_branch_and_pr(
    *,
    repo_workspace: Path,
    policy_workspace: Path,
    artifact_root: Path,
    job: RLMJob,
    fix_result: FixResult,
    settings: WorkerSettings,
    dry_run: bool = False,
    resume_pr: bool = False,
    gitea_client: GiteaClient | None = None,
) -> RemotePublishResult:
    binding_raw = job.fix_authorization
    if binding_raw is None:
        raise PublishError("branch_push", "Missing fix_authorization binding")
    binding = (
        binding_raw
        if isinstance(binding_raw, FixAuthorizationBinding)
        else FixAuthorizationBinding.model_validate(binding_raw)
    )
    branch = job.proposed_agent_branch or f"agent/{job.run_id}"
    base_ref = _resolve_pr_base_ref(binding, job)
    approved_base = binding.approved_base_sha
    approved_base_ref = binding.approved_base_ref or base_ref
    push_ref = _validate_push_destination(branch, base_ref)

    owner, repo = split_project(job.project)
    client = gitea_client or GiteaClient()
    remote_branch_preexisting = False
    existing_pr_reused = False
    head_sha: str | None = None

    if not resume_pr:
        verify_workspace_base_equals_approved(repo_workspace, approved_base)
        job_dict = job.model_dump(mode="json")
        run_closed_world_diff_gate(
            repo_root=repo_workspace,
            policy_workspace=policy_workspace,
            artifact_root=artifact_root,
            job=job_dict,
            fix_ci_hints=list(fix_result.ci_hints),
        )

    if dry_run:
        plan = RemotePublishResult(
            publish_state="dry_run_passed",
            agent_branch=branch,
            base_ref=base_ref,
            approved_base_sha=approved_base,
            dry_run=True,
            messages=["Dry run — no remote writes"],
        )
        write_redacted_json(artifact_root / "remote_publish_plan.json", plan.model_dump(mode="json"))
        return plan

    existing_remote_sha: str | None = None
    try:
        existing_remote_sha = client.get_branch_sha(owner, repo, branch)
        remote_branch_preexisting = True
    except Exception:
        existing_remote_sha = None

    if not resume_pr:
        checkout = _git_run(repo_workspace, ["git", "checkout", "-B", branch])
        if checkout.returncode != 0:
            raise PublishError("branch_push", redact_publish_text(checkout.stderr or "git checkout failed"))
        verify_workspace_base_equals_approved(repo_workspace, approved_base)
        _stage_allowed_files(repo_workspace, list(binding.allowed_files))
        commit_msg = build_commit_message(
            run_id=job.run_id,
            binding=binding,
            approved_base_sha=approved_base,
        )
        commit = _git_run(
            repo_workspace,
            ["git", "commit", "-m", commit_msg],
        )
        if commit.returncode != 0:
            if "nothing to commit" in (commit.stdout + commit.stderr).lower():
                head_sha = _git_head(repo_workspace)
            else:
                raise PublishError("branch_push", redact_publish_text(commit.stderr or "git commit failed"))
        else:
            head_sha = _git_head(repo_workspace)
    else:
        publish_path = artifact_root / "remote_publish_result.json"
        if publish_path.is_file():
            prior = json.loads(publish_path.read_text(encoding="utf-8"))
            head_sha = prior.get("head_commit_sha")
        if not head_sha:
            head_sha = _git_head(repo_workspace)

    if existing_remote_sha and head_sha and existing_remote_sha != head_sha:
        raise PublishError(
            "branch_push",
            f"Remote branch {branch} exists at {existing_remote_sha}, local head {head_sha}",
        )

    verify_remote_base_unchanged(client, owner, repo, approved_base_ref, approved_base)

    if not (existing_remote_sha and head_sha and existing_remote_sha == head_sha):
        auth_url = resolve_authenticated_repo_url(job.repo_url)
        _validate_remote_url(auth_url, settings.gitea_base_url)
        env = git_non_interactive_env(repo_url=auth_url)
        _ensure_origin(repo_workspace, auth_url, env)
        push = _git_run(
            repo_workspace,
            ["git", "push", "origin", f"HEAD:{push_ref}"],
            env=env,
        )
        if push.returncode != 0:
            partial = RemotePublishResult(
                publish_state="publish_failed",
                agent_branch=branch,
                base_ref=base_ref,
                head_commit_sha=head_sha,
                approved_base_sha=approved_base,
                remote_branch_preexisting=remote_branch_preexisting,
            )
            raise PublishError(
                "branch_push",
                redact_publish_text(push.stderr or "git push failed"),
                partial=partial,
            )

    head_sha = head_sha or client.get_branch_sha(owner, repo, branch)

    try:
        verify_remote_base_unchanged(client, owner, repo, approved_base_ref, approved_base)
    except PublishError as exc:
        partial = RemotePublishResult(
            publish_state="publish_failed_partial",
            agent_branch=branch,
            base_ref=base_ref,
            head_commit_sha=head_sha,
            approved_base_sha=approved_base,
            remote_branch_preexisting=remote_branch_preexisting or True,
            messages=[str(exc)],
        )
        _write_publish_artifact(artifact_root, partial)
        raise PublishError("stale_approval_base", str(exc), partial=partial) from exc

    pr_number: int | None = None
    pr_url: str | None = None
    try:
        existing_prs = client.list_pull_requests(owner, repo, head=branch, state="open")
        for pr in existing_prs:
            pr_base = pr.get("base", {}).get("ref", "")
            if pr_base != base_ref:
                raise PublishError(
                    "pr_open",
                    f"Existing PR #{pr.get('number')} targets {pr_base}, expected {base_ref}",
                )
            pr_number = int(pr["number"])
            pr_url = pr.get("html_url")
            existing_pr_reused = True
            break
        if pr_number is None:
            issue_num = job.trigger_context.issue_number if job.trigger_context else None
            body = build_pr_body(
                run_id=job.run_id,
                issue_number=issue_num,
                binding=binding,
                fix_result=fix_result,
                approved_base_sha=approved_base,
                ci_hints=list(fix_result.ci_hints),
            )
            title = f"agent(fix): {binding.approval_target_id}"
            created = client.create_pull_request(
                owner,
                repo,
                head=branch,
                base=base_ref,
                title=title,
                body=body,
            )
            pr_number = int(created["number"])
            pr_url = created.get("html_url")
    except PublishError:
        raise
    except Exception as exc:
        partial = RemotePublishResult(
            publish_state="publish_failed_partial",
            agent_branch=branch,
            base_ref=base_ref,
            head_commit_sha=head_sha,
            approved_base_sha=approved_base,
            remote_branch_preexisting=remote_branch_preexisting or True,
            messages=[redact_publish_text(str(exc))],
        )
        _write_publish_artifact(artifact_root, partial)
        raise PublishError("pr_open", redact_publish_text(str(exc)), partial=partial) from exc

    result = RemotePublishResult(
        publish_state="pr_opened",
        agent_branch=branch,
        base_ref=base_ref,
        head_commit_sha=head_sha,
        opened_pr_number=pr_number,
        opened_pr_url=pr_url,
        approved_base_sha=approved_base,
        remote_branch_preexisting=remote_branch_preexisting,
        existing_pr_reused=existing_pr_reused,
    )
    _write_publish_artifact(artifact_root, result)
    return result


def fix_status_for_publish_result(result: RemotePublishResult) -> str:
    if result.publish_state == "dry_run_passed":
        return FIX_STATUS_LOCAL_PATCH_PASSED
    if result.publish_state == "pr_opened":
        return FIX_STATUS_PR_OPENED_PENDING_CI
    if result.publish_state == "publish_failed_partial":
        return FIX_STATUS_BRANCH_PUBLISHED_PR_FAILED
    return FIX_STATUS_PUBLISH_FAILED
