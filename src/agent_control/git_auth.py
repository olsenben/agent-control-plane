"""HTTP(S) git authentication helpers for non-interactive clone/fetch."""

from __future__ import annotations

import os
from urllib.parse import quote, urlparse, urlunparse

from agent_control.config import Settings


def git_non_interactive_env() -> dict[str, str]:
    return {**os.environ, "GIT_TERMINAL_PROMPT": "0"}


def embed_http_credentials(
    url: str,
    token: str,
    *,
    username: str = "oauth2",
) -> str:
    """Return repo URL with embedded basic-auth credentials for Gitea HTTP(S) clone."""
    if not token or "://" not in url:
        return url
    parsed = urlparse(url)
    if parsed.username:
        return url
    user = quote(username, safe="")
    pwd = quote(token, safe="")
    host = parsed.hostname or ""
    netloc = f"{user}:{pwd}@{host}"
    if parsed.port:
        netloc = f"{user}:{pwd}@{host}:{parsed.port}"
    return urlunparse(
        (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
    )


def authenticated_repo_url(repo_url: str, settings: Settings) -> str:
    if not settings.gitea_bot_token:
        return repo_url
    username = os.environ.get("GITEA_GIT_USER", "oauth2")
    return embed_http_credentials(repo_url, settings.gitea_bot_token, username=username)
