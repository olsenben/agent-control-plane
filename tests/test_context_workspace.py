"""W1-F exact-SHA production workspace materializer tests."""

from __future__ import annotations

import inspect
import subprocess
from pathlib import Path

import pytest

from agent_control.context.workspace import (
    ExactShaWorkspaceError,
    materialize_exact_sha_workspace,
)


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
    )


def _file_url(path: Path) -> str:
    return path.resolve().as_uri()


def _init_two_commits(path: Path) -> tuple[str, str]:
    path.mkdir(parents=True)
    init = subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=path,
        capture_output=True,
        text=True,
        check=False,
    )
    if init.returncode != 0:
        subprocess.run(["git", "init"], cwd=path, capture_output=True, text=True, check=True)
        _git(path, "checkout", "-b", "main")
    _git(path, "config", "user.name", "t")
    _git(path, "config", "user.email", "t@t")
    (path / "README.md").write_text("one\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "first")
    sha1 = _git(path, "rev-parse", "HEAD").stdout.strip()
    (path / "two.txt").write_text("two\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "second")
    sha2 = _git(path, "rev-parse", "HEAD").stdout.strip()
    return sha1, sha2


def test_materialize_head_equals_requested_sha_not_branch_tip(tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    sha1, sha2 = _init_two_commits(origin)
    dest = tmp_path / "evidence"
    result = materialize_exact_sha_workspace(
        repo_url=_file_url(origin),
        target_sha=sha1,
        dest=dest,
    )
    assert result == dest
    head = _git(dest, "rev-parse", "HEAD").stdout.strip()
    assert head == sha1
    assert head != sha2
    symbolic = _git(dest, "symbolic-ref", "-q", "HEAD", check=False)
    assert symbolic.returncode != 0


def test_origin_main_advance_does_not_move_detached_head(tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    sha1, _sha2 = _init_two_commits(origin)
    dest = tmp_path / "evidence"
    materialize_exact_sha_workspace(
        repo_url=_file_url(origin),
        target_sha=sha1,
        dest=dest,
    )
    (origin / "three.txt").write_text("three\n", encoding="utf-8")
    _git(origin, "add", ".")
    _git(origin, "commit", "-m", "third")
    tip = _git(origin, "rev-parse", "HEAD").stdout.strip()
    assert tip != sha1
    _git(dest, "fetch", "origin", check=False)
    still = _git(dest, "rev-parse", "HEAD").stdout.strip()
    assert still == sha1
    symbolic = _git(dest, "symbolic-ref", "-q", "HEAD", check=False)
    assert symbolic.returncode != 0


def test_unfetchable_sha_fails_closed(tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    _init_two_commits(origin)
    dest = tmp_path / "evidence"
    missing = "ab" * 20
    with pytest.raises(ExactShaWorkspaceError):
        materialize_exact_sha_workspace(
            repo_url=_file_url(origin),
            target_sha=missing,
            dest=dest,
        )
    assert not dest.exists()


def test_missing_sha_fails_closed_without_checkout(tmp_path: Path) -> None:
    dest = tmp_path / "evidence"
    with pytest.raises(ExactShaWorkspaceError, match="target_sha missing"):
        materialize_exact_sha_workspace(
            repo_url="file:///unused",
            target_sha="   ",
            dest=dest,
        )
    assert not dest.exists()


def test_providers_are_not_given_a_git_checkout_api() -> None:
    import agent_control.context.workspace as ws

    assert list(ws.__all__) == ["ExactShaWorkspaceError", "materialize_exact_sha_workspace"]
    public = [name for name in ws.__all__ if not name.endswith("Error")]
    for name in public:
        lowered = name.lower()
        assert "checkout" not in lowered
        assert "clone" not in lowered
        assert "fetch" not in lowered


def test_materializer_source_stays_decoupled() -> None:
    import agent_control.context.workspace as ws

    source = inspect.getsource(ws)
    assert "maintenance_evals" not in source
    assert "_sync_cached_repo" not in source
    assert "ValidationError" not in source
    assert "RepoSnapshot" not in source
    assert "from agent_control.publish" not in source
    assert "import agent_control.publish" not in source
