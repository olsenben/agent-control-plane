from agent_control.context_builder import build_context_capsule
from agent_control.state_reducer import LogicalState


def test_build_context_capsule() -> None:
    state = LogicalState(project="ai-sdlc-lab/demo-app", head_sha="abc")
    capsule = build_context_capsule(state)
    assert capsule["project"] == "ai-sdlc-lab/demo-app"
    assert capsule["context_overflow"] is False
