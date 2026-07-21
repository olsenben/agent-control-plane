"""V7 T01 Inspect adapter for eval_bundle.v1."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_control.eval_export import export_eval_bundle, verify_eval_bundle_sha256
from agent_control.inspect_adapter import (
    InspectAdaptError,
    adapt_eval_bundle_file,
    bundle_to_inspect_task,
    load_eval_bundle,
    try_build_inspect_memory_dataset,
)
from agent_control.observe.events import append_control_decision
from agent_control.session.storage import persist_session_with_run_index
from agent_shared.models.agent_session import AgentSession, SessionStatus


def _seed(root: Path, project: str, run_id: str) -> Path:
    session = AgentSession(
        session_id="sess-v7t01",
        project=project,
        repo=project.split("/", 1)[1],
        subject_kind="issue",
        subject_number=1,
        command_kind="plan",
        status=SessionStatus.QUEUED,
        run_ids=[run_id],
        correlation_id="corr-v7t01",
        trace_id="tr-v7t01",
        input_state_sha="a" * 64,
        head_sha="b" * 40,
        risk_level="risk1",
        invoked_by="alice",
        created_at="2026-07-21T00:00:00+00:00",
        updated_at="2026-07-21T00:00:00+00:00",
    )
    persist_session_with_run_index(root, session)
    append_control_decision(
        root,
        project=project,
        kind="other",
        summary="v7t01",
        session_id=session.session_id,
        run_id=run_id,
        trace_id=session.trace_id,
    )
    _, path = export_eval_bundle(root, project=project, run_id=run_id, output_dir=root / "exports")
    return path


def test_adapt_verified_bundle(tmp_path: Path) -> None:
    project = "ai-sdlc-lab/demo-app"
    path = _seed(tmp_path, project, "run-v7t01")
    task, out = adapt_eval_bundle_file(path, output_dir=tmp_path / "inspect")
    assert out.is_file()
    assert task["schema_version"] == "inspect_adapt.v1"
    assert task["production_memory_touched"] is False
    assert task["memory_namespace"].startswith("bakeoff/")
    assert len(task["samples"]) >= 1
    assert task["source_eval_bundle_sha256"]
    bundle = load_eval_bundle(path)
    assert verify_eval_bundle_sha256(bundle)
    assert task["source_eval_bundle_sha256"] == bundle.eval_bundle_sha256


def test_tampered_bundle_fail_closed(tmp_path: Path) -> None:
    project = "ai-sdlc-lab/demo-app"
    path = _seed(tmp_path, project, "run-v7t01b")
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["timeline"].append({"type": "tamper"})
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(InspectAdaptError, match="sha256"):
        load_eval_bundle(bad)


def test_bundle_to_inspect_task_no_prod_memory() -> None:
    from agent_shared.models.eval_bundle import EvalBundle

    bundle = EvalBundle(
        manifest={"project": "a/b", "run_id": "r1", "command_kind": "plan"},
        timeline=[{"type": "x"}],
        stages=[{"name": "queued", "status": "ok"}],
        eval_bundle_sha256="deadbeef",
        memory_namespace="eval_export",
        production_memory_touched=False,
    )
    # Skip SHA verify path by calling converter directly
    task = bundle_to_inspect_task(bundle)
    assert task["production_memory_touched"] is False
    assert all(s["metadata"]["production_memory_touched"] is False for s in task["samples"])


def test_optional_inspect_dataset_soft_import() -> None:
    doc = {
        "samples": [
            {"id": "1", "input": "hi", "target": "", "metadata": {}},
        ]
    }
    ds = try_build_inspect_memory_dataset(doc)
    # Either None (inspect_ai not installed) or a MemoryDataset-like object
    if ds is not None:
        assert len(list(ds)) >= 1 or hasattr(ds, "samples")
