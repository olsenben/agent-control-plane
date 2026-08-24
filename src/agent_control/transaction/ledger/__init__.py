"""Append-only software_transaction and graph-edge emitters. Capture only."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent_control.events import AgentEvent, append_event
from agent_shared.hash_utils import canonical_json_hash
from agent_shared.models.transaction.admission import AdmissionFeedbackRecord
from agent_shared.models.transaction.ledger import (
    SoftwareTransaction,
    TransactionControlEvent,
    TransactionGraphEdge,
)

FEEDS_CONTROLLER = False


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_software_transaction(
    state_root: Path,
    transaction: SoftwareTransaction,
) -> tuple[Path, bool]:
    """Append software_transaction.v1 via the control-plane event ledger."""
    event_id = canonical_json_hash(
        {
            "transaction_id": transaction.transaction_id,
            "event_seq": transaction.event_seq,
            "decision_digest": transaction.decision.decision_digest,
        }
    )[:32]
    event = AgentEvent(
        event_id=event_id,
        type="software_transaction.v1",
        raw_event_type="software_transaction.v1",
        source="transaction_control",
        project=transaction.repository,
        payload=transaction.model_dump(mode="json"),
    )
    return append_event(state_root, event)


def append_transaction_graph_edge(
    store_dir: Path,
    edge: TransactionGraphEdge,
    *,
    graph_store: Any | None = None,
) -> Path:
    """Append-only JSONL capture. Never used for live decisions.

    Optional GraphStore.append_edges is a secondary capture path.
    """
    store_dir = Path(store_dir)
    store_dir.mkdir(parents=True, exist_ok=True)
    path = store_dir / "transaction_graph_edges.jsonl"
    payload = edge.model_dump(mode="json")
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            existing = json.loads(line)
            if existing.get("edge_id") == edge.edge_id:
                return path
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    if graph_store is not None:
        graph_store.append_edges(
            edge.repository,
            [
                {
                    "kind": edge.edge_type,
                    "src_kind": edge.from_entity_kind,
                    "src": edge.from_entity_id,
                    "dst_kind": edge.to_entity_kind,
                    "dst": edge.to_entity_id,
                    "provenance": "transaction_control_capture",
                }
            ],
            source_sha="",
        )
    return path


def make_feedback_record(
    *,
    record_id: str | None = None,
    proposal_id: str,
    repository: str,
    source_sha: str,
    patch_digest: str,
    bundle_id: str,
    decision: str,
    reasons: list[str] | None = None,
    task_id: str | None = None,
    tenant_id: str | None = None,
    org_id: str | None = None,
) -> AdmissionFeedbackRecord:
    return AdmissionFeedbackRecord(
        record_id=record_id or str(uuid4()),
        proposal_id=proposal_id,
        task_id=task_id,
        repository=repository,
        source_sha=source_sha,
        patch_digest=patch_digest,
        bundle_id=bundle_id,
        captured_at=utc_now(),
        decision=decision,  # type: ignore[arg-type]
        reasons=list(reasons or []),
        feeds_controller=FEEDS_CONTROLLER,
        tenant_id=tenant_id,
        org_id=org_id,
    )


def append_admission_feedback(store_dir: Path, record: AdmissionFeedbackRecord) -> Path:
    store_dir = Path(store_dir)
    store_dir.mkdir(parents=True, exist_ok=True)
    path = store_dir / "admission_feedback.jsonl"
    payload = record.model_dump(mode="json")
    assert payload.get("feeds_controller") is False
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return path


EVENT_TRANSACTION_CONTROL = "transaction_control_event.v1"
EVENT_PUBLISH_REQUESTED = "PUBLISH_REQUESTED"


def stable_publish_effect_id(
    *,
    transaction_id: str,
    capability_id: str | None,
    patch_digest: str,
    repo: str,
    source_sha: str,
    target_branch: str,
) -> str:
    return canonical_json_hash(
        {
            "transaction_id": transaction_id,
            "capability_id": capability_id,
            "patch_digest": patch_digest,
            "repo": repo,
            "source_sha": source_sha,
            "target_branch": target_branch,
        }
    )


def append_transaction_control_event(
    state_root: Path,
    event: TransactionControlEvent,
    *,
    project: str,
) -> tuple[Path, bool]:
    agent_event = AgentEvent(
        event_id=event.event_id[:32],
        type=EVENT_TRANSACTION_CONTROL,
        raw_event_type=event.event_type,
        source="transaction_control",
        project=project,
        payload=event.model_dump(mode="json"),
    )
    return append_event(state_root, agent_event)


def record_publish_requested(
    state_root: Path,
    *,
    project: str,
    transaction_id: str,
    capability_id: str | None,
    patch_digest: str,
    repo: str,
    source_sha: str,
    target_branch: str,
    expected_commit_sha: str,
    run_id: str,
    bundle_id: str,
    kind: str,
    intended_pr_title: str | None = None,
    publish_effect_id: str | None = None,
    principal: Any | None = None,
    code_revision: str | None = None,
    policy_revision: str | None = None,
) -> str:
    """Persist PUBLISH_REQUESTED before Gitea mutation. Retries reuse publish_effect_id."""
    from agent_control.publish.state import save_publish_intent
    from agent_shared.models.publish import PublishIntent
    from agent_shared.models.transaction.identity import IdentityPrincipal

    effect_id = publish_effect_id or stable_publish_effect_id(
        transaction_id=transaction_id,
        capability_id=capability_id,
        patch_digest=patch_digest,
        repo=repo,
        source_sha=source_sha,
        target_branch=target_branch,
    )
    intent = PublishIntent(
        run_id=run_id,
        bundle_id=bundle_id,
        kind=kind,
        project=project,
        agent_branch=target_branch,
        expected_commit_sha=expected_commit_sha,
        created_at=utc_now(),
        publish_effect_id=effect_id,
        transaction_id=transaction_id,
        capability_id=capability_id,
        patch_digest=patch_digest,
        source_sha=source_sha,
        intended_pr_title=intended_pr_title,
    )
    save_publish_intent(state_root, intent)
    payload = {
        "transaction_id": transaction_id,
        "capability_id": capability_id,
        "patch_digest": patch_digest,
        "repo": repo,
        "source_sha": source_sha,
        "target_branch": target_branch,
        "expected_commit_sha": expected_commit_sha,
        "publish_effect_id": effect_id,
        "run_id": run_id,
        "bundle_id": bundle_id,
        "kind": kind,
        "intended_pr_title": intended_pr_title,
    }
    principal_model = None
    if isinstance(principal, IdentityPrincipal):
        principal_model = principal
    elif isinstance(principal, dict):
        principal_model = IdentityPrincipal.model_validate(principal)
    control = TransactionControlEvent(
        event_id=effect_id[:32],
        transaction_id=transaction_id,
        event_type=EVENT_PUBLISH_REQUESTED,
        component="publish_broker",
        principal=principal_model,
        timestamp=utc_now(),
        code_revision=code_revision,
        policy_revision=policy_revision,
        payload_digest=canonical_json_hash(payload),
        payload=payload,
        repository=repo,
        run_id=run_id,
    )
    append_transaction_control_event(state_root, control, project=project)
    return effect_id
