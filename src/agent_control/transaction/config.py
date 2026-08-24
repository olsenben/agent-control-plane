"""Minimal transaction-control.yaml loader. Does not expose internals."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

_DEFAULT_PATH = Path(__file__).resolve().parents[3] / "config" / "transaction-control.yaml"


class TransactionControlConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    task_providers: list[str] = Field(default_factory=lambda: ["GITEA_ISSUE"])
    actor_provider_id: str = "fixture_deterministic"
    evidence_adapters: list[str] = Field(
        default_factory=lambda: ["P1", "P2", "P3", "P4", "P5"]
    )
    auto_admit_policy_id: str = "w5_evidence_policy.v1"


def load_transaction_control_config(path: str | Path | None = None) -> TransactionControlConfig:
    cfg_path = Path(path) if path else _DEFAULT_PATH
    if not cfg_path.is_file():
        return TransactionControlConfig()
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        return TransactionControlConfig()
    body: dict[str, Any] = raw.get("transaction_control") or raw
    if not isinstance(body, dict):
        return TransactionControlConfig()
    return TransactionControlConfig.model_validate(body)
