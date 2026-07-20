"""Slice T04 — adequacy profiles + scoped verification claims."""

from __future__ import annotations

from pathlib import Path

from agent_control.ci.comments import format_ci_status_comment
from agent_control.session.adequacy import (
    clear_profile_cache,
    evaluate_adequacy,
    profile_for_command,
)
from agent_control.session.verification import (
    apply_ci_verdict_to_session,
    emit_ingest_verification_missing,
    load_verification_claim,
    request_session_verification,
)
from agent_control.session import begin_typed_session
from agent_shared.models.ci import CiVerificationResult, RequiredWorkflow
from agent_shared.models.jobs import TriggerContext


def test_risk1_profile_missing_not_fixed_verified() -> None:
    clear_profile_cache()
    profile = profile_for_command("review")
    assert profile.profile_id == "risk1_hypothesis"
    ev = evaluate_adequacy(profile, verification_status="missing")
    assert ev.fixed_verified is False
    assert ev.outcome_label == "verification_missing"
    assert ev.status == "not_applicable"


def test_risk2_ci_passed_without_agent_tests_is_ci_regression_not_fixed() -> None:
    clear_profile_cache()
    profile = profile_for_command("fix")
    assert profile.profile_id == "risk2_fix_ci"
    ev = evaluate_adequacy(profile, verification_status="passed", agent_tests_exercised=None)
    assert ev.fixed_verified is False
    assert ev.outcome_label == "ci_regression_passed"
    assert ev.status == "incomplete"
    assert any("Agent-authored" in x or "agent-authored" in x.lower() for x in ev.limitations)


def test_risk2_ci_passed_with_exercised_agent_tests_can_be_fixed_verified() -> None:
    clear_profile_cache()
    profile = profile_for_command("fix")
    ev = evaluate_adequacy(
        profile,
        verification_status="passed",
        agent_test_paths=["tests/test_foo.py"],
        agent_tests_exercised=True,
    )
    assert ev.fixed_verified is True
    assert ev.outcome_label == "fixed_verified"
    assert ev.status == "passed"


def test_review_claim_stamps_adequacy(tmp_path: Path) -> None:
    clear_profile_cache()
    state = tmp_path / "agent-state"
    state.mkdir()
    s = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="review",
        run_id="run-adq-rev",
        head_sha="abc123",
        trigger_context=TriggerContext(
            event_type="gitea.issue_comment",
            issue_number=2,
            author="alice",
            raw_body="/agent review",
            normalized_body="/agent review",
        ),
    )
    emit_ingest_verification_missing(state, s, run_id="run-adq-rev")
    claim = load_verification_claim(state, "ai-sdlc-lab/demo-app", s.session_id)
    assert claim is not None
    assert claim.status == "missing"
    assert claim.adequacy_profile_id == "risk1_hypothesis"
    assert claim.adequacy_outcome == "verification_missing"
    assert claim.fixed_verified is False
    assert "hypotheses" in claim.limitations.lower() or "Hypothesis" in claim.limitations


def test_ci_verified_claim_stamps_scoped_adequacy(tmp_path: Path) -> None:
    clear_profile_cache()
    state = tmp_path / "agent-state"
    state.mkdir()
    s = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="fix",
        run_id="run-adq-fix",
        head_sha="src",
        trigger_context=TriggerContext(
            event_type="gitea.issue_comment",
            issue_number=2,
            author="alice",
            raw_body="/agent fix",
            normalized_body="/agent fix",
        ),
    )
    sha = "bb" * 20
    request_session_verification(
        state, project="ai-sdlc-lab/demo-app", run_id="run-adq-fix", commit_sha=sha
    )
    apply_ci_verdict_to_session(
        state,
        project="ai-sdlc-lab/demo-app",
        fix_run_id="run-adq-fix",
        verdict="verified",
        previous_verdict="pending",
        expected_head_commit_sha=sha,
        verdict_revision=1,
    )
    claim = load_verification_claim(state, "ai-sdlc-lab/demo-app", s.session_id)
    assert claim is not None
    assert claim.status == "passed"
    assert claim.adequacy_profile_id == "risk2_fix_ci"
    assert claim.adequacy_outcome == "ci_regression_passed"
    assert claim.fixed_verified is False
    assert "ci_regression_passed" in claim.claim or "incomplete" in claim.claim


def test_ci_comment_includes_adequacy_fields() -> None:
    clear_profile_cache()
    result = CiVerificationResult(
        repository="ai-sdlc-lab/demo-app",
        fix_run_id="run-x",
        expected_head_commit_sha="aa" * 20,
        verdict="verified",
        verdict_revision=1,
        required_workflows=[
            RequiredWorkflow(path=".gitea/workflows/ci.yaml", display_name="ci")
        ],
        issue_id=2,
    )
    body = format_ci_status_comment(result)
    assert "adequacy_profile: risk2_fix_ci" in body
    assert "adequacy_outcome: ci_regression_passed" in body
    assert "fixed_verified: false" in body
