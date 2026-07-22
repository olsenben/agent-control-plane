"""V9 T07 -- observe_decision.v1 (decision/why/evidence/alternatives_rejected/
remaining_uncertainty; no chain_of_thought).

Covers:

- ``sanitize_decision_metadata``: allowlist-only extraction of the four
  known sub-keys; any other key (including a ``chain_of_thought``-shaped
  name, and including one of the four known key *names* that is itself
  chain-of-thought-shaped) is withheld by name only.
- ``build_decision_from_raw_event``: builds a full ``ObserveDecisionV1``
  from a raw ``agent.control_decision`` ledger event; rejects
  non-decision/malformed events.
- ``list_decisions_for_run`` / ``decisions_panel_view``: scoped to a
  run_id, oldest first, empty when neither run_id nor session_id given.
- End-to-end via the five-panel page: panel 3 renders real decision
  content (decision/why/evidence/alternatives_rejected/remaining_uncertainty)
  when present, auto-escaped; a raw metadata dict is never embedded
  verbatim in the page source; a session with zero decisions still shows
  the pre-existing T04 placeholder text (backward compatible).
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent_control.observe.decisions import (
    ObserveDecisionV1,
    build_decision_from_raw_event,
    decisions_panel_view,
    is_chain_of_thought_like_name,
    list_decisions_for_run,
    sanitize_decision_metadata,
)
from agent_control.observe.events import append_control_decision
from agent_control.session.storage import persist_session_with_run_index
from agent_control.webhook_server import create_app
from agent_shared.models.agent_session import AgentSession, SessionStatus

PROJECT = "ai-sdlc-lab/demo-app"


def _seed_session(root: Path, *, run_id: str, session_id: str) -> AgentSession:
    session = AgentSession(
        session_id=session_id,
        project=PROJECT,
        repo=PROJECT.split("/", 1)[1],
        subject_kind="issue",
        subject_number=11,
        command_kind="review",
        status=SessionStatus.RUNNING,
        run_ids=[run_id],
        correlation_id=f"corr-{session_id}",
        trace_id=f"tr-{session_id}",
        input_state_sha="a" * 64,
        head_sha="b" * 40,
        policy_source_sha="c" * 40,
        risk_level="risk1",
        risk_tags=["needs_review"],
        invoked_by="tester",
        created_at="2026-07-22T00:00:00+00:00",
        updated_at="2026-07-22T00:05:00+00:00",
    )
    persist_session_with_run_index(root, session)
    return session


def _app(tmp_path: Path, monkeypatch, **env):
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("OBSERVE_REQUIRE_AUTH", "false")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return create_app()


# --- sanitize_decision_metadata -------------------------------------------


def test_sanitize_extracts_only_known_keys() -> None:
    metadata = {
        "why": "policy X requires manual review above risk1",
        "evidence": ["adr-0012", "graph-blast-radius-report-9"],
        "alternatives_rejected": ["auto-approve", "silent-skip"],
        "remaining_uncertainty": "coverage of edge-case Y is unverified",
        "unrelated_internal_field": "should never surface",
    }
    extracted, withheld = sanitize_decision_metadata(metadata)
    assert extracted["why"] == metadata["why"]
    assert extracted["evidence"] == metadata["evidence"]
    assert extracted["alternatives_rejected"] == metadata["alternatives_rejected"]
    assert extracted["remaining_uncertainty"] == metadata["remaining_uncertainty"]
    assert withheld == ["unrelated_internal_field"]


def test_sanitize_never_returns_a_chain_of_thought_field() -> None:
    metadata = {
        "chain_of_thought": "step 1: consider... step 2: therefore...",
        "why": "short rationale",
    }
    extracted, withheld = sanitize_decision_metadata(metadata)
    assert "chain_of_thought" not in extracted
    assert extracted["why"] == "short rationale"
    assert "chain_of_thought" in withheld


def test_sanitize_withholds_a_known_key_name_that_is_itself_cot_shaped() -> None:
    """Defense in depth: even if a future producer mislabels raw reasoning
    under a key that happens to also look chain-of-thought-shaped, it must
    never be treated as a normal known key."""
    metadata = {"why_chain_of_thought": "should never surface"}
    extracted, withheld = sanitize_decision_metadata(metadata)
    assert extracted == {}
    assert withheld == ["why_chain_of_thought"]


def test_sanitize_non_dict_metadata_returns_empty() -> None:
    extracted, withheld = sanitize_decision_metadata("not-a-dict")
    assert extracted == {}
    assert withheld == []


def test_sanitize_caps_long_strings_and_lists() -> None:
    metadata = {
        "why": "x" * 10_000,
        "evidence": [f"ev-{i}" for i in range(1000)],
    }
    extracted, _ = sanitize_decision_metadata(metadata)
    assert len(extracted["why"]) < 10_000
    assert extracted["why"].endswith("...(truncated)")
    assert len(extracted["evidence"]) <= 20


def test_is_chain_of_thought_like_name_matches_common_shapes() -> None:
    for name in ("chain_of_thought", "reasoning_trace", "internal_reasoning", "scratchpad", "cot_notes"):
        assert is_chain_of_thought_like_name(name)
    for name in ("why", "evidence", "kind", "decision_id"):
        assert not is_chain_of_thought_like_name(name)


# --- build_decision_from_raw_event ----------------------------------------


def _raw_decision_event(**metadata_overrides) -> dict:
    metadata = {
        "why": "risk1 requires human sign-off per policy",
        "evidence": ["adr-0012"],
        "alternatives_rejected": ["auto_approve"],
        "remaining_uncertainty": "none known",
        **metadata_overrides,
    }
    return {
        "type": "agent.control_decision",
        "project": PROJECT,
        "recorded_at": "2026-07-22T00:10:00+00:00",
        "payload": {
            "decision_id": "dec-abc123",
            "kind": "approval_required",
            "summary": "Escalate to human approval",
            "session_id": "sess-t07-decisions",
            "run_id": "run-t07-decisions",
            "trace_id": "tr-t07-decisions",
            "evidence_refs": ["evt-1"],
            "metadata": metadata,
        },
    }


def test_build_decision_from_raw_event_full_contract() -> None:
    decision = build_decision_from_raw_event(_raw_decision_event())
    assert isinstance(decision, ObserveDecisionV1)
    assert decision.schema_version == "observe_decision.v1"
    assert decision.decision_id == "dec-abc123"
    assert decision.kind == "approval_required"
    assert decision.decision == "Escalate to human approval"
    assert decision.why == "risk1 requires human sign-off per policy"
    assert "evt-1" in decision.evidence
    assert "adr-0012" in decision.evidence
    assert decision.alternatives_rejected == ["auto_approve"]
    assert decision.remaining_uncertainty == "none known"
    assert not hasattr(decision, "chain_of_thought")
    assert "chain_of_thought" not in decision.model_dump()


def test_build_decision_rejects_non_decision_event() -> None:
    event = _raw_decision_event()
    event["type"] = "agent.session_started"
    assert build_decision_from_raw_event(event) is None


def test_build_decision_rejects_missing_decision_id() -> None:
    event = _raw_decision_event()
    del event["payload"]["decision_id"]
    assert build_decision_from_raw_event(event) is None


def test_build_decision_never_surfaces_chain_of_thought_metadata() -> None:
    event = _raw_decision_event(chain_of_thought="the model's internal step-by-step reasoning transcript")
    decision = build_decision_from_raw_event(event)
    assert decision is not None
    dumped = decision.model_dump(mode="json")
    assert "the model's internal step-by-step reasoning transcript" not in str(dumped)
    assert "chain_of_thought" in decision.withheld_metadata_field_names


# --- list_decisions_for_run / decisions_panel_view -------------------------


def test_list_decisions_for_run_scoped_and_ordered(tmp_path: Path) -> None:
    run_id = "run-t07-list"
    session_id = "sess-t07-list"
    for i in range(3):
        append_control_decision(
            tmp_path,
            project=PROJECT,
            kind="other",
            summary=f"decision {i}",
            session_id=session_id,
            run_id=run_id,
            trace_id=f"tr-{session_id}",
            metadata={"why": f"reason {i}"},
        )
    # A decision for a different run must never appear in this run's list.
    append_control_decision(
        tmp_path,
        project=PROJECT,
        kind="other",
        summary="other run decision",
        session_id="sess-other",
        run_id="run-other",
        trace_id="tr-other",
    )
    decisions = list_decisions_for_run(tmp_path, project=PROJECT, run_id=run_id)
    assert [d.decision for d in decisions] == ["decision 0", "decision 1", "decision 2"]
    assert [d.why for d in decisions] == ["reason 0", "reason 1", "reason 2"]


def test_list_decisions_requires_run_or_session_id(tmp_path: Path) -> None:
    assert list_decisions_for_run(tmp_path, project=PROJECT) == []


def test_decisions_panel_view_shape(tmp_path: Path) -> None:
    run_id = "run-t07-panel"
    session_id = "sess-t07-panel"
    append_control_decision(
        tmp_path,
        project=PROJECT,
        kind="policy_denied",
        summary="Denied by policy",
        session_id=session_id,
        run_id=run_id,
        trace_id=f"tr-{session_id}",
        metadata={"why": "policy_source_sha mismatch"},
    )
    view = decisions_panel_view(tmp_path, project=PROJECT, run_id=run_id)
    assert view["total"] == 1
    assert view["decisions"][0]["decision"] == "Denied by policy"
    assert view["decisions"][0]["why"] == "policy_source_sha mismatch"


# --- end-to-end: session detail page panel 3 -------------------------------


def test_panel_shows_placeholder_when_no_decisions(tmp_path: Path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    run_id = "run-t07-empty"
    _seed_session(tmp_path, run_id=run_id, session_id="sess-t07-empty")
    client = TestClient(app)
    resp = client.get(f"/observe/sessions/{run_id}")
    assert resp.status_code == 200
    # Backward compatible with the pre-existing T04 assertion.
    assert "ships in T07" in resp.text


def test_panel_renders_structured_decision_fields(tmp_path: Path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    run_id = "run-t07-render"
    session_id = "sess-t07-render"
    _seed_session(tmp_path, run_id=run_id, session_id=session_id)
    append_control_decision(
        tmp_path,
        project=PROJECT,
        kind="approval_required",
        summary="Escalate to human approval",
        session_id=session_id,
        run_id=run_id,
        trace_id=f"tr-{session_id}",
        evidence_refs=["evt-9"],
        metadata={
            "why": "risk1 requires sign-off",
            "alternatives_rejected": ["auto_approve"],
            "remaining_uncertainty": "none known",
        },
    )
    client = TestClient(app)
    resp = client.get(f"/observe/sessions/{run_id}")
    assert resp.status_code == 200
    body = resp.text
    assert "Escalate to human approval" in body
    assert "risk1 requires sign-off" in body
    assert "auto_approve" in body
    assert "none known" in body
    assert "evt-9" in body


def test_panel_never_leaks_chain_of_thought_or_unrelated_metadata(tmp_path: Path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    run_id = "run-t07-cot"
    session_id = "sess-t07-cot"
    _seed_session(tmp_path, run_id=run_id, session_id=session_id)
    secret_reasoning = "STEP-BY-STEP-INTERNAL-REASONING-MUST-NEVER-APPEAR"
    append_control_decision(
        tmp_path,
        project=PROJECT,
        kind="other",
        summary="Decision with hidden reasoning attempt",
        session_id=session_id,
        run_id=run_id,
        trace_id=f"tr-{session_id}",
        metadata={
            "chain_of_thought": secret_reasoning,
            "internal_notes_should_not_render": "also secret",
        },
    )
    client = TestClient(app)
    resp = client.get(f"/observe/sessions/{run_id}")
    assert resp.status_code == 200
    body = resp.text
    assert secret_reasoning not in body
    assert "also secret" not in body
    # Field *name* is retained for audit visibility (matches the existing
    # observe_event.v1 prohibited_field_names pattern).
    assert "chain_of_thought" in body


def test_panel_escapes_hostile_decision_content(tmp_path: Path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    run_id = "run-t07-hostile"
    session_id = "sess-t07-hostile"
    _seed_session(tmp_path, run_id=run_id, session_id=session_id)
    hostile = "<script>alert(1)</script>"
    append_control_decision(
        tmp_path,
        project=PROJECT,
        kind="other",
        summary=hostile,
        session_id=session_id,
        run_id=run_id,
        trace_id=f"tr-{session_id}",
        metadata={"why": hostile},
    )
    client = TestClient(app)
    resp = client.get(f"/observe/sessions/{run_id}")
    body = resp.text
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body
