"""HTTP(S) git authentication helpers for non-interactive clone/fetch."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote, unquote, urlparse, urlunparse

from agent_control.config import Settings


def git_non_interactive_env(
    settings: Settings | None = None,
    *,
    repo_url: str | None = None,
) -> dict[str, str]:
    """Git subprocess env: no prompts; skip credential store when URL auth is used."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    token = settings.gitea_bot_token if settings is not None else ""
    url_has_auth = bool(repo_url and urlparse(repo_url).username)
    if token or url_has_auth:
        # Mounted ~/.git-credentials is read-only; store helper cannot write back.
        env["GIT_CONFIG_COUNT"] = "1"
        env["GIT_CONFIG_KEY_0"] = "credential.helper"
        env["GIT_CONFIG_VALUE_0"] = ""
    return env


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


def authenticated_repo_url_from_credentials(
    repo_url: str,
    creds_path: Path | None = None,
) -> str:
    """Embed deploy PAT from git-credentials store when bot token is unavailable."""
    path = creds_path or Path(os.environ.get("GIT_CREDENTIALS_FILE", "/root/.git-credentials"))
    if not path.is_file():
        return repo_url
    parsed_repo = urlparse(repo_url)
    repo_host = (parsed_repo.hostname or "").lower()
    repo_scheme = parsed_repo.scheme
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parsed = urlparse(line)
        if (parsed.hostname or "").lower() != repo_host or parsed.scheme != repo_scheme:
            continue
        if parsed.username and parsed.password:
            return embed_http_credentials(
                repo_url,
                parsed.password,
                username=unquote(parsed.username),
            )
    return repo_url


def resolve_authenticated_repo_url(repo_url: str, settings: Settings | None = None) -> str:
    settings = settings or Settings()
    if settings.gitea_bot_token:
        return authenticated_repo_url(repo_url, settings)
    return authenticated_repo_url_from_credentials(repo_url)
