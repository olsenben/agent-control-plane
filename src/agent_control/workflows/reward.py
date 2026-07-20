"""Flag-gated reward logging (T13 / Phase 22). Default OFF."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_control.config import Settings, get_settings
from agent_control.experiments import load_experiments_config, reward_logging_enabled
from agent_control.project_identity import sanitize_path_segment

REWARD_SCHEMA = "agent.reward.v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rewards_path(state_root: Path, repository: str) -> Path:
    return state_root / "rewards" / sanitize_path_segment(repository) / "rewards.jsonl"


def score_reward(*, outcome: str, score: float | None = None) -> float:
    """Deterministic score function (versioned)."""
    if score is not None:
        return float(score)
    table = {
        "ci_passed": 1.0,
        "ci_failed": 0.0,
        "blocked": 0.1,
        "human_required": 0.2,
        "unknown": 0.0,
    }
    return float(table.get(outcome, 0.0))


def log_reward(
    run_id: str,
    metadata: dict | None = None,
    *,
    repository: str = "ai-sdlc-lab/agent-control-plane",
    settings: Settings | None = None,
    config_path: str | None = None,
    force_enabled: bool | None = None,
) -> dict[str, Any]:
    cfg = load_experiments_config(config_path)
    enabled = reward_logging_enabled(cfg) if force_enabled is None else force_enabled
    meta = dict(metadata or {})
    if not enabled:
        return {
            "schema": REWARD_SCHEMA,
            "run_id": run_id,
            "status": "denied",
            "reason_code": "rl_reward_logging_disabled",
            **meta,
        }

    settings = settings or get_settings()
    outcome = str(meta.get("outcome") or "unknown")
    score = score_reward(outcome=outcome, score=meta.get("score"))
    record = {
        "schema": REWARD_SCHEMA,
        "run_id": run_id,
        "repository": repository,
        "outcome": outcome,
        "score": score,
        "score_fn": "deterministic_v1",
        "logged_at": _now(),
        "status": "logged",
        **{k: v for k, v in meta.items() if k not in ("outcome", "score")},
    }
    path = _rewards_path(settings.agent_state_root, repository)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    record["artifact_path"] = str(path)
    return record


def summarize_rewards(
    *,
    repository: str = "ai-sdlc-lab/agent-control-plane",
    settings: Settings | None = None,
    config_path: str | None = None,
    force_enabled: bool | None = None,
) -> dict[str, Any]:
    cfg = load_experiments_config(config_path)
    enabled = reward_logging_enabled(cfg) if force_enabled is None else force_enabled
    if not enabled:
        return {
            "status": "denied",
            "reason_code": "rl_reward_logging_disabled",
            "count": 0,
        }

    settings = settings or get_settings()
    path = _rewards_path(settings.agent_state_root, repository)
    if not path.is_file():
        return {"status": "ok", "count": 0, "mean_score": 0.0, "by_outcome": {}}

    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    by_outcome: dict[str, int] = {}
    total = 0.0
    for r in rows:
        oc = str(r.get("outcome") or "unknown")
        by_outcome[oc] = by_outcome.get(oc, 0) + 1
        total += float(r.get("score") or 0.0)
    n = len(rows)
    return {
        "status": "ok",
        "count": n,
        "mean_score": round(total / n, 4) if n else 0.0,
        "by_outcome": by_outcome,
        "artifact_path": str(path),
    }
