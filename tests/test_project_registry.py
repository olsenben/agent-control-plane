from pathlib import Path

import yaml

from agent_control.project_registry import resolve_project


def test_resolve_project_org_default(tmp_path: Path) -> None:
    registry = tmp_path / "projects.yaml"
    registry.write_text(
        yaml.safe_dump(
            {
                "platform": {
                    "repo_url_base": "http://192.168.4.60:3000",
                    "allowed_owners": ["ai-sdlc-lab"],
                    "bootstrap_default_policy": True,
                },
                "projects": {},
            }
        ),
        encoding="utf-8",
    )
    cfg = resolve_project("ai-sdlc-lab/new-service", registry_path=registry)
    assert cfg.bootstrap_default_policy is True
    assert cfg.repo_url == "http://192.168.4.60:3000/ai-sdlc-lab/new-service.git"


def test_resolve_project_outside_org_not_bootstrapped(tmp_path: Path) -> None:
    registry = tmp_path / "projects.yaml"
    registry.write_text(
        yaml.safe_dump(
            {
                "platform": {
                    "allowed_owners": ["ai-sdlc-lab"],
                    "bootstrap_default_policy": True,
                },
                "projects": {},
            }
        ),
        encoding="utf-8",
    )
    cfg = resolve_project("other-org/repo", registry_path=registry)
    assert cfg.bootstrap_default_policy is False
