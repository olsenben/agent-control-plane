"""verification_profile.v1 supplies required_workflows for demo-app."""

from __future__ import annotations

from pathlib import Path

from agent_control.ci.aggregate import merge_observation
from agent_control.ci.pending import register_pending_ci
from agent_control.transaction.evidence.profile import (
    profile_for_repository,
    required_workflows_for_repository,
)
from agent_shared.models.ci import CiVerificationResult, RequiredWorkflow, WorkflowObservation
from agent_shared.models.verification_profile import VerificationProfile


def test_demo_app_profile_has_ci_workflow() -> None:
    profile = profile_for_repository("ai-sdlc-lab/demo-app")
    assert profile is not None
    assert profile.profile_id == "demo-app"
    assert profile.required_workflows
    wf = profile.required_workflows[0]
    assert wf.workflow_id == "ci"
    assert wf.path == ".gitea/workflows/ci.yaml"
    Validation = VerificationProfile.model_validate(profile.model_dump(mode="json"))
    assert Validation.required_workflows[0].workflow_id == "ci"


def test_w5_live_evidence_fixture_profile_has_ci_workflow() -> None:
    profile = profile_for_repository("ai-sdlc-lab/w5-live-evidence-fixture")
    assert profile is not None
    assert profile.profile_id == "w5-live-evidence-fixture"
    wf = profile.required_workflows[0]
    assert wf.workflow_id == "ci"
    assert wf.path == ".gitea/workflows/ci.yaml"
    assert wf.source == "verification_profile"
    demo = profile_for_repository("ai-sdlc-lab/demo-app")
    assert demo is not None
    assert demo.profile_id == "demo-app"


def test_register_pending_ci_fills_demo_app_required_workflows(tmp_path: Path) -> None:
    record = register_pending_ci(
        tmp_path,
        fix_run_id="run-demo",
        repository="ai-sdlc-lab/demo-app",
        expected_head_commit_sha="abc1234000000000000000000000000000000000",
    )
    assert record.required_workflows
    assert record.required_workflows[0].workflow_id == "ci"
    assert record.required_workflows[0].path == ".gitea/workflows/ci.yaml"
    assert record.required_workflows[0].source == "verification_profile"


def test_unknown_repo_keeps_empty_matrix_fail_closed(tmp_path: Path) -> None:
    record = register_pending_ci(
        tmp_path,
        fix_run_id="run-other",
        repository="ai-sdlc-lab/agent-control-plane",
        expected_head_commit_sha="abc1234000000000000000000000000000000000",
    )
    assert record.required_workflows == []
    assert required_workflows_for_repository("ai-sdlc-lab/agent-control-plane") == []


def test_profile_does_not_weaken_exact_sha() -> None:
    result = CiVerificationResult(
        fix_run_id="run-1",
        repository="ai-sdlc-lab/demo-app",
        expected_head_commit_sha="sha-expected",
        required_workflows=[
            RequiredWorkflow(
                workflow_id="ci",
                path=".gitea/workflows/ci.yaml",
                display_name="ci",
                source="verification_profile",
            )
        ],
    )
    result = merge_observation(
        result,
        WorkflowObservation(
            path=".gitea/workflows/ci.yaml",
            display_name="ci",
            workflow_run_id="99",
            status="completed",
            conclusion="success",
            head_sha="sha-other",
            observed_at="2026-08-24T00:00:00Z",
        ),
    )
    assert result.verdict != "verified"
    assert result.verdict == "pending"
