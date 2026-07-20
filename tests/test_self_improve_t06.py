"""V5 T06 gated self-improvement unit tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from agent_control.self_improve.gate import (
    REASON_IN_PROD,
    REASON_NOT_GATED,
    evaluate_in_prod_self_edit,
    evaluate_proposal_eligibility,
    is_production_deploy_root,
)
from agent_control.self_improve.paths import classify_paths, is_gated_self_improve_path
from agent_control.self_improve.propose import (
    FileProposal,
    propose_self_improve,
)


def test_classify_gated_workflow_and_prompt() -> None:
    c = classify_paths(
        [
            ".gitea/workflows/ci.yaml",
            "src/agent_workers/rlm/prompts.py",
            "src/agent_control/cli.py",
        ]
    )
    assert ".gitea/workflows/ci.yaml" in c["gated"]
    assert "src/agent_workers/rlm/prompts.py" in c["gated"]
    assert "src/agent_control/cli.py" in c["other"]


def test_agent_policy_gated() -> None:
    assert is_gated_self_improve_path(".agent/policies/tools.yaml")
    assert is_gated_self_improve_path(".agent/self_improve/PROPOSALS.md")


def test_in_prod_self_edit_denied() -> None:
    d = evaluate_in_prod_self_edit(
        "/opt/ai-sdlc-lab/agent-control-plane",
        [".gitea/workflows/ci.yaml"],
    )
    assert d.policy_decision == "deny"
    assert d.reason == REASON_IN_PROD
    assert d.in_prod_target is True


def test_non_prod_workspace_allows_local_draft() -> None:
    d = evaluate_in_prod_self_edit(
        "/tmp/scratch-clone",
        [".agent/self_improve/PROPOSALS.md"],
    )
    assert d.policy_decision == "allow"
    assert d.in_prod_target is False


def test_live_marker_file(tmp_path: Path) -> None:
    (tmp_path / ".agent-control-plane-live").write_text("1", encoding="utf-8")
    assert is_production_deploy_root(tmp_path) is True
    d = evaluate_in_prod_self_edit(tmp_path, [".agent/x.yaml"])
    assert d.policy_decision == "deny"


def test_proposal_rejects_non_gated() -> None:
    d = evaluate_proposal_eligibility(["src/agent_control/cli.py"])
    assert d.policy_decision == "deny"
    assert d.reason == REASON_NOT_GATED


def test_proposal_allows_gated_only() -> None:
    d = evaluate_proposal_eligibility(
        [".agent/self_improve/PROPOSALS.md", ".gitea/workflows/ci.yaml"]
    )
    assert d.policy_decision == "allow"


def test_propose_dry_run() -> None:
    result = propose_self_improve(
        project="ai-sdlc-lab/agent-control-plane",
        files=[
            FileProposal(
                path=".agent/self_improve/PROPOSALS.md",
                content="# probe\n",
            )
        ],
        dry_run=True,
        emit_event=False,
    )
    assert result.ok is True
    assert result.dry_run is True
    assert result.branch and result.branch.startswith("agent/self-improve-")


def test_propose_opens_pr_via_api() -> None:
    client = MagicMock()
    client.get_branch_sha.return_value = "abc123base"
    client.create_branch.return_value = {"name": "agent/self-improve-test"}
    client.create_or_update_file.return_value = {
        "commit": {"sha": "deadbeef"},
    }
    client.list_pull_requests.return_value = []
    client.create_pull_request.return_value = {
        "number": 99,
        "html_url": "https://gitea.example/pr/99",
    }

    result = propose_self_improve(
        project="ai-sdlc-lab/agent-control-plane",
        files=[
            FileProposal(
                path=".agent/self_improve/PROPOSALS.md",
                content="# T06\n",
            )
        ],
        branch="agent/self-improve-test",
        dry_run=False,
        emit_event=False,
        client=client,
    )
    assert result.ok is True
    assert result.pr_number == 99
    client.create_branch.assert_called_once()
    client.create_or_update_file.assert_called_once()
    client.create_pull_request.assert_called_once()


def test_propose_rejects_src_path() -> None:
    result = propose_self_improve(
        project="ai-sdlc-lab/agent-control-plane",
        files=[FileProposal(path="README.md", content="x")],
        dry_run=True,
        emit_event=False,
    )
    assert result.ok is False
    assert result.reason == REASON_NOT_GATED
