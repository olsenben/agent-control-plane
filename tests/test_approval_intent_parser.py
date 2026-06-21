"""Intent parser tests for Slice 6A approval targets."""

from agent_control.intent_parser import parse_command_intent


def test_approve_plan_alias() -> None:
    intent = parse_command_intent("/agent approve PLAN-run-dc0b71eb")
    assert intent.activated is True
    assert intent.kind == "approve"
    assert intent.approval_target == "PLAN-run-dc0b71eb"


def test_approve_wi_suffix() -> None:
    intent = parse_command_intent("/agent approve WI-0004-dc0b71eb")
    assert intent.kind == "approve"
    assert intent.approval_target == "WI-0004-dc0b71eb"


def test_bare_approve_fails() -> None:
    assert parse_command_intent("/agent approve").activated is False


def test_reject_with_reason() -> None:
    intent = parse_command_intent("/agent reject WI-0004-dc0b71eb reason=needs scope")
    assert intent.kind == "reject"
    assert intent.approval_target == "WI-0004-dc0b71eb"
    assert intent.reject_reason == "needs scope"


def test_fix_wi_target() -> None:
    intent = parse_command_intent("/agent fix WI-0004-dc0b71eb")
    assert intent.kind == "fix"
    assert intent.approval_target == "WI-0004-dc0b71eb"


def test_fix_plan_alias() -> None:
    intent = parse_command_intent("/agent fix PLAN-run-dc0b71eb")
    assert intent.approval_target == "PLAN-run-dc0b71eb"
