from agent_control.config import Settings


def test_allowed_repos_set() -> None:
    s = Settings.model_construct(gitea_allowed_repos="a/b, c/d ")
    assert s.allowed_repos_set() == {"a/b", "c/d"}


def test_external_roles_set() -> None:
    s = Settings.model_construct(model_external_roles="judge, planner ")
    assert s.external_roles_set() == {"judge", "planner"}
