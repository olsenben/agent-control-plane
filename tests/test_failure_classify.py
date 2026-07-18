"""Failure classifier prefers pytest signals over a green ruff step in the same log."""

from __future__ import annotations

from agent_control.ci.failure_classify import classify_failure


def test_pytest_failure_not_stolen_by_ruff_step() -> None:
    log = """
+ ruff check .
All checks passed!
+ pytest -q
===== FAILURES =====
_____ test_6f2_intentional_fail _____
AssertionError: stage4 intentional test_failure
1 failed in 0.05s
"""
    assert classify_failure(log, observation_conclusion="failure") == "test_failure"


def test_ruff_failure_still_lint() -> None:
    log = "ruff check . failed\nE501 line too long\nError: Process completed with exit code 1"
    assert classify_failure(log, observation_conclusion="failure") == "lint_failure"
