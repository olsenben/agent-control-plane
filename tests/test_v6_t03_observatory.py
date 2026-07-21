"""V6 T03 Observatory routes + auth."""

from __future__ import annotations

from fastapi.testclient import TestClient

from agent_control.webhook_server import create_app


def test_observe_repo_list_requires_auth(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("OBSERVE_REQUIRE_AUTH", "true")
    monkeypatch.delenv("OBSERVE_SHARED_TOKEN", raising=False)
    app = create_app()
    client = TestClient(app)
    resp = client.get("/observe/repos/ai-sdlc-lab/demo-app")
    assert resp.status_code == 401


def test_observe_repo_list_with_shared_token(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("OBSERVE_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OBSERVE_SHARED_TOKEN", "test-observe-token")
    app = create_app()
    client = TestClient(app)
    resp = client.get(
        "/observe/repos/ai-sdlc-lab/demo-app",
        headers={"Authorization": "Bearer test-observe-token"},
    )
    assert resp.status_code == 200
    assert resp.json()["sessions"] == []


def test_observe_repo_list_auth_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("OBSERVE_REQUIRE_AUTH", "false")
    app = create_app()
    client = TestClient(app)
    resp = client.get("/observe/repos/ai-sdlc-lab/demo-app")
    assert resp.status_code == 200
    assert resp.json()["sessions"] == []
