"""observe_event.v1 field classification + safe-display normalizer (V9 T01).

This module is the H1 hard-gate choke point: raw ledger event payloads must
pass through :func:`safe_display_event` before reaching any Observatory
display surface (API JSON, SSE stream, server-rendered UI). See
``agent_shared.models.observe_event`` for the four-tier classification
contract this module implements.

Two independent layers of defense make "never expose raw secrets/prompts"
true even if a per-type table entry is wrong:

1. A global field-*name* keyword filter (:func:`is_prohibited_field_name`)
   that forces ``prohibited`` regardless of any per-type table entry. This
   is what proves prompts/tokens/env/headers/tool-creds stay excluded even
   under a maintainer mistake.
2. A default-deny per-type table: any field not explicitly listed for a
   known event ``type`` is ``prohibited``; any event whose ``type`` is not
   registered at all is entirely unknown -- none of its payload field
   *values* are ever displayed, only field names (see
   :data:`ObserveEventV1.prohibited_field_names`).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent_control.observe.ci_channel import (
    build_ci_deep_link,
    ci_log_category,
    flatten_observation_fields,
)
from agent_shared.models.observe_event import FieldClassification, ObserveEventV1

# --- Layer 1: global keyword filter (name-based, classification-independent) ---

_PROHIBITED_NAME_KEYWORDS: tuple[str, ...] = (
    "token",
    "secret",
    "password",
    "passwd",
    "credential",
    "authorization",
    "auth_header",
    "cookie",
    "api_key",
    "apikey",
    "private_key",
    "ssh_key",
    "ssh_",
    "access_key",
    "bearer",
    "header",
    "env",
    "prompt",
    "stdout",
    "stderr",
    "raw_output",
    "raw_log",
    "raw_payload",
    "payload_json",
    "args",
    "system_message",
)


def is_prohibited_field_name(name: str) -> bool:
    """Name-based prohibition, independent of any per-type classification.

    This is a defense-in-depth layer: it forces ``prohibited`` even for a
    field a maintainer mistakenly marked ``allowlisted`` in the per-type
    table below.
    """
    lname = name.lower()
    return any(keyword in lname for keyword in _PROHIBITED_NAME_KEYWORDS)


# --- Layer 2: per-type field classification table (default-deny) ---

# CT103 session correlation fields shared by every agent.session_* /
# agent.subject_context_resolved / agent.memory_* / agent.recursive_context_* /
# agent.context_packet_created / agent.verification_* event (see
# agent_shared.models.agent_session.SessionEventCorrelation).
_SESSION_CORRELATION_FIELDS: dict[str, FieldClassification] = {
    "schema_version": "allowlisted",
    "schema": "allowlisted",
    "session_id": "allowlisted",
    "run_id": "allowlisted",
    "repo": "allowlisted",
    "project": "allowlisted",
    "subject_kind": "allowlisted",
    "subject_number": "allowlisted",
    "command_kind": "allowlisted",
    "risk_level": "allowlisted",
    "risk_tags": "allowlisted",
    "input_state_sha": "allowlisted",
    "head_sha": "allowlisted",
    "correlation_id": "allowlisted",
    "trace_id": "allowlisted",
    "session_created_at": "allowlisted",
    "event_at": "allowlisted",
}


def _with_common(*extra: dict[str, FieldClassification]) -> dict[str, FieldClassification]:
    merged = dict(_SESSION_CORRELATION_FIELDS)
    for table in extra:
        merged.update(table)
    return merged


# CT102 CI channel (V9 T08): agent.fix_ci_* fields shared by every event in
# agent_shared.models.ci -- none of these carry the session-correlation
# fields above (_SESSION_CORRELATION_FIELDS), they key by fix_run_id/
# repository instead (see agent_control.observe.ci_channel).
_CI_COMMON_FIELDS: dict[str, FieldClassification] = {
    "schema_version": "allowlisted",
    "fix_run_id": "allowlisted",
    "repository": "allowlisted",
    "expected_head_commit_sha": "allowlisted",
    "pr_number": "allowlisted",
}


def _with_ci_common(*extra: dict[str, FieldClassification]) -> dict[str, FieldClassification]:
    merged = dict(_CI_COMMON_FIELDS)
    for table in extra:
        merged.update(table)
    return merged


_TYPE_FIELD_CLASSIFICATIONS: dict[str, dict[str, FieldClassification]] = {
    "agent.session_started": _with_common(
        {
            "status": "allowlisted",
            "invoked_by": "allowlisted",
            "invoked_by_id": "allowlisted",
            "acting_identity": "allowlisted",
            "approved_by": "allowlisted",
            "source_comment_id": "allowlisted",
            "source_delivery_id": "allowlisted",
        }
    ),
    "agent.subject_context_resolved": _with_common({"context_source": "allowlisted"}),
    "agent.session_finished": _with_common(
        {
            "status": "allowlisted",
            "terminal_at": "allowlisted",
            "reason_code": "allowlisted",
            "reason": "redacted",
        }
    ),
    "agent.session_failed": _with_common(
        {
            "status": "allowlisted",
            "terminal_at": "allowlisted",
            "reason_code": "allowlisted",
            "reason": "redacted",
        }
    ),
    "agent.session_blocked": _with_common(
        {
            "status": "allowlisted",
            "terminal_at": "allowlisted",
            "reason_code": "allowlisted",
            "reason": "redacted",
        }
    ),
    "agent.session_worker_event": _with_common(
        {
            "worker_event_kind": "allowlisted",
            "outcome": "allowlisted",
            "stage": "allowlisted",
            "worker_timestamp": "allowlisted",
            "evidence_digest": "allowlisted",
            "error_classification": "allowlisted",
        }
    ),
    "agent.memory_preflight_created": _with_common(
        {
            "artifact_digest": "allowlisted",
            "preflight_status": "allowlisted",
            "recursive_context_required": "allowlisted",
            "relative_path": "allowlisted",
        }
    ),
    "agent.memory_preflight_failed": _with_common(
        {
            "reason_code": "allowlisted",
            "reason": "redacted",
        }
    ),
    "agent.recursive_context_completed": _with_common(
        {
            "artifact_digest": "allowlisted",
            "invoked": "allowlisted",
            "skipped": "allowlisted",
            "stop_reason": "allowlisted",
            "relative_path": "allowlisted",
        }
    ),
    "agent.recursive_context_failed": _with_common(
        {
            "reason_code": "allowlisted",
            "reason": "redacted",
        }
    ),
    "agent.memory_admitted": _with_common(
        {
            "record_id": "allowlisted",
            "epistemic_status": "allowlisted",
            "evidence_refs": "allowlisted",
            "admission_policy_version": "allowlisted",
        }
    ),
    "agent.memory_rejected": _with_common(
        {
            "reason": "redacted",
            "admission_policy_version": "allowlisted",
        }
    ),
    "agent.context_packet_created": _with_common(
        {
            "artifact_digest": "allowlisted",
            "preflight_digest": "allowlisted",
            "context_pack_digest": "allowlisted",
            "relative_path": "allowlisted",
        }
    ),
    **{
        f"agent.verification_{suffix}": _with_common(
            {
                "claim": "allowlisted",
                "scope_commit_sha": "allowlisted",
                "source": "allowlisted",
                "status": "allowlisted",
                "command_id": "allowlisted",
                "artifact": "allowlisted",
                "limitations": "redacted",
                "verdict_revision": "allowlisted",
                "artifact_digest": "allowlisted",
            }
        )
        for suffix in ("requested", "passed", "failed", "missing")
    },
    "agent.control_decision": {
        "schema_version": "allowlisted",
        "decision_id": "allowlisted",
        "kind": "allowlisted",
        "summary": "allowlisted",
        "session_id": "allowlisted",
        "run_id": "allowlisted",
        "trace_id": "allowlisted",
        "evidence_refs": "allowlisted",
        "policy_source_sha": "allowlisted",
        "metadata": "metadata_only",
        "recorded_at": "allowlisted",
    },
    "agent.injection_assessment": {
        "schema_version": "allowlisted",
        "mode": "allowlisted",
        "risk": "allowlisted",
        "categories": "allowlisted",
        "matched_regions": "metadata_only",
        "recommended_action": "allowlisted",
        "scanner": "allowlisted",
        "authority_granted": "allowlisted",
        "content_ref": "allowlisted",
        "detail": "metadata_only",
        "assessed_at": "allowlisted",
        "run_id": "allowlisted",
        "session_id": "allowlisted",
        "project": "allowlisted",
    },
    "agent.run_completed": {
        "schema_version": "allowlisted",
        "run_id": "allowlisted",
        "job_id": "allowlisted",
        "workflow_id": "allowlisted",
        "session_id": "allowlisted",
        "trigger_event_id": "allowlisted",
        "trigger_delivery_id": "allowlisted",
        "project": "allowlisted",
        "flow": "allowlisted",
        "agent": "allowlisted",
        "risk_class": "allowlisted",
        "status": "allowlisted",
        "terminal_status": "allowlisted",
        "summary": "allowlisted",
        "artifact_root": "allowlisted",
        "command_kind": "allowlisted",
        "repo_full_name": "allowlisted",
        "issue_id": "allowlisted",
        "pr_id": "allowlisted",
        "branch": "allowlisted",
        "commit_sha": "allowlisted",
        "review_result": "metadata_only",
        "plan_result": "metadata_only",
        "fix_result": "metadata_only",
        "patch_path": "allowlisted",
        "context_sources": "allowlisted",
        "prompt_hash_source": "allowlisted",
        "summary_hash": "allowlisted",
        "engine": "allowlisted",
        "model_policy": "allowlisted",
        "risk_tags": "allowlisted",
        "risk_tag_sources": "metadata_only",
        "policy_decision": "allowlisted",
        "approval_target_id": "allowlisted",
        "plan_alias": "allowlisted",
        "plan_hash": "allowlisted",
        "blast_radius_hash": "allowlisted",
        "diff_gate_passed": "allowlisted",
        "diff_gate_violation_codes": "allowlisted",
        "diff_gate_policy_sources": "allowlisted",
        "approval_id": "allowlisted",
        "fix_status": "allowlisted",
        "agent_branch": "allowlisted",
        "head_commit_sha": "allowlisted",
        "opened_pr_number": "allowlisted",
        "opened_pr_url": "allowlisted",
        "approved_base_sha": "allowlisted",
        "publish_state": "allowlisted",
        "producer_protocol": "allowlisted",
        "bundle_id": "allowlisted",
        "attempt_id": "allowlisted",
        "bundle_kind": "allowlisted",
        "worker_result": "allowlisted",
    },
    # --- CT102 CI channel (V9 T08, agent_shared.models.ci) ---
    "agent.fix_ci_observed": _with_ci_common(
        {
            "delivery_id": "allowlisted",
            # "observation" (the raw nested WorkflowObservation blob) is
            # deliberately absent from this table -- default-deny means it
            # is withheld (name-only); ci_channel.flatten_observation_fields
            # already promoted its known-safe scalars to the
            # "observation_*" keys below before classification ran.
            "observation_workflow_id": "allowlisted",
            "observation_path": "allowlisted",
            "observation_display_name": "allowlisted",
            "observation_workflow_run_id": "allowlisted",
            "observation_run_attempt": "allowlisted",
            "observation_status": "allowlisted",
            "observation_conclusion": "allowlisted",
            "observation_head_sha": "allowlisted",
            "observation_pr_number": "allowlisted",
            "observation_api_verification_status": "allowlisted",
            "observation_observed_at": "allowlisted",
        }
    ),
    "agent.fix_ci_verdict_changed": _with_ci_common(
        {
            "previous_verdict": "allowlisted",
            "verdict": "allowlisted",
            "verdict_revision": "allowlisted",
            "reason_codes": "allowlisted",
            "evaluated_at": "allowlisted",
        }
    ),
    "agent.fix_ci_failure_evidence_collected": _with_ci_common(
        {
            "evidence_observation_id": "allowlisted",
            "workflow_run_id": "allowlisted",
            "workflow_run_attempt": "allowlisted",
            "status": "allowlisted",
            "failure_class": "allowlisted",
            "has_terminal_failed_job": "allowlisted",
        }
    ),
    "agent.fix_ci_failure_evidence_unavailable": _with_ci_common(
        {
            "evidence_observation_id": "allowlisted",
            "workflow_run_id": "allowlisted",
            "workflow_run_attempt": "allowlisted",
            "status": "allowlisted",
            "reason_codes": "allowlisted",
        }
    ),
    "agent.fix_ci_repair_requested": _with_ci_common(
        {
            "evidence_observation_id": "allowlisted",
            "repair_attempt": "allowlisted",
            "repair_key": "allowlisted",
        }
    ),
    "agent.fix_ci_repair_blocked": _with_ci_common(
        {
            "reason_codes": "allowlisted",
            "label": "allowlisted",
        }
    ),
    "agent.fix_ci_repair_started": _with_ci_common(
        {
            "repair_attempt": "allowlisted",
            "repair_key": "allowlisted",
        }
    ),
    "agent.fix_ci_repair_pushed": {
        "schema_version": "allowlisted",
        "fix_run_id": "allowlisted",
        "repository": "allowlisted",
        "previous_head_commit_sha": "allowlisted",
        "new_head_commit_sha": "allowlisted",
        "pr_number": "allowlisted",
        "repair_attempt": "allowlisted",
        "repair_key": "allowlisted",
    },
    "agent.fix_ci_repair_exhausted": _with_ci_common(
        {
            "repair_attempt": "allowlisted",
            "max_attempts": "allowlisted",
        }
    ),
    "agent.fix_ci_repair_stale": _with_ci_common(
        {
            "repair_attempt": "allowlisted",
            "repair_key": "allowlisted",
            "reason": "allowlisted",
            "observed_head_commit_sha": "allowlisted",
        }
    ),
}


def is_known_event_type(event_type: str) -> bool:
    return event_type in _TYPE_FIELD_CLASSIFICATIONS


def classify_field(event_type: str, field_name: str) -> FieldClassification:
    """Classify one payload field. Fails closed on any ambiguity."""
    if is_prohibited_field_name(field_name):
        return "prohibited"
    table = _TYPE_FIELD_CLASSIFICATIONS.get(event_type)
    if table is None:
        return "prohibited"
    return table.get(field_name, "prohibited")


# --- Rendering ---

_MAX_ALLOWLISTED_STR_LEN = 500
_MAX_ALLOWLISTED_LIST_LEN = 50


def _cap_value(value: Any) -> Any:
    """Defensive value cap for allowlisted fields (curated fields should be short)."""
    if isinstance(value, str) and len(value) > _MAX_ALLOWLISTED_STR_LEN:
        return value[:_MAX_ALLOWLISTED_STR_LEN] + "...(truncated)"
    if isinstance(value, list):
        capped = value[:_MAX_ALLOWLISTED_LIST_LEN]
        return [_cap_value(v) for v in capped]
    return value


def _metadata_descriptor(value: Any) -> dict[str, Any]:
    """Structural-only descriptor for metadata_only fields -- never the raw value."""
    if isinstance(value, (list, tuple, set)):
        return {"present": True, "count": len(value)}
    if isinstance(value, dict):
        return {"present": True, "count": len(value)}
    return {"present": True}


def _summary_builder_session(verb: str) -> Callable[[dict[str, Any]], str]:
    def _build(fields: dict[str, Any]) -> str:
        who = fields.get("invoked_by") or fields.get("acting_identity") or "agent"
        command = fields.get("command_kind") or "?"
        return f"Session {verb} ({command}) by {who}"

    return _build


def _summary_terminal(label: str) -> Callable[[dict[str, Any]], str]:
    def _build(fields: dict[str, Any]) -> str:
        code = fields.get("reason_code")
        suffix = f" ({code})" if code else ""
        return f"Session {label}{suffix}"

    return _build


_SUMMARY_BUILDERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "agent.session_started": _summary_builder_session("started"),
    "agent.subject_context_resolved": lambda f: "Subject context resolved",
    "agent.session_finished": _summary_terminal("finished"),
    "agent.session_failed": _summary_terminal("failed"),
    "agent.session_blocked": _summary_terminal("blocked"),
    "agent.session_worker_event": lambda f: f"Worker event: {f.get('worker_event_kind', '?')}",
    "agent.memory_preflight_created": lambda f: "Memory preflight created",
    "agent.memory_preflight_failed": lambda f: "Memory preflight failed",
    "agent.recursive_context_completed": lambda f: "Recursive context completed",
    "agent.recursive_context_failed": lambda f: "Recursive context failed",
    "agent.memory_admitted": lambda f: f"Memory admitted ({f.get('epistemic_status', '?')})",
    "agent.memory_rejected": lambda f: "Memory rejected",
    "agent.context_packet_created": lambda f: "Context packet created",
    "agent.verification_requested": lambda f: f"Verification requested: {f.get('claim', '?')}",
    "agent.verification_passed": lambda f: f"Verification passed: {f.get('claim', '?')}",
    "agent.verification_failed": lambda f: f"Verification failed: {f.get('claim', '?')}",
    "agent.verification_missing": lambda f: f"Verification missing: {f.get('claim', '?')}",
    "agent.control_decision": lambda f: f.get("summary") or f"Control decision: {f.get('kind', 'other')}",
    "agent.injection_assessment": (
        lambda f: f"Injection assessment: risk={f.get('risk', 'none')} action={f.get('recommended_action', 'allow')}"
    ),
    "agent.run_completed": lambda f: f"Run completed: {f.get('status', f.get('terminal_status', '?'))}",
    "agent.fix_ci_observed": (
        lambda f: (
            f"CT102 CI observed: {f.get('observation_status', '?')}"
            f"/{f.get('observation_conclusion', '?')}"
            f" (run {f.get('observation_workflow_run_id', '?')})"
        )
    ),
    "agent.fix_ci_verdict_changed": (
        lambda f: (
            f"CT102 CI verdict: {f.get('previous_verdict', '?')} -> {f.get('verdict', '?')}"
            f" (rev {f.get('verdict_revision', '?')})"
        )
    ),
    "agent.fix_ci_failure_evidence_collected": (
        lambda f: f"CI failure evidence collected: {f.get('failure_class', '?')}"
    ),
    "agent.fix_ci_failure_evidence_unavailable": lambda f: "CI failure evidence unavailable",
    "agent.fix_ci_repair_requested": (
        lambda f: f"CI repair requested (attempt {f.get('repair_attempt', '?')})"
    ),
    "agent.fix_ci_repair_blocked": (
        lambda f: f"CI repair blocked: {f.get('label', 'agent:blocked')}"
    ),
    "agent.fix_ci_repair_started": (
        lambda f: f"CI repair started (attempt {f.get('repair_attempt', '?')})"
    ),
    "agent.fix_ci_repair_pushed": lambda f: "CI repair pushed new commit",
    "agent.fix_ci_repair_exhausted": (
        lambda f: (
            f"CI repair exhausted (attempt {f.get('repair_attempt', '?')}"
            f"/{f.get('max_attempts', '?')})"
        )
    ),
    "agent.fix_ci_repair_stale": lambda f: f"CI repair stale: {f.get('reason', '?')}",
}


def _summary_for(event_type: str, display_fields: dict[str, Any]) -> str:
    builder = _SUMMARY_BUILDERS.get(event_type)
    if builder is None:
        return event_type
    try:
        return builder(display_fields)
    except Exception:
        return event_type


def safe_display_event(event: dict[str, Any]) -> ObserveEventV1:
    """Normalize one raw ledger event dict into a display-safe ``observe_event.v1``.

    ``event`` is expected to carry at least ``type`` and ``payload``; other
    envelope keys (``event_id``, ``sequence``, ``ledger_sequence``,
    ``recorded_at``, ``project``, ``source``) are passed through verbatim --
    they are envelope metadata, not payload content, and were already
    trusted before this event reached the ledger.

    Unknown event types (``type`` not in the classification registry) never
    expose any payload field value -- only field names are retained.
    """
    # V9 T08: agent.fix_ci_observed carries a nested WorkflowObservation;
    # promote its known-safe scalars to top-level "observation_*" keys
    # before classification, which only ever operates on top-level payload
    # keys (see agent_control.observe.ci_channel.flatten_observation_fields).
    # A no-op for every other event type.
    event = flatten_observation_fields(event)
    event_type = str(event.get("type") or "")
    payload = event.get("payload")
    known = is_known_event_type(event_type)

    display_fields: dict[str, Any] = {}
    metadata_only_names: list[str] = []
    redacted_names: list[str] = []
    prohibited_names: list[str] = []

    if isinstance(payload, dict):
        if known:
            for name, value in payload.items():
                classification = classify_field(event_type, name)
                if value is None:
                    if classification == "prohibited":
                        prohibited_names.append(name)
                    continue
                if classification == "allowlisted":
                    display_fields[name] = _cap_value(value)
                elif classification == "metadata_only":
                    display_fields[name] = _metadata_descriptor(value)
                    metadata_only_names.append(name)
                elif classification == "redacted":
                    display_fields[name] = "<redacted>"
                    redacted_names.append(name)
                else:
                    prohibited_names.append(name)
        else:
            # Unknown event type: never expose any payload value, ever.
            prohibited_names = sorted(payload.keys())

    summary = (
        _summary_for(event_type, display_fields)
        if known
        else f"Unrecognized event type: {event_type or 'unknown'}"
    )

    # V9 T08: CT102 Actions deep link, built only from the trusted
    # structured "repository"/"observation_workflow_run_id" fields that
    # already passed allowlisted classification above -- never the
    # webhook's own raw "html_url" (agent_control.observe.ci_channel never
    # even reads that field). Omitted entirely (no key) when either field
    # is absent/unsafe or GITEA_BASE_URL is unset/malformed.
    if event_type == "agent.fix_ci_observed":
        deep_link = build_ci_deep_link(
            repository=display_fields.get("repository"),
            workflow_run_id=display_fields.get("observation_workflow_run_id"),
        )
        if deep_link:
            display_fields["ci_deep_link"] = deep_link

    return ObserveEventV1(
        event_id=event.get("event_id"),
        type=event_type,
        sequence=int(event.get("sequence") or 0),
        ledger_sequence=event.get("ledger_sequence"),
        recorded_at=event.get("recorded_at"),
        project=event.get("project"),
        source=event.get("source"),
        known_type=known,
        category=ci_log_category(event_type),
        summary=summary,
        display_fields=display_fields,
        metadata_only_field_names=metadata_only_names,
        redacted_field_names=redacted_names,
        prohibited_field_names=prohibited_names,
    )


def safe_display_events(events: list[dict[str, Any]]) -> list[ObserveEventV1]:
    return [safe_display_event(ev) for ev in events]
