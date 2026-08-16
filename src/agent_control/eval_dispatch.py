"""Generic evaluation dispatch for ``maintenance_eval_dispatch.v1``.

Accepts a local Git workspace already checked out at an exact ``head_sha`` and
runs the frozen patch-author engine against it. This is the smallest ACP entry
point that lets maintenance-evals drive the trusted agent path without a Gitea
webhook, Redis enqueue, or shallow branch clone.

Transport: JSON object on stdin, JSON object on stdout (see
``JsonCommandControlPlaneClient`` in maintenance-evals).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agent_shared.constants import RiskClass
from agent_shared.models.intent import CommandIntent
from agent_workers.patch.apply import ApplyFixError, apply_fix_to_workspace
from agent_workers.rlm.fake_engine import FakeRLMEngine
from agent_workers.rlm.official_engine import OfficialRLMEngine

DISPATCH_SCHEMA = "maintenance_eval_dispatch.v1"
SESSION_SCHEMA = "maintenance_eval_session.v1"
DEFAULT_ENGINE = "official"


class EvalDispatchError(RuntimeError):
    """Fail-closed evaluation dispatch error."""


def session_root() -> Path:
    """Directory for create-only eval session records."""
    configured = os.environ.get("EVAL_DISPATCH_SESSION_ROOT")
    if configured:
        root = Path(configured)
    else:
        state = os.environ.get("AGENT_STATE_ROOT", "/tmp/agent-state")
        root = Path(state) / "eval-dispatch-sessions"
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_engine_name() -> str:
    return (os.environ.get("EVAL_DISPATCH_ENGINE") or DEFAULT_ENGINE).strip().lower()


def control_plane_sha() -> str:
    pinned = os.environ.get("CONTROL_PLANE_SHA") or os.environ.get("EVAL_CONTROL_PLANE_SHA")
    if pinned and len(pinned) == 40:
        return pinned
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "0" * 40


def handle_message(payload: dict[str, Any]) -> dict[str, Any]:
    """Dispatch one JSON-RPC-style evaluation adapter message."""
    operation = payload.get("operation")
    if operation == "dispatch":
        request = payload.get("request")
        if not isinstance(request, dict):
            raise EvalDispatchError("dispatch requires a request object")
        session_id = dispatch_evaluation(request)
        return {"session_id": session_id}
    if operation == "get_session":
        session_id = payload.get("session_id")
        project = payload.get("project")
        if not isinstance(session_id, str) or not isinstance(project, str):
            raise EvalDispatchError("get_session requires session_id and project")
        return get_session(session_id, project)
    raise EvalDispatchError(f"unsupported operation: {operation!r}")


def dispatch_evaluation(
    request: dict[str, Any],
    *,
    engine_factory: Callable[[str], Any] | None = None,
) -> str:
    """Run the patch-author path against ``request['workspace']`` at ``head_sha``."""
    if request.get("schema") != DISPATCH_SCHEMA:
        raise EvalDispatchError(f"expected schema {DISPATCH_SCHEMA}")
    workspace = Path(str(request["workspace"]))
    head_sha = str(request["head_sha"])
    project = str(request["project"])
    if not workspace.is_dir():
        raise EvalDispatchError(f"workspace does not exist: {workspace}")
    actual = _git_sha(workspace)
    if actual != head_sha:
        raise EvalDispatchError(
            f"exact-SHA invariant failed: workspace HEAD {actual} != requested {head_sha}"
        )

    session_id = f"sess-eval-{uuid.uuid4().hex}"
    run_id = f"run-eval-{uuid.uuid4().hex}"
    artifact_dir = session_root() / session_id / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=False)

    allowed_files = _workspace_files(workspace)
    job = _build_eval_job(
        request=request,
        session_id=session_id,
        run_id=run_id,
        allowed_files=allowed_files,
    )
    engine_name = resolve_engine_name()
    factory = engine_factory or _default_engine
    engine = factory(engine_name)
    try:
        result = engine.run(
            job,
            workspace,
            {"warnings": []},
            artifact_dir=str(artifact_dir),
        )
    except Exception as exc:  # noqa: BLE001 — surface as failed session
        record = _failed_session(
            session_id=session_id,
            project=project,
            head_sha=head_sha,
            run_id=run_id,
            reason_code="dispatch_timeout"
            if "timeout" in str(exc).lower()
            else "evaluated_agent",
            reason=str(exc),
        )
        _write_session(session_id, record)
        return session_id

    result_sha = head_sha
    files_changed = 0
    if getattr(result, "fix_result", None) is not None and result.fix_result is not None:
        try:
            apply_fix_to_workspace(
                workspace,
                result.fix_result,
                allowed_files=allowed_files or list(result.fix_result.files_changed),
                artifact_root=artifact_dir,
            )
            files_changed = len(result.fix_result.files_changed)
            result_sha = _commit_workspace(workspace, message=f"eval-dispatch {session_id}")
        except ApplyFixError as exc:
            record = _failed_session(
                session_id=session_id,
                project=project,
                head_sha=head_sha,
                run_id=run_id,
                reason_code="evaluated_agent",
                reason=f"patch apply failed: {exc}",
            )
            _write_session(session_id, record)
            return session_id

    verification = request.get("verification") or {}
    official_ok, additional_ok, claim = _run_verification_commands(
        workspace=workspace,
        result_sha=result_sha,
        verification=verification,
        artifact_dir=artifact_dir,
    )
    status = "finished" if official_ok else "failed"
    record = {
        "schema": SESSION_SCHEMA,
        "schema_version": "agent_session.v1",
        "session_id": session_id,
        "project": project,
        "repo": project.rsplit("/", 1)[-1] if "/" in project else project,
        "status": status,
        "head_sha": head_sha,
        "result_sha": result_sha,
        "policy_source_sha": str(request.get("policy_source_sha") or ""),
        "control_plane_sha": control_plane_sha(),
        "worker_image_digest": os.environ.get("WORKER_IMAGE_DIGEST", "local-eval-dispatch"),
        "ci_image_digest": os.environ.get("CI_IMAGE_DIGEST", "local-eval-dispatch"),
        "run_ids": [run_id],
        "terminal_reason_code": None if official_ok else "evaluated_agent",
        "terminal_reason": None if official_ok else "official verification did not pass",
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "finished_at": _utc_now(),
        "verification_claim": claim,
        "evaluation_telemetry": {
            "official_benchmark_pass": official_ok,
            "v10_additional_verification_pass": additional_ok,
            "primary_model": os.environ.get("MODEL_3080_NAME", "qwen2.5-coder:14b"),
            "model_config_hash": os.environ.get("MODEL_CONFIG_HASH", ""),
            "controller_backend": str(request.get("controller_backend") or "none"),
            "solver_attempts": 1,
            "repair_attempts": 0,
            "ci_cycles": 1,
            "files_changed": files_changed,
            "wall_seconds": None,
            "local_gpu_seconds": None,
            "agent_execution": True,
            "eval_dispatch_engine": engine_name,
            "eval_run_id": request.get("eval_run_id"),
            "arm": request.get("arm"),
            "context_strategy": request.get("context_strategy"),
            "memory_policy": (request.get("memory") or {}).get("policy"),
            "memory_namespace": (request.get("memory") or {}).get("namespace"),
        },
        "engine_summary": getattr(result, "summary", None),
        "eval_dispatch": {
            "workspace": str(workspace),
            "artifact_dir": str(artifact_dir),
            "engine": engine_name,
        },
    }
    _write_session(session_id, record)
    return session_id


def get_session(session_id: str, project: str) -> dict[str, Any]:
    """Return a previously written evaluation session record."""
    path = session_root() / f"{session_id}.json"
    if not path.is_file():
        raise EvalDispatchError(f"unknown session_id: {session_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("project") != project:
        raise EvalDispatchError(
            f"session {session_id} belongs to {payload.get('project')!r}, not {project!r}"
        )
    return payload


def _default_engine(name: str) -> Any:
    if name in {"fake", "fake_rlm", "deterministic"}:
        return FakeRLMEngine()
    if name in {"official", "official_rlm", "qwen"}:
        return OfficialRLMEngine()
    raise EvalDispatchError(f"unknown EVAL_DISPATCH_ENGINE: {name!r}")


def _build_eval_job(
    *,
    request: dict[str, Any],
    session_id: str,
    run_id: str,
    allowed_files: list[str],
) -> dict[str, Any]:
    project = str(request["project"])
    owner, _, repo = project.partition("/")
    if not repo:
        owner, repo = "eval", project
    limits = request.get("limits") or {}
    return {
        "schema_version": "rlm_job.v1",
        "run_id": run_id,
        "job_id": f"job-{run_id}",
        "workflow_id": f"wf-{run_id}",
        "session_id": session_id,
        "workflow_definition": "eval_dispatch",
        "flow_config_id": "eval_dispatch",
        "flow_version": "1",
        "flow_config_schema_version": "1",
        "project": project,
        "owner": owner or "eval",
        "repo": repo,
        "repo_url": f"file://{request['workspace']}",
        "primary_branch": "HEAD",
        "policy_ref": "HEAD",
        "task_ref": str(request["head_sha"]),
        "flow": "developer_flow",
        "agent": "developer",
        "risk_class": RiskClass.WRITE_PATCH.value,
        "command_intent": CommandIntent(
            kind="fix",
            natural_language_task=str(request.get("problem_statement") or ""),
        ).model_dump(mode="json"),
        "safety": {
            "activation_required": False,
            "command_scope": "fix",
            "allow_repo_write": True,
            "allow_test_execution": True,
            "allow_network": False,
            "allow_push": False,
            "allow_merge": False,
            "sandbox_required": True,
            "requires_manual_approval": False,
        },
        "limits": {
            "max_depth": 0,
            "max_child_agents": 0,
            "max_parallel_children": 0,
            "max_iterations": 4,
            "time_budget_seconds": int(limits.get("wall_seconds") or 1800),
        },
        "fix_authorization": {
            "approval_id": f"eval-{run_id}",
            "approval_target_id": f"eval-{run_id}",
            "plan_run_id": run_id,
            "plan_hash": "0" * 64,
            "blast_radius_hash": "0" * 64,
            "allowed_files": allowed_files,
            "plan_summary": "evaluation dispatch local patch",
            "plan_steps": [],
            "ci_hints": [],
            "approved_base_sha": str(request["head_sha"]),
            "approved_base_ref": "HEAD",
            "policy_source_sha": str(request.get("policy_source_sha") or ""),
        },
        "model_policy": {},
        "trigger_context": {
            "source": "maintenance_eval_dispatch",
            "event_type": "eval_dispatch",
            "raw_body": str(request.get("problem_statement") or ""),
        },
    }


def _workspace_files(workspace: Path) -> list[str]:
    try:
        output = subprocess.check_output(
            ["git", "-C", str(workspace), "ls-files"],
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    return [line for line in output.splitlines() if line.strip()]


def _git_sha(workspace: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(workspace), "rev-parse", "HEAD"],
        text=True,
    ).strip()


def _commit_workspace(workspace: Path, *, message: str) -> str:
    # Keep git chatter off stdout: JsonCommandControlPlaneClient expects a
    # single JSON object on stdout from ``agentctl eval dispatch``.
    subprocess.check_call(
        ["git", "-C", str(workspace), "add", "-A"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    status = subprocess.check_output(
        ["git", "-C", str(workspace), "status", "--porcelain"],
        text=True,
    )
    if status.strip():
        subprocess.check_call(
            [
                "git",
                "-C",
                str(workspace),
                "-c",
                "user.name=eval-dispatch",
                "-c",
                "user.email=eval-dispatch@localhost",
                "commit",
                "-m",
                message,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return _git_sha(workspace)


def _run_verification_commands(
    *,
    workspace: Path,
    result_sha: str,
    verification: dict[str, Any],
    artifact_dir: Path,
) -> tuple[bool, bool, dict[str, Any]]:
    official = list(verification.get("official_commands") or [])
    additional = list(verification.get("v10_additional_commands") or [])
    official_ok = _run_command_list(workspace, official, artifact_dir / "official.log")
    additional_ok = _run_command_list(
        workspace, additional, artifact_dir / "additional.log"
    )
    status = "passed" if official_ok else "failed"
    claim = {
        "artifact_digest": f"sha256:eval-{result_sha[:12]}",
        "status": status,
        "scope_commit_sha": result_sha,
        "adequacy_status": "adequate" if official_ok else "inadequate",
        "limitations": "" if additional_ok else "v10_additional_verification_failed",
    }
    return official_ok, additional_ok, claim


def _run_command_list(workspace: Path, commands: list[str], log_path: Path) -> bool:
    if not commands:
        # No commands declared: treat as pass so generic dispatch stays usable
        # for harness smoke without benchmark-specific verifiers.
        log_path.write_text("no commands\n", encoding="utf-8")
        return True
    ok = True
    lines: list[str] = []
    for command in commands:
        try:
            completed = subprocess.run(
                command,
                cwd=str(workspace),
                shell=True,
                check=False,
                capture_output=True,
                text=True,
                timeout=600,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            ok = False
            lines.append(f"$ {command}\nERROR {exc}\n")
            continue
        lines.append(
            f"$ {command}\nexit={completed.returncode}\n"
            f"{completed.stdout}\n{completed.stderr}\n"
        )
        if completed.returncode != 0:
            ok = False
    log_path.write_text("".join(lines), encoding="utf-8")
    return ok


def _failed_session(
    *,
    session_id: str,
    project: str,
    head_sha: str,
    run_id: str,
    reason_code: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "schema": SESSION_SCHEMA,
        "schema_version": "agent_session.v1",
        "session_id": session_id,
        "project": project,
        "repo": project.rsplit("/", 1)[-1] if "/" in project else project,
        "status": "failed",
        "head_sha": head_sha,
        "result_sha": None,
        "policy_source_sha": "",
        "control_plane_sha": control_plane_sha(),
        "worker_image_digest": "local-eval-dispatch",
        "ci_image_digest": "local-eval-dispatch",
        "run_ids": [run_id],
        "terminal_reason_code": reason_code,
        "terminal_reason": reason,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "finished_at": _utc_now(),
        "verification_claim": {
            "artifact_digest": "",
            "status": "failed",
            "scope_commit_sha": head_sha,
            "adequacy_status": "inadequate",
            "limitations": reason,
        },
        "evaluation_telemetry": {
            "official_benchmark_pass": False,
            "v10_additional_verification_pass": False,
            "agent_execution": True,
            "solver_attempts": 1,
        },
    }


def _write_session(session_id: str, record: dict[str, Any]) -> None:
    path = session_root() / f"{session_id}.json"
    if path.exists():
        raise EvalDispatchError(f"session already exists: {session_id}")
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: list[str] | None = None) -> int:
    """CLI entry: read one JSON message from stdin, write one JSON response."""
    del argv  # reserved for future flags; transport is stdin/stdout only
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"invalid JSON: {exc}"}), flush=True)
        return 2
    try:
        response = handle_message(payload)
    except EvalDispatchError as exc:
        print(json.dumps({"error": str(exc)}), flush=True)
        return 1
    print(json.dumps(response), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
