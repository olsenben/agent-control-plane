"""Structured session event log (session_events.jsonl)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent_shared.constants import SessionEventType
from agent_shared.models.events import SessionEvent
from agent_workers.security.redactor import SecretRedactor


class SessionEventWriter:
    def __init__(self, path: Path, run_id: str, redactor: SecretRedactor | None = None) -> None:
        self.path = path
        self.run_id = run_id
        self.redactor = redactor or SecretRedactor()
        self.events_scanned = 0

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def emit(
        self,
        event: SessionEventType | str,
        *,
        request_id: str | None = None,
        tool: str | None = None,
        args: dict | None = None,
        status: str | None = None,
        message: str | None = None,
        content: str | None = None,
        artifact: str | None = None,
        reason: str | None = None,
        bytes_count: int | None = None,
    ) -> str:
        rid = request_id or str(uuid4())
        payload = SessionEvent(
            ts=self._now(),
            run_id=self.run_id,
            event=event.value if isinstance(event, SessionEventType) else event,
            request_id=rid,
            tool=tool,
            args=args or {},
            status=status,
            message=message,
            content=content,
            artifact=artifact,
            reason=reason,
            bytes=bytes_count,
        )
        line_dict = payload.model_dump(mode="json", exclude_none=True)
        redacted, count = self.redactor.redact_dict(line_dict)
        redacted["redacted_secrets"] = count
        self.events_scanned += 1
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(redacted, ensure_ascii=False) + "\n")
        return rid
