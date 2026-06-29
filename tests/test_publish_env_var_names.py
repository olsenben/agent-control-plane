"""Verify only FIX_REMOTE_PUBLISH_ENABLED controls remote publish."""

from __future__ import annotations

import pytest

from agent_control.approval.dispatch_fix import fix_remote_publish_enabled, _safety_for_fix
from agent_workers.settings import get_worker_settings


def test_publish_env_var_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FIX_REMOTE_PUBLISH_ENABLED", raising=False)
    monkeypatch.delenv("FIX_PUBLISH_ENABLED", raising=False)
    monkeypatch.delenv("REMOTE_PUBLISH_ENABLED", raising=False)
    assert fix_remote_publish_enabled() is False
    safety = _safety_for_fix()
    assert safety.allow_push is False
    assert safety.allow_network is False

    monkeypatch.setenv("FIX_REMOTE_PUBLISH_ENABLED", "true")
    assert fix_remote_publish_enabled() is True
    safety_on = _safety_for_fix()
    assert safety_on.allow_push is True
    assert safety_on.allow_network is True

    monkeypatch.setenv("FIX_PUBLISH_ENABLED", "true")
    monkeypatch.setenv("REMOTE_PUBLISH_ENABLED", "true")
    monkeypatch.setenv("FIX_REMOTE_PUBLISH_ENABLED", "false")
    assert fix_remote_publish_enabled() is False

    monkeypatch.setenv("FIX_REMOTE_PUBLISH_ENABLED", "true")
    settings = get_worker_settings()
    assert settings.fix_remote_publish_enabled is True
