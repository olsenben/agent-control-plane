"""Fast verifier execution (VExp W2-B).

Advisory only; emits ``FastVerificationResult``. Never final authority.
"""

from __future__ import annotations

import subprocess
import time
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_shared.models.fast_verification import (
    FastVerificationRequest,
    FastVerificationResult,
    VerifierSelection,
)

from agent_control.repair.command_selection import DEV_FAST_VERIFY_TIMEOUT_S


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _map_exit_to_status(
    *,
    exit_code: int,
    timed_out: bool,
    execution_error: str | None,
) -> tuple[str, str]:
    if execution_error:
        if "timeout" in execution_error.lower() or timed_out:
            return "timeout", "infrastructure"
        if "blocked" in execution_error.lower():
            return "blocked", "infrastructure"
        return "error", "infrastructure"
    if timed_out:
        return "timeout", "infrastructure"
    if exit_code == 0:
        return "passed", "none"
    return "failed", "evaluated_agent"


def run_fast_verification(
    *,
    request: FastVerificationRequest,
    workspace: Path,
    artifact_dir: Path,
    command_runner: Any | None = None,
) -> FastVerificationResult:
    """Execute one bounded fast verification in a materialized workspace."""
    selection = request.verifier_selection
    started = _utc_now()
    start = time.monotonic()

    if command_runner is not None:
        outcome = command_runner(selection.command_ref, workspace, selection.timeout_s)
        exit_code = int(outcome.get("exit_code", 1))
        stdout = str(outcome.get("stdout", ""))
        stderr = str(outcome.get("stderr", ""))
        timed_out = bool(outcome.get("timed_out", False))
        exec_error = outcome.get("error")
    else:
        exit_code, stdout, stderr, timed_out, exec_error = _default_runner(
            selection.command_ref,
            workspace,
            selection.timeout_s,
        )

    duration = time.monotonic() - start
    stdout_ref = _persist_log(artifact_dir, "fast_stdout", stdout)
    stderr_ref = _persist_log(artifact_dir, "fast_stderr", stderr)

    status, failure_origin = _map_exit_to_status(
        exit_code=exit_code,
        timed_out=timed_out,
        execution_error=str(exec_error) if exec_error else None,
    )

    return FastVerificationResult(
        task_id=request.task_id,
        session_id=request.session_id,
        snapshot_sha=request.snapshot_sha,
        patch_hash=request.patch_hash,
        attempt_number=request.attempt_number,
        status=status,  # type: ignore[arg-type]
        failure_origin=failure_origin,  # type: ignore[arg-type]
        verifier_selection=selection,
        exit_code=exit_code,
        duration_seconds=round(duration, 4),
        stdout_artifact_ref=stdout_ref,
        stderr_artifact_ref=stderr_ref,
        started_at=started,
        finished_at=_utc_now(),
    )


def unavailable_fast_result(
    *,
    task_id: str,
    session_id: str,
    snapshot_sha: str,
    patch_hash: str,
    attempt_number: int = 0,
) -> FastVerificationResult:
    """Return unavailable status when no verifier could be selected."""
    return FastVerificationResult(
        task_id=task_id,
        session_id=session_id,
        snapshot_sha=snapshot_sha,
        patch_hash=patch_hash,
        attempt_number=attempt_number,
        status="unavailable",
        failure_origin="infrastructure",
        verifier_selection=VerifierSelection(
            verifier_id="unavailable",
            source="eval_manifest",
            command_ref="",
            display_name="unavailable",
            timeout_s=DEV_FAST_VERIFY_TIMEOUT_S,
        ),
    )


def from_command_outcome(
    *,
    task_id: str,
    session_id: str,
    snapshot_sha: str,
    patch_hash: str,
    selection: VerifierSelection,
    outcome: Mapping[str, Any],
    attempt_number: int = 0,
    artifact_dir: Path | None = None,
) -> FastVerificationResult:
    """DEV adapter: map a CommandOutcome-like dict to FastVerificationResult."""
    exit_code = int(outcome.get("exit_code", 1))
    stdout = str(outcome.get("stdout_tail") or outcome.get("stdout") or "")
    stderr = str(outcome.get("stderr_tail") or outcome.get("stderr") or "")
    stdout_ref = None
    stderr_ref = None
    if artifact_dir is not None:
        stdout_ref = _persist_log(artifact_dir, "fast_stdout", stdout)
        stderr_ref = _persist_log(artifact_dir, "fast_stderr", stderr)

    status, failure_origin = _map_exit_to_status(
        exit_code=exit_code,
        timed_out=False,
        execution_error=None,
    )
    return FastVerificationResult(
        task_id=task_id,
        session_id=session_id,
        snapshot_sha=snapshot_sha,
        patch_hash=patch_hash,
        attempt_number=attempt_number,
        status=status,  # type: ignore[arg-type]
        failure_origin=failure_origin,  # type: ignore[arg-type]
        verifier_selection=selection,
        exit_code=exit_code,
        duration_seconds=float(outcome.get("duration_seconds") or 0),
        stdout_artifact_ref=stdout_ref,
        stderr_artifact_ref=stderr_ref,
    )


def _default_runner(
    command: str,
    workspace: Path,
    timeout_s: int,
) -> tuple[int, str, str, bool, str | None]:
    if not command.strip():
        return 1, "", "empty command", False, "empty command"
    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        return completed.returncode, completed.stdout, completed.stderr, False, None
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if exc.stdout else ""
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        return 124, stdout, stderr, True, "timeout"
    except OSError as exc:
        return 1, "", str(exc), False, str(exc)


def _persist_log(artifact_dir: Path, prefix: str, content: str) -> str:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    name = f"{prefix}-{uuid.uuid4().hex[:8]}.log"
    path = artifact_dir / name
    path.write_text(content[-1_048_576:], encoding="utf-8")
    return name
