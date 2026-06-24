"""Closed-world policy loading and glob matching."""

from pathlib import Path

import yaml

from agent_shared.closed_world.loader import load_closed_world_policy
from agent_shared.closed_world.policy import ClosedWorldPolicy, path_matches_glob


def test_path_matches_glob_starstar() -> None:
    assert path_matches_glob(".gitea/workflows/ci.yaml", ".gitea/workflows/**")
    assert not path_matches_glob("src/foo.py", ".gitea/workflows/**")


def test_path_matches_requirements_glob() -> None:
    assert path_matches_glob("requirements-dev.txt", "requirements*.txt")


def test_load_platform_fallback(tmp_path: Path) -> None:
    policy = load_closed_world_policy(tmp_path)
    assert policy.schema_version == "closed_world_policy.v1"
    assert "platform_default/closed_world.yml" in policy.policy_sources
    assert policy.limits.max_files_changed == 20


def test_load_repo_policy(tmp_path: Path) -> None:
    policies = tmp_path / ".agent" / "policies"
    policies.mkdir(parents=True)
    (policies / "closed_world.yaml").write_text(
        yaml.dump(
            {
                "schema": "closed_world_policy.v1",
                "requires_human_approval": ["custom.lock"],
            }
        ),
        encoding="utf-8",
    )
    policy = load_closed_world_policy(tmp_path)
    assert ".agent/policies/closed_world.yaml" in policy.policy_sources
    assert "custom.lock" in policy.requires_elevated_approval


def test_merge_project_generated_files(tmp_path: Path) -> None:
    agent = tmp_path / ".agent"
    agent.mkdir()
    (agent / "project.yaml").write_text(
        yaml.dump({"state": {"generated_files": [".agent/state/foo.json"]}}),
        encoding="utf-8",
    )
    policy = load_closed_world_policy(tmp_path)
    assert ".agent/state/foo.json" in policy.generated_file_globs
