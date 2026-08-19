"""W1-E/F context_mode, discriminated job transport, production V2 factory."""

from __future__ import annotations

import inspect
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from agent_control.config import Settings
from agent_control.context.v1_adapter import render_v2
from agent_control.context.v2_dispatch import (
    CONTEXT_MODE_BASELINE_V1,
    CONTEXT_MODE_V2,
    CONTEXT_MODE_V2_LEXICAL,
    from_eval,
    from_production,
    make_context_builder,
    resolve_production_context_mode,
)
from agent_control.eval_arm_context import CONTEXT_MODES, H1_ARMS, apply_arm_context, apply_eval_context
from agent_control.eval_dispatch import DISPATCH_SCHEMA, dispatch_evaluation, get_session
from agent_control.graph.context_pack import compile_context_pack
from agent_control.project_registry import RefResolution
from agent_shared.hash_utils import sha256_text
from agent_shared.models.context_pack import ContextPack
from agent_shared.models.context_pack_v2 import (
    ContextPackV2,
    ContextTask,
    CurrentEvidence,
    EvidenceItem,
)
from agent_shared.models.evidence_query import ContextTaskSpec
from agent_workers.rlm.fake_engine import FakeRLMEngine
from agent_workers.rlm.official_engine import (
    assemble_official_engine_prompts,
    load_job_context_pack,
    render_job_context_pack,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "vexp_mini_repo"


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


def _eval_kwargs(workspace: Path, sha: str, **overrides: object) -> dict:
    payload: dict[str, object] = {
        "arm": "local-deterministic",
        "controller_backend": "none",
        "workspace": workspace,
        "project": "vexp/mini",
        "question": "Fix foo in src/pkg/foo.py",
        "session_id": "sess-ctx",
        "run_id": "run-ctx",
        "source_sha": sha,
        "policy_source_sha": "b" * 40,
        "state_root": workspace / "state",
        "context_mode": "baseline_v1",
    }
    payload.update(overrides)
    return payload


def _dispatch_request(repo: Path, sha: str, **overrides: object) -> dict:
    payload: dict[str, object] = {
        "schema": DISPATCH_SCHEMA,
        "eval_run_id": "eval-ctx",
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
        "upstream_task_id": "sample-ctx",
        "context_mode": "baseline_v1",
    }
    payload.update(overrides)
    return payload


def test_context_modes_do_not_replace_h1_arms() -> None:
    assert H1_ARMS == (
        "local-direct",
        "local-deterministic",
        "local-recursive-fallback",
        "local-recursive-2070",
    )
    assert CONTEXT_MODES == ("baseline_v1", "context_v2_lexical", "context_v2")


def test_baseline_v1_still_applies_local_deterministic_v1_pack(tmp_path: Path) -> None:
    workspace, sha = _git_init_copy(tmp_path)
    via_mode = apply_eval_context(**_eval_kwargs(workspace, sha, context_mode="baseline_v1"))
    via_arm = apply_arm_context(
        **{
            k: v
            for k, v in _eval_kwargs(workspace, sha).items()
            if k != "context_mode"
        }
    )
    assert via_mode.context_pack is not None
    assert via_mode.context_pack["schema_version"] == "context_pack.v1"
    assert via_mode.context_pack["prior_memory"] == []
    assert via_arm.context_pack is not None
    assert via_arm.context_pack["schema_version"] == "context_pack.v1"
    assert via_mode.recursive_invoked is False


def test_context_v2_lexical_puts_v2_pack_lexical_only(tmp_path: Path) -> None:
    workspace, sha = _git_init_copy(tmp_path)
    ctx = apply_eval_context(
        **_eval_kwargs(workspace, sha, context_mode="context_v2_lexical")
    )
    assert ctx.context_pack is not None
    assert ctx.context_pack["schema_version"] == "context-pack.v2"
    assert ctx.context_pack["experience"]["authorized_records"] == []
    assert ctx.recursive_invoked is False
    assert ctx.controller_telemetry["controller_model_invoked"] is False
    assert ctx.treatment_integrity["context_pack_version"] == "context-pack.v2"
    assert ctx.treatment_integrity["evidence_provider_ids"] == ["lexical"]
    events = {item["event_name"] for item in ctx.experience_events}
    assert events == {"context.candidate_evidence", "context.evidence_selected"}
    for envelope in ctx.experience_events:
        payload_text = json.dumps(envelope["payload"])
        assert "prompt" not in payload_text.lower()


def test_context_v2_puts_full_provider_v2_pack(tmp_path: Path) -> None:
    workspace, sha = _git_init_copy(tmp_path)
    ctx = apply_eval_context(**_eval_kwargs(workspace, sha, context_mode="context_v2"))
    assert ctx.context_pack is not None
    assert ctx.context_pack["schema_version"] == "context-pack.v2"
    providers = ctx.treatment_integrity["evidence_provider_ids"]
    assert "lexical" in providers
    assert "symbol" in providers
    assert "graph" in providers
    assert ctx.recursive_invoked is False


def test_dispatch_baseline_v1_records_v1_hashes(
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
    assert telemetry["context_mode"] == "baseline_v1"
    assert telemetry["repair_attempts"] == 0
    assert telemetry["recursive_invoked"] is False
    assert captured
    pack = captured[0]["context_pack"]
    assert pack["schema_version"] == "context_pack.v1"
    assert telemetry["context_pack_version"] == "context_pack.v1"
    assert telemetry["context_pack_hash"]
    assert telemetry["rendered_context_hash"]
    assert telemetry["target_sha"] == sha


def test_dispatch_context_v2_persists_treatment_hashes(
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
    telemetry = session["evaluation_telemetry"]
    assert captured[0]["context_pack"]["schema_version"] == "context-pack.v2"
    assert telemetry["context_pack_version"] == "context-pack.v2"
    assert telemetry["repo_snapshot_id"]
    assert telemetry["target_sha"] == sha
    assert telemetry["context_pack_hash"]
    assert telemetry["rendered_context_hash"]
    assert telemetry["evidence_provider_ids"]
    assert telemetry["repair_attempts"] == 0
    assert telemetry["recursive_invoked"] is False
    artifact_dir = Path(session["eval_dispatch"]["artifact_dir"])
    messages = json.loads(
        (artifact_dir / "official_engine_messages.json").read_text(encoding="utf-8")
    )
    user = messages["user"]
    assert "=== context-pack.v2 ===" in user
    assert "=== context_pack.v1 ===" not in user
    pack = load_job_context_pack(captured[0])
    rendered = render_job_context_pack(pack)
    assert rendered in user
    assert sha256_text(rendered) == telemetry["rendered_context_hash"]
    assert rendered == render_v2(pack)


def test_v2_pack_is_not_silently_rendered_as_v1(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "README.md").write_text("hello\n", encoding="utf-8")
    pack = ContextPackV2(
        task=ContextTask(project="vexp/mini", issue_text="fix foo"),
        current_evidence=CurrentEvidence(
            lexical=[EvidenceItem(text="def foo(): pass", source="lexical.rg", id="e1")]
        ),
    )
    job = {
        "run_id": "run-v2",
        "session_id": "sess-v2",
        "project": "vexp/mini",
        "flow": "developer_flow",
        "agent": "developer",
        "risk_class": "write_patch",
        "command_intent": {"kind": "fix", "natural_language_task": "fix foo"},
        "safety": {"command_scope": "fix"},
        "fix_authorization": {"allowed_files": ["README.md"]},
        "context_pack": pack.model_dump(mode="json"),
    }
    assembled = assemble_official_engine_prompts(job=job, workspace=workspace)
    assert "=== context-pack.v2 ===" in assembled["context_text"]
    assert "=== context_pack.v1 ===" not in assembled["user"]
    assert "def foo(): pass" in assembled["user"]
    v1 = ContextPack(project="vexp/mini", search_hits=["only-v1-hit"])
    v1_job = dict(job)
    v1_job["context_pack"] = v1.model_dump(mode="json")
    v1_assembled = assemble_official_engine_prompts(job=v1_job, workspace=workspace)
    assert "=== context_pack.v1 ===" in v1_assembled["context_text"]
    assert "only-v1-hit" in v1_assembled["user"]


def test_unknown_schema_version_is_not_a_silent_fallback(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "README.md").write_text("hello\n", encoding="utf-8")
    job = {
        "command_intent": {"kind": "inspect", "natural_language_task": "x"},
        "safety": {"command_scope": "inspect"},
        "risk_class": "read_only",
        "context_pack": {"schema_version": "context_pack.v9", "project": "x"},
    }
    with pytest.raises(ValueError, match="unsupported context_pack schema_version"):
        assemble_official_engine_prompts(job=job, workspace=workspace)


def test_fake_engine_v2_pack_does_not_read_blast_radius(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "README.md").write_text("hello\n", encoding="utf-8")
    pack = ContextPackV2(
        task=ContextTask(project="vexp/mini", issue_text="review foo"),
        current_evidence=CurrentEvidence(
            lexical=[EvidenceItem(text="def foo", source="lexical.rg")]
        ),
    )
    job = {
        "run_id": "run-fake-v2",
        "session_id": "sess-fake-v2",
        "project": "vexp/mini",
        "flow": "review",
        "agent": "reviewer",
        "risk_class": "read_only_with_repo_context",
        "workflow_definition": "review",
        "flow_config_id": "review",
        "flow_version": "1",
        "command_intent": {"kind": "review", "natural_language_task": "review foo"},
        "safety": {"command_scope": "review"},
        "context_pack": pack.model_dump(mode="json"),
    }
    result = FakeRLMEngine().run(job, workspace, {"warnings": []}, artifact_dir=str(tmp_path))
    assert result.review_result is not None


def test_production_default_is_baseline_v1_compile_context_pack() -> None:
    settings = Settings(_env_file=None)
    assert settings.context_mode == CONTEXT_MODE_BASELINE_V1
    assert resolve_production_context_mode(settings) == CONTEXT_MODE_BASELINE_V1
    from agent_control.session import prepare_dispatch

    source = inspect.getsource(prepare_dispatch.prepare_typed_rlm_dispatch)
    assert "compile_context_pack" in source
    assert "CONTEXT_MODE_BASELINE_V1" in source
    assert inspect.isfunction(compile_context_pack)


def test_production_v2_factory_materializes_detached_sha_then_builds(tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    shutil.copytree(FIXTURE, origin)
    subprocess.check_call(["git", "init"], cwd=origin)
    subprocess.check_call(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "add", "."],
        cwd=origin,
    )
    subprocess.check_call(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "first"],
        cwd=origin,
    )
    sha1 = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=origin, text=True).strip()
    (origin / "later.txt").write_text("tip\n", encoding="utf-8")
    subprocess.check_call(["git", "-c", "user.name=t", "-c", "user.email=t@t", "add", "."], cwd=origin)
    subprocess.check_call(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "second"],
        cwd=origin,
    )
    sha2 = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=origin, text=True).strip()
    assert sha1 != sha2
    refs = RefResolution(
        policy_ref="main",
        policy_sha=sha1,
        task_ref="HEAD",
        task_sha=sha1,
        base_ref="main",
        target_sha=sha1,
        primary_branch="main",
    )
    dest = tmp_path / "evidence"
    result = from_production(
        project="vexp/mini",
        refs=refs,
        repo_url=origin.resolve().as_uri(),
        dest=dest,
        task=ContextTaskSpec(project="vexp/mini", issue_text="Fix foo in src/pkg/foo.py"),
        mode=CONTEXT_MODE_V2,
    )
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=dest, text=True).strip()
    assert head == sha1
    assert head != sha2
    symbolic = subprocess.run(
        ["git", "symbolic-ref", "-q", "HEAD"],
        cwd=dest,
        capture_output=True,
        text=True,
        check=False,
    )
    assert symbolic.returncode != 0
    assert result.context_pack.schema_version == "context-pack.v2"
    assert result.snapshot.workspace_path == str(dest)
    assert result.snapshot.target_sha == sha1
    module = inspect.getsource(
        __import__("agent_control.context.v2_dispatch", fromlist=["from_production"])
    )
    assert "graph.snapshot" not in module
    assert "materialize_exact_sha_workspace" in module


def test_from_eval_does_not_reclone(tmp_path: Path) -> None:
    workspace, sha = _git_init_copy(tmp_path)
    marker = workspace / "already-here.txt"
    marker.write_text("keep\n", encoding="utf-8")
    result = from_eval(
        repository_id="vexp/mini",
        target_sha=sha,
        workspace_path=workspace,
        task=ContextTaskSpec(project="vexp/mini", issue_text="Fix foo in src/pkg/foo.py"),
        mode=CONTEXT_MODE_V2_LEXICAL,
    )
    assert marker.is_file()
    assert result.snapshot.workspace_path == str(workspace)
    assert result.build_trace.providers_invoked == ["lexical"]


def test_same_builder_class_eval_and_production() -> None:
    eval_builder = make_context_builder(CONTEXT_MODE_V2)
    prod_builder = make_context_builder(CONTEXT_MODE_V2)
    assert type(eval_builder) is type(prod_builder)
    from agent_control.context.builder import ContextBuilder

    assert isinstance(eval_builder, ContextBuilder)
