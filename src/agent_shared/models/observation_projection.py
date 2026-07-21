"""Read-only observation projection schema (V6 T01)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ProjectionStageStatus = Literal["present", "missing", "partial"]


class ObservationStage(BaseModel):
    name: str
    status: ProjectionStageStatus = "missing"
    sequence: int = 0
    detail: dict[str, Any] = Field(default_factory=dict)


class ObservationProjection(BaseModel):
    schema_version: str = "observation_projection.v1"
    session_id: str | None = None
    run_id: str | None = None
    trace_id: str | None = None
    project: str | None = None
    command_kind: str | None = None
    status: str | None = None
    max_sequence: int = 0
    stages: list[ObservationStage] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    complete: bool = False
