"""Project registry: repo URLs, protected refs, bootstrap policy flags."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import yaml

from agent_control.config import Settings, get_settings

POLICY_SCHEMA_VERSION = "policy_source.v1"


class PolicySourcePinError(RuntimeError):
    """CT103 could not resolve an immutable protected-default-branch policy pin."""


@dataclass(frozen=True)
class ProjectConfig:
    project: str
    repo_url: str
    default_branch: str
    protected_policy_ref: str
    bootstrap_default_policy: bool = False


@dataclass(frozen=True)
class PolicySourcePin:
    """Immutable policy identity resolved once on CT103 for a job/attempt."""

    policy_source_repo: str
    policy_source_remote: str
    policy_source_ref: str
    policy_source_sha: str
    policy_schema_version: str = POLICY_SCHEMA_VERSION

    def as_job_fields(self) -> dict[str, str]:
        return {
            "policy_source_repo": self.policy_source_repo,
            "policy_source_remote": self.policy_source_remote,
            "policy_source_ref": self.policy_source_ref,
            "policy_source_sha": self.policy_source_sha,
            "policy_schema_version": self.policy_schema_version,
            "policy_ref": self.policy_source_ref,
        }


@dataclass(frozen=True)
class RefResolution:
    policy_ref: str
    policy_sha: str | None
    task_ref: str
    task_sha: str | None
    base_ref: str
    target_sha: str | None
    primary_branch: str


def normalize_policy_remote(repo_url: str) -> str:
    """Canonical remote identity: scheme://host[:port]/owner/repo (no creds, no .git).

    ``file://`` URLs are allowed in tests; identity is the normalized filesystem path.
    """
    parsed = urlparse(repo_url.strip())
    scheme = (parsed.scheme or "https").lower()
    if scheme == "file":
        path = (parsed.path or "").rstrip("/")
        if path.endswith(".git"):
            path = path[:-4]
        if not path:
            raise PolicySourcePinError(f"invalid policy remote url: {repo_url!r}")
        return f"file://{path}"

    host = (parsed.hostname or "").lower()
    if not host:
        raise PolicySourcePinError(f"invalid policy remote url: {repo_url!r}")
    netloc = host
    if parsed.port:
        netloc = f"{host}:{parsed.port}"
    path = (parsed.path or "").rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if not path.startswith("/"):
        path = "/" + path
    return urlunparse((scheme, netloc, path, "", "", ""))


def resolve_policy_source_pin(
    project: str,
    settings: Settings | None = None,
    *,
    existing: PolicySourcePin | None = None,
    registry_path: Path | None = None,
) -> PolicySourcePin:
    """Resolve protected-default-branch tip once. Reuse ``existing`` when SHA already set."""
    if existing is not None and existing.policy_source_sha.strip():
        return existing

    settings = settings or get_settings()
    cfg = resolve_project(project, settings=settings, registry_path=registry_path)
    ref = (cfg.protected_policy_ref or cfg.default_branch or "main").replace("refs/heads/", "")
    remote = normalize_policy_remote(cfg.repo_url)

    from agent_control.gitea_client import GiteaClient
    from agent_shared.project_ids import split_project

    owner, repo = split_project(project)
    try:
        sha = str(GiteaClient(settings).get_branch_sha(owner, repo, ref) or "").strip()
    except Exception as exc:  # noqa: BLE001 — fail closed on any resolve error
        raise PolicySourcePinError(f"failed to resolve policy SHA for {project}@{ref}: {exc}") from exc
    if not sha or len(sha) < 7:
        raise PolicySourcePinError(f"empty policy SHA for {project}@{ref}")

    return PolicySourcePin(
        policy_source_repo=project,
        policy_source_remote=remote,
        policy_source_ref=ref,
        policy_source_sha=sha,
        policy_schema_version=POLICY_SCHEMA_VERSION,
    )


def pin_from_job_fields(
    *,
    policy_source_repo: str = "",
    policy_source_remote: str = "",
    policy_source_ref: str = "",
    policy_source_sha: str = "",
    policy_schema_version: str = POLICY_SCHEMA_VERSION,
    project: str = "",
    repo_url: str = "",
    policy_ref: str = "main",
) -> PolicySourcePin | None:
    """Rebuild a pin from job/reservation fields when SHA is already recorded."""
    sha = (policy_source_sha or "").strip()
    if not sha:
        return None
    repo = (policy_source_repo or project or "").strip()
    ref = (policy_source_ref or policy_ref or "main").replace("refs/heads/", "")
    remote = (policy_source_remote or "").strip()
    if not remote and repo_url:
        remote = normalize_policy_remote(repo_url)
    if not repo or not remote:
        return None
    return PolicySourcePin(
        policy_source_repo=repo,
        policy_source_remote=remote,
        policy_source_ref=ref,
        policy_source_sha=sha,
        policy_schema_version=policy_schema_version or POLICY_SCHEMA_VERSION,
    )


def _default_registry_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "projects.yaml"


@lru_cache(maxsize=1)
def _load_registry_file(path: str) -> dict[str, Any]:
    registry_path = Path(path)
    if not registry_path.exists():
        return {"projects": {}}
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    return data


def _platform_defaults(raw: dict[str, Any]) -> dict[str, Any]:
    platform = raw.get("platform") or {}
    if not isinstance(platform, dict):
        return {}
    return platform


def _project_from_platform(
    project: str,
    platform: dict[str, Any],
    *,
    fallback_repo_base: str,
) -> ProjectConfig | None:
    if "/" not in project:
        return None
    owner, _repo = project.split("/", 1)
    allowed = platform.get("allowed_owners") or []
    if owner not in allowed:
        return None
    repo_base = str(platform.get("repo_url_base", fallback_repo_base)).rstrip("/")
    return ProjectConfig(
        project=project,
        repo_url=f"{repo_base}/{project}.git",
        default_branch=str(platform.get("default_branch", "main")),
        protected_policy_ref=str(platform.get("protected_policy_ref", "main")),
        bootstrap_default_policy=bool(platform.get("bootstrap_default_policy", False)),
    )


def load_project_registry(registry_path: Path | None = None) -> dict[str, ProjectConfig]:
    path = registry_path or _default_registry_path()
    raw = _load_registry_file(str(path))
    platform = _platform_defaults(raw)
    projects: dict[str, ProjectConfig] = {}
    for name, cfg in (raw.get("projects") or {}).items():
        if not isinstance(cfg, dict):
            continue
        repo_url = str(cfg.get("repo_url", "")).strip()
        if not repo_url:
            resolved = _project_from_platform(name, platform, fallback_repo_base="")
            if resolved is None:
                continue
            repo_url = resolved.repo_url
        projects[name] = ProjectConfig(
            project=name,
            repo_url=repo_url,
            default_branch=str(cfg.get("default_branch", platform.get("default_branch", "main"))),
            protected_policy_ref=str(
                cfg.get("protected_policy_ref", platform.get("protected_policy_ref", "main"))
            ),
            bootstrap_default_policy=bool(
                cfg.get(
                    "bootstrap_default_policy",
                    platform.get("bootstrap_default_policy", False),
                )
            ),
        )
    return projects


def resolve_project(
    project: str,
    settings: Settings | None = None,
    registry_path: Path | None = None,
) -> ProjectConfig:
    settings = settings or get_settings()
    path = registry_path or _default_registry_path()
    raw = _load_registry_file(str(path))
    registry = load_project_registry(registry_path)
    if project in registry:
        return registry[project]
    platform = _platform_defaults(raw)
    fallback_repo_base = settings.gitea_base_url.rstrip("/")
    platform_cfg = _project_from_platform(project, platform, fallback_repo_base=fallback_repo_base)
    if platform_cfg is not None:
        return platform_cfg
    return ProjectConfig(
        project=project,
        repo_url=f"{fallback_repo_base}/{project}.git",
        default_branch="main",
        protected_policy_ref="main",
        bootstrap_default_policy=False,
    )


def resolve_refs(project: str, event: dict[str, Any], settings: Settings | None = None) -> RefResolution:
    cfg = resolve_project(project, settings=settings)
    payload = event.get("payload") or {}
    etype = event.get("type", "")
    primary = cfg.protected_policy_ref or cfg.default_branch

    pr = payload.get("pull_request") or {}
    if etype.startswith("gitea.pr_") or pr:
        base_ref = (pr.get("base") or {}).get("ref") or primary
        head_sha = (pr.get("head") or {}).get("sha")
        head_ref = (pr.get("head") or {}).get("ref") or base_ref
        return RefResolution(
            policy_ref=base_ref.replace("refs/heads/", ""),
            policy_sha=(pr.get("base") or {}).get("sha"),
            task_ref=head_ref.replace("refs/heads/", ""),
            task_sha=head_sha,
            base_ref=base_ref.replace("refs/heads/", ""),
            target_sha=head_sha,
            primary_branch=cfg.default_branch,
        )

    if etype == "gitea.push":
        ref = str(payload.get("ref", primary)).replace("refs/heads/", "")
        after = payload.get("after")
        return RefResolution(
            policy_ref=primary,
            policy_sha=None,
            task_ref=ref,
            task_sha=after,
            base_ref=ref,
            target_sha=after,
            primary_branch=cfg.default_branch,
        )

    if etype.startswith("gitea.workflow_"):
        run = payload.get("workflow_run") or payload.get("workflow_job") or {}
        sha = run.get("head_sha") or payload.get("after")
        return RefResolution(
            policy_ref=primary,
            policy_sha=None,
            task_ref=primary,
            task_sha=sha,
            base_ref=primary,
            target_sha=sha,
            primary_branch=cfg.default_branch,
        )

    return RefResolution(
        policy_ref=primary,
        policy_sha=None,
        task_ref=primary,
        task_sha=payload.get("after"),
        base_ref=primary,
        target_sha=payload.get("after"),
        primary_branch=cfg.default_branch,
    )


def is_approval_authority(
    author: str | None,
    project: str,
    settings: Settings | None = None,
) -> bool:
    """True when author may grant or reject Risk 2 approvals for project."""
    settings = settings or get_settings()
    if not author:
        return False
    author_lower = str(author).lower()
    owner_login = project.split("/", 1)[0] if "/" in project else ""
    if owner_login and author_lower == owner_login.lower():
        return True
    return author_lower in settings.approver_logins_set()


def build_trigger_context(
    event: dict[str, Any],
    intent_body: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    payload = event.get("payload") or {}
    etype = event.get("type", "")
    issue = payload.get("issue") or {}
    pr = payload.get("pull_request") or {}
    comment = payload.get("comment") or {}
    user = comment.get("user") or issue.get("user") or {}
    author = user.get("login") or (issue.get("user") or {}).get("login")
    author_id_raw = user.get("id")
    try:
        author_id = int(author_id_raw) if author_id_raw is not None else None
    except (TypeError, ValueError):
        author_id = None
    project = event.get("project", "")
    base = settings.gitea_base_url.rstrip("/")

    issue_number = issue.get("number") or (pr.get("number") if pr else None)
    pr_number = pr.get("number") if pr else None
    comment_id = str(comment.get("id", "")) if comment else None

    author_is_owner = is_approval_authority(author, project, settings=settings)

    comment_url = None
    if issue_number and comment_id:
        if pr_number:
            comment_url = f"{base}/{project}/pulls/{pr_number}#issuecomment-{comment_id}"
        else:
            comment_url = f"{base}/{project}/issues/{issue_number}#issuecomment-{comment_id}"

    reply_target = None
    if comment_id:
        reply_target = {"kind": "issue_comment", "id": comment_id}

    return {
        "source": "gitea",
        "event_type": etype,
        "issue_number": issue_number,
        "pr_number": pr_number,
        "comment_id": comment_id,
        "comment_url": comment_url,
        "discussion_id": None,
        "author": author,
        "author_id": author_id,
        "author_is_owner": author_is_owner,
        "raw_body": intent_body,
        "normalized_body": intent_body.strip(),
        "reply_mode": "same_thread_if_possible",
        "reply_target": reply_target,
    }
