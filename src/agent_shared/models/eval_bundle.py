"""Framework-neutral evaluation export bundle (V6 T08)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EvalBundle(BaseModel):
    schema_version: str = "eval_bundle.v1"
    manifest: dict[str, Any] = Field(default_factory=dict)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    stages: list[dict[str, Any]] = Field(default_factory=list)
    eval_bundle_sha256: str = ""
    memory_namespace: str = "eval_export"
    production_memory_touched: bool = False
