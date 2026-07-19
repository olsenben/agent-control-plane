"""Remote push + PR reconciliation for CT103 publish broker only."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from agent_control.config import Settings
from agent_control.git_auth import git_non_interactive_env, resolve_authenticated_repo_url
from agent_control.gitea_client import GiteaClient
from agent_shared.git_patch import git_run
from agent_shared.project_ids import split_project
from agent_workers.publish.formatters import build_commit_message, build_pr_body
from agent_workers.publish.safe_write import redact_publish_text

_PROTECTED = frozenset({"main", "master"})


class RemoteMutationError(Exception):
    def __init__(self, stage: str, message: str, *, stale: bool = False):
        self.stage = stage
        self.stale = stale
        super().__init__(redact_publish_text(message))


def validate_push_ref(agent_branch: str, base_ref: str) -> str:
    if not agent_branch.startswith("agent/"):
        raise RemoteMutationError("branch_push", f"Invalid agent branch: {agent_branch}")
    if agent_branch == base_ref or agent_branch in _PROTECTED:
        raise RemoteMutationError("branch_push", "Direct push to PR base or protected branch forbidden")
    return f"refs/heads/{agent_branch}"


def _validate_host(repo_url: str, allowed_base: str) -> None:
    parsed = urlparse(repo_url)
    host = (parsed.hostname or "").lower()
    allowed = urlparse(allowed_base if "://" in allowed_base else f"https://{allowed_base}")
    if host != (allowed.hostname or "").lower():
        raise RemoteMutationError("branch_push", f"Remote host {host!r} not allowed")


def _ensure_origin(repo: Path, repo_url: str, env: dict[str, str]) -> None:
    proc = git_run(repo, ["git", "remote", "get-url", "origin"], env=env)
    if proc.returncode != 0:
        add = git_run(repo, ["git", "remote", "add", "origin", repo_url], env=env)
        if add.returncode != 0:
            raise RemoteMutationError("branch_push", add.stderr or "remote add failed")
    else:
        set_url = git_run(repo, ["git", "remote", "set-url", "origin", repo_url], env=env)
        if set_url.returncode != 0:
            raise RemoteMutationError("branch_push", set_url.stderr or "remote set-url failed")


def push_commit(
    *,
    workspace: Path,
    commit_sha: str,
    agent_branch: str,
    base_ref: str,
    repo_url: str,
    settings: Settings,
) -> None:
    """Non-force push of an exact commit to refs/heads/agent/*."""
    push_ref = validate_push_ref(agent_branch, base_ref)
    auth_url = resolve_authenticated_repo_url(repo_url, settings)
    _validate_host(auth_url, settings.gitea_base_url)
    env = git_non_interactive_env(settings, repo_url=auth_url)
    _ensure_origin(workspace, auth_url, env)
    # Ensure local ref points at commit
    git_run(workspace, ["git", "update-ref", "HEAD", commit_sha], env=env)
    push = git_run(
        workspace,
        ["git", "push", "origin", f"{commit_sha}:{push_ref}"],
        env=env,
    )
    if push.returncode != 0:
        err = (push.stderr or push.stdout or "").lower()
        stale = "non-fast-forward" in err or "fetch first" in err or "rejected" in err
        raise RemoteMutationError(
            "branch_push",
            push.stderr or "git push failed",
            stale=stale,
        )


def push_repair_fast_forward(
    *,
    workspace: Path,
    commit_sha: str,
    agent_branch: str,
    expected_remote_sha: str,
    repository: str,
    repo_url: str,
    settings: Settings,
    gitea_client: GiteaClient | None = None,
) -> dict:
    """Non-force FF push onto existing agent branch. Never rebases or force-pushes."""
    if not agent_branch.startswith("agent/") or agent_branch in _PROTECTED:
        return {"ok": False, "stale": False, "reason_codes": ["branch_policy"]}

    client = gitea_client or GiteaClient(settings)
    try:
        owner, repo = split_project(repository)
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

    # Parent of commit must be expected_remote_sha
    parent = git_run(workspace, ["git", "rev-parse", f"{commit_sha}^"]).stdout.strip()
    if parent != expected_remote_sha:
        return {"ok": False, "stale": False, "reason_codes": ["parent_mismatch"]}

    try:
        push_commit(
            workspace=workspace,
            commit_sha=commit_sha,
            agent_branch=agent_branch,
            base_ref="main",
            repo_url=repo_url,
            settings=settings,
        )
    except RemoteMutationError as exc:
        return {
            "ok": False,
            "stale": exc.stale,
            "reason": "push_rejected" if exc.stale else "push_failed",
            "detail": str(exc),
        }
    return {"ok": True, "new_head_commit_sha": commit_sha}


def open_or_find_pr(
    *,
    client: GiteaClient,
    owner: str,
    repo: str,
    agent_branch: str,
    base_ref: str,
    title: str,
    body: str,
) -> tuple[int, str | None, bool]:
    """Idempotent PR create/find by head branch."""
    existing = client.list_pull_requests(owner, repo, head=agent_branch, state="open")
    # Gitea may ignore `head=` — always match head ref client-side.
    head_suffix = agent_branch.split(":", 1)[-1]
    for pr in existing:
        pr_head = (pr.get("head") or {}).get("ref", "")
        if pr_head not in (agent_branch, head_suffix):
            continue
        pr_base = pr.get("base", {}).get("ref", "")
        if pr_base != base_ref:
            raise RemoteMutationError(
                "pr_open",
                f"Existing PR #{pr.get('number')} targets {pr_base}, expected {base_ref}",
            )
        return int(pr["number"]), pr.get("html_url"), True
    created = client.create_pull_request(
        owner, repo, head=agent_branch, base=base_ref, title=title, body=body
    )
    return int(created["number"]), created.get("html_url"), False


# Re-export formatters for broker convenience
__all__ = [
    "RemoteMutationError",
    "build_commit_message",
    "build_pr_body",
    "open_or_find_pr",
    "push_commit",
    "push_repair_fast_forward",
    "validate_push_ref",
]
