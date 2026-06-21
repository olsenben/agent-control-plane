"""Fix command requires explicit approval target in Slice 6A."""

from agent_control.intent_parser import parse_command_intent


def test_bare_fix_fails() -> None:
    assert parse_command_intent("/agent fix").activated is False


def test_prose_fix_fails() -> None:
    assert parse_command_intent("/agent fix the webhook enqueue gap").activated is False


def test_finding_scoped_fix_fails() -> None:
    assert parse_command_intent("/agent fix F-001").activated is False
