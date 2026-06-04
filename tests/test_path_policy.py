from agent_control.path_policy import is_denied, matches_any


def test_matches_any() -> None:
    assert matches_any("src/foo.py", ["src/**"])
    assert not matches_any("docs/a.md", ["src/**"])


def test_is_denied() -> None:
    assert is_denied(".agent/project.yaml", [".agent/**"])
