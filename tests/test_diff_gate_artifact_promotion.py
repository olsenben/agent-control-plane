"""raw_patch.diff vs patch.diff promotion."""

import json
import subprocess
from pathlib import Path

import pytest

from agent_shared.models.fix import FixFileChange, FixResult
from agent_workers.gates.runner import DiffGateError, run_closed_world_diff_gate
from agent_workers.patch.apply import apply_fix_to_workspace


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True, capture_output=True)
    (path / "src").mkdir()
    (path / "src" / "allowed.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


def _job(allowed: list[str], blast_hash: str) -> dict:
    return {
        "fix_authorization": {
            "allowed_files": allowed,
            "ci_hints": ["pytest -q"],
            "blast_radius_hash": blast_hash,
            "plan_steps": [{"id": "S1", "files": allowed}],
        },
        "context_pack": {"blast_radius": {"affected_services": ["svc"]}},
    }


def test_gate_pass_promotes_patch(tmp_path: Path) -> None:
    from agent_shared.hash_utils import hash_blast_radius
    from agent_shared.models.review import BlastRadiusContext

    repo = tmp_path / "repo"
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _init_repo(repo)
    br = BlastRadiusContext(affected_services=["svc"])
    h = hash_blast_radius(br)
    allowed = ["src/allowed.py"]
    fix = FixResult(
        changes=[FixFileChange(path="src/allowed.py", edit_kind="replace", content="x = 2\n")]
    )
    apply_fix_to_workspace(repo, fix, allowed, artifacts)
    assert (artifacts / "raw_patch.diff").is_file()
    assert not (artifacts / "patch.diff").exists()

    result = run_closed_world_diff_gate(
        repo_root=repo,
        policy_workspace=tmp_path,
        artifact_root=artifacts,
        job=_job(allowed, h),
    )
    assert result.passed
    assert (artifacts / "patch.diff").is_file()


def test_gate_fail_no_patch_diff(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _init_repo(repo)
    allowed = ["src/allowed.py"]
    fix = FixResult(
        changes=[
            FixFileChange(
                path="src/allowed.py",
                edit_kind="replace",
                content="x = 2\nAWS_SECRET_ACCESS_KEY=leaked\n",
            )
        ]
    )
    apply_fix_to_workspace(repo, fix, allowed, artifacts)
    with pytest.raises(DiffGateError):
        run_closed_world_diff_gate(
            repo_root=repo,
            policy_workspace=tmp_path,
            artifact_root=artifacts,
            job=_job(allowed, "wrong-hash"),
        )
    assert (artifacts / "raw_patch.diff").is_file()
    assert not (artifacts / "patch.diff").exists()
    assert (artifacts / "diff_gate_result.json").is_file()
    gate = json.loads((artifacts / "diff_gate_result.json").read_text(encoding="utf-8"))
    assert gate["passed"] is False
