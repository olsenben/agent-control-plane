"""Policy alias requires_human_approval -> requires_elevated_approval."""

from pathlib import Path

import yaml

from agent_shared.closed_world.loader import load_closed_world_policy


def test_requires_human_approval_alias(tmp_path: Path) -> None:
    policies = tmp_path / ".agent" / "policies"
    policies.mkdir(parents=True)
    (policies / "closed_world.yaml").write_text(
        yaml.dump({"requires_human_approval": ["legacy.toml"]}),
        encoding="utf-8",
    )
    policy = load_closed_world_policy(tmp_path)
    assert "legacy.toml" in policy.requires_elevated_approval
