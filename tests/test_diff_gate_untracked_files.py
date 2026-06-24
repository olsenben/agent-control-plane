"""Untracked files included in diff gate changed_files."""

import json
import subprocess
from pathlib import Path

import pytest

from agent_workers.gates.runner import DiffGateError, collect_changed_files, run_closed_world_diff_gate


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True, capture_output=True)
    (path / "README.md").write_text("# base\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


def test_untracked_file_detected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "secret_new.py").write_text("x = 1\n", encoding="utf-8")
    changed = collect_changed_files(repo)
    assert "secret_new.py" in changed


def test_untracked_outside_allowed_fails_gate(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _init_repo(repo)
    (artifacts / "raw_patch.diff").write_text("", encoding="utf-8")
    (repo / "extra.py").write_text("new\n", encoding="utf-8")

    job = {
        "fix_authorization": {
            "allowed_files": ["README.md"],
            "ci_hints": [],
            "blast_radius_hash": "00",
            "plan_steps": [{"id": "S1", "files": ["README.md"]}],
        },
        "context_pack": {"blast_radius": {"missing_graph_edges": ["not implemented"]}},
    }
    with pytest.raises(DiffGateError):
        run_closed_world_diff_gate(
            repo_root=repo,
            policy_workspace=tmp_path,
            artifact_root=artifacts,
            job=job,
        )
    gate = json.loads((artifacts / "diff_gate_result.json").read_text(encoding="utf-8"))
    codes = [v["code"] for v in gate["violations"]]
    assert "out_of_scope_path" in codes
