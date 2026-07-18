"""Tests for demo CI-repair intentional-fail removal heuristic."""

from __future__ import annotations

import subprocess
from pathlib import Path

from agent_workers.ci_repair import _generate_intentional_fail_removal_patch


def _git_init_with_file(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "add", rel], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "seed"],
        cwd=root,
        check=True,
        capture_output=True,
    )


def test_intentional_fail_removal_matches_return_annotation(tmp_path: Path) -> None:
    content = (
        "from demo_app.math_service import multiply\n\n\n"
        "def test_multiply() -> None:\n"
        "    assert multiply(3, 4) == 12\n\n\n"
        "def test_6f2_intentional_fail() -> None:\n"
        '    assert False, "stage4 intentional test_failure for repair_allowed"\n'
    )
    _git_init_with_file(tmp_path, "tests/test_math_service.py", content)
    out = _generate_intentional_fail_removal_patch(
        tmp_path, ["tests/test_math_service.py"]
    )
    assert out is not None
    assert out == tmp_path.parent / "repair_patch.diff"
    diff = out.read_text(encoding="utf-8")
    assert "test_6f2_intentional_fail" in diff
    # Working tree reset after generating diff
    restored = (tmp_path / "tests/test_math_service.py").read_text(encoding="utf-8")
    assert "test_6f2_intentional_fail" in restored
    # Patch file must not live inside the worktree as an untracked path
    assert not (tmp_path / "repair_patch.diff").exists()
