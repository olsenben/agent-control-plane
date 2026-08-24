"""Append-only ledger and graph-edge helpers."""

from __future__ import annotations

from pathlib import Path

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
from agent_shared.models.transaction.admission import EvidenceRef, TaskRef
from agent_shared.models.transaction.ledger import (
    ActorRef,
    DecisionRef,
    PatchRef,
    SoftwareTransaction,
    TransactionGraphEdge,
)


def _identity():
    return attribution(
        on_behalf_of=human_initiator("alice"),
        executed_by=fixture_actor_identity(),
        authorized_by=control_plane(),
    )


def test_software_transaction_append_only(tmp_path: Path) -> None:
    tx = SoftwareTransaction(
        transaction_id="tx-1",
        tenant_id="t",
        org_id="o",
        repository="org/repo",
        task=TaskRef(task_id="task-1", task_digest="a" * 64),
        actor=ActorRef(
            session_id="s1",
            actor_identity=fixture_actor_identity(),
            worker_identity=fixture_actor_identity(run_id="w"),
        ),
        patch=PatchRef(source_sha="abc1234", patch_digest="b" * 64),
        evidence=EvidenceRef(bundle_id="bun-1", bundle_digest="c" * 64),
        decision=DecisionRef(decision="AUTO_ADMIT", decision_digest="d" * 64),
        capability=None,
        durable_outcome="AUTO_ADMITTED_CAPABILITY_MINTED",
        identity=_identity(),
        recorded_at="2026-08-24T00:00:00+00:00",
        event_seq=1,
    )
    path, created = append_software_transaction(tmp_path, tx)
    assert created is True
    path2, created2 = append_software_transaction(tmp_path, tx)
    assert path2 == path
    assert created2 is False


def test_graph_edge_append_only(tmp_path: Path) -> None:
    edge = TransactionGraphEdge(
        edge_id="e1",
        edge_type="HUMAN_INITIATED_TASK",
        from_entity_id="alice",
        from_entity_kind="HUMAN",
        to_entity_id="task-1",
        to_entity_kind="TASK",
        tenant_id="t",
        org_id="o",
        repository="org/repo",
        captured_at="2026-08-24T00:00:00+00:00",
        identity=_identity(),
    )
    path = append_transaction_graph_edge(tmp_path, edge)
    append_transaction_graph_edge(tmp_path, edge)
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1
    assert '"used_for_live_decision": false' in lines[0]


def test_feedback_does_not_feed_controller(tmp_path: Path) -> None:
    record = make_feedback_record(
        proposal_id="p1",
        repository="org/repo",
        source_sha="abc1234",
        patch_digest="a" * 64,
        bundle_id="b1",
        decision="ESCALATE",
        reasons=["REQUIRED_PROVIDER_FAILED"],
        tenant_id="t",
        org_id="o",
    )
    assert record.feeds_controller is False
    assert record.learning_enabled is False
    append_admission_feedback(tmp_path, record)
