"""Prepare typed RLM dispatch with mandatory deterministic preflight (Slice 5.5a).

Pipeline (locked):
  frozen SHAs on job → AgentSession → MemoryPreflight (durable) → ContextPack
  → ContextPacket (durable) → complete RLMJob → identity check

Call sites supply a built RLMJob (+ optional changed_files); this module owns
session bind, preflight, pack stamp, packet, and identity validation.
Enqueue remains with the caller so fix/repair can emit their own post-enqueue events.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_control.config import Settings, get_settings
from agent_control.graph.context_pack import compile_context_pack
from agent_control.memory.preflight import compile_memory_preflight
from agent_control.memory.preflight_artifacts import (
    ArtifactConflictError,
    context_pack_digest,
    load_context_packet_artifact,
    load_preflight_artifact,
    persist_context_packet_artifact,
    persist_preflight_artifact,
)
from agent_control.session.events import (
    append_context_packet_created,
    append_memory_preflight_created,
    append_memory_preflight_failed,
)
from agent_control.session.lifecycle import (
    TYPED_SESSION_COMMANDS,
    begin_typed_session,
    bind_session_to_job,
    finalize_enqueue_failure,
)
from agent_control.session.storage import SessionStoreError, persist_session_with_run_index
from agent_shared.models.agent_session import AgentSession
from agent_shared.models.context_pack import ContextPack
from agent_shared.models.jobs import RLMJob
from agent_shared.models.memory_preflight import ContextPacket, MemoryPreflight


class PreflightFatalError(RuntimeError):
    """Identity / schema / durable persist failure — must not enqueue."""


class IdentityInvariantError(PreflightFatalError):
    """Source/policy SHA mismatch across session, preflight, pack, packet, job."""


@dataclass
class PreparedTypedDispatch:
    job: RLMJob
    session: AgentSession
    preflight: MemoryPreflight
    packet: ContextPacket
    preflight_created: bool
    packet_created: bool
    recursive_context_result: object | None = None
    recursive_context_created: bool = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def assert_identity_invariant(
    *,
    session: AgentSession,
    preflight: MemoryPreflight,
    packet: ContextPacket,
    pack: ContextPack | None,
    job: RLMJob,
) -> None:
    source = session.head_sha or ""
    policy = session.policy_source_sha or ""
    checks = {
        "session.head_sha": source,
        "session.policy_source_sha": policy,
        "preflight.source_sha": preflight.source_sha or "",
        "preflight.policy_source_sha": preflight.policy_source_sha or "",
        "packet.source_sha": packet.source_sha or "",
        "packet.policy_source_sha": packet.policy_source_sha or "",
        "job.target_sha": job.target_sha or "",
        "job.policy_source_sha": job.policy_source_sha or "",
    }
    if pack is not None:
        checks["pack.source_sha"] = pack.source_sha or ""
        checks["pack.policy_source_sha"] = pack.policy_source_sha or ""

    if checks["job.target_sha"] != source:
        raise IdentityInvariantError(
            f"job.target_sha {checks['job.target_sha']!r} != session.head_sha {source!r}"
        )
    if checks["job.policy_source_sha"] != policy:
        raise IdentityInvariantError(
            f"job.policy_source_sha {checks['job.policy_source_sha']!r} != "
            f"session.policy_source_sha {policy!r}"
        )
    for key, value in checks.items():
        if key.startswith("job."):
            continue
        if key.endswith("source_sha") and "policy" not in key:
            if value != source:
                raise IdentityInvariantError(
                    f"{key}={value!r} != frozen source_sha={source!r}"
                )
        if key.endswith("policy_source_sha"):
            if value != policy:
                raise IdentityInvariantError(
                    f"{key}={value!r} != frozen policy_source_sha={policy!r}"
                )


def prepare_typed_rlm_dispatch(
    state_root: Path,
    job: RLMJob,
    *,
    settings: Settings | None = None,
    changed_files: list[str] | None = None,
    subject_kind: str | None = None,
    subject_number: int | None = None,
    invoked_by: str | None = None,
    approved_by: str | None = None,
    ensure_context_pack: bool = True,
) -> PreparedTypedDispatch:
    """Session → preflight → pack → packet → identity-checked job.

    Does not enqueue. On fatal failure emits memory_preflight_failed (when
    applicable) and finalizes the session as failed, then raises PreflightFatalError.
    """
    settings = settings or get_settings()
    kind = (job.command_intent.kind if job.command_intent else None) or ""
    if kind not in TYPED_SESSION_COMMANDS:
        raise PreflightFatalError(f"prepare_typed_rlm_dispatch requires typed kind, got {kind!r}")

    # Freeze SHAs from the job — never re-resolve HEAD afterward.
    source_sha = job.target_sha or ""
    policy_sha = job.policy_source_sha or ""

    session = begin_typed_session(
        state_root,
        project=job.project,
        command_kind=kind,  # type: ignore[arg-type]
        run_id=job.run_id,
        head_sha=source_sha,
        trigger_context=job.trigger_context,
        policy_source_sha=policy_sha,
        subject_kind=subject_kind,  # type: ignore[arg-type]
        subject_number=subject_number,
        invoked_by=invoked_by,
        source_delivery_id=job.trigger_delivery_id,
        approved_by=approved_by,
    )
    # Ensure policy_source_sha is recorded even on idempotent session reuse.
    if (session.policy_source_sha or "") != policy_sha and not session.policy_source_sha:
        session = session.model_copy(update={"policy_source_sha": policy_sha, "updated_at": _now()})
        persist_session_with_run_index(state_root, session)

    job = bind_session_to_job(job, session)

    try:
        existing_pf = load_preflight_artifact(state_root, session.project, session.session_id)
        if existing_pf is not None and session.memory_preflight is not None:
            preflight = existing_pf
            pf_ref = session.memory_preflight
            pf_created = False
        else:
            preflight = compile_memory_preflight(
                session=session,
                run_id=job.run_id,
                source_sha=source_sha,
                policy_source_sha=policy_sha,
                trigger_context=job.trigger_context,
                settings=settings,
                changed_files=changed_files,
                issue_text=(job.context_pack.issue_text if job.context_pack else None),
            )
            # Stabilize created_at for digest idempotency across retries.
            preflight = preflight.model_copy(update={"created_at": session.created_at})
            preflight, pf_ref, pf_created = persist_preflight_artifact(state_root, preflight)
            if pf_created:
                append_memory_preflight_created(
                    state_root,
                    session,
                    run_id=job.run_id,
                    digest=pf_ref.digest,
                    status=preflight.status,
                    recursive_context_required=preflight.recursive_context_required,
                    relative_path=pf_ref.relative_path,
                )
    except (ArtifactConflictError, SessionStoreError, OSError, ValueError) as exc:
        _fail_preflight(
            state_root,
            session,
            run_id=job.run_id,
            reason=str(exc),
            reason_code="preflight_persist_failed",
        )
        raise PreflightFatalError(str(exc)) from exc

    # Context pack: reuse existing or compile; stamp frozen SHAs.
    pack = job.context_pack
    if pack is None and ensure_context_pack:
        try:
            pack = compile_context_pack(
                job.project,
                job.trigger_context,
                settings=settings,
                command_kind=kind,
                changed_files=changed_files,
            )
        except Exception as exc:  # noqa: BLE001 — pack failure is fatal for worker continuity
            _fail_preflight(
                state_root,
                session,
                run_id=job.run_id,
                reason=f"context_pack compile failed: {exc}",
                reason_code="context_pack_failed",
            )
            raise PreflightFatalError(f"context_pack compile failed: {exc}") from exc

    if pack is not None:
        sources = list(pack.context_sources)
        if "memory_preflight" not in sources:
            sources.append("memory_preflight")
        pack = pack.model_copy(
            update={
                "source_sha": source_sha,
                "policy_source_sha": policy_sha,
                "context_sources": sources,
            }
        )
        job = job.model_copy(update={"context_pack": pack})

    # V6 T06 — shadow injection scan (never grants authority; never blocks enqueue).
    if pack is not None and (pack.issue_text or "").strip():
        from agent_control.security.injection_events import append_injection_assessment
        from agent_control.security.injection_scanner import assess_text_shadow

        assessment = assess_text_shadow(
            pack.issue_text or "",
            content_ref="context_pack.issue_text",
            project=job.project,
            run_id=job.run_id,
            session_id=session.session_id,
        )
        assessments = list(pack.injection_assessments or [])
        assessments.append(assessment.model_dump(mode="json"))
        pack = pack.model_copy(update={"injection_assessments": assessments})
        job = job.model_copy(update={"context_pack": pack})
        try:
            append_injection_assessment(state_root, assessment)
        except Exception:
            # Shadow scan must not fail dispatch.
            pass

    pack_digest = context_pack_digest(pack) if pack is not None else ""

    try:
        existing_pkt = load_context_packet_artifact(
            state_root, session.project, session.session_id
        )
        if existing_pkt is not None and session.context_packet is not None:
            packet = existing_pkt
            pkt_ref = session.context_packet
            pkt_created = False
        else:
            packet = ContextPacket(
                session_id=session.session_id,
                run_id=job.run_id,
                repo=session.project,
                source_sha=source_sha,
                policy_source_sha=policy_sha,
                created_at=session.created_at,
                preflight_digest=preflight.artifact_digest,
                preflight_relative_path=pf_ref.relative_path,
                context_pack_digest=pack_digest,
                bounded_source_index=list(pack.context_sources) if pack else [],
                truncation_budget=dict(pack.budget) if pack else {},
            )
            packet, pkt_ref, pkt_created = persist_context_packet_artifact(state_root, packet)
            if pkt_created:
                append_context_packet_created(
                    state_root,
                    session,
                    run_id=job.run_id,
                    digest=pkt_ref.digest,
                    preflight_digest=preflight.artifact_digest,
                    context_pack_digest=pack_digest,
                    relative_path=pkt_ref.relative_path,
                )
    except (ArtifactConflictError, SessionStoreError, OSError, ValueError) as exc:
        _fail_preflight(
            state_root,
            session,
            run_id=job.run_id,
            reason=str(exc),
            reason_code="context_packet_persist_failed",
        )
        raise PreflightFatalError(str(exc)) from exc

    session = session.model_copy(
        update={
            "memory_preflight": pf_ref,
            "context_packet": pkt_ref,
            "updated_at": _now(),
        }
    )
    try:
        persist_session_with_run_index(state_root, session)
    except SessionStoreError as exc:
        _fail_preflight(
            state_root,
            session,
            run_id=job.run_id,
            reason=str(exc),
            reason_code="session_ref_persist_failed",
        )
        raise PreflightFatalError(str(exc)) from exc

    # Slice 8c — conditional recursive context (lazy import only when required).
    rc_result = None
    rc_created = False
    if preflight.recursive_context_required:
        from agent_control.recursive_context.artifacts import (
            load_recursive_context_artifact,
            persist_recursive_context_artifact,
        )
        from agent_control.recursive_context.telemetry import controller_telemetry_payload
        from agent_control.recursive_context.worker import run_conditional_recursive_context
        from agent_control.session.events import append_recursive_context_completed

        existing_rc = load_recursive_context_artifact(
            state_root, session.project, session.session_id
        )
        if existing_rc is not None and session.recursive_context is not None:
            rc_result = existing_rc
            rc_ref = session.recursive_context
            rc_created = False
        else:
            try:
                rc_result = run_conditional_recursive_context(
                    preflight=preflight,
                    settings=settings,
                    state_root=state_root,
                    controller_backend=settings.recursive_context_controller_backend or None,
                )
                rc_result, rc_ref, rc_created = persist_recursive_context_artifact(
                    state_root, rc_result
                )
                if rc_created:
                    append_recursive_context_completed(
                        state_root,
                        session,
                        run_id=job.run_id,
                        digest=rc_ref.digest,
                        invoked=rc_result.invoked,
                        skipped=rc_result.skipped,
                        stop_reason=rc_result.stop_reason,
                        relative_path=rc_ref.relative_path,
                        controller_telemetry=controller_telemetry_payload(rc_result),
                    )
                session = session.model_copy(
                    update={"recursive_context": rc_ref, "updated_at": _now()}
                )
                persist_session_with_run_index(state_root, session)
            except Exception as exc:  # noqa: BLE001 — fail-soft; do not block enqueue
                from agent_control.session.events import append_recursive_context_failed

                append_recursive_context_failed(
                    state_root,
                    session,
                    run_id=job.run_id,
                    reason=str(exc),
                )
                rc_result = None
                rc_created = False

    job = job.model_copy(
        update={
            "memory_preflight_digest": preflight.artifact_digest,
            "context_packet_digest": packet.artifact_digest,
            "recursive_context_digest": (
                session.recursive_context.digest if session.recursive_context else None
            ),
        }
    )

    try:
        assert_identity_invariant(
            session=session,
            preflight=preflight,
            packet=packet,
            pack=pack,
            job=job,
        )
    except IdentityInvariantError as exc:
        _fail_preflight(
            state_root,
            session,
            run_id=job.run_id,
            reason=str(exc),
            reason_code="identity_invariant_failed",
        )
        raise

    return PreparedTypedDispatch(
        job=job,
        session=session,
        preflight=preflight,
        packet=packet,
        preflight_created=pf_created,
        packet_created=pkt_created,
        recursive_context_result=rc_result,
        recursive_context_created=rc_created,
    )


def _fail_preflight(
    state_root: Path,
    session: AgentSession,
    *,
    run_id: str,
    reason: str,
    reason_code: str,
) -> None:
    try:
        append_memory_preflight_failed(
            state_root,
            session,
            run_id=run_id,
            reason=reason,
            reason_code=reason_code,
        )
    except Exception:  # noqa: BLE001 — best effort before terminal
        pass
    try:
        finalize_enqueue_failure(
            state_root,
            session,
            run_id=run_id,
            reason=reason,
        )
    except Exception:  # noqa: BLE001
        pass


def attach_preflight_for_non_rlm_session(
    state_root: Path,
    session: AgentSession,
    *,
    run_id: str,
    source_sha: str,
    policy_source_sha: str = "",
    trigger_context: Any,
    settings: Settings | None = None,
) -> tuple[AgentSession, MemoryPreflight]:
    """Repair / non-pack paths: still require durable preflight on the session."""
    settings = settings or get_settings()
    try:
        preflight = compile_memory_preflight(
            session=session,
            run_id=run_id,
            source_sha=source_sha,
            policy_source_sha=policy_source_sha,
            trigger_context=trigger_context,
            settings=settings,
        )
        preflight, pf_ref, created = persist_preflight_artifact(state_root, preflight)
        if created:
            append_memory_preflight_created(
                state_root,
                session,
                run_id=run_id,
                digest=pf_ref.digest,
                status=preflight.status,
                recursive_context_required=preflight.recursive_context_required,
                relative_path=pf_ref.relative_path,
            )
        # Minimal packet without context_pack (repair worker path).
        packet = ContextPacket(
            session_id=session.session_id,
            run_id=run_id,
            repo=session.project,
            source_sha=source_sha,
            policy_source_sha=policy_source_sha,
            created_at=_now(),
            preflight_digest=preflight.artifact_digest,
            preflight_relative_path=pf_ref.relative_path,
            context_pack_digest="",
            bounded_source_index=["memory_preflight"],
        )
        packet, pkt_ref, pkt_created = persist_context_packet_artifact(state_root, packet)
        if pkt_created:
            append_context_packet_created(
                state_root,
                session,
                run_id=run_id,
                digest=pkt_ref.digest,
                preflight_digest=preflight.artifact_digest,
                context_pack_digest="",
                relative_path=pkt_ref.relative_path,
            )
        session = session.model_copy(
            update={
                "memory_preflight": pf_ref,
                "context_packet": pkt_ref,
                "policy_source_sha": policy_source_sha or session.policy_source_sha,
                "updated_at": _now(),
            }
        )
        persist_session_with_run_index(state_root, session)
        return session, preflight
    except (ArtifactConflictError, SessionStoreError, OSError, ValueError) as exc:
        _fail_preflight(
            state_root,
            session,
            run_id=run_id,
            reason=str(exc),
            reason_code="preflight_persist_failed",
        )
        raise PreflightFatalError(str(exc)) from exc
