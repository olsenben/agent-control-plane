"""Transaction PDP: evidence bus + frozen C. Broker (PEP) enforces the decision.

Does not retune C. Does not reimplement admission/evidence/capability.
C-facing inputs are units, paths, and verification only (no Gitea types).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_control.events import AgentEvent, append_event
from agent_control.publish.envelope import (
    build_task_envelope,
    load_task_envelope,
    persist_task_envelope,
    policy_digest_for,
    tenant_org_from_project,
)
from agent_control.session.storage import load_session_by_run, sessions_dir
from agent_control.transaction.admission import (
    AUTO_ADMIT,
    C_LOAD_MODE,
    ESCALATE,
    FROZEN_C_HASH,
    HARNESS_SPECIFIC_CONTROL_LOGIC,
    MODEL_SPECIFIC_CONTROL_LOGIC,
    SCANNER_SPECIFIC_ADMISSION_LOGIC,
    SCANNER_SPECIFIC_C_LOGIC,
    make_escalation,
    wrap_decide_c,
)
from agent_control.transaction.policy_bundle import (
    bind_g0_input,
    create_policy_bundle_receipt,
)
from agent_control.transaction.preflight import (
    PREFLIGHT_READY,
    evaluate_transaction_preflight,
    incomplete_admission_decision,
)
from agent_control.transaction.capability import (
    ALREADY_CLAIMED,
    CAPABILITY_ALREADY_CONSUMED,
    CapabilityAlreadyClaimed,
    CapabilityAlreadyConsumed,
    CapabilityInvalidated,
    CapabilityNotConsuming,
    FilesystemCapabilityStore,
    complete_consumed_capability,
    consume_capability,
    mint_capability,
    public_receipt,
)
from agent_control.transaction.evidence import (
    build_route,
    classify_change_classes,
    project_bundle_onto_c_inputs,
    routed_providers,
    run_evidence_bus,
)
from agent_control.transaction.identity import (
    agent_worker,
    attribution,
    control_plane,
    human_initiator,
)
from agent_control.transaction.ledger import (
    append_admission_feedback,
    append_software_transaction,
    append_transaction_graph_edge,
    make_feedback_record,
)
from agent_control.transaction.proposal import finalize_proposal
from agent_control.transaction.task_freeze import (
    TASK_FREEZE_FILENAME,
    freeze_task_issue_at_creation,
    p4_live_kwargs,
)
from agent_control.transaction.trees import MaterializedTrees, materialize_source_candidate_trees
from agent_control.transaction.witness import StateWitnessError
from agent_shared.hash_utils import canonical_json_hash, sha256_text
from agent_shared.models.agent_session import AgentSession
from agent_shared.models.bundle import PatchBundleManifest
from agent_shared.models.transaction.admission import (
    PatchAdmissionDecision,
    PolicyFields,
    TaskRef,
)
from agent_shared.models.transaction.identity import CompositeIdentity
from agent_shared.models.transaction.ledger import (
    ActorRef,
    CapabilityRef,
    DecisionRef,
    EvidenceRef,
    PatchRef,
    SoftwareTransaction,
    TransactionGraphEdge,
)
from agent_shared.models.transaction.capability import DurablePatchCapability
from agent_shared.models.transaction.proposal import PatchProposal
from agent_shared.models.transaction.task import (
    PolicyContext,
    RequestedChange,
    TaskEnvelope,
    task_digest_for,
)

EVENT_PATCH_ADMISSION_DECISION = "patch_admission_decision.v1"
EVENT_ADMISSION_ESCALATION = "admission_escalation.v1"
EVENT_DURABLE_PATCH_CAPABILITY = "durable_patch_capability.v1"

assert MODEL_SPECIFIC_CONTROL_LOGIC == "NO"
assert SCANNER_SPECIFIC_ADMISSION_LOGIC == "NO"
assert SCANNER_SPECIFIC_C_LOGIC == "NO"
assert HARNESS_SPECIFIC_CONTROL_LOGIC == "NO"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def capability_store(state_root: Path) -> FilesystemCapabilityStore:
    return FilesystemCapabilityStore(state_root / "transaction" / "capabilities")


def transaction_dir(state_root: Path, project: str, run_id: str) -> Path:
    return sessions_dir(state_root, project).parent / "transaction" / run_id


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def digest64(value: str) -> str:
    text = (value or "").strip().lower()
    if len(text) == 64 and all(ch in "0123456789abcdef" for ch in text):
        return text
    return sha256_text(value or "")


def changed_files_from_patch(text: str) -> list[str]:
    files: list[str] = []
    for line in text.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:].replace("\\", "/")
            if path and path != "/dev/null":
                files.append(path)
    return files


def stable_proposal_id(*, run_id: str, bundle_id: str, patch_digest: str) -> str:
    return canonical_json_hash(
        {"run_id": run_id, "bundle_id": bundle_id, "patch_digest": patch_digest}
    )


def units_from_changed_files(
    changed_files: list[str],
    authorized_files: list[str],
) -> list[dict[str, Any]]:
    authorized = {path.replace("\\", "/") for path in authorized_files}
    units: list[dict[str, Any]] = []
    for raw in changed_files:
        path = raw.replace("\\", "/")
        receipts = ["TASK_NAMED"] if path in authorized else ["UNRELATED_OR_UNKNOWN"]
        units.append(
            {
                "path": path,
                "element_key": f"file:{path}",
                "symbol": Path(path).stem or path,
                "change_kind": "changed",
                "receipts": receipts,
                "visibility": "private",
                "privileged": False,
                "local_creation": False,
                "callers": [],
                "side_effect_category": "NONE",
            }
        )
    return units


def in_process_adapter_kwargs(
    *,
    envelope: TaskEnvelope,
    units: list[dict[str, Any]],
    p1_passed: bool = True,
    p1_force_failure: bool = False,
    source_root: str | None = None,
    candidate_root: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Deterministic in-process providers keyed by evidence_route.v1.

    P2 empty-kwargs synthetic PASS is not the live path. When SAST trees are
    supplied, P2 runs the live provider; otherwise P2 is omitted and a routed
    live adapter fail-closes instead of inventing SECURITY_PASS.
    """
    kwargs: dict[str, dict[str, Any]] = {
        "P1": {"verdict": {"passed": p1_passed, "detail": "in_process_functional"}},
        "P3": {},
        "P4": {
            "task": {
                "authorized_files": list(envelope.authorized_files),
                "authorized_surfaces": list(envelope.authorized_surfaces),
                "authorized_change_classes": list(envelope.authorized_change_classes),
            }
        },
        "P5": {"units": units},
    }
    if source_root or candidate_root:
        p2: dict[str, Any] = {}
        if source_root:
            p2["source_root"] = source_root
        if candidate_root:
            p2["candidate_root"] = candidate_root
        kwargs["P2"] = p2
    if p1_force_failure:
        kwargs["P1"] = {"force_failure": True}
    return kwargs


def _p2_live_trees(bundle_root: Path) -> dict[str, str]:
    """Intended SOURCE/CANDIDATE paths. Missing dirs fail-closed in the live P2 adapter."""
    return {
        "source_root": str(bundle_root / "source"),
        "candidate_root": str(bundle_root / "candidate"),
    }


def _identity_for(
    envelope: TaskEnvelope,
    session: AgentSession | None,
) -> CompositeIdentity:
    if envelope.identity is not None:
        return envelope.identity
    human = envelope.human_initiator
    login = session.invoked_by if session is not None else human.identity_id
    return attribution(
        on_behalf_of=human_initiator(login),
        executed_by=agent_worker("agentworker"),
        authorized_by=control_plane(),
    )


def _append_typed_event(
    state_root: Path,
    *,
    event_type: str,
    project: str,
    event_id: str,
    payload: dict[str, Any],
) -> None:
    event = AgentEvent(
        event_id=event_id[:32] if len(event_id) > 32 else event_id,
        type=event_type,
        raw_event_type=event_type,
        source="transaction_control",
        project=project,
        payload=payload,
    )
    append_event(state_root, event)


def _graph_edge(
    *,
    edge_id: str,
    edge_type: str,
    from_id: str,
    from_kind: str,
    to_id: str,
    to_kind: str,
    envelope: TaskEnvelope,
    transaction_id: str,
    identity: CompositeIdentity,
) -> TransactionGraphEdge:
    return TransactionGraphEdge(
        edge_id=edge_id,
        edge_type=edge_type,  # type: ignore[arg-type]
        from_entity_id=from_id,
        from_entity_kind=from_kind,  # type: ignore[arg-type]
        to_entity_id=to_id,
        to_entity_kind=to_kind,  # type: ignore[arg-type]
        tenant_id=envelope.tenant_id,
        org_id=envelope.org_id,
        repository=envelope.repository,
        transaction_id=transaction_id,
        captured_at=utc_now(),
        identity=identity,
    )


@dataclass
class PdpResult:
    decision: str
    reasons: list[str]
    envelope: TaskEnvelope
    proposal: PatchProposal
    admission: PatchAdmissionDecision
    evidence: dict[str, Any]
    policy: PolicyFields
    identity: CompositeIdentity
    patch_digest: str
    evidence_bundle_digest: str
    allowed_target_branch: str
    capability: Any | None
    escalation: Any | None
    transaction_id: str
    store: FilesystemCapabilityStore


def _ensure_envelope(
    state_root: Path,
    *,
    project: str,
    run_id: str,
    session: AgentSession | None,
    authorized_files: list[str],
    source_sha: str,
    invoked_by: str,
) -> TaskEnvelope:
    if session is not None:
        existing = load_task_envelope(state_root, project, session.session_id)
        if existing is not None:
            return existing
        envelope = build_task_envelope(
            session=session,
            changed_files=authorized_files,
            source_sha=source_sha or session.head_sha,
            authorized_files=authorized_files,
        )
        persist_task_envelope(state_root, envelope, session_id=session.session_id)
        return envelope
    tenant_id, org_id = tenant_org_from_project(project)
    human = human_initiator(invoked_by or "unknown")
    policy_id = "w5_evidence_policy.v1"
    digest = policy_digest_for(policy_id=policy_id, policy_version="v1")
    sha = source_sha if len(source_sha) >= 7 else (source_sha + "0" * 7)[:7]
    payload = {
        "schema_version": "task_envelope.v1",
        "task_id": f"task:{run_id}",
        "tenant_id": tenant_id,
        "org_id": org_id,
        "repository": project,
        "source_sha": sha,
        "task_provider": "GITEA_ISSUE",
        "provider_task_id": run_id,
        "human_initiator": human.model_dump(mode="json"),
        "initiator_identity": human.identity_id,
        "identity": attribution(
            on_behalf_of=human,
            executed_by=agent_worker("agentworker"),
            authorized_by=control_plane(),
        ).model_dump(mode="json"),
        "task_type": "FUNCTIONAL_MAINTENANCE",
        "requested_change": RequestedChange(summary="publish").model_dump(mode="json"),
        "authorized_change_classes": ["PRODUCTION_SOURCE_CHANGE"],
        "authorized_files": list(authorized_files),
        "authorized_surfaces": [],
        "security_finding_ids": [],
        "policy_context": PolicyContext(
            policy_id=policy_id,
            policy_version="v1",
            policy_digest=digest,
            admission_implementation_digest=FROZEN_C_HASH,
        ).model_dump(mode="json"),
        "created_at": utc_now(),
    }
    return TaskEnvelope.model_validate({**payload, "task_digest": task_digest_for(payload)})


def _load_or_build_proposal(
    store_dir: Path,
    *,
    session_id: str,
    run_id: str,
    bundle_id: str,
    bundle_root: Path,
    manifest: PatchBundleManifest,
    envelope: TaskEnvelope,
    changed_files: list[str],
    identity: CompositeIdentity,
) -> PatchProposal:
    patch_digest = digest64(manifest.patch_sha256)
    proposal_id = stable_proposal_id(
        run_id=run_id, bundle_id=bundle_id, patch_digest=patch_digest
    )
    path = store_dir / "proposals" / f"{proposal_id}.json"
    existing = _load_json(path)
    if existing is not None:
        proposal = PatchProposal.model_validate(existing)
        if proposal.finalized:
            return proposal
        return finalize_proposal(proposal)
    attached = bundle_root / "patch_proposal.json"
    if attached.is_file():
        proposal = PatchProposal.model_validate(json.loads(attached.read_text(encoding="utf-8")))
        if proposal.finalized:
            _atomic_write_json(path, proposal.model_dump(mode="json"))
            return proposal
        proposal = finalize_proposal(proposal)
        _atomic_write_json(path, proposal.model_dump(mode="json"))
        return proposal
    raw_patch = bundle_root / (manifest.patch_filename or "patch.diff")
    raw_digest = digest64(manifest.patch_sha256)
    tree = digest64(manifest.producer_tree_sha or manifest.producer_base_sha)
    proposal = PatchProposal(
        session_id=session_id,
        proposal_id=proposal_id,
        repo=envelope.repository,
        tenant_id=envelope.tenant_id,
        org_id=envelope.org_id,
        task_id=envelope.task_id,
        source_sha=manifest.producer_base_sha,
        source_tree_digest=tree,
        patch_digest=patch_digest,
        changed_files=changed_files,
        actor_identity=identity.EXECUTED_BY,
        worker_identity=agent_worker("agentworker"),
        identity=identity,
        created_at=utc_now(),
        raw_patch_location=str(raw_patch),
        raw_patch_digest=raw_digest,
    )
    proposal = finalize_proposal(proposal)
    _atomic_write_json(path, proposal.model_dump(mode="json"))
    return proposal


def _record_ledger(
    state_root: Path,
    store_dir: Path,
    *,
    result: PdpResult,
    event_seq: int,
    durable_outcome: str,
    capability_id: str | None = None,
    capability_digest: str | None = None,
) -> None:
    envelope = result.envelope
    identity = result.identity
    tx = SoftwareTransaction(
        transaction_id=result.transaction_id,
        tenant_id=envelope.tenant_id,
        org_id=envelope.org_id,
        repository=envelope.repository,
        task=TaskRef(task_id=envelope.task_id, task_digest=envelope.task_digest),
        actor=ActorRef(
            session_id=result.proposal.session_id,
            actor_identity=identity.EXECUTED_BY,
            worker_identity=agent_worker("agentworker"),
        ),
        patch=PatchRef(
            proposal_id=result.proposal.proposal_id,
            source_sha=result.proposal.source_sha,
            patch_digest=result.patch_digest,
        ),
        evidence=EvidenceRef(
            bundle_id=str(result.evidence.get("bundle_id") or "unknown"),
            bundle_digest=result.evidence_bundle_digest,
        ),
        decision=DecisionRef(
            decision=result.decision,  # type: ignore[arg-type]
            decision_digest=result.admission.decision_digest,
            escalation_id=(
                result.escalation.escalation_id if result.escalation is not None else None
            ),
        ),
        capability=(
            CapabilityRef(
                capability_id=capability_id,
                admission_decision_digest=result.admission.decision_digest,
                capability_digest=capability_digest,
            )
            if capability_id
            else None
        ),
        durable_outcome=durable_outcome,  # type: ignore[arg-type]
        identity=identity,
        recorded_at=utc_now(),
        event_seq=event_seq,
    )
    append_software_transaction(state_root, tx)
    feedback = make_feedback_record(
        proposal_id=str(result.proposal.proposal_id or result.transaction_id),
        repository=envelope.repository,
        source_sha=result.proposal.source_sha,
        patch_digest=result.patch_digest,
        bundle_id=str(result.evidence.get("bundle_id") or "unknown"),
        decision=result.decision,
        reasons=list(result.reasons),
        task_id=envelope.task_id,
        tenant_id=envelope.tenant_id,
        org_id=envelope.org_id,
    )
    append_admission_feedback(store_dir, feedback)
    edges = [
        ("HUMAN_INITIATED_TASK", identity.ON_BEHALF_OF.identity_id, "HUMAN", envelope.task_id, "TASK"),
        ("TASK_CREATED_SESSION", envelope.task_id, "TASK", result.proposal.session_id, "SESSION"),
        (
            "SESSION_PRODUCED_PATCH",
            result.proposal.session_id,
            "SESSION",
            str(result.proposal.proposal_id),
            "PATCH",
        ),
        (
            "EVIDENCE_SUPPORTS_PATCH",
            str(result.evidence.get("bundle_id") or "evidence"),
            "EVIDENCE",
            str(result.proposal.proposal_id),
            "PATCH",
        ),
        (
            "POLICY_GOVERNED_DECISION",
            envelope.policy_context.policy_id,
            "POLICY",
            result.admission.decision_digest,
            "DECISION",
        ),
    ]
    if result.decision == AUTO_ADMIT and capability_id:
        edges.append(
            (
                "DECISION_MINTED_CAPABILITY",
                result.admission.decision_digest,
                "DECISION",
                capability_id,
                "CAPABILITY",
            )
        )
    for edge_type, from_id, from_kind, to_id, to_kind in edges:
        append_transaction_graph_edge(
            store_dir,
            _graph_edge(
                edge_id=canonical_json_hash(
                    {
                        "tx": result.transaction_id,
                        "type": edge_type,
                        "from": from_id,
                        "to": to_id,
                        "seq": event_seq,
                    }
                )[:32],
                edge_type=edge_type,
                from_id=from_id,
                from_kind=from_kind,
                to_id=to_id,
                to_kind=to_kind,
                envelope=envelope,
                transaction_id=result.transaction_id,
                identity=identity,
            ),
        )


def record_published_transaction(
    state_root: Path,
    result: PdpResult,
    *,
    pr_number: int | None,
    commit_sha: str,
) -> None:
    store_dir = transaction_dir(state_root, result.envelope.repository, result.proposal.session_id)
    cap_id = result.capability.capability_id if result.capability is not None else None
    cap_digest = (
        result.capability.capability_digest if result.capability is not None else None
    )
    _record_ledger(
        state_root,
        store_dir,
        result=result,
        event_seq=2,
        durable_outcome="PUBLISHED",
        capability_id=cap_id,
        capability_digest=cap_digest,
    )
    if cap_id and pr_number is not None:
        append_transaction_graph_edge(
            store_dir,
            _graph_edge(
                edge_id=canonical_json_hash(
                    {"tx": result.transaction_id, "type": "CAPABILITY_PUBLISHED_PR", "pr": pr_number}
                )[:32],
                edge_type="CAPABILITY_PUBLISHED_PR",
                from_id=cap_id,
                from_kind="CAPABILITY",
                to_id=str(pr_number),
                to_kind="PR",
                envelope=result.envelope,
                transaction_id=result.transaction_id,
                identity=result.identity,
            ),
        )
    _ = commit_sha


def witness_and_consume(
    result: PdpResult,
    *,
    current_base_sha: str,
    patch_digest: str,
    repo: str,
    target_ref: str,
    policy_digest: str,
) -> dict[str, Any]:
    """State witness then atomic consume. Typed failures do not publish."""
    if result.capability is None:
        return {"allowed": False, "status": "NO_CAPABILITY", "reasons": ["NO_CAPABILITY"]}
    try:
        consumed = consume_capability(
            capability_id=result.capability.capability_id,
            store=result.store,
            current_base_sha=current_base_sha,
            patch_digest=patch_digest,
            repo=repo,
            target_ref=target_ref,
            policy_digest=policy_digest,
            evidence_bundle_digest=result.evidence_bundle_digest,
        )
    except StateWitnessError as exc:
        return {"allowed": False, "status": exc.code, "reasons": [exc.code]}
    except CapabilityAlreadyConsumed:
        return {
            "allowed": False,
            "status": CAPABILITY_ALREADY_CONSUMED,
            "reasons": [CAPABILITY_ALREADY_CONSUMED],
        }
    except CapabilityAlreadyClaimed:
        return {
            "allowed": False,
            "status": ALREADY_CLAIMED,
            "reasons": [ALREADY_CLAIMED],
        }
    except CapabilityInvalidated as exc:
        return {
            "allowed": False,
            "status": exc.code,
            "reasons": [exc.code],
        }
    return consumed


def witness_and_complete_consume(result: PdpResult) -> dict[str, Any]:
    """Complete CONSUMING -> CONSUMED after confirmed Gitea success. Idempotent if already CONSUMED."""
    if result.capability is None:
        return {"allowed": False, "status": "NO_CAPABILITY", "reasons": ["NO_CAPABILITY"]}
    try:
        return complete_consumed_capability(
            capability_id=result.capability.capability_id,
            store=result.store,
        )
    except CapabilityNotConsuming as exc:
        return {"allowed": False, "status": exc.code, "reasons": [exc.code]}
    except CapabilityAlreadyConsumed:
        return {
            "allowed": False,
            "status": CAPABILITY_ALREADY_CONSUMED,
            "reasons": [CAPABILITY_ALREADY_CONSUMED],
        }


def run_publish_pdp(
    *,
    state_root: Path,
    project: str,
    run_id: str,
    bundle_id: str,
    bundle_root: Path,
    manifest: PatchBundleManifest,
    authorized_files: list[str],
    source_sha: str,
    agent_branch: str,
    invoked_by: str = "unknown",
    adapter_kwargs: dict[str, dict[str, Any]] | None = None,
    repo_url: str | None = None,
    issue_client: Any | None = None,
) -> PdpResult:
    """Evidence bus → frozen C. AUTO_ADMIT mints capability; else no capability."""
    session = load_session_by_run(state_root, project, run_id)
    session_id = session.session_id if session is not None else f"sess-{run_id}"
    envelope = _ensure_envelope(
        state_root,
        project=project,
        run_id=run_id,
        session=session,
        authorized_files=authorized_files,
        source_sha=source_sha,
        invoked_by=invoked_by,
    )
    identity = _identity_for(envelope, session)
    patch_path = bundle_root / (manifest.patch_filename or "patch.diff")
    patch_text = patch_path.read_text(encoding="utf-8", errors="replace") if patch_path.is_file() else ""
    changed = changed_files_from_patch(patch_text) or list(authorized_files)
    store_dir = transaction_dir(state_root, project, session_id)
    proposal = _load_or_build_proposal(
        store_dir,
        session_id=session_id,
        run_id=run_id,
        bundle_id=bundle_id,
        bundle_root=bundle_root,
        manifest=manifest,
        envelope=envelope,
        changed_files=changed,
        identity=identity,
    )
    patch_digest = proposal.patch_digest
    from agent_control.transaction.barriers import (
        KIND_CANCELLED,
        KIND_TIMED_OUT,
        DurableBarrierError,
        PHASE_EVIDENCE,
        PHASE_MINT,
        barrier_kinds,
        check_durable_effect_allowed,
        persist_escalate_barrier,
        persist_reject_barrier,
    )

    kinds = barrier_kinds(state_root, run_id)
    if KIND_CANCELLED in kinds or KIND_TIMED_OUT in kinds:
        check_durable_effect_allowed(state_root, run_id=run_id, phase=PHASE_EVIDENCE)
    units = units_from_changed_files(changed, list(envelope.authorized_files or authorized_files))
    change_classes = classify_change_classes(
        changed_files=changed,
        task_type=envelope.task_type,
        security_finding_ids=envelope.security_finding_ids,
        units=units,
        authorized_change_classes=list(envelope.authorized_change_classes),
    )
    route = build_route(
        change_classes,
        route_id="default_deterministic_v1",
        tenant_id=envelope.tenant_id,
        org_id=envelope.org_id,
        repository=envelope.repository,
        task_id=envelope.task_id,
        patch_digest=patch_digest,
    )
    evidence_key = canonical_json_hash(
        {
            "proposal_id": proposal.proposal_id,
            "route_id": route.route_id,
            "patch_digest": patch_digest,
            "source_sha": proposal.source_sha,
        }
    )
    evidence_path = store_dir / "evidence" / f"{evidence_key}.json"
    cached = _load_json(evidence_path)
    routed_ids = {item.provider_id for item in routed_providers(route)}
    trees = MaterializedTrees(
        source_root=bundle_root / "source",
        candidate_root=bundle_root / "candidate",
        source_tree_digest=None,
        candidate_tree_digest=None,
        source_ready=False,
        candidate_ready=False,
    )
    if repo_url is not None or "P2" in routed_ids:
        trees = materialize_source_candidate_trees(
            bundle_root=bundle_root,
            source_sha=source_sha or proposal.source_sha,
            patch_path=patch_path,
            repo_url=repo_url,
            project=project,
            patch_digest=patch_digest,
            receipt_dir=store_dir,
        )
    freeze_result = None
    if "P4" in routed_ids:
        freeze_result = freeze_task_issue_at_creation(
            repository=envelope.repository,
            provider_task_id=envelope.provider_task_id,
            store_path=store_dir / TASK_FREEZE_FILENAME,
            client=issue_client,
        )
    if adapter_kwargs is not None:
        kwargs = dict(adapter_kwargs)
    else:
        kwargs = in_process_adapter_kwargs(envelope=envelope, units=units)
        kwargs["P2"] = {
            **_p2_live_trees(bundle_root),
            "artifact_dir": str(store_dir / "evidence" / "p2"),
        }
        if freeze_result is not None:
            kwargs["P4"] = p4_live_kwargs(
                freeze_result,
                repository=envelope.repository,
                task_id=envelope.task_id,
            )
    binding: dict[str, Any] = {
        "repo": envelope.repository,
        "source_sha": proposal.source_sha,
        "patch_digest": patch_digest,
    }
    if trees.candidate_tree_digest:
        binding["candidate_digest"] = trees.candidate_tree_digest
    if cached is None:
        check_durable_effect_allowed(state_root, run_id=run_id, phase=PHASE_EVIDENCE)
        evidence = run_evidence_bus(
            binding=binding,
            route=route,
            adapter_kwargs=kwargs,
            run_id=run_id,
            proposal_id=proposal.proposal_id,
            task_id=envelope.task_id,
        )
        _atomic_write_json(evidence_path, evidence)
    else:
        evidence = cached
    bundle_digest = str(evidence.get("bundle_digest") or digest64(json.dumps(evidence, sort_keys=True)))
    projected_units, projected_verify, _notes = project_bundle_onto_c_inputs(
        units,
        {"passed": True, "incomplete": False},
        evidence,
    )
    policy = PolicyFields(
        policy_id=envelope.policy_context.policy_id,
        policy_version=envelope.policy_context.policy_version,
        policy_digest=envelope.policy_context.policy_digest,
        admission_implementation_digest=envelope.policy_context.admission_implementation_digest
        or FROZEN_C_HASH,
    )
    g0_binding = bind_g0_input(changed)
    policy_receipt = create_policy_bundle_receipt(
        policy=policy,
        g0=g0_binding,
        c_load_mode=C_LOAD_MODE,
    )
    receipt_path = store_dir / "policy_bundles" / f"{policy_receipt.bundle_digest}.json"
    _atomic_write_json(receipt_path, policy_receipt.model_dump(mode="json"))
    preflight = evaluate_transaction_preflight(
        changed_paths=changed,
        units=projected_units,
        verification=projected_verify,
        policy=policy,
        g0=g0_binding,
        proposal_id=str(proposal.proposal_id),
        patch_digest=patch_digest,
        policy_bundle_digest=policy_receipt.bundle_digest,
    )
    preflight_path = store_dir / "preflight" / f"{policy_receipt.bundle_digest}.json"
    _atomic_write_json(preflight_path, preflight.model_dump(mode="json"))
    admission_key = canonical_json_hash(
        {
            "proposal_id": proposal.proposal_id,
            "bundle_digest": bundle_digest,
            "policy_digest": policy.policy_digest,
            "policy_bundle_digest": policy_receipt.bundle_digest,
            "g0_input_state": g0_binding.state,
        }
    )
    admission_path = store_dir / "admission" / f"{admission_key}.json"
    cached_admission = _load_json(admission_path)
    required_failed = bool(evidence.get("required_provider_failures") or evidence.get("auto_admit_blocked"))
    if cached_admission is None:
        writable = []
        for path in envelope.authorized_files or authorized_files:
            norm = path.replace("\\", "/")
            writable.append({"path": norm, "element_key": f"file:{norm}"})
        decision_map = {"writable_resources": writable}
        if preflight.status != PREFLIGHT_READY:
            reason = preflight.incomplete_reason or "PDP_INPUT_INCOMPLETE"
            admission = incomplete_admission_decision(
                proposal_id=str(proposal.proposal_id),
                patch_digest=patch_digest,
                policy=policy,
                reason=reason,
                g0_input_state=g0_binding.state,
                policy_bundle_digest=policy_receipt.bundle_digest,
                verification=projected_verify,
            )
        else:
            admission = wrap_decide_c(
                units=projected_units,
                changed_paths=changed,
                decision=decision_map,
                g0=list(g0_binding.violations),
                verification=projected_verify,
                policy=policy,
                proposal_id=str(proposal.proposal_id),
                patch_digest=patch_digest,
                tenant_id=envelope.tenant_id,
                org_id=envelope.org_id,
                repository=envelope.repository,
                required_provider_failed=required_failed,
                g0_input_state=g0_binding.state,
                policy_bundle_digest=policy_receipt.bundle_digest,
            )
        payload = admission.model_dump(mode="json")
        payload["g0_input_state"] = g0_binding.state
        payload["policy_bundle_digest"] = policy_receipt.bundle_digest
        _atomic_write_json(admission_path, payload)
    else:
        admission = PatchAdmissionDecision.model_validate(cached_admission)

    store = capability_store(state_root)
    transaction_id = canonical_json_hash(
        {"proposal_id": proposal.proposal_id, "run_id": run_id, "bundle_id": bundle_id}
    )
    result = PdpResult(
        decision=admission.decision,
        reasons=list(admission.reasons),
        envelope=envelope,
        proposal=proposal,
        admission=admission,
        evidence=evidence,
        policy=policy,
        identity=identity,
        patch_digest=patch_digest,
        evidence_bundle_digest=bundle_digest,
        allowed_target_branch=agent_branch,
        capability=None,
        escalation=None,
        transaction_id=transaction_id,
        store=store,
    )
    _append_typed_event(
        state_root,
        event_type=EVENT_PATCH_ADMISSION_DECISION,
        project=project,
        event_id=admission.decision_digest,
        payload=admission.model_dump(mode="json"),
    )
    if admission.decision == AUTO_ADMIT:
        try:
            check_durable_effect_allowed(
                state_root,
                run_id=run_id,
                phase=PHASE_MINT,
                transaction_id=transaction_id,
                proposal_id=str(proposal.proposal_id),
            )
        except DurableBarrierError:
            return result
        cap_id = canonical_json_hash(
            {
                "proposal_id": proposal.proposal_id,
                "decision_digest": admission.decision_digest,
                "patch_digest": patch_digest,
            }
        )
        existing_cap = store.get(cap_id)
        if existing_cap is not None:
            body = {
                key: value
                for key, value in existing_cap.items()
                if key in DurablePatchCapability.model_fields
            }
            capability = DurablePatchCapability.model_validate(body)
        else:
            capability = mint_capability(
                repo=envelope.repository,
                tenant_id=envelope.tenant_id,
                org_id=envelope.org_id,
                source_sha=proposal.source_sha,
                patch_digest=patch_digest,
                allowed_target_branch=agent_branch,
                policy_digest=policy.policy_digest,
                verification_digest=canonical_json_hash(projected_verify),
                admission_decision_digest=admission.decision_digest,
                evidence_bundle_digest=bundle_digest,
                task_id=envelope.task_id,
                session_id=session_id,
                human_initiator=identity.ON_BEHALF_OF,
                agent_identity=identity.EXECUTED_BY,
                store=store,
                capability_id=cap_id,
            )
        result.capability = capability
        receipt = public_receipt(
            {**capability.model_dump(mode="json"), "consumed": bool(existing_cap and existing_cap.get("consumed"))}
            if existing_cap
            else capability.model_dump(mode="json")
        )
        _append_typed_event(
            state_root,
            event_type=EVENT_DURABLE_PATCH_CAPABILITY,
            project=project,
            event_id=digest64(cap_id)[:32],
            payload=receipt.model_dump(mode="json"),
        )
        _record_ledger(
            state_root,
            store_dir,
            result=result,
            event_seq=1,
            durable_outcome="AUTO_ADMITTED_CAPABILITY_MINTED",
            capability_id=capability.capability_id,
            capability_digest=capability.capability_digest,
        )
        return result
    if admission.decision == ESCALATE:
        escalation = make_escalation(
            escalation_id=canonical_json_hash({"admission": admission.decision_digest, "kind": "escalate"}),
            tenant_id=envelope.tenant_id,
            org_id=envelope.org_id,
            repository=envelope.repository,
            task_id=envelope.task_id,
            source_sha=proposal.source_sha,
            patch_digest=patch_digest,
            task_digest=envelope.task_digest,
            bundle_id=str(evidence.get("bundle_id") or "unknown"),
            bundle_digest=bundle_digest,
            reasons=list(admission.reasons) or ["ESCALATE"],
            policy=policy,
            risk_classification=admission.risk_tier,
            identity=identity,
            proposal_id=proposal.proposal_id,
            decision_id=admission.decision_digest,
            created_at=utc_now(),
        )
        result.escalation = escalation
        esc_path = store_dir / "escalations" / f"{escalation.escalation_id}.json"
        _atomic_write_json(esc_path, escalation.model_dump(mode="json"))
        persist_escalate_barrier(
            state_root,
            run_id=run_id,
            transaction_id=transaction_id,
            project=project,
        )
        _append_typed_event(
            state_root,
            event_type=EVENT_ADMISSION_ESCALATION,
            project=project,
            event_id=escalation.escalation_id[:32],
            payload=escalation.model_dump(mode="json"),
        )
        _record_ledger(
            state_root,
            store_dir,
            result=result,
            event_seq=1,
            durable_outcome="ESCALATED_NO_CAPABILITY",
        )
        return result
    reject_path = store_dir / "decisions" / f"{admission.decision_digest}.json"
    _atomic_write_json(reject_path, admission.model_dump(mode="json"))
    persist_reject_barrier(
        state_root,
        run_id=run_id,
        transaction_id=transaction_id,
        project=project,
    )
    _record_ledger(
        state_root,
        store_dir,
        result=result,
        event_seq=1,
        durable_outcome="REJECTED_NO_CAPABILITY",
    )
    return result
