"""Optional Gitea comment posting from worker-report — disabled (V4.1.1).

Comments are posted by CT103 (results-ingest / publish-broker) using GITEA_BOT_TOKEN.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_shared.models.events import AgentRunCompletedEvent
from agent_workers.settings import WorkerSettings


def maybe_post_comment(
    settings: WorkerSettings,
    job: dict[str, Any],
    completed: AgentRunCompletedEvent,
    artifact_root: Path,
) -> dict[str, Any]:
    return {"status": "skipped", "reason": "ct103_brokerage_comments_only"}
