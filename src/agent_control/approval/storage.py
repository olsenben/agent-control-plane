"""Approval file storage on agent-state."""

from __future__ import annotations

import json
import os
from pathlib import Path

from agent_control.project_identity import approval_file_path, canonical_project
from agent_shared.models.approval import WorkItemApproval


def load_approval(state_root: Path, project: str, approval_target_id: str) -> WorkItemApproval | None:
    path = approval_file_path(state_root, project, approval_target_id)
    if not path.is_file():
        return None
    return WorkItemApproval.model_validate(json.loads(path.read_text(encoding="utf-8")))


def save_approval(state_root: Path, approval: WorkItemApproval) -> Path:
    project = canonical_project(approval.project)
    path = approval_file_path(state_root, project, approval.approval_target_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = approval.model_dump_json(indent=2)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)
    return path


def list_approvals(state_root: Path, project: str, *, issue_id: int | None = None) -> list[WorkItemApproval]:
    from agent_control.project_identity import approvals_dir

    root = approvals_dir(state_root, project)
    if not root.is_dir():
        return []
    items: list[WorkItemApproval] = []
    for path in sorted(root.glob("*.json")):
        if path.name.endswith(".tmp"):
            continue
        approval = WorkItemApproval.model_validate(json.loads(path.read_text(encoding="utf-8")))
        if issue_id is None or approval.issue_id == issue_id:
            items.append(approval)
    return items
