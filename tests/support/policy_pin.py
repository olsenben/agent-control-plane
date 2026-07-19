"""Shared fixtures for V4.1.1 policy_source_sha pinning in worker tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_control.project_registry import PolicySourcePin

FAKE_POLICY_SHA = "0123456789abcdef0123456789abcdef01234567"

FAKE_POLICY_PIN = PolicySourcePin(
    policy_source_repo="ai-sdlc-lab/demo-app",
    policy_source_remote="http://192.168.4.60:3000/ai-sdlc-lab/demo-app",
    policy_source_ref="main",
    policy_source_sha=FAKE_POLICY_SHA,
)


def pin_job_fields(project: str = "ai-sdlc-lab/demo-app") -> dict[str, str]:
    return {
        "policy_source_repo": project,
        "policy_source_remote": f"http://192.168.4.60:3000/{project}",
        "policy_source_ref": "main",
        "policy_source_sha": FAKE_POLICY_SHA,
        "policy_schema_version": "policy_source.v1",
        "policy_ref": "main",
    }


def install_fake_policy_pin(monkeypatch: Any) -> None:
    """Mock CT103 pin resolve + worker pinned checkout/verify for unit tests."""

    def _fake_checkout(_settings: object, pin: PolicySourcePin, dest: Path, clone_url: str | None = None) -> Path:
        dest.mkdir(parents=True, exist_ok=True)
        (dest / ".agent").mkdir(parents=True, exist_ok=True)
        cfg = dest / ".agent" / "agent-config.yml"
        if not cfg.exists():
            cfg.write_text("agents: {}\n", encoding="utf-8")
        (dest / ".git").mkdir(exist_ok=True)
        (dest / ".git" / "policy_source_remote").write_text(pin.policy_source_remote + "\n", encoding="utf-8")
        readme = dest / "README.md"
        if not readme.exists():
            readme.write_text("# policy\n", encoding="utf-8")
        return dest

    monkeypatch.setattr(
        "agent_control.workflows.dispatch.resolve_policy_source_pin",
        lambda *a, **k: FAKE_POLICY_PIN,
    )
    monkeypatch.setattr(
        "agent_control.approval.dispatch_fix.resolve_policy_source_pin",
        lambda *a, **k: FAKE_POLICY_PIN,
    )
    monkeypatch.setattr(
        "agent_workers.flows.runner.checkout_pinned_policy_workspace",
        _fake_checkout,
    )
    monkeypatch.setattr(
        "agent_workers.repo.policy_loader.verify_pinned_policy_workspace",
        lambda *a, **k: None,
    )
