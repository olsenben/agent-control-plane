"""V6 T01 — trace, provenance, observation projection."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_control.observe.events import append_control_decision
from agent_control.observe.projection import build_observation_projection
from agent_control.observe.provenance import build_provenance_items, trust_class_for_source
from agent_control.session.lifecycle import begin_typed_session, create_session_record
from agent_control.telemetry import init_telemetry, short_span, telemetry_stats
from agent_shared.input_state import make_trace_id
from agent_shared.models.context_pack import ContextPack
from agent_shared.models.jobs import TriggerContext


def test_make_trace_id_is_32_hex() -> None:
    tid = make_trace_id()
    assert len(tid) == 32
    int(tid, 16)


def test_trust_class_mapping() -> None:
    assert trust_class_for_source("gitea_issue") == "untrusted_issue_content"
    assert trust_class_for_source("adr_slice") == "trusted_policy"


def test_provenance_items_from_sources() -> None:
    items = build_provenance_items(["gitea_issue", "adr_slice"])
    assert len(items) == 2
    assert items[0]["trust_class"] == "untrusted_issue_content"


def test_create_session_record_has_trace_id() -> None:
    session = create_session_record(
        project="ai-sdlc-lab/demo-app",
        command_kind="review",
        run_id="run-t01-test",
        head_sha="abc123",
        trigger_context=TriggerContext(
            event_type="issue_comment",
            author="alice",
            issue_number=1,
        ),
    )
    assert session.trace_id
    assert len(session.trace_id) == 32


def test_telemetry_noop_without_otel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    init_telemetry()
    before = telemetry_stats().spans_started
    with short_span("test.span", trace_id=make_trace_id()):
        pass
    assert telemetry_stats().spans_started == before + 1


def test_control_decision_and_projection(tmp_path: Path) -> None:
    project = "ai-sdlc-lab/demo-app"
    run_id = "run-t01-proj"
    session = begin_typed_session(
        tmp_path,
        project=project,
        command_kind="review",
        run_id=run_id,
        head_sha="deadbeef",
        trigger_context=TriggerContext(event_type="issue_comment", author="bob", issue_number=2),
    )
    append_control_decision(
        tmp_path,
        project=project,
        kind="approval_required",
        summary="test decision",
        session_id=session.session_id,
        run_id=run_id,
        trace_id=session.trace_id,
    )
    doc = build_observation_projection(tmp_path, project=project, run_id=run_id)
    assert doc.trace_id == session.trace_id
    assert doc.max_sequence >= 2
    assert any(s.name == "decisions" for s in doc.stages)
    sequences = [e["sequence"] for e in doc.events]
    assert sequences == sorted(sequences)



def test_context_pack_model_carries_provenance() -> None:
    pack = ContextPack(
        project="ai-sdlc-lab/demo-app",
        context_sources=["gitea_issue"],
        provenance_items=build_provenance_items(["gitea_issue"]),
    )
    assert pack.provenance_items[0]["trust_class"] == "untrusted_issue_content"
