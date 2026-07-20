"""Tournament judge — only among CI-passing candidates; all-fail → no winner."""

from __future__ import annotations

from typing import Any


def run_judge(candidates: list[dict]) -> dict[str, Any]:
    """Pick a deterministic winner among passing candidates.

    Preference order: test_first_patch > minimal_patch > others (by strategy name).
    If none passed CI, winner is None (no merge recommendation).
    """
    passing = [c for c in candidates if (c.get("ci_status") == "passed" or c.get("eligible_for_judge"))]
    if not passing:
        return {
            "status": "no_winner",
            "role": "judge",
            "winner": None,
            "candidates": len(candidates),
            "passing": 0,
            "stop_reason": "all_candidates_failed_ci",
        }

    preference = {
        "test_first_patch": 0,
        "minimal_patch": 1,
        "refactor_safe_patch": 2,
        "conservative_no_public_api_change": 3,
    }

    def _key(c: dict[str, Any]) -> tuple[int, int]:
        return (preference.get(str(c.get("strategy") or ""), 99), int(c.get("index") or 99))

    winner = sorted(passing, key=_key)[0]
    return {
        "status": "ok",
        "role": "judge",
        "winner": {
            "index": winner.get("index"),
            "strategy": winner.get("strategy"),
            "branch": winner.get("branch"),
        },
        "candidates": len(candidates),
        "passing": len(passing),
        "stop_reason": "winner_selected",
    }
