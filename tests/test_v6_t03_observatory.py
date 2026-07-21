"""V6 T03 Observatory routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from agent_control.webhook_server import create_app


def test_observe_repo_list_empty(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    app = create_app()
    client = TestClient(app)
    resp = client.get("/observe/repos/ai-sdlc-lab/demo-app")
    assert resp.status_code == 200
    assert resp.json()["sessions"] == []
