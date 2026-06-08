from unittest.mock import MagicMock, patch

from agent_control.queue import deterministic_job_id, enqueue_state_reduction, sanitize_job_id


def test_sanitize_job_id() -> None:
    assert sanitize_job_id("abc:123/ok") == "abc-123-ok"


def test_deterministic_job_id_format() -> None:
    job_id = deterministic_job_id("state", "2b2e3ecb3f878ec98c9b1ecd1174de69")
    assert job_id == "state-2b2e3ecb3f878ec98c9b1ecd1174de69"
    assert ":" not in job_id


@patch("agent_control.queue.Queue")
@patch("agent_control.queue.get_redis")
def test_enqueue_state_reduction(mock_get_redis: MagicMock, mock_queue_cls: MagicMock) -> None:
    conn = MagicMock()
    conn.set.return_value = True
    mock_get_redis.return_value = conn
    queue = MagicMock()
    job = MagicMock()
    job.id = "state-evt123"
    queue.enqueue.return_value = job
    mock_queue_cls.return_value = queue

    with patch("agent_control.queue._rq_supports_unique", return_value=False):
        result = enqueue_state_reduction(
            "redis://localhost:6379/0",
            "evt123",
            "ai-sdlc-lab/demo-app",
            "/data/agent-state",
        )

    assert result == "state-evt123"
    queue.enqueue.assert_called_once()
    call_kwargs = queue.enqueue.call_args.kwargs
    assert call_kwargs["job_id"] == "state-evt123"


@patch("agent_control.queue.Queue")
@patch("agent_control.queue.get_redis")
def test_enqueue_dedupe_skips_second_job(mock_get_redis: MagicMock, mock_queue_cls: MagicMock) -> None:
    conn = MagicMock()
    conn.set.return_value = False
    mock_get_redis.return_value = conn

    with patch("agent_control.queue._rq_supports_unique", return_value=False):
        result = enqueue_state_reduction(
            "redis://localhost:6379/0",
            "evt123",
            "ai-sdlc-lab/demo-app",
            "/data/agent-state",
        )

    assert result is None
    mock_queue_cls.return_value.enqueue.assert_not_called()
