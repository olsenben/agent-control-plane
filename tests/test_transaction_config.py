"""transaction-control.yaml loader."""

from __future__ import annotations

from pathlib import Path

from agent_control.transaction.config import load_transaction_control_config


def test_default_config_loader() -> None:
    cfg = load_transaction_control_config()
    assert cfg.actor_provider_id == "fixture_deterministic"
    assert "P1" in cfg.evidence_adapters
    assert cfg.auto_admit_policy_id == "w5_evidence_policy.v1"


def test_minimal_yaml(tmp_path: Path) -> None:
    path = tmp_path / "transaction-control.yaml"
    path.write_text(
        "transaction_control:\n  enabled: true\n  actor_provider_id: fixture_deterministic\n",
        encoding="utf-8",
    )
    cfg = load_transaction_control_config(path)
    assert cfg.enabled is True
    assert cfg.actor_provider_id == "fixture_deterministic"
