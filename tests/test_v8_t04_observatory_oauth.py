"""V8 T04 — Observatory Gitea user bearer + shared-token + fail-closed."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from agent_control.config import Settings
from agent_control.observe.auth import require_observe_repo_read


PROJECT = "ai-sdlc-lab/demo-app"


def _settings(tmp_path, **kwargs) -> Settings:
    base = {
        "AGENT_STATE_ROOT": str(tmp_path),
        "GITEA_BASE_URL": "https://git.example.test",
        "OBSERVE_REQUIRE_AUTH": True,
    }
    base.update(kwargs)
    return Settings(**base)


def test_unauth_401(tmp_path) -> None:
    with pytest.raises(HTTPException) as ei:
        require_observe_repo_read(PROJECT, settings=_settings(tmp_path))
    assert ei.value.status_code == 401


def test_shared_token_ok(tmp_path) -> None:
    settings = _settings(tmp_path, OBSERVE_SHARED_TOKEN="shared-secret")
    require_observe_repo_read(
        PROJECT,
        authorization="Bearer shared-secret",
        settings=settings,
    )


def test_user_bearer_repo_read_ok(tmp_path) -> None:
    settings = _settings(tmp_path)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"permissions": {"pull": True}}
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.return_value = mock_resp

    with patch("httpx.Client", return_value=mock_client):
        require_observe_repo_read(
            PROJECT,
            authorization="Bearer gitea-user-token",
            settings=settings,
        )

    mock_client.get.assert_called_once()
    url = mock_client.get.call_args.args[0]
    assert url.endswith(f"/api/v1/repos/{PROJECT}")
    assert mock_client.get.call_args.kwargs["headers"]["Authorization"] == "token gitea-user-token"


def test_user_bearer_x_gitea_token_ok(tmp_path) -> None:
    settings = _settings(tmp_path)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"permissions": {"admin": True}}
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.return_value = mock_resp

    with patch("httpx.Client", return_value=mock_client):
        require_observe_repo_read(
            PROJECT,
            x_gitea_token="pat-from-header",
            settings=settings,
        )


def test_user_bearer_no_pull_403(tmp_path) -> None:
    settings = _settings(tmp_path)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"permissions": {"pull": False, "push": False, "admin": False}}
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.return_value = mock_resp

    with patch("httpx.Client", return_value=mock_client):
        with pytest.raises(HTTPException) as ei:
            require_observe_repo_read(
                PROJECT,
                authorization="Bearer no-access-token",
                settings=settings,
            )
    assert ei.value.status_code == 403


def test_oauth_config_keys_default_empty(tmp_path) -> None:
    settings = _settings(tmp_path)
    assert settings.observe_oauth_client_id is None
    assert settings.observe_oauth_client_secret is None
    assert settings.observe_oauth_redirect_uri is None
