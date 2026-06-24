"""Apply fix to workspace tests."""

import subprocess
from pathlib import Path

import pytest

from agent_shared.models.fix import FixFileChange, FixResult
from agent_workers.patch.apply import ApplyFixError, apply_fix_to_workspace


def _init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=path, check=True, capture_output=True)


def _commit_all(path: Path, message: str = "baseline") -> None:
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message, "--allow-empty"], cwd=path, check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / "src").mkdir()
    (repo / "src" / "allowed.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "src" / "other.py").write_text("y = 2\n", encoding="utf-8")
    _commit_all(repo)
    return repo


def test_apply_success_writes_patch(git_repo: Path, tmp_path: Path) -> None:
    allowed = ["src/allowed.py"]
    fix = FixResult(
        scope_summary="test",
        files_changed=allowed,
        changes=[
            FixFileChange(
                path="src/allowed.py",
                edit_kind="replace",
                content="x = 42\n",
            )
        ],
    )
    patch = apply_fix_to_workspace(git_repo, fix, allowed, tmp_path)
    assert patch == "raw_patch.diff"
    assert (tmp_path / "raw_patch.diff").exists()
    assert not (tmp_path / "patch.diff").exists()
    assert "42" in (git_repo / "src" / "allowed.py").read_text(encoding="utf-8")


def test_post_apply_diff_subset_fails_on_extra_write(
    git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowed = ["src/allowed.py"]
    fix = FixResult(
        changes=[
            FixFileChange(path="src/allowed.py", edit_kind="replace", content="x = 2\n"),
        ]
    )

    def _fake_diff(_repo: Path) -> list[str]:
        return ["src/allowed.py", "src/other.py"]

    monkeypatch.setattr("agent_workers.patch.apply._git_diff_name_only", _fake_diff)
    with pytest.raises(ApplyFixError) as exc:
        apply_fix_to_workspace(git_repo, fix, allowed, tmp_path)
    assert exc.value.stage == "post_apply_diff_assert"


def test_create_requires_explicit_allowed_file(git_repo: Path, tmp_path: Path) -> None:
    fix = FixResult(
        changes=[
            FixFileChange(path="src/new.py", edit_kind="create", content="new\n"),
        ]
    )
    with pytest.raises(ApplyFixError):
        apply_fix_to_workspace(git_repo, fix, ["src/allowed.py"], tmp_path)


def test_replace_missing_file_fails(git_repo: Path, tmp_path: Path) -> None:
    fix = FixResult(
        changes=[
            FixFileChange(path="src/missing.py", edit_kind="replace", content="nope\n"),
        ]
    )
    with pytest.raises(ApplyFixError):
        apply_fix_to_workspace(git_repo, fix, ["src/missing.py"], tmp_path)
