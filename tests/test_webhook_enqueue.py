import hashlib
import hmac
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from agent_control.config import Settings
from agent_control.events import reduction_outbox_path
from agent_control.webhook_server import create_app

ISSUE_COMMENT_PAYLOAD = {
    "action": "created",
    "issue": {
        "number": 1,
        "title": "test",
        "repository": {"full_name": "ai-sdlc-lab/agent-control-plane"},
    },
    "comment": {"body": "test"},
    "repository": {"full_name": "ai-sdlc-lab/agent-control-plane"},
}


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings.model_construct(
        gitea_webhook_secret="test-secret",
        gitea_allowed_repos="ai-sdlc-lab/*",
        agent_state_root=tmp_path,
        redis_url="redis://localhost:6379/0",
    )
    return TestClient(create_app(settings))


def test_webhook_enqueues_on_success(client: TestClient) -> None:
    body = json.dumps(ISSUE_COMMENT_PAYLOAD).encode()
    with patch("agent_control.webhook_server.enqueue_state_reduction", return_value="state-job-1") as mock_enqueue:
        response = client.post(
            "/webhooks/gitea",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Gitea-Signature": _sign("test-secret", body),
                "X-Gitea-Delivery": "delivery-1",
                "X-Gitea-Event": "issue_comment",
            },
        )
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    mock_enqueue.assert_called_once()


def test_webhook_writes_outbox_on_enqueue_failure(client: TestClient, tmp_path: Path) -> None:
    body = json.dumps(ISSUE_COMMENT_PAYLOAD).encode()
    with patch(
        "agent_control.webhook_server.enqueue_state_reduction",
        side_effect=RuntimeError("redis down"),
    ):
        response = client.post(
            "/webhooks/gitea",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Gitea-Signature": _sign("test-secret", body),
                "X-Gitea-Delivery": "delivery-2",
                "X-Gitea-Event": "issue_comment",
            },
        )
    assert response.status_code == 200
    event_id = response.json()["event_id"]
    outbox = reduction_outbox_path(tmp_path, event_id)
    assert outbox.exists()


def test_webhook_dedupe_skips_enqueue(client: TestClient) -> None:
    body = json.dumps(ISSUE_COMMENT_PAYLOAD).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Gitea-Signature": _sign("test-secret", body),
        "X-Gitea-Delivery": "delivery-3",
        "X-Gitea-Event": "issue_comment",
    }
    with patch("agent_control.webhook_server.enqueue_state_reduction") as mock_enqueue:
        client.post("/webhooks/gitea", content=body, headers=headers)
        client.post("/webhooks/gitea", content=body, headers=headers)
    assert mock_enqueue.call_count == 1
