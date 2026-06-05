from agent_control.config import Settings


def test_allowed_repos_set() -> None:
    s = Settings.model_construct(gitea_allowed_repos="a/b, c/d ")
    assert s.allowed_repos_set() == {"a/b", "c/d"}


def test_is_repo_allowed_exact() -> None:
    s = Settings.model_construct(gitea_allowed_repos="ai-sdlc-lab/demo-app")
    assert s.is_repo_allowed("ai-sdlc-lab/demo-app")
    assert not s.is_repo_allowed("ai-sdlc-lab/agent-control-plane")


def test_is_repo_allowed_owner_wildcard() -> None:
    s = Settings.model_construct(gitea_allowed_repos="ai-sdlc-lab/*")
    assert s.is_repo_allowed("ai-sdlc-lab/demo-app")
    assert s.is_repo_allowed("ai-sdlc-lab/agent-control-plane")
    assert not s.is_repo_allowed("olsenben/personal-app")


def test_is_repo_allowed_global_wildcard() -> None:
    s = Settings.model_construct(gitea_allowed_repos="*")
    assert s.is_repo_allowed("olsenben/personal-app")


def test_external_roles_set() -> None:
    s = Settings.model_construct(model_external_roles="judge, planner ")
    assert s.external_roles_set() == {"judge", "planner"}
