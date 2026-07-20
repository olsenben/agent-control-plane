"""T13 flag-gated tournaments + rewards."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_control.agents.judge import run_judge
from agent_control.config import Settings
from agent_control.workflows import reward as reward_wf
from agent_control.workflows import tournament as tournament_wf


@pytest.fixture
def state_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "agent-state"
    state.mkdir()
    monkeypatch.setenv("AGENT_STATE_ROOT", str(state))
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("AGENT_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    return state


def test_tournament_denied_when_flag_off(state_env: Path) -> None:
    out = tournament_wf.spawn_tournament("F-1", force_enabled=False)
    assert out["status"] == "denied"
    assert out["reason_code"] == "patch_tournament_disabled"


def test_tournament_spawn_and_all_fail_no_winner(state_env: Path) -> None:
    settings = Settings(
        AGENT_STATE_ROOT=str(state_env),
        AGENT_RUNS_DIR=str(state_env.parent / "runs"),
        AGENT_CACHE_DIR=str(state_env.parent / "cache"),
        REDIS_URL="redis://localhost:6379/0",
    )
    spawned = tournament_wf.spawn_tournament(
        "F-2", candidates=3, settings=settings, force_enabled=True
    )
    assert spawned["status"] == "spawned"
    tid = spawned["tournament_id"]
    for i in (1, 2, 3):
        tournament_wf.mark_candidate_ci(tid, i, ci_status="failed", settings=settings)
    judged = tournament_wf.judge_tournament(tid, settings=settings, force_enabled=True)
    assert judged["winner"] is None
    assert judged["stop_reason"] == "all_candidates_failed_ci"


def test_tournament_prefers_test_first_among_passers(state_env: Path) -> None:
    settings = Settings(
        AGENT_STATE_ROOT=str(state_env),
        AGENT_RUNS_DIR=str(state_env.parent / "runs"),
        AGENT_CACHE_DIR=str(state_env.parent / "cache"),
        REDIS_URL="redis://localhost:6379/0",
    )
    spawned = tournament_wf.spawn_tournament(
        "F-3", candidates=3, settings=settings, force_enabled=True
    )
    tid = spawned["tournament_id"]
    tournament_wf.mark_candidate_ci(tid, 1, ci_status="passed", settings=settings)  # minimal
    tournament_wf.mark_candidate_ci(tid, 2, ci_status="passed", settings=settings)  # test_first
    tournament_wf.mark_candidate_ci(tid, 3, ci_status="failed", settings=settings)
    judged = tournament_wf.judge_tournament(tid, settings=settings, force_enabled=True)
    assert judged["winner"]["strategy"] == "test_first_patch"


def test_judge_direct() -> None:
    v = run_judge([{"index": 1, "strategy": "minimal_patch", "ci_status": "failed"}])
    assert v["winner"] is None


def test_reward_denied_when_flag_off(state_env: Path) -> None:
    out = reward_wf.log_reward("run-1", force_enabled=False)
    assert out["status"] == "denied"


def test_reward_log_and_summarize(state_env: Path) -> None:
    settings = Settings(
        AGENT_STATE_ROOT=str(state_env),
        AGENT_RUNS_DIR=str(state_env.parent / "runs"),
        AGENT_CACHE_DIR=str(state_env.parent / "cache"),
        REDIS_URL="redis://localhost:6379/0",
    )
    r1 = reward_wf.log_reward(
        "run-a", {"outcome": "ci_passed"}, settings=settings, force_enabled=True
    )
    assert r1["status"] == "logged"
    assert r1["score"] == 1.0
    reward_wf.log_reward(
        "run-b", {"outcome": "ci_failed"}, settings=settings, force_enabled=True
    )
    summary = reward_wf.summarize_rewards(settings=settings, force_enabled=True)
    assert summary["count"] == 2
    assert summary["by_outcome"]["ci_passed"] == 1
