"""Tests for OfficialRLMEngine plan kind validation."""

import pytest

from agent_workers.rlm.official_engine import _validate_kind_and_risk


def test_validate_plan_kind() -> None:
    _validate_kind_and_risk("plan", "planning_only")


def test_validate_plan_wrong_risk_raises() -> None:
    with pytest.raises(ValueError, match="planning_only"):
        _validate_kind_and_risk("plan", "read_only")
