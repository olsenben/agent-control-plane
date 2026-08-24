"""W5 Observatory software-transaction view-model (read-only, redacted)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from agent_control.events import AgentEvent, append_event
from agent_control.observe.safe_display import safe_display_event
from agent_control.observe.transaction_view import (
    transaction_graph_edges_path,
    transaction_panel_view,
)
from agent_control.session.storage import persist_session_with_run_index
from agent_control.transaction.identity import (
    attribution,
    control_plane,
    fixture_actor_identity,
    human_initiator,
)
from agent_control.transaction.ledger import (
    append_admission_feedback,
    append_software_transaction,
    append_transaction_graph_edge,
    make_feedback_record,
)
from agent_control.webhook_server import create_app
from agent_shared.models.agent_session import AgentSession, SessionStatus
from agent_shared.models.transaction.admission import EvidenceRef, TaskRef
from agent_shared.models.transaction.ledger import (
    ActorRef,
    CapabilityRef,
    DecisionRef,
    PatchRef,
    SoftwareTransaction,
    TransactionGraphEdge,
)

PROJECT = "org/repo"
SECRET_VALUE = "super-secret-capability-token"
SCANNER_PAYLOAD = "SECRET_SCANNER_PAYLOAD_XYZ"
RAW_FINDING = "raw-finding-message-should-not-leak"


def _identity():
    return attribution(
        on_behalf_of=human_initiator("alice"),
        executed_by=fixture_actor_identity(run_id="run-obs-tx"),
        authorized_by=control_plane(),
    )


def _seed_session(
    root: Path,
    *,
    run_id: str = "run-obs-tx",
    session_id: str = "sess-obs-tx",
) -> AgentSession:
    session = AgentSession(
        session_id=session_id,
        project=PROJECT,
        repo="repo",
        subject_kind="issue",
        subject_number=9,
        command_kind="fix",
        status=SessionStatus.RUNNING,
        run_ids=[run_id],
        correlation_id=f"corr-{session_id}",
        trace_id=f"tr-{session_id}",
        input_state_sha="a" * 64,
        head_sha="b" * 40,
        policy_source_sha="c" * 40,
        risk_level="risk1",
        risk_tags=["needs_review"],
        invoked_by="alice",
        created_at="2026-08-24T00:00:00+00:00",
        updated_at="2026-08-24T00:05:00+00:00",
    )
    persist_session_with_run_index(root, session)
    return session


def _transaction(**overrides: object) -> SoftwareTransaction:
    kwargs: dict[str, object] = {
        "transaction_id": "tx-obs-1",
        "tenant_id": "t",
        "org_id": "o",
        "repository": PROJECT,
        "task": TaskRef(task_id="task-1", task_digest="a" * 64),
        "actor": ActorRef(
            session_id="sess-obs-tx",
            actor_identity=fixture_actor_identity(run_id="run-obs-tx"),
            worker_identity=fixture_actor_identity(run_id="w"),
        ),
        "patch": PatchRef(source_sha="abc1234", patch_digest="b" * 64),
        "evidence": EvidenceRef(bundle_id="bun-1", bundle_digest="c" * 64),
        "decision": DecisionRef(decision="AUTO_ADMIT", decision_digest="d" * 64),
        "capability": CapabilityRef(
            capability_id="cap-1",
            admission_decision_digest="d" * 64,
            capability_digest="e" * 64,
        ),
        "durable_outcome": "AUTO_ADMITTED_CAPABILITY_MINTED",
        "identity": _identity(),
        "recorded_at": "2026-08-24T00:10:00+00:00",
        "event_seq": 1,
    }
    kwargs.update(overrides)
    return SoftwareTransaction(**kwargs)  # type: ignore[arg-type]


def _poisoned_payload(tx: SoftwareTransaction) -> dict:
    payload = tx.model_dump(mode="json")
    payload["trace_id"] = "tr-sess-obs-tx"
    payload["run_id"] = "run-obs-tx"
    payload["reasons"] = ["WITHIN_PREDICTED_SCOPE"]
    payload["secret"] = SECRET_VALUE
    capability = dict(payload.get("capability") or {})
    capability["secret"] = SECRET_VALUE
    payload["capability"] = capability
    evidence = dict(payload.get("evidence") or {})
    evidence["items"] = [
        {
            "provider_id": "sast-1",
            "result_status": "PASS",
            "evidence_type": "SAST",
            "trust_class": "CONFIGURED_SECURITY_TOOL",
            "raw_output": SCANNER_PAYLOAD,
            "sarif": {"runs": [{"results": [RAW_FINDING]}]},
            "findings": [{"message": RAW_FINDING}],
        }
    ]
    payload["evidence"] = evidence
    return payload


def _append_poisoned_event(root: Path, tx: SoftwareTransaction) -> None:
    payload = _poisoned_payload(tx)
    event = AgentEvent(
        event_id="obs-tx-poisoned",
        type="software_transaction.v1",
        raw_event_type="software_transaction.v1",
        source="transaction_control",
        project=PROJECT,
        payload=payload,
    )
    append_event(root, event)


REQUIRED_VIEW_KEYS = (
    "task",
    "actor",
    "patch",
    "evidence_providers",
    "evidence_status",
    "admission_result",
    "decision_reasons",
    "capability_status",
    "publish_status",
    "ci_verification_status",
    "timeline",
    "trace_id",
    "transaction_id",
)

_FORBIDDEN_VIEW_KEYS = frozenset(
    {
        "secret",
        "sarif",
        "findings",
        "raw_output",
        "scanner_payload",
        "raw_findings",
    }
)


def _assert_no_secret_or_scanner_keys(value: object) -> None:
    if isinstance(value, dict):
        for key, inner in value.items():
            assert str(key).lower() not in _FORBIDDEN_VIEW_KEYS
            _assert_no_secret_or_scanner_keys(inner)
    elif isinstance(value, list):
        for item in value:
            _assert_no_secret_or_scanner_keys(item)


def test_empty_view_has_required_fields_and_trace_id(tmp_path: Path) -> None:
    session = _seed_session(tmp_path)
    view = transaction_panel_view(
        tmp_path, project=PROJECT, run_id="run-obs-tx", session=session
    )
    for key in REQUIRED_VIEW_KEYS:
        assert key in view
    assert view["authoritative"] is False
    assert view["present"] is False
    assert view["transaction_id"] is None
    assert view["trace_id"] == "tr-sess-obs-tx"
    assert view["task"]["status"] == "session_fallback"
    assert view["capability_status"]["status"] == "unavailable"
    dumped = json.dumps(view)
    assert SECRET_VALUE not in dumped
    assert SCANNER_PAYLOAD not in dumped


def test_view_model_redacts_capability_secret_and_scanner_payload(tmp_path: Path) -> None:
    session = _seed_session(tmp_path)
    _append_poisoned_event(tmp_path, _transaction())
    view = transaction_panel_view(
        tmp_path, project=PROJECT, run_id="run-obs-tx", session=session
    )
    dumped = json.dumps(view)
    assert SECRET_VALUE not in dumped
    assert SCANNER_PAYLOAD not in dumped
    assert RAW_FINDING not in dumped
    _assert_no_secret_or_scanner_keys(view)
    assert view["transaction_id"] == "tx-obs-1"
    assert view["trace_id"] == "tr-sess-obs-tx"
    assert view["task"]["task_id"] == "task-1"
    assert view["actor"]["initiator_id"] == "alice"
    assert view["patch"]["patch_digest"] == "b" * 64
    assert view["admission_result"] == "AUTO_ADMIT"
    assert "WITHIN_PREDICTED_SCOPE" in view["decision_reasons"]
    assert view["capability_status"]["capability_id"] == "cap-1"
    assert view["capability_status"]["status"] == "minted"
    assert view["publish_status"] == "not_published"
    providers = view["evidence_providers"]
    assert providers
    assert providers[0]["provider_id"] == "sast-1"
    assert providers[0]["status"] == "PASS"
    assert "raw_output" not in json.dumps(providers)
    assert "sarif" not in json.dumps(providers)
    for row in view["timeline"]:
        assert "transaction_id" in row
        assert "trace_id" in row


def test_safe_display_software_transaction_withholds_secrets(tmp_path: Path) -> None:
    payload = _poisoned_payload(_transaction())
    display = safe_display_event(
        {
            "type": "software_transaction.v1",
            "payload": payload,
            "event_id": "e1",
            "project": PROJECT,
        }
    )
    assert display.known_type is True
    assert display.category == "transaction"
    blob = json.dumps(display.model_dump(mode="json"))
    assert SECRET_VALUE not in blob
    assert SCANNER_PAYLOAD not in blob
    assert RAW_FINDING not in blob
    assert display.display_fields.get("transaction_id") == "tx-obs-1"
    assert display.display_fields.get("trace_id") == "tr-sess-obs-tx"
    capability_meta = display.display_fields.get("capability")
    assert capability_meta == {"present": True, "count": len(payload["capability"])}
    assert "secret" in display.prohibited_field_names


def test_graph_edges_and_feedback_bind_timeline_and_reasons(tmp_path: Path) -> None:
    session = _seed_session(tmp_path)
    tx = _transaction(
        capability=None,
        durable_outcome="ESCALATED_NO_CAPABILITY",
        decision=DecisionRef(decision="ESCALATE", decision_digest="d" * 64),
    )
    append_software_transaction(tmp_path, tx)
    store_dir = transaction_graph_edges_path(tmp_path, PROJECT).parent
    append_transaction_graph_edge(
        store_dir,
        TransactionGraphEdge(
            edge_id="e1",
            edge_type="HUMAN_INITIATED_TASK",
            from_entity_id="alice",
            from_entity_kind="HUMAN",
            to_entity_id="task-1",
            to_entity_kind="TASK",
            tenant_id="t",
            org_id="o",
            repository=PROJECT,
            transaction_id="tx-obs-1",
            captured_at="2026-08-24T00:01:00+00:00",
            identity=_identity(),
        ),
    )
    append_admission_feedback(
        store_dir,
        make_feedback_record(
            proposal_id="p1",
            repository=PROJECT,
            source_sha="abc1234",
            patch_digest="b" * 64,
            bundle_id="bun-1",
            decision="ESCALATE",
            reasons=["REQUIRED_PROVIDER_FAILED"],
            tenant_id="t",
            org_id="o",
        ),
    )
    view = transaction_panel_view(
        tmp_path, project=PROJECT, run_id="run-obs-tx", session=session
    )
    assert view["present"] is True
    assert view["admission_result"] == "ESCALATE" or view["decision_reasons"]
    assert "REQUIRED_PROVIDER_FAILED" in view["decision_reasons"]
    kinds = {row["kind"] for row in view["timeline"]}
    assert "HUMAN_INITIATED_TASK" in kinds
    assert any(row.get("transaction_id") == "tx-obs-1" for row in view["timeline"])
    assert view["capability_status"]["status"] == "none"


def test_session_detail_renders_transaction_panel(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("OBSERVE_REQUIRE_AUTH", "false")
    session = _seed_session(tmp_path)
    _append_poisoned_event(tmp_path, _transaction())
    client = TestClient(create_app())
    resp = client.get("/observe/sessions/run-obs-tx")
    assert resp.status_code == 200
    body = resp.text
    assert "Software transaction (read-only)" in body
    assert "not an admission or publish authority" in body
    for label in (
        "TASK",
        "ACTOR / INITIATOR",
        "PATCH SUMMARY + DIGEST",
        "EVIDENCE PROVIDERS / STATUS",
        "ADMISSION RESULT",
        "DECISION REASONS",
        "CAPABILITY STATUS",
        "PUBLISH STATUS",
        "CI / VERIFICATION STATUS",
        "TIMELINE",
    ):
        assert label in body
    assert "tx-obs-1" in body
    assert session.trace_id in body
    assert SECRET_VALUE not in body
    assert SCANNER_PAYLOAD not in body
    assert RAW_FINDING not in body
