"""Memory writeback orchestration on result ingest."""

from __future__ import annotations

from agent_control.config import Settings, get_settings
from agent_control.memory.mapper import memory_record_from_completed
from agent_control.memory.store import MemoryStore
from agent_shared.models.events import AgentRunCompletedEvent
from agent_shared.models.memory import MemoryRecord


def writeback_from_completed(
    event: AgentRunCompletedEvent,
    settings: Settings | None = None,
) -> MemoryRecord | None:
    record = memory_record_from_completed(event)
    if record is None:
        return None
    settings = settings or get_settings()
    store = MemoryStore(settings.memory_db_path)
    return store.upsert_record(record)


def get_memory_store(settings: Settings | None = None) -> MemoryStore:
    settings = settings or get_settings()
    return MemoryStore(settings.memory_db_path)
