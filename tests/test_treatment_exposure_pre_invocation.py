"""Pre-invocation treatment provenance survives parse/retry/exception failures."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from agent_control.context.treatment_artifacts import (
    PACK_FILENAME,
    RENDERED_FILENAME,
    TREATMENT_FILENAME,
)
from agent_control.context.v1_adapter import render_v2
from agent_control.eval_dispatch import DISPATCH_SCHEMA, dispatch_evaluation, get_session
from agent_shared.hash_utils import canonical_json_hash, sha256_text
from agent_workers.rlm.fake_engine import FakeRLMEngine
from agent_workers.rlm.official_engine import load_job_context_pack, render_job_context_pack

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "vexp_mini_repo"
PARSE_ERROR = (
    "Failed to parse fix output: Expecting ',' delimiter: line 9 column 20 (char 459)"
)
RETRY_TIMEOUT = (
    f"{PARSE_ERROR}; json retry failed: timed out; missing-json repair failed: timed out"
)


def _git_init_copy(tmp_path: Path) -> tuple[Path, str]:
    dest = tmp_path / "repo"
    shutil.copytree(FIXTURE, dest)
    subprocess.check_call(["git", "init"], cwd=dest)
    subprocess.check_call(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "add", "."],
        cwd=dest,
    )
    subprocess.check_call(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "init"],
        cwd=dest,
    )
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=dest, text=True).strip()
    return dest, sha


def _dispatch_request(repo: Path, sha: str, **overrides: object) -> dict:
    payload: dict[str, object] = {
        "schema": DISPATCH_SCHEMA,
        "eval_run_id": "eval-treatment",
        "project": "vexp/mini",
        "workspace": str(repo),
        "head_sha": sha,
        "policy_source_sha": "b" * 40,
        "problem_statement": "Fix foo in src/pkg/foo.py",
        "arm": "local-deterministic",
        "context_strategy": "deterministic",
        "controller_backend": "none",
        "frontier_escalation": False,
        "memory": {
            "policy": "off",
            "enabled": False,
            "namespace": "n",
            "audit_history_action": "retain",
        },
        "verification": {"official_commands": [], "v10_additional_commands": []},
        "limits": {"wall_seconds": 30, "attempts": 1},
        "evaluation_mode": "retrieval",
        "upstream_task_id": "sample-treatment",
        "context_mode": "context_v2",
    }
    payload.update(overrides)
    return payload


def _assert_pre_invocation_artifacts(artifact_dir: Path) -> dict:
    treatment_path = artifact_dir / TREATMENT_FILENAME
    pack_path = artifact_dir / PACK_FILENAME
    rendered_path = artifact_dir / RENDERED_FILENAME
    assert treatment_path.is_file(), artifact_dir
    assert pack_path.is_file()
    assert rendered_path.is_file()
    record = json.loads(treatment_path.read_text(encoding="utf-8"))
    pack_dump = json.loads(pack_path.read_text(encoding="utf-8"))
    rendered = rendered_path.read_text(encoding="utf-8")
    assert record["schema_version"] == "pre_invocation_treatment.v1"
    assert record["sequence_position"] == "pre_model_invocation"
    assert record["context_pack_hash"] == canonical_json_hash(pack_dump)
    assert record["rendered_context_hash"] == sha256_text(rendered)
    assert record["treatment"]["repair_attempt_index"] == 0
    assert record["treatment"]["recursive_invocations"] == 0
    return record


def _assert_session_links_treatment(session: dict, artifact: dict) -> None:
    tel = session["evaluation_telemetry"]
    assert tel["context_pack_hash"] == artifact["context_pack_hash"]
    assert tel["rendered_context_hash"] == artifact["rendered_context_hash"]
    assert tel["context_pack_version"] == artifact["context_pack_version"]
    assert tel["treatment_exposure_artifact"] == TREATMENT_FILENAME
    assert tel["invocation_id"] == artifact["invocation_id"]
    assert tel["repair_attempts"] == 0
    assert tel["recursive_invoked"] is False


def test_context_v2_persists_treatment_before_successful_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVAL_DISPATCH_SESSION_ROOT", str(tmp_path / "sessions"))
    monkeypatch.setenv("EVAL_DISPATCH_ENGINE", "fake")
    repo, sha = _git_init_copy(tmp_path / "ws")
    seen: list[Path] = []

    class _Capture(FakeRLMEngine):
        def run(self, job, workspace, policy, *, artifact_dir=None, **kwargs):  # noqa: ANN001
            path = Path(str(artifact_dir))
            seen.append(path)
            _assert_pre_invocation_artifacts(path)
            return super().run(job, workspace, policy, artifact_dir=artifact_dir, **kwargs)

    session_id = dispatch_evaluation(
        _dispatch_request(repo, sha, context_mode="context_v2"),
        engine_factory=lambda _name: _Capture(),
    )
    session = get_session(session_id, "vexp/mini")
    artifact_dir = Path(session["eval_dispatch"]["artifact_dir"])
    artifact = _assert_pre_invocation_artifacts(artifact_dir)
    _assert_session_links_treatment(session, artifact)
    tel = session["evaluation_telemetry"]
    assert tel["context_pack_version"] == "context-pack.v2"
    assert tel["evidence_provider_ids"]
    assert seen and seen[0] == artifact_dir
    pack = load_job_context_pack(
        {"context_pack": json.loads((artifact_dir / PACK_FILENAME).read_text(encoding="utf-8"))}
    )
    rendered = (artifact_dir / RENDERED_FILENAME).read_text(encoding="utf-8")
    assert rendered == render_v2(pack)
    assert rendered == render_job_context_pack(pack)
    assert artifact["experiment_arm"] == "context_v2"
    assert artifact["target_sha"] == sha
    assert artifact["repository"] == "vexp/mini"


def test_invalid_json_failure_keeps_pre_invocation_treatment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVAL_DISPATCH_SESSION_ROOT", str(tmp_path / "sessions"))
    hashes_before_raise: list[str] = []

    class _InvalidJson:
        def run(self, job, workspace, policy, *, artifact_dir=None, **kwargs):  # noqa: ANN001
            del job, workspace, policy, kwargs
            artifact = _assert_pre_invocation_artifacts(Path(str(artifact_dir)))
            hashes_before_raise.append(artifact["context_pack_hash"])
            raise ValueError(PARSE_ERROR)

    repo, sha = _git_init_copy(tmp_path / "ws")
    session_id = dispatch_evaluation(
        _dispatch_request(repo, sha, context_mode="context_v2", evaluation_mode="patch"),
        engine_factory=lambda _name: _InvalidJson(),
    )
    session = get_session(session_id, "vexp/mini")
    assert session["status"] == "failed"
    assert session["terminal_reason_code"] == "evaluated_agent"
    assert "Failed to parse fix output" in session["terminal_reason"]
    artifact_dir = Path(session["eval_dispatch"]["artifact_dir"])
    artifact = _assert_pre_invocation_artifacts(artifact_dir)
    _assert_session_links_treatment(session, artifact)
    assert hashes_before_raise == [artifact["context_pack_hash"]]
    assert artifact["context_pack_version"] == "context-pack.v2"
    assert list(artifact_dir.glob(TREATMENT_FILENAME)) == [artifact_dir / TREATMENT_FILENAME]


def test_json_retry_timeout_keeps_same_treatment_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVAL_DISPATCH_SESSION_ROOT", str(tmp_path / "sessions"))
    first_hash: list[str] = []

    class _RetryTimeout:
        def run(self, job, workspace, policy, *, artifact_dir=None, **kwargs):  # noqa: ANN001
            del job, workspace, policy, kwargs
            artifact = _assert_pre_invocation_artifacts(Path(str(artifact_dir)))
            first_hash.append(artifact["context_pack_hash"])
            raise ValueError(RETRY_TIMEOUT)

    repo, sha = _git_init_copy(tmp_path / "ws")
    session_id = dispatch_evaluation(
        _dispatch_request(repo, sha, context_mode="context_v2", evaluation_mode="patch"),
        engine_factory=lambda _name: _RetryTimeout(),
    )
    session = get_session(session_id, "vexp/mini")
    assert session["terminal_reason_code"] == "evaluated_agent"
    assert "json retry failed: timed out" in session["terminal_reason"]
    artifact_dir = Path(session["eval_dispatch"]["artifact_dir"])
    treatments = list(artifact_dir.glob("treatment_exposure*.json"))
    assert treatments == [artifact_dir / TREATMENT_FILENAME]
    artifact = _assert_pre_invocation_artifacts(artifact_dir)
    _assert_session_links_treatment(session, artifact)
    assert first_hash == [artifact["context_pack_hash"]]
    tel = session["evaluation_telemetry"]
    assert tel["context_pack_hash"] == first_hash[0]


def test_exception_after_model_before_patch_keeps_treatment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVAL_DISPATCH_SESSION_ROOT", str(tmp_path / "sessions"))

    class _AfterModel:
        def run(self, job, workspace, policy, *, artifact_dir=None, **kwargs):  # noqa: ANN001
            del workspace, policy, kwargs
            path = Path(str(artifact_dir))
            _assert_pre_invocation_artifacts(path)
            (path / "official_engine_messages.json").write_text(
                json.dumps({"system": "s", "user": "=== context-pack.v2 ===\n", "context_chars": 1})
                + "\n",
                encoding="utf-8",
            )
            (path / "model_output_excerpt_attempt_1.json").write_text("{}\n", encoding="utf-8")
            raise ValueError("exception after model invocation before patch extraction")

    repo, sha = _git_init_copy(tmp_path / "ws")
    session_id = dispatch_evaluation(
        _dispatch_request(repo, sha, context_mode="context_v2", evaluation_mode="patch"),
        engine_factory=lambda _name: _AfterModel(),
    )
    session = get_session(session_id, "vexp/mini")
    assert session["status"] == "failed"
    artifact = _assert_pre_invocation_artifacts(Path(session["eval_dispatch"]["artifact_dir"]))
    _assert_session_links_treatment(session, artifact)
    assert artifact["context_pack_hash"]
    assert session["evaluation_telemetry"]["context_mode"] == "context_v2"


def test_baseline_v1_behavior_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVAL_DISPATCH_SESSION_ROOT", str(tmp_path / "sessions"))
    monkeypatch.setenv("EVAL_DISPATCH_ENGINE", "fake")
    repo, sha = _git_init_copy(tmp_path / "ws")
    captured: list[dict] = []

    class _Capture(FakeRLMEngine):
        def run(self, job, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            captured.append(job)
            return super().run(job, *args, **kwargs)

    session_id = dispatch_evaluation(
        _dispatch_request(repo, sha, context_mode="baseline_v1"),
        engine_factory=lambda _name: _Capture(),
    )
    session = get_session(session_id, "vexp/mini")
    telemetry = session["evaluation_telemetry"]
    assert captured[0]["context_pack"]["schema_version"] == "context_pack.v1"
    assert telemetry["context_pack_version"] == "context_pack.v1"
    assert telemetry["context_mode"] == "baseline_v1"
    assert telemetry["repair_attempts"] == 0
    assert telemetry["recursive_invoked"] is False
    assert telemetry["context_pack_hash"]
    assert telemetry["rendered_context_hash"]
    artifact_dir = Path(session["eval_dispatch"]["artifact_dir"])
    artifact = _assert_pre_invocation_artifacts(artifact_dir)
    assert artifact["context_pack_version"] == "context_pack.v1"
    pack_dump = json.loads((artifact_dir / PACK_FILENAME).read_text(encoding="utf-8"))
    rendered = (artifact_dir / RENDERED_FILENAME).read_text(encoding="utf-8")
    assert telemetry["context_pack_hash"] == canonical_json_hash(pack_dump)
    assert telemetry["rendered_context_hash"] == sha256_text(rendered)


def test_treatment_hashes_match_serialized_pack_and_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVAL_DISPATCH_SESSION_ROOT", str(tmp_path / "sessions"))
    monkeypatch.setenv("EVAL_DISPATCH_ENGINE", "fake")
    repo, sha = _git_init_copy(tmp_path / "ws")
    captured: list[dict] = []

    class _Capture(FakeRLMEngine):
        def run(self, job, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            captured.append(job)
            return super().run(job, *args, **kwargs)

    session_id = dispatch_evaluation(
        _dispatch_request(repo, sha, context_mode="context_v2"),
        engine_factory=lambda _name: _Capture(),
    )
    session = get_session(session_id, "vexp/mini")
    artifact_dir = Path(session["eval_dispatch"]["artifact_dir"])
    artifact = _assert_pre_invocation_artifacts(artifact_dir)
    pack = load_job_context_pack(captured[0])
    rendered = render_job_context_pack(pack)
    assert artifact["context_pack_hash"] == canonical_json_hash(pack.model_dump(mode="json"))
    assert artifact["rendered_context_hash"] == sha256_text(rendered)
    tel = session["evaluation_telemetry"]
    assert tel["context_pack_hash"] == artifact["context_pack_hash"]
    assert tel["rendered_context_hash"] == artifact["rendered_context_hash"]
    assert tel["context_pack_version"] == "context-pack.v2"
    assert artifact["experiment_arm"] == "context_v2"
    assert "lexical" in artifact["evidence_provider_ids"]


def test_no_behavioral_drift_on_v2_failure_or_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVAL_DISPATCH_SESSION_ROOT", str(tmp_path / "sessions"))
    monkeypatch.setenv("EVAL_DISPATCH_ENGINE", "fake")
    repo, sha = _git_init_copy(tmp_path / "ws")

    class _Boom:
        def run(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            raise ValueError(RETRY_TIMEOUT)

    failed_id = dispatch_evaluation(
        _dispatch_request(repo, sha, context_mode="context_v2", eval_run_id="eval-fail"),
        engine_factory=lambda _name: _Boom(),
    )
    ok_id = dispatch_evaluation(
        _dispatch_request(repo, sha, context_mode="context_v2", eval_run_id="eval-ok"),
        engine_factory=lambda _name: FakeRLMEngine(),
    )
    for session_id in (failed_id, ok_id):
        session = get_session(session_id, "vexp/mini")
        tel = session["evaluation_telemetry"]
        assert tel["repair_attempts"] == 0
        assert tel["recursive_invoked"] is False
        assert "2070" not in json.dumps(tel).lower()
        assert session["eval_dispatch"]["engine"] in {"fake", "official"}
        assert tel.get("controller_backend") in {None, "none"}
