"""Deterministic FailureEvidence normalization (VExp W2-A).

Input domain: ``FastVerificationResult`` + referenced stdout/stderr artifacts.
Does not import eval harness domain types directly.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from agent_shared.models.failure_evidence import (
    MAX_ASSERTION_SUMMARY,
    MAX_EXCEPTION_SUMMARY,
    MAX_FILE_PATHS,
    MAX_SYMBOL_NAMES,
    MAX_TRACEBACK_FRAMES,
    FAILURE_CLASS,
    FailureEvidence,
    TruncationMeta,
)
from agent_shared.models.fast_verification import FastVerificationResult

NORMALIZER_VERSION = "failure_evidence_normalizer.v1"

_PYTEST_FAILED_LINE = re.compile(
    r"^(?P<path>[^\s]+)::(?P<testid>[^\s]+)\s+FAILED",
    re.MULTILINE,
)
_ASSERTION_ERROR = re.compile(r"(AssertionError:.{0,500})", re.DOTALL)
_EXCEPTION_LINE = re.compile(r"^(\w+(?:Error|Exception)):\s*(.{0,200})", re.MULTILINE)
_TRACEBACK_FRAME = re.compile(
    r'File "(?P<path>[^"]+)", line (?P<line>\d+)(?:, in (?P<func>[^\n]+))?'
)
_SYMBOL_DEF = re.compile(r"^\s*(?:def|class)\s+(\w+)", re.MULTILINE)


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[: limit - 3] + "...", True


def _bounded_list(items: list[str], limit: int) -> tuple[list[str], bool]:
    deduped = list(dict.fromkeys(items))
    if len(deduped) <= limit:
        return deduped, False
    return deduped[:limit], True


def _read_artifact(ref: str | None, artifact_root: Path | None) -> str:
    if not ref or artifact_root is None:
        return ""
    path = artifact_root / ref if not Path(ref).is_absolute() else Path(ref)
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _classify_failure(
    *,
    exit_code: int | None,
    stdout: str,
    stderr: str,
    status: str,
) -> FAILURE_CLASS:
    combined = f"{stdout}\n{stderr}"
    if status == "timeout":
        return "timeout"
    if "SyntaxError" in combined:
        return "syntax_error"
    if "AssertionError" in combined or "assert " in combined.lower():
        return "assertion_failure"
    if _PYTEST_FAILED_LINE.search(combined):
        return "test_failure"
    if _EXCEPTION_LINE.search(combined):
        return "exception"
    if exit_code not in (None, 0):
        return "unknown"
    return "unknown"


def normalize_fast_verification_result(
    result: FastVerificationResult,
    *,
    artifact_root: Path | None = None,
    failure_id: str | None = None,
) -> FailureEvidence | None:
    """Normalize a failed fast verification into bounded FailureEvidence."""
    if result.status != "failed" or result.failure_origin != "evaluated_agent":
        return None

    stdout = _read_artifact(result.stdout_artifact_ref, artifact_root)
    stderr = _read_artifact(result.stderr_artifact_ref, artifact_root)
    combined = f"{stdout}\n{stderr}"

    failing_paths: list[str] = []
    failing_ids: list[str] = []
    for match in _PYTEST_FAILED_LINE.finditer(combined):
        failing_paths.append(match.group("path"))
        failing_ids.append(match.group("testid"))

    assertion_summary = ""
    assertion_trunc = False
    for match in _ASSERTION_ERROR.finditer(combined):
        assertion_summary, assertion_trunc = _truncate(match.group(1).strip(), MAX_ASSERTION_SUMMARY)
        break
    if not assertion_summary:
        for match in _EXCEPTION_LINE.finditer(combined):
            assertion_summary, assertion_trunc = _truncate(
                f"{match.group(1)}: {match.group(2).strip()}",
                MAX_ASSERTION_SUMMARY,
            )
            break

    exception_summary = ""
    exception_trunc = False
    for match in _EXCEPTION_LINE.finditer(combined):
        exception_summary, exception_trunc = _truncate(
            f"{match.group(1)}: {match.group(2).strip()}",
            MAX_EXCEPTION_SUMMARY,
        )
        break

    traceback_locations: list[str] = []
    file_paths: list[str] = []
    symbol_names: list[str] = []
    for match in _TRACEBACK_FRAME.finditer(combined):
        loc = f"{match.group('path')}:{match.group('line')}"
        if match.group("func"):
            loc += f" in {match.group('func').strip()}"
        traceback_locations.append(loc)
        file_paths.append(match.group("path"))
        if match.group("func"):
            symbol_names.append(match.group("func").strip())

    for match in _SYMBOL_DEF.finditer(combined):
        symbol_names.append(match.group(1))

    traceback_locations, tb_trunc = _bounded_list(traceback_locations, MAX_TRACEBACK_FRAMES)
    file_paths, fp_trunc = _bounded_list(file_paths, MAX_FILE_PATHS)
    symbol_names, sym_trunc = _bounded_list(symbol_names, MAX_SYMBOL_NAMES)
    failing_paths, _ = _bounded_list(failing_paths, MAX_FILE_PATHS)
    failing_ids, _ = _bounded_list(failing_ids, MAX_FILE_PATHS)

    failure_class = _classify_failure(
        exit_code=result.exit_code,
        stdout=stdout,
        stderr=stderr,
        status=result.status,
    )

    return FailureEvidence(
        failure_id=failure_id or f"fail-{uuid.uuid4().hex[:12]}",
        task_id=result.task_id,
        session_id=result.session_id,
        attempt_number=result.attempt_number,
        verifier_id=result.verifier_selection.verifier_id,
        command_id=result.verifier_selection.verifier_id,
        command=result.verifier_selection.command_ref,
        display_name=result.verifier_selection.display_name,
        exit_code=result.exit_code,
        failure_class=failure_class,
        failing_test_paths=failing_paths,
        failing_test_ids=failing_ids,
        assertion_summary=assertion_summary,
        exception_summary=exception_summary,
        traceback_locations=traceback_locations,
        file_paths=file_paths,
        symbol_names=symbol_names,
        patch_hash=result.patch_hash,
        stdout_artifact_ref=result.stdout_artifact_ref,
        stderr_artifact_ref=result.stderr_artifact_ref,
        verification_artifact_ref=None,
        normalizer_version=NORMALIZER_VERSION,
        truncation=TruncationMeta(
            assertion_summary_truncated=assertion_trunc,
            exception_summary_truncated=exception_trunc,
            traceback_frames_truncated=tb_trunc,
            file_paths_truncated=fp_trunc,
            symbol_names_truncated=sym_trunc,
        ),
    )
