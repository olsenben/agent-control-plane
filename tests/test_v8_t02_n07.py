"""V8 T02 / N07 — publish deny after approver collaborator revoke (hermetic)."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from agent_control.config import Settings
from agent_control.gitea_client import GiteaClient


@pytest.mark.live_gitea_auth
def test_user_has_repo_permission_404_non_acting_is_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Revoked collaborator must not inherit the bot token's repo admin perms."""
    settings = Settings(GITEA_BOT_TOKEN="tok", GITEA_ACTING_IDENTITY="agent-bot")
    client = GiteaClient(settings)

    class _Resp:
        status_code = 404

        def raise_for_status(self):
            raise AssertionError("404 should not raise_for_status")

        def json(self):
            return {}

    class _Http:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, headers=None):
            return _Resp()

    monkeypatch.setattr(httpx, "Client", _Http)
    client.get_repo = MagicMock(  # type: ignore[method-assign]
        return_value={"permissions": {"admin": True, "push": True, "pull": True}}
    )
    assert client.user_has_repo_permission("ai-sdlc-lab", "demo-app", "temp-approver", need="write") is False
    client.get_repo.assert_not_called()

    # Acting identity may fall back to token repo permissions.
    assert client.user_has_repo_permission("ai-sdlc-lab", "demo-app", "agent-bot", need="write") is True
    client.get_repo.assert_called_once()
