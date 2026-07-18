"""Approval claim + git plumbing boundary tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agent_control.approval.service import (
    claim_approval_for_publish,
    release_approval_claim,
)
from agent_control.approval.storage import save_approval
from agent_control.publish.remote import RemoteMutationError, validate_push_ref
from agent_shared.git_patch import (
    apply_patch_to_index,
    commit_tree,
    git_run,
    git_write_tree,
    verify_commit_parent_and_tree,
)
from agent_shared.models.approval import WorkItemApproval


def _approval(**kwargs) -> WorkItemApproval:
    base = dict(
        approval_id="a1",
        approval_target_id="tgt-1",
        plan_alias="plan",
        plan_run_id="plan-1",
        plan_hash="ph",
        blast_radius_hash="bh",
        project="ai-sdlc-lab/demo-app",
        issue_id=1,
        allowed_files=["README.md"],
        approved_by_login="owner",
        approved_at="2026-01-01T00:00:00Z",
        expires_at="2099-01-01T00:00:00Z",
        status="reserved",
        reserved_by_fix_run_id="run-1",
        approved_base_sha="abc",
    )
    base.update(kwargs)
    return WorkItemApproval(**base)


def test_claim_and_duplicate_claim(tmp_path: Path) -> None:
    a = _approval()
    save_approval(tmp_path, a)
    c1 = claim_approval_for_publish(tmp_path, a, publish_job_id="job-a")
    assert c1 is not None
    assert c1.status == "claimed"
    c2 = claim_approval_for_publish(tmp_path, a, publish_job_id="job-b")
    assert c2 is None
    # Same job idempotent
    c3 = claim_approval_for_publish(tmp_path, c1, publish_job_id="job-a")
    assert c3 is not None
    released = release_approval_claim(tmp_path, c1)
    assert released.status == "reserved"


def test_push_ref_constrained() -> None:
    assert validate_push_ref("agent/run-1", "main") == "refs/heads/agent/run-1"
    with pytest.raises(RemoteMutationError):
        validate_push_ref("main", "main")
    with pytest.raises(RemoteMutationError):
        validate_push_ref("feature/x", "main")


def test_commit_tree_parent_and_tree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "f.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    parent = git_run(repo, ["git", "rev-parse", "HEAD"]).stdout.strip()

    (repo / "f.txt").write_text("one\ntwo\n", encoding="utf-8")
    # Produce a patch and apply via index
    diff = git_run(repo, ["git", "diff"])
    patch = tmp_path / "p.diff"
    patch.write_text(diff.stdout, encoding="utf-8")
    git_run(repo, ["git", "checkout", "--", "f.txt"])
    apply_patch_to_index(repo, patch)
    tree = git_write_tree(repo)
    commit = commit_tree(repo, tree_sha=tree, parent_sha=parent, message="agent test")
    verify_commit_parent_and_tree(
        repo, commit, expected_parent=parent, expected_tree=tree
    )
