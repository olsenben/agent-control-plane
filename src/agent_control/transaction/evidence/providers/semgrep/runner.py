"""Execute Semgrep CE as a distinct process or container.

Never inherits durable Gitea tokens, capability signing keys, broker creds, or
actor creds. Candidate/source trees are mounted read-only. --config auto is
refused. Exit 0 with findings is FINDINGS_PRESENT, not a clean scan.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from agent_control.transaction.evidence.providers.semgrep.ruleset import (
    SEMGREP_IMAGE,
    SEMGREP_VERSION,
    compute_ruleset_digest,
    loaded_rule_ids,
    ruleset_path,
)
from agent_control.transaction.evidence.receipts import evidence_hash
from agent_control.transaction.evidence.sarif import sarif_digest

SCHEMA_EXECUTION = "provider_execution_receipt.v1"
OUTCOME_SUCCESS = "TOOL_EXECUTION_SUCCESS"
OUTCOME_FINDINGS = "FINDINGS_PRESENT"
OUTCOME_FAILURE = "TOOL_EXECUTION_FAILURE"
DEFAULT_TIMEOUT_SEC = 120.0
DEFAULT_CPUS = "1"
DEFAULT_MEMORY = "512m"

_CREDENTIAL_KEY_MARKERS = (
    "GITEA_",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "CAPABILITY",
    "BROKER",
    "AWS_",
    "OPENAI",
    "ANTHROPIC",
    "GIT_ASKPASS",
    "GIT_CREDENTIAL",
    "SSH_",
    "PRIVATE_KEY",
    "API_KEY",
    "BOT_TOKEN",
)


class SemgrepExecutor(Protocol):
    def __call__(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str],
        timeout_sec: float,
        cwd: str | None = None,
    ) -> dict[str, Any]:
        ...


class ProviderRunError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail or code


def sanitized_env(source: Mapping[str, str] | None = None) -> dict[str, str]:
    """Drop durable credentials. Provider is uncredentialed."""
    allow = {"PATH", "HOME", "LANG", "LC_ALL", "TZ", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT", "WINDIR"}
    env: dict[str, str] = {}
    for key, value in dict(source if source is not None else os.environ).items():
        upper = key.upper()
        if any(marker in upper for marker in _CREDENTIAL_KEY_MARKERS):
            continue
        if key in allow or upper in allow:
            env[key] = value
    env.setdefault("PATH", os.environ.get("PATH", "/usr/bin:/bin"))
    env["SEMGREP_SEND_METRICS"] = "off"
    env["SEMGREP_USER_AGENT_APPEND"] = "ai-sdlc-lab-evidence-provider"
    return env


def _forbid_auto_config(argv: Sequence[str]) -> None:
    joined = " ".join(argv)
    if "--config auto" in joined or "--config=auto" in joined:
        raise ProviderRunError("CONFIG_AUTO_FORBIDDEN", "--config auto is not allowed")


def subprocess_executor(
    argv: Sequence[str],
    *,
    env: Mapping[str, str],
    timeout_sec: float,
    cwd: str | None = None,
) -> dict[str, Any]:
    _forbid_auto_config(argv)
    started = time.monotonic()
    try:
        completed = subprocess.run(  # noqa: S603 - argv is constructed internally
            list(argv),
            capture_output=True,
            text=True,
            env=dict(env),
            timeout=timeout_sec,
            cwd=cwd,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ProviderRunError("MISSING_BINARY", str(exc)) from exc
    except subprocess.TimeoutExpired as exc:
        duration_ms = (time.monotonic() - started) * 1000.0
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return {
            "exit_code": None,
            "timed_out": True,
            "stdout": stdout,
            "stderr": stderr,
            "duration_ms": duration_ms,
        }
    duration_ms = (time.monotonic() - started) * 1000.0
    return {
        "exit_code": int(completed.returncode),
        "timed_out": False,
        "stdout": completed.stdout or "",
        "stderr": completed.stderr or "",
        "duration_ms": duration_ms,
    }


def _which_semgrep() -> str | None:
    return shutil.which("semgrep")


def _which_docker() -> str | None:
    return shutil.which("docker")


def _local_semgrep_version(semgrep_bin: str, executor: SemgrepExecutor) -> str | None:
    try:
        result = executor(
            [semgrep_bin, "--version"],
            env=sanitized_env(),
            timeout_sec=15.0,
        )
    except ProviderRunError:
        return None
    text = f"{result.get('stdout') or ''} {result.get('stderr') or ''}"
    for token in text.replace(",", " ").split():
        if token[0:1].isdigit() and "." in token:
            return token.strip()
    return None


def _scan_argv_local(*, semgrep_bin: str, target: Path, ruleset: Path, sarif_out: Path) -> list[str]:
    return [
        semgrep_bin,
        "scan",
        "--config",
        str(ruleset),
        "--sarif",
        "--sarif-output",
        str(sarif_out),
        "--metrics",
        "off",
        "--disable-version-check",
        "--quiet",
        str(target),
    ]


def _scan_argv_docker(
    *,
    docker_bin: str,
    target: Path,
    ruleset: Path,
    work_dir: Path,
) -> list[str]:
    return [
        docker_bin,
        "run",
        "--rm",
        "--network",
        "none",
        "--cpus",
        DEFAULT_CPUS,
        "--memory",
        DEFAULT_MEMORY,
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "-e",
        "HOME=/tmp",  # Semgrep writes ~/.semgrep; keep --read-only + network none viable.
        "-v",
        f"{target.resolve()}:/src:ro",
        "-v",
        f"{ruleset.resolve()}:/rules/{ruleset.name}:ro",
        "-v",
        f"{work_dir.resolve()}:/out:rw",
        SEMGREP_IMAGE,
        "semgrep",
        "scan",
        "--config",
        f"/rules/{ruleset.name}",
        "--sarif",
        "--sarif-output",
        "/out/semgrep.sarif",
        "--metrics",
        "off",
        "--disable-version-check",
        "--quiet",
        "/src",
    ]


def resolve_runtime(executor: SemgrepExecutor | None = None) -> tuple[str, str]:
    """Return (kind, binary). kind is docker|local."""
    run = executor or subprocess_executor
    docker_bin = _which_docker()
    if docker_bin:
        return "docker", docker_bin
    semgrep_bin = _which_semgrep()
    if not semgrep_bin:
        raise ProviderRunError("MISSING_BINARY", "semgrep binary and docker are unavailable")
    version = _local_semgrep_version(semgrep_bin, run)
    if version != SEMGREP_VERSION:
        raise ProviderRunError(
            "VERSION_MISMATCH",
            f"semgrep {version or 'unknown'} != pinned {SEMGREP_VERSION}",
        )
    return "local", semgrep_bin


def _execution_receipt(
    *,
    provider_id: str,
    target: str,
    argv: Sequence[str],
    result: Mapping[str, Any],
    raw_artifact_digest: str | None,
    ruleset_digest: str,
    outcome: str,
    detail: str | None = None,
    network: str,
) -> dict[str, Any]:
    stdout = str(result.get("stdout") or "")
    stderr = str(result.get("stderr") or "")
    return {
        "schema_version": SCHEMA_EXECUTION,
        "provider_id": provider_id,
        "producer_id": "semgrep_ce",
        "producer_version": SEMGREP_VERSION,
        "target": target,
        "outcome": outcome,
        "exit_code": result.get("exit_code"),
        "timed_out": bool(result.get("timed_out")),
        "duration_ms": result.get("duration_ms"),
        "stdout_digest": evidence_hash(stdout),
        "stderr_digest": evidence_hash(stderr),
        "raw_artifact_digest": raw_artifact_digest,
        "ruleset_digest": ruleset_digest,
        "argv": list(argv),
        "network": network,
        "detail": detail,
    }


def run_semgrep_scan(
    *,
    target: Path,
    scan_target: str,
    provider_id: str = "P2",
    ruleset: Path | None = None,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    artifact_dir: Path | None = None,
    executor: SemgrepExecutor | None = None,
    injected_sarif: str | bytes | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one read-only scan. Returns execution receipt + parsed SARIF payload."""
    run = executor or subprocess_executor
    rules = ruleset or ruleset_path()
    if not rules.is_file():
        raise ProviderRunError("MISSING_RULESET", str(rules))
    rule_ids = loaded_rule_ids(rules)
    if not rule_ids:
        raise ProviderRunError("ZERO_RULES", "frozen ruleset loaded zero rules")
    digest = compute_ruleset_digest(rules)

    if injected_sarif is not None:
        if isinstance(injected_sarif, (bytes, str)):
            raw = injected_sarif.decode("utf-8") if isinstance(injected_sarif, bytes) else injected_sarif
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ProviderRunError("MALFORMED_SARIF", str(exc)) from exc
        elif isinstance(injected_sarif, Mapping):
            payload = dict(injected_sarif)
            raw = json.dumps(payload, sort_keys=True)
        else:
            raise ProviderRunError("MALFORMED_SARIF", "injected SARIF is not JSON")
        return {
            "execution": _execution_receipt(
                provider_id=provider_id,
                target=scan_target,
                argv=["injected"],
                result={
                    "exit_code": 0,
                    "timed_out": False,
                    "stdout": "",
                    "stderr": "",
                    "duration_ms": 0,
                },
                raw_artifact_digest=sarif_digest(raw),
                ruleset_digest=digest,
                outcome=OUTCOME_SUCCESS,
                network="none",
            ),
            "sarif": payload,
            "raw_sarif": raw,
            "raw_sarif_digest": sarif_digest(raw),
            "ruleset_digest": digest,
            "loaded_rule_ids": rule_ids,
        }

    if not target.is_dir():
        raise ProviderRunError("UNBOUND_TREE", f"scan target missing: {target}")

    work = Path(tempfile.mkdtemp(prefix="semgrep-p2-"))
    sarif_out = work / "semgrep.sarif"
    if executor is not None:
        argv = _scan_argv_local(
            semgrep_bin="semgrep",
            target=target,
            ruleset=rules,
            sarif_out=sarif_out,
        )
        network = "none"
        cwd = str(target)
        run = executor
    else:
        kind, binary = resolve_runtime(run)
        if kind == "docker":
            argv = _scan_argv_docker(
                docker_bin=binary,
                target=target,
                ruleset=rules,
                work_dir=work,
            )
            network = "none"
            cwd = None
        else:
            argv = _scan_argv_local(
                semgrep_bin=binary,
                target=target,
                ruleset=rules,
                sarif_out=sarif_out,
            )
            network = "host-unspecified"
            cwd = str(target)
    _forbid_auto_config(argv)

    result = run(argv, env=sanitized_env(), timeout_sec=timeout_sec, cwd=cwd)
    if result.get("timed_out"):
        receipt = _execution_receipt(
            provider_id=provider_id,
            target=scan_target,
            argv=argv,
            result=result,
            raw_artifact_digest=None,
            ruleset_digest=digest,
            outcome=OUTCOME_FAILURE,
            detail="TIMEOUT",
            network=network,
        )
        return {
            "execution": receipt,
            "sarif": None,
            "raw_sarif": None,
            "raw_sarif_digest": None,
            "ruleset_digest": digest,
            "loaded_rule_ids": rule_ids,
            "failure": "TIMEOUT",
        }

    exit_code = result.get("exit_code")
    # Semgrep without --error: 0 success (findings possible), 2+ tool failure.
    if exit_code not in {0, 1}:
        receipt = _execution_receipt(
            provider_id=provider_id,
            target=scan_target,
            argv=argv,
            result=result,
            raw_artifact_digest=None,
            ruleset_digest=digest,
            outcome=OUTCOME_FAILURE,
            detail=f"EXIT_{exit_code}",
            network=network,
        )
        return {
            "execution": receipt,
            "sarif": None,
            "raw_sarif": None,
            "raw_sarif_digest": None,
            "ruleset_digest": digest,
            "loaded_rule_ids": rule_ids,
            "failure": "TOOL_EXECUTION_FAILURE",
        }

    if not sarif_out.is_file():
        stdout = str(result.get("stdout") or "")
        if stdout.strip().startswith("{"):
            raw = stdout
        else:
            receipt = _execution_receipt(
                provider_id=provider_id,
                target=scan_target,
                argv=argv,
                result=result,
                raw_artifact_digest=None,
                ruleset_digest=digest,
                outcome=OUTCOME_FAILURE,
                detail="MISSING_SARIF",
                network=network,
            )
            return {
                "execution": receipt,
                "sarif": None,
                "raw_sarif": None,
                "raw_sarif_digest": None,
                "ruleset_digest": digest,
                "loaded_rule_ids": rule_ids,
                "failure": "MISSING_SARIF",
            }
    else:
        raw = sarif_out.read_text(encoding="utf-8")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        receipt = _execution_receipt(
            provider_id=provider_id,
            target=scan_target,
            argv=argv,
            result=result,
            raw_artifact_digest=sarif_digest(raw),
            ruleset_digest=digest,
            outcome=OUTCOME_FAILURE,
            detail="MALFORMED_SARIF",
            network=network,
        )
        return {
            "execution": receipt,
            "sarif": None,
            "raw_sarif": raw,
            "raw_sarif_digest": sarif_digest(raw),
            "ruleset_digest": digest,
            "loaded_rule_ids": rule_ids,
            "failure": "MALFORMED_SARIF",
            "parse_error": str(exc),
        }

    if artifact_dir is not None:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        dest = artifact_dir / f"{scan_target}.sarif.json"
        dest.write_text(raw, encoding="utf-8")

    raw_digest = sarif_digest(raw)
    receipt = _execution_receipt(
        provider_id=provider_id,
        target=scan_target,
        argv=argv,
        result=result,
        raw_artifact_digest=raw_digest,
        ruleset_digest=digest,
        outcome=OUTCOME_SUCCESS,
        network=network,
    )
    return {
        "execution": receipt,
        "sarif": payload,
        "raw_sarif": raw,
        "raw_sarif_digest": raw_digest,
        "ruleset_digest": digest,
        "loaded_rule_ids": rule_ids,
        "failure": None,
    }
