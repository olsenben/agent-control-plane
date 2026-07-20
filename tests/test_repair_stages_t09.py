"""T09 staged repair expand status."""

from __future__ import annotations

from agent_control.ci.repair_stages import repair_stage_status
from agent_control.config import Settings


def _settings(**kwargs) -> Settings:
    base = dict(
        AGENT_STATE_ROOT="/tmp/acp-t09-state",
        AGENT_RUNS_DIR="/tmp/acp-t09-runs",
        AGENT_CACHE_DIR="/tmp/acp-t09-cache",
        REDIS_URL="redis://localhost:6379/0",
        FIX_CI_OBSERVE_ENABLED=True,
        FIX_CI_FAILURE_EVIDENCE_ENABLED=True,
        FIX_CI_REPAIR_ENABLED=True,
        FIX_CI_REPAIR_ALLOWED_REPOS="ai-sdlc-lab/agent-control-plane",
        FIX_CI_REPAIR_ALLOWED_CLASSES="lint_failure",
        FIX_CI_REPAIR_PUBLISH_ENABLED=False,
    )
    base.update(kwargs)
    return Settings(**base)


def test_stage_status_repair_no_publish() -> None:
    st = repair_stage_status(_settings())
    assert st["schema"] == "repair_stage_status.v1"
    assert st["stages"]["observe"]["stage_ok"] is True
    assert st["stages"]["repair_no_publish"]["stage_ok"] is True
    assert st["stages"]["repair_no_publish"]["publish_denied_when_flag_off"] is True
    assert st["stages"]["repair_no_publish"]["demo_denied"] is True
    assert st["stages"]["one_class_publish"]["publish_flag"] is False
    assert st["t09_complete"] is True


def test_stage_status_one_class_publish() -> None:
    st = repair_stage_status(_settings(FIX_CI_REPAIR_PUBLISH_ENABLED=True))
    assert st["stages"]["one_class_publish"]["stage_ok"] is True
    assert st["stages"]["one_class_publish"]["scope_widened"] is False
    assert st["t09_complete"] is True


def test_scope_widened_when_extra_class() -> None:
    st = repair_stage_status(
        _settings(
            FIX_CI_REPAIR_ALLOWED_CLASSES="lint_failure,test_failure",
            FIX_CI_REPAIR_PUBLISH_ENABLED=True,
        )
    )
    assert st["stages"]["one_class_publish"]["scope_widened"] is True
