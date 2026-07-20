"""Flag-gated patch tournaments (T13 / Phase 21). Default OFF."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_control.config import Settings, get_settings
from agent_control.experiments import (
    load_experiments_config,
    max_tournament_candidates,
    patch_tournament_enabled,
)
from agent_control.project_identity import sanitize_path_segment
from agent_control.agents.judge import run_judge

_STRATEGIES = (
    "minimal_patch",
    "test_first_patch",
    "refactor_safe_patch",
    "conservative_no_public_api_change",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tournaments_dir(state_root: Path, repository: str) -> Path:
    return state_root / "tournaments" / sanitize_path_segment(repository)


def spawn_tournament(
    finding_id: str,
    candidates: int = 3,
    *,
    repository: str = "ai-sdlc-lab/agent-control-plane",
    settings: Settings | None = None,
    config_path: str | None = None,
    force_enabled: bool | None = None,
) -> dict[str, Any]:
    """Create a bounded tournament record. Does not push branches unless enabled later."""
    cfg = load_experiments_config(config_path)
    enabled = patch_tournament_enabled(cfg) if force_enabled is None else force_enabled
    if not enabled:
        return {
            "status": "denied",
            "reason_code": "patch_tournament_disabled",
            "workflow": "tournament",
            "finding_id": finding_id,
            "hint": "Set experiments.patch_tournament: true in config/experiments.yaml",
        }

    settings = settings or get_settings()
    cap = max_tournament_candidates(cfg)
    n = max(1, min(int(candidates), cap, len(_STRATEGIES)))
    tournament_id = f"tourn-{uuid.uuid4().hex[:12]}"
    candidate_rows: list[dict[str, Any]] = []
    for i in range(n):
        strategy = _STRATEGIES[i]
        branch = f"agent/tournament-{tournament_id}-{i + 1}-{strategy.replace('_', '-')}"
        candidate_rows.append(
            {
                "index": i + 1,
                "strategy": strategy,
                "branch": branch,
                "ci_status": "pending",
                "closed_world": "pending",
                "eligible_for_judge": False,
            }
        )

    record = {
        "schema": "patch_tournament.v1",
        "tournament_id": tournament_id,
        "finding_id": finding_id,
        "repository": repository,
        "created_at": _now(),
        "candidates": candidate_rows,
        "winner": None,
        "stop_reason": None,
        "status": "spawned",
        "notes": [
            "Branches are reserved names only — no auto-push until HITL/ops enables.",
            "Judge only considers candidates with ci_status=passed.",
        ],
    }
    path = _tournaments_dir(settings.agent_state_root, repository) / f"{tournament_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    record["artifact_path"] = str(path)
    return record


def load_tournament(
    tournament_id: str,
    *,
    repository: str = "ai-sdlc-lab/agent-control-plane",
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    path = _tournaments_dir(settings.agent_state_root, repository) / f"{tournament_id}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def mark_candidate_ci(
    tournament_id: str,
    index: int,
    *,
    ci_status: str,
    repository: str = "ai-sdlc-lab/agent-control-plane",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Test/helper: update one candidate CI outcome and persist."""
    settings = settings or get_settings()
    rec = load_tournament(tournament_id, repository=repository, settings=settings)
    if not rec:
        return {"status": "not_found", "tournament_id": tournament_id}
    for c in rec.get("candidates") or []:
        if int(c.get("index", -1)) == int(index):
            c["ci_status"] = ci_status
            c["eligible_for_judge"] = ci_status == "passed"
            break
    path = _tournaments_dir(settings.agent_state_root, repository) / f"{tournament_id}.json"
    path.write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return rec


def judge_tournament(
    tournament_id: str,
    *,
    repository: str = "ai-sdlc-lab/agent-control-plane",
    settings: Settings | None = None,
    config_path: str | None = None,
    force_enabled: bool | None = None,
) -> dict[str, Any]:
    cfg = load_experiments_config(config_path)
    enabled = patch_tournament_enabled(cfg) if force_enabled is None else force_enabled
    if not enabled:
        return {
            "status": "denied",
            "reason_code": "patch_tournament_disabled",
            "tournament_id": tournament_id,
        }

    settings = settings or get_settings()
    rec = load_tournament(tournament_id, repository=repository, settings=settings)
    if not rec:
        return {"status": "not_found", "tournament_id": tournament_id}

    passing = [c for c in rec.get("candidates") or [] if c.get("ci_status") == "passed"]
    verdict = run_judge(passing)
    rec["judge"] = verdict
    rec["winner"] = verdict.get("winner")
    rec["stop_reason"] = verdict.get("stop_reason")
    rec["status"] = "judged"
    rec["judged_at"] = _now()
    path = _tournaments_dir(settings.agent_state_root, repository) / f"{tournament_id}.json"
    path.write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return rec
