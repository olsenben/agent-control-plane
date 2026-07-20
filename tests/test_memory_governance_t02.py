"""V5 T02 — memory-as-governance: block fix on repeated_failed_fix."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agent_control.approval.service import evaluate_fix_request, grant_approval
from agent_control.config import Settings
from agent_control.events import load_project_events
from agent_control.memory.governance import (
    EVENT_MEMORY_GOVERNANCE_DENIED,
    RISK_TAG_REPEATED_FAILED_FIX,
    append_memory_governance_denied,
    memory_as_governance_check,
)
from agent_control.memory.store import MemoryStore
from agent_shared.models.memory import (
    MemoryAudit,
    MemoryGovernance,
    MemoryRecord,
    RecommendedNextStep,
)
from conftest import seed_plan_completed


def _iso(offset_seconds: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)).isoformat()


def _failed_fix(
    *,
    run_id: str,
    repo: str,
    issue_id: int,
    failure_class: str,
    files: list[str],
    created_at: str,
    fingerprint: str | None = None,
) -> MemoryRecord:
    owner, name = repo.split("/", 1)
    return MemoryRecord(
        record_id=f"mem-{run_id}",
        run_id=run_id,
        repo_owner=owner,
        repo_name=name,
        repo_full_name=repo,
        issue_id=issue_id,
        source_command="fix",
        source_run_id=run_id,
        confidence="medium",
        memory_quality="structured_result",
        epistemic_status="observed",
        created_at=created_at,
        updated_at=created_at,
        files_touched=files,
        governance=MemoryGovernance(
            risk_tags=[RISK_TAG_REPEATED_FAILED_FIX],
            policy_decision="deny",
            risk_class=2,
        ),
        audit=MemoryAudit(engine="test", ingested_at=created_at),
        recommended_next_step=RecommendedNextStep(
            command="human",
            rationale="failed",
            machine_readable={
                "outcome": "failed",
                "failure_class": failure_class,
                "evidence_fingerprint": fingerprint or f"{run_id}:{failure_class}",
                "files_touched": files,
            },
        ),
    )


def _new_evidence_marker(
    *,
    run_id: str,
    repo: str,
    issue_id: int,
    created_at: str,
) -> MemoryRecord:
    owner, name = repo.split("/", 1)
    return MemoryRecord(
        record_id=f"mem-{run_id}",
        run_id=run_id,
        repo_owner=owner,
        repo_name=name,
        repo_full_name=repo,
        issue_id=issue_id,
        source_command="review",
        source_run_id=run_id,
        confidence="medium",
        memory_quality="structured_result",
        epistemic_status="inferred",
        evidence_refs=["human:new_evidence"],
        created_at=created_at,
        updated_at=created_at,
        governance=MemoryGovernance(risk_class=1),
        audit=MemoryAudit(engine="test", ingested_at=created_at),
        recommended_next_step=RecommendedNextStep(
            command="fix",
            rationale="new evidence admitted",
            machine_readable={"new_evidence": True},
        ),
    )


def test_governance_allow_when_no_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "memory.sqlite"
    settings = Settings(AGENT_STATE_ROOT=tmp_path)
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    store = MemoryStore(db)
    decision = memory_as_governance_check(
        "ai-sdlc-lab/demo-app",
        42,
        file_paths=["src/a.py"],
        settings=settings,
        store=store,
    )
    assert decision.policy_decision == "allow"


def test_governance_deny_repeated_failure_class(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    settings = Settings(AGENT_STATE_ROOT=tmp_path)
    store = MemoryStore(settings.memory_db_path)
    repo = "ai-sdlc-lab/demo-app"
    store.upsert_record(
        _failed_fix(
            run_id="run-fail-1",
            repo=repo,
            issue_id=7,
            failure_class="lint_failure",
            files=["src/a.py"],
            created_at=_iso(-120),
        )
    )
    store.upsert_record(
        _failed_fix(
            run_id="run-fail-2",
            repo=repo,
            issue_id=7,
            failure_class="lint_failure",
            files=["src/a.py"],
            created_at=_iso(-60),
        )
    )
    decision = memory_as_governance_check(
        repo,
        7,
        file_paths=["src/a.py"],
        settings=settings,
        store=store,
    )
    assert decision.policy_decision == "deny"
    assert decision.failure_class == "lint_failure"
    assert decision.attempt_count == 2
    assert RISK_TAG_REPEATED_FAILED_FIX in decision.risk_tags
    assert decision.reason and decision.reason.startswith("memory_governance:")


def test_governance_allow_with_new_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    settings = Settings(AGENT_STATE_ROOT=tmp_path)
    store = MemoryStore(settings.memory_db_path)
    repo = "ai-sdlc-lab/demo-app"
    store.upsert_record(
        _failed_fix(
            run_id="run-fail-1",
            repo=repo,
            issue_id=8,
            failure_class="lint_failure",
            files=["src/a.py"],
            created_at=_iso(-120),
        )
    )
    store.upsert_record(
        _failed_fix(
            run_id="run-fail-2",
            repo=repo,
            issue_id=8,
            failure_class="lint_failure",
            files=["src/a.py"],
            created_at=_iso(-60),
        )
    )
    store.upsert_record(
        _new_evidence_marker(
            run_id="run-evidence",
            repo=repo,
            issue_id=8,
            created_at=_iso(-10),
        )
    )
    decision = memory_as_governance_check(
        repo,
        8,
        file_paths=["src/a.py"],
        settings=settings,
        store=store,
    )
    assert decision.policy_decision == "allow"


def test_governance_audit_event_emitted(tmp_path: Path) -> None:
    from agent_control.memory.governance import GovernanceDecision

    decision = GovernanceDecision(
        policy_decision="deny",
        reason="memory_governance:repeated_failed_fix failure_class=lint_failure attempts=2",
        failure_class="lint_failure",
        attempt_count=2,
        overlapping_files=["src/a.py"],
        risk_tags=[RISK_TAG_REPEATED_FAILED_FIX],
        matched_run_ids=["run-a", "run-b"],
    )
    path, created = append_memory_governance_denied(
        tmp_path,
        project="ai-sdlc-lab/demo-app",
        issue_id=9,
        approval_target_id="WI-0009-abcd1234",
        decision=decision,
        comment_id=99,
    )
    assert created is True
    assert path.exists()
    events = load_project_events(tmp_path, "ai-sdlc-lab/demo-app")
    denied = [e for e in events if e.get("type") == EVENT_MEMORY_GOVERNANCE_DENIED]
    assert len(denied) == 1
    payload = denied[0]["payload"]
    assert payload["policy_decision"] == "deny"
    assert RISK_TAG_REPEATED_FAILED_FIX in payload["risk_tags"]
    _, created2 = append_memory_governance_denied(
        tmp_path,
        project="ai-sdlc-lab/demo-app",
        issue_id=9,
        approval_target_id="WI-0009-abcd1234",
        decision=decision,
        comment_id=99,
    )
    assert created2 is False


def test_evaluate_fix_blocked_by_memory_governance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    store = MemoryStore(tmp_path / "memory" / "memory.sqlite")
    repo = "ai-sdlc-lab/agent-control-plane"
    target = seed_plan_completed(tmp_path)
    approval, _, _ = grant_approval(
        tmp_path,
        project=repo,
        issue_id=4,
        target=target,
        approver_login="ai-sdlc-lab",
        author_is_owner=True,
    )
    assert approval is not None
    files = list(approval.allowed_files) or ["README.md"]
    store.upsert_record(
        _failed_fix(
            run_id="run-fail-1",
            repo=repo,
            issue_id=4,
            failure_class="lint_failure",
            files=files,
            created_at=_iso(-120),
        )
    )
    store.upsert_record(
        _failed_fix(
            run_id="run-fail-2",
            repo=repo,
            issue_id=4,
            failure_class="lint_failure",
            files=files,
            created_at=_iso(-60),
        )
    )
    ev = evaluate_fix_request(
        tmp_path,
        project=repo,
        issue_id=4,
        target=target,
    )
    assert ev.policy_decision == "blocked"
    assert ev.reason and "memory_governance" in ev.reason
    events = load_project_events(tmp_path, repo)
    assert any(e.get("type") == EVENT_MEMORY_GOVERNANCE_DENIED for e in events)
