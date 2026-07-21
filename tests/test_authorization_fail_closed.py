"""Unit coverage for V6 fail-closed repo permission helper."""

from __future__ import annotations

import pytest

from agent_control.authorization import check_user_repo_permission
from agent_control.config import Settings


@pytest.mark.live_gitea_auth
def test_check_user_repo_permission_fail_closed_without_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITEA_BOT_TOKEN", raising=False)
    settings = Settings(GITEA_BOT_TOKEN="")
    assert (
        check_user_repo_permission("ai-sdlc-lab/demo-app", "alice", settings=settings) is False
    )


@pytest.mark.live_gitea_auth
def test_check_user_repo_permission_fail_closed_on_client_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Boom:
        def user_has_repo_permission(self, *a, **k):
            raise RuntimeError("gitea down")

    monkeypatch.setattr("agent_control.gitea_client.GiteaClient", lambda settings=None: _Boom())
    settings = Settings(GITEA_BOT_TOKEN="tok")
    assert (
        check_user_repo_permission("ai-sdlc-lab/demo-app", "alice", settings=settings) is False
    )
