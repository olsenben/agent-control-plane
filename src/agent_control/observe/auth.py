"""Observatory repository-read authorization (V6 T03 QA hardening)."""

from __future__ import annotations

import hmac
import logging
from typing import Annotated

from fastapi import Header, HTTPException, Request

from agent_control.config import Settings, get_settings

logger = logging.getLogger(__name__)


def extract_bearer_token(
    authorization: str | None = None,
    x_gitea_token: str | None = None,
) -> str | None:
    if x_gitea_token and x_gitea_token.strip():
        return x_gitea_token.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


def _token_has_repo_read(project: str, token: str, settings: Settings) -> bool:
    """Validate *token* can read *project* via Gitea API (as that user)."""
    try:
        import httpx

        owner, repo = project.split("/", 1)
        base = settings.gitea_base_url.rstrip("/")
        url = f"{base}/api/v1/repos/{owner}/{repo}"
        headers = {"Authorization": f"token {token}"}
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 404:
                return False
            if resp.status_code >= 400:
                logger.warning(
                    "observe_auth_gitea_denied project=%s status=%s",
                    project,
                    resp.status_code,
                )
                return False
            data = resp.json()
            perms = data.get("permissions") or {}
            return bool(perms.get("pull") or perms.get("admin") or perms.get("push"))
    except Exception:
        logger.exception("observe_auth_gitea_check_failed project=%s", project)
        return False


def require_observe_repo_read(
    project: str,
    *,
    request: Request | None = None,
    authorization: str | None = None,
    x_gitea_token: str | None = None,
    settings: Settings | None = None,
) -> None:
    """Fail closed: unauthorized callers get 401/403 on Observatory surfaces."""
    settings = settings or get_settings()
    if not settings.observe_require_auth:
        return

    token = extract_bearer_token(authorization, x_gitea_token)
    if not token and request is not None:
        token = extract_bearer_token(
            request.headers.get("authorization"),
            request.headers.get("x-gitea-token"),
        )
    if not token:
        raise HTTPException(status_code=401, detail="observatory authentication required")

    shared = (settings.observe_shared_token or "").strip()
    if shared and hmac.compare_digest(token, shared):
        return

    if not _token_has_repo_read(project, token, settings):
        raise HTTPException(status_code=403, detail="repository read access required")


def ObserveAuthDeps(
    authorization: Annotated[str | None, Header()] = None,
    x_gitea_token: Annotated[str | None, Header(alias="X-Gitea-Token")] = None,
) -> tuple[str | None, str | None]:
    return authorization, x_gitea_token
