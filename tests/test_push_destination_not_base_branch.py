"""Push destination must be agent branch only, never PR base."""

from __future__ import annotations

import pytest

from agent_workers.publish.remote import PublishError, _validate_push_destination


def test_push_destination_not_base_branch() -> None:
    ref = _validate_push_destination("agent/run-abc", "main")
    assert ref == "refs/heads/agent/run-abc"

    with pytest.raises(PublishError) as exc:
        _validate_push_destination("main", "main")
    assert "invalid agent branch" in str(exc.value).lower()

    with pytest.raises(PublishError) as exc:
        _validate_push_destination("agent/main", "agent/main")
    assert "forbidden" in str(exc.value).lower()

    with pytest.raises(PublishError) as exc:
        _validate_push_destination("feature/x", "main")
    assert "Invalid agent branch" in str(exc.value)
