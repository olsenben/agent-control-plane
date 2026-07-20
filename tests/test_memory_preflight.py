"""Slice 5.5a — deterministic memory preflight."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from agent_control.memory.preflight import (
    compile_memory_preflight,
    decide_recursive_context,
)
from agent_control.memory.preflight_artifacts import (
    ArtifactConflictError,
    load_preflight_artifact,
    persist_preflight_artifact,
)
from agent_control.queue import EnqueueResult
from agent_control.session import (
    PreflightFatalError,
    begin_typed_session,
    load_session,
    prepare_typed_rlm_dispatch,
)
from agent_control.session.events import append_session_event
from agent_control.workflows.dispatch import maybe_dispatch_rlm_root
from agent_shared.models.intent import CommandIntent
from agent_shared.models.jobs import TriggerContext
from agent_shared.models.memory_preflight import (
    MAX_RELEVANT_PRIOR_RUNS,
    THRESHOLD_PRIOR_MEMORY,
    MemoryPreflight,
)
from agent_shared.models.state import VerificationState
from support.policy_pin import install_fake_policy_pin


def _tc(*, issue: int = 2, author: str = "alice") -> TriggerContext:
    return TriggerContext(
        event_type="gitea.issue_comment",
        issue_number=issue,
        author=author,
        raw_body="/agent review",
        normalized_body="/agent review",
    )


@pytest.fixture
def state_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "agent-state"
    runs = tmp_path / "agent-runs"
    state.mkdir()
    runs.mkdir()
    monkeypatch.setenv("AGENT_STATE_ROOT", str(state))
    monkeypatch.setenv("AGENT_RUNS_DIR", str(runs))
    monkeypatch.setenv("AGENT_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("MODEL_ROUTING_POLICY", "fake")
    install_fake_policy_pin(monkeypatch)
    return state


def test_decide_recursive_context_trivial() -> None:
    required, reasons, skip = decide_recursive_context(
        prior_memory_count=0,
        distinct_prior_root_causes=0,
        missing_graph_edge_count=0,
    )
    assert required is False
    assert reasons == []
    assert skip == "deterministic_preflight_sufficient"


def test_decide_recursive_context_prior_memory_over_budget() -> None:
    required, reasons, skip = decide_recursive_context(
        prior_memory_count=THRESHOLD_PRIOR_MEMORY,
        distinct_prior_root_causes=0,
        missing_graph_edge_count=0,
    )
    assert required is True
    assert "prior_memory_over_budget" in reasons
    assert skip == ""


def test_compile_preflight_bounds_and_trivial(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = begin_typed_session(
        state_env,
        project="ai-sdlc-lab/demo-app",
        command_kind="review",
        run_id="run-pf-trivial",
        head_sha="abc123",
        trigger_context=_tc(),
        policy_source_sha="pol456",
    )
    oversized = [
        {
            "record_id": f"mem-{i}",
            "run_id": f"run-old-{i}",
            "memory_quality": "model_generated",
            "findings": [],
            "uncertain_hypotheses": [],
        }
        for i in range(MAX_RELEVANT_PRIOR_RUNS + 5)
    ]
    monkeypatch.setattr(
        "agent_control.memory.preflight.retrieve_prior_memory_dicts",
        lambda *a, **k: oversized,
    )
    preflight = compile_memory_preflight(
        session=session,
        run_id="run-pf-trivial",
        source_sha="abc123",
        policy_source_sha="pol456",
        trigger_context=_tc(),
    )
    assert preflight.schema_version == "memory_preflight.v1"
    assert preflight.retrieval_mode == "deterministic_only"
    assert preflight.source_sha == "abc123"
    assert preflight.policy_source_sha == "pol456"
    assert len(preflight.relevant_prior_runs) <= MAX_RELEVANT_PRIOR_RUNS
    assert "relevant_prior_runs" in preflight.truncated_sections
    assert preflight.recursive_context_required is True  # over threshold
    assert "prior_memory_over_budget" in preflight.invocation_reasons


def test_degraded_when_graph_fails(state_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = begin_typed_session(
        state_env,
        project="ai-sdlc-lab/demo-app",
        command_kind="review",
        run_id="run-pf-degrade",
        head_sha="sha-d",
        trigger_context=_tc(),
        policy_source_sha="pol-d",
    )

    def _boom(*_a, **_k):
        raise RuntimeError("graph down")

    monkeypatch.setattr("agent_control.memory.preflight.compute_blast_radius", _boom)
    preflight = compile_memory_preflight(
        session=session,
        run_id="run-pf-degrade",
        source_sha="sha-d",
        policy_source_sha="pol-d",
        trigger_context=_tc(),
    )
    assert preflight.status == "degraded"
    assert preflight.component_results.graph == "unavailable"
    assert "graph" in preflight.component_errors


def test_persist_idempotent_and_conflict(state_env: Path) -> None:
    session = begin_typed_session(
        state_env,
        project="ai-sdlc-lab/demo-app",
        command_kind="plan",
        run_id="run-pf-idem",
        head_sha="sha-i",
        trigger_context=_tc(),
        policy_source_sha="pol-i",
    )
    pf = compile_memory_preflight(
        session=session,
        run_id="run-pf-idem",
        source_sha="sha-i",
        policy_source_sha="pol-i",
        trigger_context=_tc(),
    )
    pf = pf.model_copy(update={"created_at": session.created_at})
    stamped, ref, created = persist_preflight_artifact(state_env, pf)
    assert created is True
    assert stamped.artifact_digest
    stamped2, ref2, created2 = persist_preflight_artifact(state_env, pf)
    assert created2 is False
    assert stamped2.artifact_digest == stamped.artifact_digest
    assert ref2.digest == ref.digest

    conflict = pf.model_copy(update={"skip_reason": "different"})
    with pytest.raises(ArtifactConflictError):
        persist_preflight_artifact(state_env, conflict)


def test_prepare_identity_and_worker_continuity(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_control.workflows.dispatch import build_rlm_job

    vs = VerificationState(
        project="ai-sdlc-lab/demo-app",
        command_intent=CommandIntent(
            activated=True,
            activation="/agent",
            kind="review",
            natural_language_task="",
            confidence=1.0,
        ),
        dispatch_recommended=True,
    )
    trigger = {
        "event_id": "pf-ident",
        "delivery_id": "d-pf",
        "type": "gitea.issue_comment",
        "project": "ai-sdlc-lab/demo-app",
        "payload": {
            "comment": {"body": "/agent review", "id": 1, "user": {"login": "alice"}},
            "issue": {"number": 2},
        },
    }
    job = build_rlm_job(vs, trigger)
    assert job is not None
    frozen = "frozen-source-sha-001"
    policy = job.policy_source_sha or "policy-pin-001"
    job = job.model_copy(update={"target_sha": frozen, "policy_source_sha": policy})

    prepared = prepare_typed_rlm_dispatch(state_env, job)
    assert prepared.job.context_pack is not None
    assert "memory_preflight" in prepared.job.context_pack.context_sources
    assert prepared.job.memory_preflight_digest == prepared.preflight.artifact_digest
    assert prepared.job.context_packet_digest == prepared.packet.artifact_digest
    assert prepared.session.head_sha == frozen
    assert prepared.preflight.source_sha == frozen
    assert prepared.packet.source_sha == frozen
    assert prepared.job.context_pack.source_sha == frozen
    assert prepared.job.target_sha == frozen
    assert prepared.preflight.policy_source_sha == policy
    assert prepared.preflight.recursive_context_required is False
    assert prepared.preflight.invocation_reasons == []

    # Idempotent second prepare — no second created event.
    prepared2 = prepare_typed_rlm_dispatch(state_env, job)
    assert prepared2.preflight_created is False
    assert prepared2.packet_created is False
    assert prepared2.preflight.artifact_digest == prepared.preflight.artifact_digest

    from agent_control.events import load_project_events

    events = load_project_events(state_env, "ai-sdlc-lab/demo-app")
    types = [e.get("type") for e in events]
    assert types.count("agent.memory_preflight_created") == 1
    assert types.count("agent.context_packet_created") == 1


def test_moving_branch_keeps_frozen_sha(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_control.workflows.dispatch import build_rlm_job

    vs = VerificationState(
        project="ai-sdlc-lab/demo-app",
        command_intent=CommandIntent(
            activated=True,
            activation="/agent",
            kind="plan",
            natural_language_task="",
            confidence=1.0,
        ),
        dispatch_recommended=True,
    )
    trigger = {
        "event_id": "pf-move",
        "delivery_id": "d-move",
        "type": "gitea.issue_comment",
        "project": "ai-sdlc-lab/demo-app",
        "payload": {
            "comment": {"body": "/agent plan", "id": 2, "user": {"login": "alice"}},
            "issue": {"number": 2},
        },
    }
    job = build_rlm_job(vs, trigger)
    assert job is not None
    frozen = "sha-before-move"
    job = job.model_copy(update={"target_sha": frozen})

    # Simulate branch HEAD moving after resolution — compilers must not re-resolve.
    def _fake_refs(*_a, **_k):
        raise AssertionError("must not re-resolve refs after freeze")

    monkeypatch.setattr("agent_control.project_registry.resolve_refs", _fake_refs)
    prepared = prepare_typed_rlm_dispatch(state_env, job)
    assert prepared.preflight.source_sha == frozen
    assert prepared.job.target_sha == frozen


def test_fatal_persist_no_enqueue(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_control.workflows.dispatch import build_rlm_job

    vs = VerificationState(
        project="ai-sdlc-lab/demo-app",
        command_intent=CommandIntent(
            activated=True,
            activation="/agent",
            kind="review",
            natural_language_task="",
            confidence=1.0,
        ),
        dispatch_recommended=True,
    )
    trigger = {
        "event_id": "pf-fatal",
        "delivery_id": "d-fatal",
        "type": "gitea.issue_comment",
        "project": "ai-sdlc-lab/demo-app",
        "payload": {
            "comment": {"body": "/agent review", "id": 3, "user": {"login": "alice"}},
            "issue": {"number": 2},
        },
    }
    job = build_rlm_job(vs, trigger)
    assert job is not None
    job = job.model_copy(update={"target_sha": "sha-fatal"})

    def _boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(
        "agent_control.session.prepare_dispatch.persist_preflight_artifact",
        _boom,
    )
    enqueued = {"called": False}

    def _enqueue(*_a, **_k):
        enqueued["called"] = True
        return EnqueueResult(outcome="enqueued", job_id="should-not")

    monkeypatch.setattr("agent_control.queue.enqueue_rlm_root", _enqueue)
    result = maybe_dispatch_rlm_root(vs, trigger, "redis://localhost:6379/0")
    # maybe_dispatch rebuilds job — patch prepare instead via fail path
    with pytest.raises(PreflightFatalError):
        prepare_typed_rlm_dispatch(state_env, job)
    assert enqueued["called"] is False or result.get("reason") == "preflight_failed"

    from agent_control.events import load_project_events

    events = load_project_events(state_env, "ai-sdlc-lab/demo-app")
    types = [e.get("type") for e in events]
    assert "agent.memory_preflight_failed" in types
    # Exactly one terminal among failed events for this run
    terminals = [t for t in types if t in ("agent.session_failed", "agent.session_blocked")]
    assert len(terminals) == 1


def test_dispatch_emits_preflight_before_enqueue(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    order: list[str] = []

    def _enqueue(redis_url: str, payload: dict) -> EnqueueResult:
        order.append("enqueue")
        assert payload.get("memory_preflight_digest")
        assert payload.get("context_packet_digest")
        assert payload.get("context_pack") is not None
        assert payload["session_id"].startswith("sess-")
        return EnqueueResult(outcome="enqueued", job_id="rq-pf-1")

    monkeypatch.setattr("agent_control.queue.enqueue_rlm_root", _enqueue)

    orig_created = append_session_event

    def _wrap(state_root, *, event_type: str, **kwargs):
        if event_type in (
            "agent.memory_preflight_created",
            "agent.context_packet_created",
        ):
            order.append(event_type)
        return orig_created(state_root, event_type=event_type, **kwargs)

    monkeypatch.setattr("agent_control.session.events.append_session_event", _wrap)
    # prepare_dispatch imports append helpers that call append_session_event —
    # also patch the imported names used inside prepare_dispatch.
    monkeypatch.setattr(
        "agent_control.session.prepare_dispatch.append_memory_preflight_created",
        lambda *a, **k: order.append("agent.memory_preflight_created") or (Path("."), True),
    )
    monkeypatch.setattr(
        "agent_control.session.prepare_dispatch.append_context_packet_created",
        lambda *a, **k: order.append("agent.context_packet_created") or (Path("."), True),
    )

    vs = VerificationState(
        project="ai-sdlc-lab/demo-app",
        command_intent=CommandIntent(
            activated=True,
            activation="/agent",
            kind="review",
            natural_language_task="",
            confidence=1.0,
        ),
        dispatch_recommended=True,
    )
    trigger = {
        "event_id": "pf-order",
        "delivery_id": "d-order",
        "type": "gitea.issue_comment",
        "project": "ai-sdlc-lab/demo-app",
        "payload": {
            "comment": {"body": "/agent review", "id": 9, "user": {"login": "alice"}},
            "issue": {"number": 2},
        },
    }
    result = maybe_dispatch_rlm_root(vs, trigger, "redis://localhost:6379/0")
    assert result["dispatched"] is True
    assert "agent.memory_preflight_created" in order
    assert "agent.context_packet_created" in order
    assert order.index("agent.memory_preflight_created") < order.index("enqueue")
    assert order.index("agent.context_packet_created") < order.index("enqueue")
    assert result.get("memory_preflight_digest")

    loaded = load_session(state_env, "ai-sdlc-lab/demo-app", result["session_id"])
    assert loaded is not None
    assert loaded.memory_preflight is not None
    disk = load_preflight_artifact(state_env, "ai-sdlc-lab/demo-app", result["session_id"])
    assert disk is not None
    assert disk.recursive_context_required is False


def test_no_2070_client_constructed(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert no recursive-controller / 2070 client is imported during prepare.

    Slice 8c may load recursive_context modules in other tests; clear them first,
    then assert the false/skip prepare path does not re-import them.
    """
    import sys

    for name in list(sys.modules):
        if (
            "recursive_context" in name
            or "rlm_controller" in name
            or "gpu_2070" in name
        ):
            del sys.modules[name]

    from agent_control.workflows.dispatch import build_rlm_job

    vs = VerificationState(
        project="ai-sdlc-lab/demo-app",
        command_intent=CommandIntent(
            activated=True,
            activation="/agent",
            kind="review",
            natural_language_task="",
            confidence=1.0,
        ),
        dispatch_recommended=True,
    )
    trigger = {
        "event_id": "pf-no2070",
        "delivery_id": "d-no",
        "type": "gitea.issue_comment",
        "project": "ai-sdlc-lab/demo-app",
        "payload": {
            "comment": {"body": "/agent review", "id": 4, "user": {"login": "alice"}},
            "issue": {"number": 2},
        },
    }
    job = build_rlm_job(vs, trigger)
    assert job is not None
    prepare_typed_rlm_dispatch(state_env, job)
    banned_after = [
        name
        for name in list(sys.modules)
        if "recursive_context" in name or "rlm_controller" in name or "gpu_2070" in name
    ]
    assert banned_after == []


@pytest.mark.parametrize("kind", ["review", "plan"])
def test_dispatch_contract_review_plan(
    state_env: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    captured: dict = {}

    def _enqueue(redis_url: str, payload: dict) -> EnqueueResult:
        captured["payload"] = payload
        return EnqueueResult(outcome="enqueued", job_id=f"rq-{kind}")

    monkeypatch.setattr("agent_control.queue.enqueue_rlm_root", _enqueue)
    vs = VerificationState(
        project="ai-sdlc-lab/demo-app",
        command_intent=CommandIntent(
            activated=True,
            activation="/agent",
            kind=kind,
            natural_language_task="",
            confidence=1.0,
        ),
        dispatch_recommended=True,
    )
    trigger = {
        "event_id": f"pf-{kind}",
        "delivery_id": f"d-{kind}",
        "type": "gitea.issue_comment",
        "project": "ai-sdlc-lab/demo-app",
        "payload": {
            "comment": {
                "body": f"/agent {kind}",
                "id": 10,
                "user": {"login": "alice"},
            },
            "issue": {"number": 2},
        },
    }
    result = maybe_dispatch_rlm_root(vs, trigger, "redis://localhost:6379/0")
    assert result["dispatched"] is True
    assert captured["payload"]["memory_preflight_digest"]
    pack_sha = captured["payload"]["context_pack"].get("source_sha") or ""
    job_sha = captured["payload"].get("target_sha") or ""
    assert pack_sha == job_sha


def test_fix_path_preflight(state_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fix enqueue goes through prepare_typed_rlm_dispatch."""
    from agent_control.approval.dispatch_fix import enqueue_fix_after_authorization
    from agent_shared.models.approval import WorkItemApproval
    from agent_shared.models.plan import PlanResult
    from agent_shared.models.review import BlastRadiusContext
    from agent_control.approval.plan_lookup import PlanRunRecord
    from datetime import datetime, timezone

    captured: dict = {}

    def _enqueue(redis_url: str, payload: dict) -> EnqueueResult:
        captured["payload"] = payload
        return EnqueueResult(outcome="enqueued", job_id="rq-fix-pf")

    monkeypatch.setattr(
        "agent_control.approval.dispatch_fix.enqueue_rlm_root",
        _enqueue,
    )
    monkeypatch.setattr(
        "agent_control.approval.dispatch_fix.reserve_approval_for_fix",
        lambda *a, **k: a[1],
    )
    monkeypatch.setattr(
        "agent_control.approval.dispatch_fix.append_fix_enqueued",
        lambda *a, **k: (Path("."), True),
    )
    monkeypatch.setattr(
        "agent_control.approval.dispatch_fix.append_approval_reserved",
        lambda *a, **k: (Path("."), True),
    )

    now = datetime.now(timezone.utc).isoformat()
    plan = PlanResult(
        scope_summary="demo",
        steps=[],
        blast_radius=BlastRadiusContext(),
        ci_hints=[],
        confidence="medium",
        risk_tags=[],
    )
    approval = WorkItemApproval(
        approval_id="apr-1",
        approval_target_id="PLAN-run-x",
        plan_alias="PLAN-run-x",
        project="ai-sdlc-lab/demo-app",
        issue_id=2,
        plan_run_id="run-plan-x",
        plan_hash="ph",
        blast_radius_hash="bh",
        allowed_files=["README.md"],
        approved_base_sha="fix-base-sha",
        approved_base_ref="main",
        approved_by_login="alice",
        approved_at=now,
        expires_at=now,
        status="approved",
    )
    plan_record = PlanRunRecord(
        run_id="run-plan-x",
        project="ai-sdlc-lab/demo-app",
        issue_id=2,
        approval_target_id="PLAN-run-x",
        plan_alias="PLAN-run-x",
        plan_result=plan,
        plan_hash="ph",
        blast_radius_hash="bh",
        allowed_files=["README.md"],
    )
    trigger = {
        "event_id": "fix-pf-1",
        "delivery_id": "d-fix",
        "type": "gitea.issue_comment",
        "project": "ai-sdlc-lab/demo-app",
        "payload": {
            "comment": {"body": "/agent fix PLAN-run-x", "id": 11, "user": {"login": "alice"}},
            "issue": {"number": 2},
        },
    }
    # build_fix_rlm_job needs compile_context_pack + resolve — may need light mocks
    with patch(
        "agent_control.approval.dispatch_fix.compile_context_pack"
    ) as mock_pack:
        from agent_shared.models.context_pack import ContextPack

        mock_pack.return_value = ContextPack(
            project="ai-sdlc-lab/demo-app",
            issue_number=2,
            blast_radius=BlastRadiusContext(),
            context_sources=["test"],
        )
        # hash_blast_radius must match approval — use empty blast
        monkeypatch.setattr(
            "agent_control.approval.dispatch_fix.hash_blast_radius",
            lambda _br: "bh",
        )
        out = enqueue_fix_after_authorization(
            state_env,
            trigger_event=trigger,
            approval=approval,
            plan_record=plan_record,
            comment_id=11,
        )
    assert out.get("enqueued") is True
    assert out.get("memory_preflight_digest")
    assert captured["payload"]["memory_preflight_digest"]
    assert captured["payload"]["target_sha"] == "fix-base-sha" or captured["payload"][
        "context_pack"
    ].get("source_sha")


def test_schema_round_trip() -> None:
    pf = MemoryPreflight(
        session_id="sess-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        run_id="run-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        repo="ai-sdlc-lab/demo-app",
        source_sha="abc",
        created_at="2026-07-20T00:00:00+00:00",
    )
    raw = pf.model_dump(mode="json")
    again = MemoryPreflight.model_validate(raw)
    assert again.session_id == pf.session_id
    assert again.retrieval_mode == "deterministic_only"
