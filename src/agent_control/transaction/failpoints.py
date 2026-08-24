"""Injectable crash/failpoints for durability tests. Default disabled. Not in C."""

from __future__ import annotations

import json
import os
import signal
from pathlib import Path
from typing import Iterable

AFTER_INTENT_BEFORE_PUSH = "after_intent_before_push"
AFTER_PUSH_BEFORE_ACK = "after_push_before_ack"
AFTER_PR_BEFORE_ACK = "after_pr_before_ack"
AFTER_CI_REQUEST_BEFORE_REDUCER = "after_ci_request_before_reducer"

KNOWN_FAILPOINTS = frozenset(
    {
        AFTER_INTENT_BEFORE_PUSH,
        AFTER_PUSH_BEFORE_ACK,
        AFTER_PR_BEFORE_ACK,
        AFTER_CI_REQUEST_BEFORE_REDUCER,
    }
)

ENV_FAILPOINTS = "AGENT_FAILPOINTS"
ENV_FAILPOINT_MODE = "AGENT_FAILPOINT_MODE"
MODE_EXCEPTION = "exception"
MODE_KILL = "kill"


class FailpointAbort(RuntimeError):
    """Catchable abort used by unit tests. Does not kill the pytest process."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)


def failpoints_path(state_root: Path, run_id: str) -> Path:
    return Path(state_root) / "transaction" / "failpoints" / f"{run_id}.json"


def _names_from_env() -> set[str]:
    raw = os.environ.get(ENV_FAILPOINTS, "") or ""
    return {item.strip() for item in raw.split(",") if item.strip()}


def _names_from_file(state_root: Path | None, run_id: str | None) -> set[str]:
    if state_root is None or not run_id:
        return set()
    path = failpoints_path(state_root, run_id)
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    enabled = data.get("enabled") if isinstance(data, dict) else None
    if not isinstance(enabled, list):
        return set()
    return {str(item).strip() for item in enabled if str(item).strip()}


def enabled_failpoints(*, run_id: str | None = None, state_root: Path | None = None) -> set[str]:
    """Union of AGENT_FAILPOINTS and per-run failpoints/{run_id}.json. Default empty."""
    return _names_from_env() | _names_from_file(state_root, run_id)


def failpoint_mode() -> str:
    raw = (os.environ.get(ENV_FAILPOINT_MODE, "") or MODE_EXCEPTION).strip().lower()
    if raw == MODE_KILL:
        return MODE_KILL
    return MODE_EXCEPTION


def hit(name: str, *, run_id: str | None = None, state_root: Path | None = None) -> None:
    """No-op unless `name` is enabled. Default mode raises FailpointAbort."""
    enabled = enabled_failpoints(run_id=run_id, state_root=state_root)
    if name not in enabled:
        return
    if failpoint_mode() == MODE_KILL:
        os.kill(os.getpid(), signal.SIGKILL)
        return
    raise FailpointAbort(name)


def enable_for_run(
    state_root: Path,
    run_id: str,
    names: Iterable[str],
) -> Path:
    path = failpoints_path(state_root, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"enabled": [str(item) for item in names if str(item)]}
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)
    return path
