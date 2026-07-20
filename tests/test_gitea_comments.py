"""Gitea comment formatter tests (Slice 6D.1 + T10)."""

import ast
from pathlib import Path

from agent_control.gitea_comments import format_fix_started
from agent_control.invocation_ack import DEFAULT_ACTING_IDENTITY


def test_format_fix_started_broker_when_remote_publish_enabled() -> None:
    body = format_fix_started(
        run_id="run-abc",
        approval_target_id="WI-0001",
        allowed_files=["README.md"],
        remote_publish_enabled=True,
    )
    assert "V4.1.1 / 6D.2" in body
    assert "publish-broker" in body
    assert "agent/run-abc" in body
    assert "open PR" in body
    assert f"acting_identity: `{DEFAULT_ACTING_IDENTITY}`" in body
    assert "run_id: `run-abc`" in body


def test_format_fix_started_local_when_remote_publish_disabled() -> None:
    body = format_fix_started(
        run_id="run-abc",
        approval_target_id="WI-0001",
        allowed_files=["README.md"],
        remote_publish_enabled=False,
    )
    assert "workspace-local" in body.lower()
    assert "no remote publish" in body.lower()
    assert f"acting_identity: `{DEFAULT_ACTING_IDENTITY}`" in body


def test_gitea_comments_does_not_import_dispatch_fix() -> None:
    path = Path(__file__).resolve().parents[1] / "src" / "agent_control" / "gitea_comments.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    assert "agent_control.approval.dispatch_fix" not in imports
    assert "agent_control.workflows.dispatch_fix" not in imports
