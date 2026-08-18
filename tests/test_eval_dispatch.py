"""Tests for maintenance_eval_dispatch.v1 local evaluation dispatch."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agent_control.eval_dispatch import (
    DISPATCH_SCHEMA,
    EvalDispatchError,
    _python_argv,
    _run_command_list,
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


def test_h1_local_direct_has_no_context_pack(workspace: tuple[Path, str]) -> None:
    repo, sha = workspace
    request = {
        "schema": DISPATCH_SCHEMA,
        "eval_run_id": "eval-h1-a",
        "project": "synthlab/retry-toolkit",
        "workspace": str(repo),
        "head_sha": sha,
        "policy_source_sha": "2532de7cf5098baa461e49b92e0d338c089cff45",
        "problem_statement": "Find src/foo.py helpers",
        "arm": "local-direct",
        "context_strategy": "ordinary bounded repository and tool context",
        "controller_backend": "none",
        "frontier_escalation": False,
        "memory": {"policy": "off", "enabled": False, "namespace": "n", "audit_history_action": "retain"},
        "verification": {"official_commands": [], "v10_additional_commands": []},
        "limits": {"wall_seconds": 30, "attempts": 1},
        "evaluation_mode": "retrieval",
        "upstream_task_id": "sample-1",
    }
    session_id = dispatch_evaluation(request)
    session = get_session(session_id, "synthlab/retry-toolkit")
    telemetry = session["evaluation_telemetry"]
    assert telemetry["controller_model_invoked"] is False
    assert telemetry["recursive_invoked"] is False
    assert session["head_sha"] == sha
    assert (repo / "arb_trajectory.jsonl").is_file()


def test_h1_local_deterministic_attaches_pack(workspace: tuple[Path, str]) -> None:
    repo, sha = workspace
    (repo / "src").mkdir()
    (repo / "src" / "foo.py").write_text("def helpers():\n    return 1\n", encoding="utf-8")
    subprocess.check_call(["git", "-C", str(repo), "add", "src/foo.py"])
    subprocess.check_call(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "foo"],
    )
    sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    request = {
        "schema": DISPATCH_SCHEMA,
        "eval_run_id": "eval-h1-b",
        "project": "synthlab/retry-toolkit",
        "workspace": str(repo),
        "head_sha": sha,
        "policy_source_sha": "2532de7cf5098baa461e49b92e0d338c089cff45",
        "problem_statement": "Inspect src/foo.py helpers",
        "arm": "local-deterministic",
        "context_strategy": "deterministic CT103 preflight graph FTS and context pack",
        "controller_backend": "none",
        "frontier_escalation": False,
        "memory": {"policy": "off", "enabled": False, "namespace": "n", "audit_history_action": "retain"},
        "verification": {"official_commands": [], "v10_additional_commands": []},
        "limits": {"wall_seconds": 30, "attempts": 1},
        "evaluation_mode": "retrieval",
        "upstream_task_id": "sample-2",
    }
    session_id = dispatch_evaluation(request)
    session = get_session(session_id, "synthlab/retry-toolkit")
    telemetry = session["evaluation_telemetry"]
    assert telemetry["controller_model_invoked"] is False
    assert telemetry["recursive_invoked"] is False
    assert telemetry.get("retrieved_files") is not None


MEMORY_DIAGNOSTIC_SENTINEL = "MEMORY_DIAGNOSTIC_SENTINEL_73A1"


def test_dispatch_without_diagnostic_injection_does_not_put_sentinel_in_pack(
    workspace: tuple[Path, str],
) -> None:
    from agent_workers.rlm.fake_engine import FakeRLMEngine

    repo, sha = workspace
    captured: list[dict] = []

    class _CaptureEngine(FakeRLMEngine):
        def run(self, job, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            captured.append(job)
            return super().run(job, *args, **kwargs)

    request = {
        "schema": DISPATCH_SCHEMA,
        "eval_run_id": "eval-h3-inherit",
        "project": "synthlab/retry-toolkit",
        "workspace": str(repo),
        "head_sha": sha,
        "policy_source_sha": "2532de7cf5098baa461e49b92e0d338c089cff45",
        "problem_statement": "Inspect README.md",
        "arm": "local-deterministic",
        "context_strategy": "deterministic CT103 preflight graph FTS and context pack",
        "controller_backend": "none",
        "frontier_escalation": False,
        "memory": {
            "policy": "inherit",
            "enabled": True,
            "namespace": "ns",
            "audit_history_action": "retain",
            "records": [
                {
                    "memory_id": "mem-diag-73a1",
                    "reusable_claim": MEMORY_DIAGNOSTIC_SENTINEL,
                }
            ],
        },
        "verification": {"official_commands": [], "v10_additional_commands": []},
        "limits": {"wall_seconds": 30, "attempts": 1},
        "evaluation_mode": "retrieval",
        "upstream_task_id": "sample-no-diag",
    }
    session_id = dispatch_evaluation(request, engine_factory=lambda _name: _CaptureEngine())
    session = get_session(session_id, "synthlab/retry-toolkit")
    assert session["evaluation_telemetry"].get("diagnostic_injection") is False
    assert captured
    pack = captured[0].get("context_pack") or {}
    assert MEMORY_DIAGNOSTIC_SENTINEL not in json.dumps(pack)
    assert pack.get("prior_memory") == []
    assert captured[0].get("persist_official_engine_messages") is not True


def test_diagnostic_injection_persists_mem_id_on_real_fix_result_path(
    workspace: tuple[Path, str],
) -> None:
    from agent_workers.rlm.fake_engine import FakeRLMEngine

    repo, sha = workspace
    mem_id = "mem-cccccccccccccccccccccccc"

    class _CitingEngine(FakeRLMEngine):
        def run(self, job, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            result = super().run(job, *args, **kwargs)
            if result.fix_result is not None:
                result.fix_result.scope_summary = f"applied {mem_id}"
            return result

    request = {
        "schema": DISPATCH_SCHEMA,
        "eval_run_id": "eval-diag-cite",
        "project": "synthlab/retry-toolkit",
        "workspace": str(repo),
        "head_sha": sha,
        "policy_source_sha": "2532de7cf5098baa461e49b92e0d338c089cff45",
        "problem_statement": "Patch README.md using prior memory if applicable",
        "arm": "local-deterministic",
        "context_strategy": "deterministic CT103 preflight graph FTS and context pack",
        "controller_backend": "none",
        "frontier_escalation": False,
        "memory": {
            "policy": "preserve_verified",
            "enabled": True,
            "namespace": "diag",
            "audit_history_action": "retain",
            "diagnostic_injection": True,
            "records": [
                {
                    "memory_id": mem_id,
                    "reusable_claim": MEMORY_DIAGNOSTIC_SENTINEL,
                    "evidence_refs": ["vclaim-diag"],
                    "validity": "valid",
                }
            ],
        },
        "verification": {"official_commands": [], "v10_additional_commands": []},
        "limits": {"wall_seconds": 30, "attempts": 1},
    }
    session_id = dispatch_evaluation(request, engine_factory=lambda _name: _CitingEngine())
    session = get_session(session_id, "synthlab/retry-toolkit")
    assert session["evaluation_telemetry"]["diagnostic_injection"] is True
    artifact_dir = Path(session["eval_dispatch"]["artifact_dir"])
    fix_path = artifact_dir / "fix_result.json"
    assert fix_path.is_file()
    payload = json.loads(fix_path.read_text(encoding="utf-8"))
    assert mem_id in payload["scope_summary"]
    messages_path = artifact_dir / "official_engine_messages.json"
    assert messages_path.is_file()
    messages = json.loads(messages_path.read_text(encoding="utf-8"))
    assert MEMORY_DIAGNOSTIC_SENTINEL in (messages.get("user") or "")


def test_python_argv_uses_sys_executable() -> None:
    import sys

    argv = _python_argv("python -m pytest tests/test_retry_toolkit_e02.py -q")
    assert argv[0] == sys.executable
    assert argv[1:3] == ("-m", "pytest")


def test_run_command_list_substitutes_python_and_placeholders(
    tmp_path: Path,
) -> None:
    import sys

    script = tmp_path / "check.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    log_path = tmp_path / "official.log"
    ok, infra = _run_command_list(
        tmp_path,
        [f"python {script.name}"],
        log_path,
        {},
    )
    assert ok is True
    assert infra is False
    log = log_path.read_text(encoding="utf-8")
    assert sys.executable in log


def test_run_command_list_unsubstituted_placeholder_is_infrastructure(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "additional.log"
    ok, infra = _run_command_list(
        tmp_path,
        ["python ${EVAL_CORPUS_ROOT}/invariants/x.py ${WORKSPACE}"],
        log_path,
        {},
    )
    assert ok is False
    assert infra is True
    assert "unsubstituted placeholder" in log_path.read_text(encoding="utf-8")


def test_failed_engine_run_persists_artifact_dir(
    workspace: tuple[Path, str],
) -> None:
    repo, sha = workspace

    class _Boom:
        def run(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            raise ValueError("forced parse failure")

    request = {
        "schema": DISPATCH_SCHEMA,
        "eval_run_id": "eval-parse-fail",
        "project": "synthlab/retry-toolkit",
        "workspace": str(repo),
        "head_sha": sha,
        "policy_source_sha": "2532de7cf5098baa461e49b92e0d338c089cff45",
        "problem_statement": "x",
        "arm": "local-deterministic",
        "context_strategy": "local-deterministic",
        "controller_backend": "none",
        "frontier_escalation": False,
        "memory": {"policy": "off", "enabled": False, "namespace": "n", "audit_history_action": "retain"},
        "verification": {"official_commands": [], "v10_additional_commands": []},
        "limits": {"wall_seconds": 10, "attempts": 1},
    }
    session_id = dispatch_evaluation(request, engine_factory=lambda _name: _Boom())
    session = get_session(session_id, "synthlab/retry-toolkit")
    artifact_dir = Path(session["eval_dispatch"]["artifact_dir"])
    assert artifact_dir.is_dir()
    assert artifact_dir.name == "artifacts"
    assert session["status"] == "failed"

