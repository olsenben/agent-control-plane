"""Read-only Observatory software-transaction view-model (W5).

Observatory is not a PDP and not a PEP. This module never mints
capabilities, never calls frozen C, and never publishes. It projects
already-recorded ``software_transaction.v1`` ledger events, append-only
graph-edge capture, and existing session / CI events into a display-safe
dict for ``session_detail.html``.

Missing live broker events are not an error: every required field is
always present, with a typed empty/unavailable state when the matching
record does not exist yet.

Vendor-neutral correlation fields on the view-model are ``trace_id`` and
``transaction_id`` (never SCM-specific names). Capability secrets and raw
scanner payloads are stripped before they reach a template or API.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_control.events import load_project_events
from agent_control.observe.safe_display import is_prohibited_field_name
from agent_shared.models.agent_session import AgentSession

SOFTWARE_TRANSACTION_TYPE = "software_transaction.v1"
GRAPH_EDGE_TYPE = "transaction_graph_edge.v1"
TRANSACTION_LOG_CATEGORY = "transaction"

# Nested blobs that must never be copied into the view-model even when a
# producer (or a test fixture) plants them on the ledger payload.
_SCANNER_PAYLOAD_KEYS = frozenset(
    {
        "findings",
        "sarif",
        "results",
        "runs",
        "raw_findings",
        "scanner_payload",
        "raw_artifact",
        "raw_artifact_location",
        "locations",
        "message",
        "extra",
        "items",
        "receipts",
        "invalid_receipts",
        "detail",
        "notes",
    }
)
_CAPABILITY_SECRET_KEYS = frozenset(
    {
        "secret",
        "capability_secret",
        "signing_secret",
        "signing_key",
        "private_material",
    }
)
_PUBLIC_CAPABILITY_KEYS = (
    "capability_id",
    "capability_digest",
    "admission_decision_digest",
    "consumed",
    "expired",
    "replayed",
    "issued_at",
    "expires_at",
    "issuer",
    "allowed_target_branch",
    "patch_digest",
    "source_sha",
    "repo",
    "lifecycle",
)

_MAX_STR_LEN = 500
_MAX_LIST_LEN = 50
_MAX_TIMELINE = 50

_UNAVAILABLE = "unavailable"


def transaction_log_category(event_type: str) -> str | None:
    """Observatory log-category tag for transaction ledger types."""
    if event_type in {
        SOFTWARE_TRANSACTION_TYPE,
        GRAPH_EDGE_TYPE,
        "transaction_control_event.v1",
        "PUBLISH_REQUESTED",
        "STUCK_TRANSACTION",
        "RUN_CANCELLED",
        "RUN_TIMED_OUT",
    }:
        return TRANSACTION_LOG_CATEGORY
    return None


def flatten_software_transaction_fields(event: dict[str, Any]) -> dict[str, Any]:
    """Promote known-safe scalars to top-level payload keys for safe_display.

    Nested objects stay in the payload so the default-deny table can mark
    them ``metadata_only`` (name/count only). Secret-shaped and scanner
    payload keys are never copied.
    """
    if event.get("type") != SOFTWARE_TRANSACTION_TYPE:
        return event
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return event

    flattened = dict(payload)
    for key in (
        "transaction_id",
        "tenant_id",
        "org_id",
        "repository",
        "schema_version",
        "durable_outcome",
        "recorded_at",
        "event_seq",
        "append_only",
        "run_id",
        "trace_id",
    ):
        if key in payload and not is_prohibited_field_name(key):
            flattened[key] = payload[key]

    task = payload.get("task") if isinstance(payload.get("task"), dict) else {}
    for src, dest in (
        ("task_id", "task_id"),
        ("task_digest", "task_digest"),
        ("provider_task_id", "provider_task_id"),
    ):
        if task.get(src) is not None:
            flattened[dest] = task[src]

    actor = payload.get("actor") if isinstance(payload.get("actor"), dict) else {}
    if actor.get("session_id"):
        flattened["actor_session_id"] = actor["session_id"]
    _copy_principal(actor.get("actor_identity"), flattened, "actor")
    _copy_principal(actor.get("worker_identity"), flattened, "worker")

    patch = payload.get("patch") if isinstance(payload.get("patch"), dict) else {}
    for src, dest in (
        ("proposal_id", "proposal_id"),
        ("source_sha", "source_sha"),
        ("patch_digest", "patch_digest"),
    ):
        if patch.get(src) is not None:
            flattened[dest] = patch[src]

    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    if evidence.get("bundle_id"):
        flattened["bundle_id"] = evidence["bundle_id"]
    if evidence.get("bundle_digest"):
        flattened["bundle_digest"] = evidence["bundle_digest"]

    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    if decision.get("decision") is not None:
        flattened["admission_decision"] = decision["decision"]
    if decision.get("decision_digest"):
        flattened["decision_digest"] = decision["decision_digest"]
    if decision.get("escalation_id"):
        flattened["escalation_id"] = decision["escalation_id"]

    capability = payload.get("capability") if isinstance(payload.get("capability"), dict) else {}
    for key in _PUBLIC_CAPABILITY_KEYS:
        if key in capability and not _is_secret_or_scanner_key(key):
            flattened[key if key != "repo" else "capability_repo"] = capability[key]

    identity = payload.get("identity") if isinstance(payload.get("identity"), dict) else {}
    _copy_principal(identity.get("ON_BEHALF_OF"), flattened, "identity_on_behalf_of")
    _copy_principal(identity.get("EXECUTED_BY"), flattened, "identity_executed_by")
    _copy_principal(identity.get("AUTHORIZED_BY"), flattened, "identity_authorized_by")

    copied = dict(event)
    copied["payload"] = flattened
    return copied


def resolve_transaction_run_id(
    event: dict[str, Any],
    *,
    state_root: Path | None = None,
    project: str | None = None,
) -> str | None:
    """``run_id`` for ``software_transaction.v1``, or ``None`` for other types.

    Prefers an explicit payload/envelope ``run_id``. When the broker has not
    yet stamped one, falls back to the actor session's first run id (needs
    ``state_root`` + ``project``).
    """
    if str(event.get("type") or "") != SOFTWARE_TRANSACTION_TYPE:
        return None
    payload = event.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    rid = payload.get("run_id") or event.get("run_id")
    if isinstance(rid, str) and rid:
        return rid
    if state_root is None or not project:
        return None
    session_id = resolve_transaction_session_id(event)
    if not session_id:
        return None
    try:
        from agent_control.session.storage import load_session

        session = load_session(state_root, project, session_id)
    except Exception:
        return None
    if session is None or not session.run_ids:
        return None
    first = session.run_ids[0]
    return first if isinstance(first, str) and first else None


def resolve_transaction_session_id(event: dict[str, Any]) -> str | None:
    """``actor.session_id`` for ``software_transaction.v1``."""
    if str(event.get("type") or "") != SOFTWARE_TRANSACTION_TYPE:
        return None
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    sid = payload.get("session_id")
    if isinstance(sid, str) and sid:
        return sid
    actor = payload.get("actor")
    if isinstance(actor, dict):
        nested = actor.get("session_id")
        if isinstance(nested, str) and nested:
            return nested
    return None


def transaction_graph_edges_path(state_root: Path, project: str) -> Path:
    owner, repo = project.split("/", 1)
    return state_root / "projects" / owner / repo / "transaction_graph_edges.jsonl"


def admission_feedback_path(state_root: Path, project: str) -> Path:
    owner, repo = project.split("/", 1)
    return state_root / "projects" / owner / repo / "admission_feedback.jsonl"


def transaction_panel_view(
    state_root: Path,
    *,
    project: str,
    run_id: str,
    session: AgentSession | None = None,
) -> dict[str, Any]:
    """Panel view-model for one session/run. Always returns every required key."""
    session_id = session.session_id if session is not None else None
    trace_id = session.trace_id if session is not None else None

    events = load_project_events(state_root, project)
    matched = [
        ev
        for ev in events
        if ev.get("type") == SOFTWARE_TRANSACTION_TYPE
        and _transaction_matches(
            ev.get("payload") if isinstance(ev.get("payload"), dict) else {},
            run_id=run_id,
            session_id=session_id,
            trace_id=trace_id,
        )
    ]
    record = matched[-1] if matched else None
    payload = record.get("payload") if record and isinstance(record.get("payload"), dict) else {}

    edges = _load_jsonl(transaction_graph_edges_path(state_root, project))
    feedback = _load_jsonl(admission_feedback_path(state_root, project))

    view = _empty_view(trace_id=trace_id)
    if session is not None:
        _apply_session_fallback(view, session)

    if payload:
        _apply_transaction_payload(view, payload)
        view["present"] = True

    _apply_feedback_reasons(view, feedback, payload)
    _apply_ci_status(view, state_root, project=project, session=session)
    view["timeline"] = _build_timeline(
        payload=payload,
        edges=edges,
        session=session,
        recorded_at=_opt_str(record.get("recorded_at")) if record else None,
    )
    return _redact_view(view)


def _empty_view(*, trace_id: str | None) -> dict[str, Any]:
    return {
        "authoritative": False,
        "present": False,
        "transaction_id": None,
        "trace_id": trace_id,
        "task": {
            "task_id": None,
            "task_digest": None,
            "provider_task_id": None,
            "status": _UNAVAILABLE,
        },
        "actor": {
            "initiator_id": None,
            "initiator_kind": None,
            "actor_id": None,
            "actor_kind": None,
            "worker_id": None,
            "worker_kind": None,
            "session_id": None,
            "status": _UNAVAILABLE,
        },
        "patch": {
            "summary": None,
            "patch_digest": None,
            "source_sha": None,
            "proposal_id": None,
            "status": _UNAVAILABLE,
        },
        "evidence_providers": [],
        "evidence_status": _UNAVAILABLE,
        "evidence": {
            "bundle_id": None,
            "bundle_digest": None,
            "status": _UNAVAILABLE,
            "providers": [],
        },
        "admission_result": None,
        "decision_reasons": [],
        "capability_status": {
            "capability_id": None,
            "status": _UNAVAILABLE,
            "capability_digest": None,
            "consumed": None,
            "expired": None,
            "replayed": None,
            "issuer": None,
        },
        "publish_status": _UNAVAILABLE,
        "ci_verification_status": {
            "status": _UNAVAILABLE,
            "phase": None,
            "claim_status": None,
        },
        "timeline": [],
        "durable_outcome": None,
    }


def _apply_session_fallback(view: dict[str, Any], session: AgentSession) -> None:
    """Bind TASK / ACTOR / CI / timeline identity to the existing session."""
    view["trace_id"] = session.trace_id
    if view["task"]["status"] == _UNAVAILABLE:
        view["task"]["task_id"] = f"{session.subject_kind}:{session.subject_number}"
        view["task"]["status"] = "session_fallback"
    if view["actor"]["status"] == _UNAVAILABLE:
        view["actor"]["initiator_id"] = session.invoked_by
        view["actor"]["initiator_kind"] = "HUMAN_INITIATOR"
        view["actor"]["actor_id"] = session.acting_identity
        view["actor"]["session_id"] = session.session_id
        view["actor"]["status"] = "session_fallback"


def _apply_transaction_payload(view: dict[str, Any], payload: dict[str, Any]) -> None:
    view["transaction_id"] = _opt_str(payload.get("transaction_id"))
    if payload.get("trace_id"):
        view["trace_id"] = _opt_str(payload.get("trace_id"))
    view["durable_outcome"] = _opt_str(payload.get("durable_outcome"))

    task = payload.get("task") if isinstance(payload.get("task"), dict) else {}
    view["task"] = {
        "task_id": _opt_str(task.get("task_id")),
        "task_digest": _opt_str(task.get("task_digest")),
        "provider_task_id": _opt_str(task.get("provider_task_id")),
        "status": "recorded" if task.get("task_id") else _UNAVAILABLE,
    }

    actor = payload.get("actor") if isinstance(payload.get("actor"), dict) else {}
    identity = payload.get("identity") if isinstance(payload.get("identity"), dict) else {}
    on_behalf = identity.get("ON_BEHALF_OF") if isinstance(identity.get("ON_BEHALF_OF"), dict) else {}
    executed = identity.get("EXECUTED_BY") if isinstance(identity.get("EXECUTED_BY"), dict) else {}
    actor_id_obj = actor.get("actor_identity") if isinstance(actor.get("actor_identity"), dict) else {}
    worker_obj = actor.get("worker_identity") if isinstance(actor.get("worker_identity"), dict) else {}
    view["actor"] = {
        "initiator_id": _opt_str(on_behalf.get("identity_id")) or _opt_str(actor_id_obj.get("identity_id")),
        "initiator_kind": _opt_str(on_behalf.get("principal_kind")) or "HUMAN_INITIATOR",
        "actor_id": _opt_str(executed.get("identity_id")) or _opt_str(actor_id_obj.get("identity_id")),
        "actor_kind": _opt_str(executed.get("principal_kind")) or _opt_str(actor_id_obj.get("principal_kind")),
        "worker_id": _opt_str(worker_obj.get("identity_id")),
        "worker_kind": _opt_str(worker_obj.get("principal_kind")),
        "session_id": _opt_str(actor.get("session_id")),
        "status": "recorded",
    }

    patch = payload.get("patch") if isinstance(payload.get("patch"), dict) else {}
    digest = _opt_str(patch.get("patch_digest"))
    source_sha = _opt_str(patch.get("source_sha"))
    summary_parts = [p for p in (source_sha, digest) if p]
    view["patch"] = {
        "summary": " ".join(summary_parts) if summary_parts else None,
        "patch_digest": digest,
        "source_sha": source_sha,
        "proposal_id": _opt_str(patch.get("proposal_id")),
        "status": "recorded" if digest or source_sha else _UNAVAILABLE,
    }

    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    providers = _evidence_providers_from_payload(payload, evidence)
    bundle_id = _opt_str(evidence.get("bundle_id"))
    bundle_digest = _opt_str(evidence.get("bundle_digest"))
    evidence_status = "recorded" if bundle_id or providers else _UNAVAILABLE
    view["evidence_providers"] = providers
    view["evidence_status"] = evidence_status
    view["evidence"] = {
        "bundle_id": bundle_id,
        "bundle_digest": bundle_digest,
        "status": evidence_status,
        "providers": providers,
    }

    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    view["admission_result"] = _opt_str(decision.get("decision"))
    reasons = payload.get("reasons") if isinstance(payload.get("reasons"), list) else []
    view["decision_reasons"] = _cap_str_list(reasons)

    view["capability_status"] = _capability_status(
        payload.get("capability") if isinstance(payload.get("capability"), dict) else None,
        durable_outcome=view["durable_outcome"],
    )
    view["publish_status"] = _publish_status(view["durable_outcome"])
    view["ci_verification_status"] = _ci_from_outcome(view["durable_outcome"])


def _evidence_providers_from_payload(
    payload: dict[str, Any],
    evidence: dict[str, Any],
) -> list[dict[str, Any]]:
    """Status-only provider rows. Never copies scanner payloads or findings."""
    rows: list[dict[str, Any]] = []
    candidates: list[Any] = []
    for key in ("providers", "provider_status"):
        value = evidence.get(key) or payload.get(key)
        if isinstance(value, list):
            candidates.extend(value)
    # Bundles may be planted on the payload for tests; only status fields
    # are read. Raw ``items`` / ``receipts`` values are not copied.
    for key in ("items", "receipts"):
        value = evidence.get(key) or payload.get(key)
        if isinstance(value, list):
            candidates.extend(value)
    for item in candidates[:_MAX_LIST_LEN]:
        if not isinstance(item, dict):
            continue
        provider_id = (
            _opt_str(item.get("provider_id"))
            or _producer_id(item.get("producer"))
            or _opt_str(item.get("identity_id"))
        )
        status = _opt_str(item.get("result_status") or item.get("status"))
        evidence_type = _opt_str(item.get("evidence_type") or item.get("adapter_class"))
        trust_class = _opt_str(item.get("trust_class"))
        if not any((provider_id, status, evidence_type)):
            continue
        rows.append(
            {
                "provider_id": provider_id,
                "status": status or _UNAVAILABLE,
                "evidence_type": evidence_type,
                "trust_class": trust_class,
            }
        )
    return rows


def _capability_status(
    capability: dict[str, Any] | None,
    *,
    durable_outcome: str | None,
) -> dict[str, Any]:
    if not capability and not durable_outcome:
        return {
            "capability_id": None,
            "status": _UNAVAILABLE,
            "capability_digest": None,
            "consumed": None,
            "lifecycle": None,
            "expired": None,
            "replayed": None,
            "issuer": None,
        }
    public: dict[str, Any] = {}
    if capability:
        for key in _PUBLIC_CAPABILITY_KEYS:
            if key in capability and not _is_secret_or_scanner_key(key):
                public[key] = capability[key]
    status = "none"
    lifecycle = str(public.get("lifecycle") or "")
    if durable_outcome == "AUTO_ADMITTED_CAPABILITY_MINTED" or lifecycle == "MINTED":
        status = "minted"
    if lifecycle == "CONSUMING":
        status = "consuming"
    elif durable_outcome == "PUBLISHED" or public.get("consumed") is True or lifecycle == "CONSUMED":
        status = "consumed"
    elif public.get("expired") is True or lifecycle == "EXPIRED":
        status = "expired"
    elif lifecycle == "INVALIDATED":
        status = "invalidated"
    elif public.get("replayed") is True:
        status = "replayed"
    elif public.get("capability_id") or public.get("capability_digest"):
        status = "minted"
    elif durable_outcome in {"ESCALATED_NO_CAPABILITY", "REJECTED_NO_CAPABILITY"}:
        status = "none"
    return {
        "capability_id": _opt_str(public.get("capability_id")),
        "status": status,
        "capability_digest": _opt_str(public.get("capability_digest")),
        "consumed": public.get("consumed") if isinstance(public.get("consumed"), bool) else None,
        "lifecycle": lifecycle or None,
        "expired": public.get("expired") if isinstance(public.get("expired"), bool) else None,
        "replayed": public.get("replayed") if isinstance(public.get("replayed"), bool) else None,
        "issuer": _opt_str(public.get("issuer")),
    }


def _publish_status(durable_outcome: str | None) -> str:
    if durable_outcome is None:
        return _UNAVAILABLE
    if durable_outcome == "PUBLISHED":
        return "published"
    if durable_outcome == "TRANSACTION_FINALIZED":
        return "finalized"
    return "not_published"


def _ci_from_outcome(durable_outcome: str | None) -> dict[str, Any]:
    mapping = {
        "VERIFICATION_PASSED": "passed",
        "VERIFICATION_FAILED": "failed",
        "VERIFICATION_MISSING": "missing",
    }
    status = mapping.get(durable_outcome or "", _UNAVAILABLE)
    return {"status": status, "phase": None, "claim_status": None}


def _apply_feedback_reasons(
    view: dict[str, Any],
    feedback: list[dict[str, Any]],
    payload: dict[str, Any],
) -> None:
    if view["decision_reasons"]:
        return
    tx_id = view.get("transaction_id")
    digest = (view.get("patch") or {}).get("patch_digest")
    for record in reversed(feedback):
        if not isinstance(record, dict):
            continue
        if digest and record.get("patch_digest") and record.get("patch_digest") != digest:
            continue
        if tx_id and record.get("transaction_id") and record.get("transaction_id") != tx_id:
            continue
        reasons = record.get("reasons")
        if isinstance(reasons, list) and reasons:
            view["decision_reasons"] = _cap_str_list(reasons)
            if view["admission_result"] is None:
                view["admission_result"] = _opt_str(record.get("decision"))
            return
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    extra_reasons = decision.get("reasons")
    if isinstance(extra_reasons, list):
        view["decision_reasons"] = _cap_str_list(extra_reasons)


def _apply_ci_status(
    view: dict[str, Any],
    state_root: Path,
    *,
    project: str,
    session: AgentSession | None,
) -> None:
    current = view["ci_verification_status"]
    if current.get("status") not in {None, _UNAVAILABLE}:
        return
    if session is None:
        return
    try:
        from agent_control.observe.ci_channel import current_ci_phase_view

        phase = current_ci_phase_view(
            state_root, project=project, session_id=session.session_id
        )
    except Exception:
        phase = None
    if not phase:
        return
    view["ci_verification_status"] = {
        "status": phase.get("claim_status") or phase.get("phase") or "recorded",
        "phase": phase.get("phase"),
        "claim_status": phase.get("claim_status"),
    }


def _build_timeline(
    *,
    payload: dict[str, Any],
    edges: list[dict[str, Any]],
    session: AgentSession | None,
    recorded_at: str | None,
) -> list[dict[str, Any]]:
    """Transaction-scoped timeline. Does not replay the generic observe.sqlite log.

    Session events already render in panel 2 (paginated). This panel only
    shows software_transaction.v1 + graph-edge capture, with a single
    session-identity row when neither exists yet.
    """
    rows: list[dict[str, Any]] = []
    tx_id = _opt_str(payload.get("transaction_id")) if payload else None
    trace_id = _opt_str(payload.get("trace_id")) if payload else None
    if session is not None and not trace_id:
        trace_id = session.trace_id
    session_id = session.session_id if session is not None else None

    if tx_id or recorded_at:
        rows.append(
            {
                "at": recorded_at,
                "kind": SOFTWARE_TRANSACTION_TYPE,
                "summary": _transaction_timeline_summary(payload),
                "transaction_id": tx_id,
                "trace_id": trace_id,
            }
        )

    for edge in edges:
        if not isinstance(edge, dict):
            continue
        edge_tx = _opt_str(edge.get("transaction_id"))
        if tx_id and edge_tx and edge_tx != tx_id:
            continue
        if not tx_id and session_id:
            if session_id not in {
                edge.get("from_entity_id"),
                edge.get("to_entity_id"),
            } and edge_tx:
                continue
        rows.append(
            {
                "at": _opt_str(edge.get("captured_at")),
                "kind": _opt_str(edge.get("edge_type")) or GRAPH_EDGE_TYPE,
                "summary": (
                    f"{edge.get('from_entity_kind')}->{edge.get('to_entity_kind')} "
                    f"({edge.get('edge_type')})"
                ),
                "transaction_id": edge_tx or tx_id,
                "trace_id": trace_id,
            }
        )

    if not rows and session is not None:
        rows.append(
            {
                "at": session.updated_at,
                "kind": "session",
                "summary": f"session {session.status.value} ({session.command_kind})",
                "transaction_id": None,
                "trace_id": trace_id,
            }
        )

    rows.sort(key=lambda item: (item.get("at") or "", item.get("kind") or ""))
    return rows[:_MAX_TIMELINE]


def _transaction_timeline_summary(payload: dict[str, Any]) -> str:
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    outcome = payload.get("durable_outcome") or "?"
    label = decision.get("decision") or outcome
    return f"Software transaction {label}"


def _transaction_matches(
    payload: dict[str, Any],
    *,
    run_id: str | None,
    session_id: str | None,
    trace_id: str | None,
) -> bool:
    if run_id and payload.get("run_id") == run_id:
        return True
    if trace_id and payload.get("trace_id") == trace_id:
        return True
    actor = payload.get("actor") if isinstance(payload.get("actor"), dict) else {}
    if session_id and actor.get("session_id") == session_id:
        return True
    if session_id and payload.get("session_id") == session_id:
        return True
    return False


def _redact_view(view: dict[str, Any]) -> dict[str, Any]:
    """Drop secret-shaped keys and scanner payloads anywhere in the tree."""
    return _redact_value(view)  # type: ignore[return-value]


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, inner in value.items():
            if _is_secret_or_scanner_key(str(key)):
                continue
            cleaned[str(key)] = _redact_value(inner)
        return cleaned
    if isinstance(value, list):
        return [_redact_value(item) for item in value[:_MAX_LIST_LEN]]
    if isinstance(value, str) and len(value) > _MAX_STR_LEN:
        return value[:_MAX_STR_LEN] + "...(truncated)"
    return value


def _is_secret_or_scanner_key(name: str) -> bool:
    lname = name.lower()
    if lname in _CAPABILITY_SECRET_KEYS or lname in _SCANNER_PAYLOAD_KEYS:
        return True
    return is_prohibited_field_name(name)


def _copy_principal(value: Any, dest: dict[str, Any], prefix: str) -> None:
    if not isinstance(value, dict):
        return
    identity_id = value.get("identity_id")
    kind = value.get("principal_kind")
    if identity_id is not None and not is_prohibited_field_name(f"{prefix}_identity_id"):
        dest[f"{prefix}_identity_id"] = identity_id
    if kind is not None:
        dest[f"{prefix}_identity_kind"] = kind


def _producer_id(producer: Any) -> str | None:
    if isinstance(producer, dict):
        return _opt_str(producer.get("name") or producer.get("identity_id") or producer.get("issuer"))
    if isinstance(producer, str):
        return producer
    return None


def _opt_str(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _cap_str_list(values: list[Any]) -> list[str]:
    out: list[str] = []
    for item in values[:_MAX_LIST_LEN]:
        if not isinstance(item, str) or not item:
            continue
        out.append(item[:_MAX_STR_LEN] if len(item) > _MAX_STR_LEN else item)
    return out


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows
