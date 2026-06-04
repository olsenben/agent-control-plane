from pathlib import Path

from agent_control.repo_snapshot import snapshot_repo


def test_snapshot_stub(tmp_path: Path) -> None:
    result = snapshot_repo("ai-sdlc-lab", "demo-app", "main", tmp_path)
    assert result["owner"] == "ai-sdlc-lab"
    assert result["status"] == "stub"
