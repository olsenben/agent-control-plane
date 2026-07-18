"""Legacy CT104 remote publish module — mutation removed (V4.1.1).

Push/PR live in ``agent_control.publish.remote``. Workers must not import mutation
helpers. Staging helpers live in ``agent_shared.git_patch``.
"""

from __future__ import annotations

from pathlib import Path

from agent_shared.git_patch import git_head, git_run, stage_allowed_files

# Compatibility aliases used by ci_repair staging (no push)
_git_run = git_run
_git_head = git_head
_stage_allowed_files = stage_allowed_files


class PublishError(Exception):
    def __init__(self, stage: str, message: str, *, partial=None):
        self.stage = stage
        self.partial = partial
        super().__init__(message)


def publish_fix_branch_and_pr(**_kwargs):
    raise RuntimeError(
        "CT104 remote publish removed (V4.1.1). Use CT103 publish-broker."
    )


def push_repair_fast_forward(**_kwargs):
    raise RuntimeError(
        "CT104 repair push removed (V4.1.1). Use CT103 publish-broker."
    )


def fix_status_for_publish_result(_result) -> str:
    raise RuntimeError("CT104 publish status mapping removed (V4.1.1)")


def verify_workspace_base_equals_approved(repo_root: Path, approved_base_sha: str | None) -> None:
    if not approved_base_sha:
        return
    head = git_head(repo_root)
    if head != approved_base_sha:
        raise PublishError(
            "stale_approval_base",
            f"Workspace HEAD {head} does not equal approved base {approved_base_sha}",
        )
