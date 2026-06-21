"""Command intent parsed from Gitea activation comments."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CommandIntent(BaseModel):
    schema_version: str = "command_intent.v1"
    activated: bool = False
    activation: str | None = None
    kind: str | None = None
    natural_language_task: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    work_item_id: str | None = None
    approval_target: str | None = None
    reject_reason: str | None = None
