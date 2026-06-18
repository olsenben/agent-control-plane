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


def test_authenticated_repo_url_uses_settings_token(monkeypatch) -> None:
    monkeypatch.delenv("GITEA_GIT_USER", raising=False)
    settings = Settings(GITEA_BOT_TOKEN="abc123")
    url = authenticated_repo_url(
        "http://gitea.local:3000/ai-sdlc-lab/demo-app.git",
        settings,
    )
    assert "oauth2:abc123@gitea.local" in url
