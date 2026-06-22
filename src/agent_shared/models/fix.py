"""Structured fix output models (Slice 6B)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

EditKind = Literal["replace", "append", "create"]
FixConfidence = Literal["low", "medium", "high"]


class FixFileChange(BaseModel):
    path: str
    summary: str = ""
    edit_kind: EditKind = "replace"
    content: str = ""
    original_sha256: str | None = None


class FixResult(BaseModel):
    schema_version: str = "fix_result.v1"
    scope_summary: str = ""
    files_changed: list[str] = Field(default_factory=list)
    changes: list[FixFileChange] = Field(default_factory=list)
    ci_hints: list[str] = Field(default_factory=list)
    risk_tags: list[str] = Field(default_factory=list)
    confidence: FixConfidence = "medium"
    approval_target_id: str = ""
    plan_run_id: str = ""
