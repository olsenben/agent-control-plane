"""Tests for shared patch path validation."""

import pytest

from agent_shared.patch_paths import (
    PatchPathError,
    is_protected_patch_path,
    normalize_repo_relative_path,
    validate_allowed_patch_path,
)


def test_normalize_strips_and_posix() -> None:
    assert normalize_repo_relative_path("./src/foo.py") == "src/foo.py"
    assert normalize_repo_relative_path("src\\bar.py") == "src/bar.py"


def test_reject_absolute_and_traversal() -> None:
    with pytest.raises(PatchPathError):
        normalize_repo_relative_path("/etc/passwd")
    with pytest.raises(PatchPathError):
        normalize_repo_relative_path("src/../secret.py")
    with pytest.raises(PatchPathError):
        normalize_repo_relative_path("C:/Windows/foo")


def test_protected_prefixes() -> None:
    assert is_protected_patch_path(".gitea/workflows/ci.yaml")
    assert is_protected_patch_path("docs/adr/001.md")
    assert not is_protected_patch_path("src/agent_control/foo.py")


def test_validate_allowed_files() -> None:
    allowed = ["src/agent_control/dispatch.py"]
    assert validate_allowed_patch_path("src/agent_control/dispatch.py", allowed) == (
        "src/agent_control/dispatch.py"
    )
    with pytest.raises(PatchPathError):
        validate_allowed_patch_path("other.py", allowed)
    with pytest.raises(PatchPathError):
        validate_allowed_patch_path(".agent/foo", allowed)
