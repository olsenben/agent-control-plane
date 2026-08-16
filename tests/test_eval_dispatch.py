"""Tests for maintenance_eval_dispatch.v1 local evaluation dispatch."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agent_control.eval_dispatch import (
    DISPATCH_SCHEMA,
    EvalDispatchError,
    dispatch_evaluation,
    get_session,
    handle_message,
)


def _init_repo(path: Path) -> str:
    path.mkdir(parents=True)
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.check_call(["git", "init"], cwd=path)
    subprocess.check_call(["git", "-c", "user.name=t", "-c", "user.email=t@t", "add", "."], cwd=path)
    subprocess.check_call(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "init"],
        cwd=path,
    )
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    monkeypatch.setenv("EVAL_DISPATCH_SESSION_ROOT", str(tmp_path / "sessions"))
    monkeypatch.setenv("EVAL_DISPATCH_ENGINE", "fake")
    repo = tmp_path / "repo"
    sha = _init_repo(repo)
    return repo, sha


def test_dispatch_runs_fake_engine_and_preserves_head_sha(
    workspace: tuple[Path, str],
) -> None:
    repo, sha = workspace
    request = {
        "schema": DISPATCH_SCHEMA,
        "eval_run_id": "eval-test-1",
        "project": "synthlab/retry-toolkit",
        "workspace": str(repo),
        "head_sha": sha,
        "policy_source_sha": "2532de7cf5098baa461e49b92e0d338c089cff45",
        "problem_statement": "Add a comment to README.",
        "arm": "local-recursive-memory-reset",
        "context_strategy": "deterministic",
        "controller_backend": "deterministic",
        "frontier_escalation": False,
        "memory": {"policy": "reset", "enabled": True, "namespace": "ns", "audit_history_action": "retain"},
        "verification": {"official_commands": [], "v10_additional_commands": []},
        "limits": {"wall_seconds": 60, "attempts": 1},
    }
    session_id = dispatch_evaluation(request)
    assert session_id.startswith("sess-eval-")
    session = get_session(session_id, "synthlab/retry-toolkit")
    assert session["head_sha"] == sha
    assert session["status"] == "finished"
    assert session["evaluation_telemetry"]["agent_execution"] is True
    assert session["result_sha"]
    assert len(session["result_sha"]) == 40


def test_dispatch_rejects_wrong_head_sha(workspace: tuple[Path, str]) -> None:
    repo, _sha = workspace
    request = {
        "schema": DISPATCH_SCHEMA,
        "eval_run_id": "eval-test-2",
        "project": "synthlab/retry-toolkit",
        "workspace": str(repo),
        "head_sha": "1" * 40,
        "problem_statement": "x",
        "arm": "a",
        "context_strategy": "deterministic",
        "controller_backend": "none",
        "frontier_escalation": False,
        "memory": {"policy": "off", "enabled": False, "namespace": "n", "audit_history_action": "retain"},
        "verification": {"official_commands": [], "v10_additional_commands": []},
        "limits": {"wall_seconds": 10, "attempts": 1},
        "policy_source_sha": "2532de7cf5098baa461e49b92e0d338c089cff45",
    }
    with pytest.raises(EvalDispatchError, match="exact-SHA"):
        dispatch_evaluation(request)


def test_stdio_round_trip(workspace: tuple[Path, str]) -> None:
    repo, sha = workspace
    request = {
        "schema": DISPATCH_SCHEMA,
        "eval_run_id": "eval-test-3",
        "project": "synthlab/ledger-core",
        "workspace": str(repo),
        "head_sha": sha,
        "policy_source_sha": "2532de7cf5098baa461e49b92e0d338c089cff45",
        "problem_statement": "noop",
        "arm": "a",
        "context_strategy": "deterministic",
        "controller_backend": "none",
        "frontier_escalation": False,
        "memory": {"policy": "off", "enabled": False, "namespace": "n", "audit_history_action": "retain"},
        "verification": {"official_commands": ["true"], "v10_additional_commands": ["true"]},
        "limits": {"wall_seconds": 10, "attempts": 1},
    }
    dispatched = handle_message({"operation": "dispatch", "request": request})
    session = handle_message(
        {
            "operation": "get_session",
            "session_id": dispatched["session_id"],
            "project": "synthlab/ledger-core",
        }
    )
    assert session["verification_claim"]["status"] == "passed"
    assert json.dumps(session)  # serializable
