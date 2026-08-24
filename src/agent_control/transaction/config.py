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
    authoritative_verifier_id: str = "ct102_functional_ci"
    retry_policy: dict[str, dict[str, Any]] = Field(
        default_factory=lambda: {
            "worker_dispatch": {
                "max_attempts": 3,
                "exhaustion_code": "WORKER_DISPATCH_RETRY_EXHAUSTED",
            },
            "evidence_adapters": {
                "max_attempts": 3,
                "exhaustion_code": "EVIDENCE_ADAPTER_RETRY_EXHAUSTED",
            },
            "gitea_reads": {"max_attempts": 5, "exhaustion_code": "GITEA_READ_RETRY_EXHAUSTED"},
            "gitea_publish": {"max_attempts": 2, "exhaustion_code": "GITEA_PUBLISH_RETRY_EXHAUSTED"},
            "ci_polling": {"max_attempts": 10, "exhaustion_code": "CI_POLLING_RETRY_EXHAUSTED"},
        }
    )
    stuck_sla_seconds: dict[str, int] = Field(
        default_factory=lambda: {
            "PATCH_PROPOSED": 900,
            "EVIDENCE_PENDING": 900,
            "ESCALATED": 3600,
            "CAPABILITY_MINTED": 900,
            "PUBLISH_REQUESTED": 600,
            "VERIFICATION_PENDING": 1800,
        }
    )


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
