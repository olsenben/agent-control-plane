"""Tests for git HTTP credential helpers."""

from agent_control.git_auth import authenticated_repo_url, embed_http_credentials
from agent_control.config import Settings


def test_embed_http_credentials_adds_oauth2_token() -> None:
    url = "http://192.168.4.60:3000/ai-sdlc-lab/agent-control-plane.git"
    out = embed_http_credentials(url, "secret-token", username="oauth2")
    assert out == "http://oauth2:secret-token@192.168.4.60:3000/ai-sdlc-lab/agent-control-plane.git"


def test_embed_http_credentials_skips_when_already_authenticated() -> None:
    url = "http://deploy:tok@192.168.4.60:3000/owner/repo.git"
    assert embed_http_credentials(url, "other") == url


def test_git_non_interactive_env_disables_credential_helper_when_token_set() -> None:
    from agent_control.git_auth import git_non_interactive_env

    settings = Settings(GITEA_BOT_TOKEN="abc123")
    env = git_non_interactive_env(settings)
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_CONFIG_KEY_0"] == "credential.helper"
    assert env["GIT_CONFIG_VALUE_0"] == ""


def test_authenticated_repo_url_uses_settings_token(monkeypatch) -> None:
    monkeypatch.delenv("GITEA_GIT_USER", raising=False)
    settings = Settings(GITEA_BOT_TOKEN="abc123")
    url = authenticated_repo_url(
        "http://gitea.local:3000/ai-sdlc-lab/demo-app.git",
        settings,
    )
    assert "oauth2:abc123@gitea.local" in url
