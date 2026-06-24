"""Closed-world policy model and glob matching."""

from __future__ import annotations

import fnmatch
from pathlib import PurePosixPath

from pydantic import BaseModel, Field


class DiffLimits(BaseModel):
    max_files_changed: int = 20
    max_diff_lines: int = 500


class SecretScanPolicy(BaseModel):
    enabled: bool = True


class TestDeletionPolicy(BaseModel):
    flag_deleted_test_files: bool = True
    flag_assertion_removals: bool = True


class PlanScopePolicy(BaseModel):
    warn_on_drift: bool = True
    fail_on_drift: bool = False


class ClosedWorldPolicy(BaseModel):
    schema_version: str = "closed_world_policy.v1"
    mode: str = "deny_by_default"
    limits: DiffLimits = Field(default_factory=DiffLimits)
    always_denied: list[str] = Field(default_factory=list)
    allowed_by_default: list[str] = Field(default_factory=list)
    requires_elevated_approval: list[str] = Field(default_factory=list)
    lockfile_globs: list[str] = Field(default_factory=list)
    generated_file_globs: list[str] = Field(default_factory=list)
    secret_scan: SecretScanPolicy = Field(default_factory=SecretScanPolicy)
    test_deletion: TestDeletionPolicy = Field(default_factory=TestDeletionPolicy)
    plan_scope: PlanScopePolicy = Field(default_factory=PlanScopePolicy)
    policy_sources: list[str] = Field(default_factory=list)


def normalize_path(path: str) -> str:
    raw = (path or "").strip().replace("\\", "/")
    if raw.startswith("./"):
        raw = raw[2:]
    return PurePosixPath(raw).as_posix()


def path_matches_glob(path: str, pattern: str) -> bool:
    """Match repo-relative path against glob (supports ** suffix patterns)."""
    norm = normalize_path(path)
    pat = pattern.replace("\\", "/")
    if pat.endswith("/**"):
        prefix = pat[:-3].rstrip("/")
        if norm == prefix or norm.startswith(prefix + "/"):
            return True
        return False
    if "**" in pat:
        parts = pat.split("**")
        if len(parts) == 2:
            prefix, suffix = parts[0].rstrip("/"), parts[1].lstrip("/")
            if prefix and not norm.startswith(prefix):
                return False
            if suffix:
                return fnmatch.fnmatch(norm.split("/")[-1], suffix) or fnmatch.fnmatch(norm, suffix)
            return True
    return fnmatch.fnmatch(norm, pat)


def any_glob_match(path: str, patterns: list[str]) -> bool:
    return any(path_matches_glob(path, p) for p in patterns)


def paths_matching_any(changed_files: list[str], patterns: list[str]) -> list[str]:
    return sorted({p for p in changed_files if any_glob_match(p, patterns)})
