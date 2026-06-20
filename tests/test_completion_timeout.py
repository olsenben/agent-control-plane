"""Tests for model completion timeout derived from job limits."""

from agent_workers.rlm.budget import (
    DEFAULT_COMPLETION_TIMEOUT_SECONDS,
    MAX_COMPLETION_TIMEOUT_SECONDS,
    completion_timeout_seconds,
)


def test_completion_timeout_uses_job_budget() -> None:
    job = {"limits": {"time_budget_seconds": 600}}
    assert completion_timeout_seconds(job) == 600.0


def test_completion_timeout_caps_at_max() -> None:
    job = {"limits": {"time_budget_seconds": 1800}}
    assert completion_timeout_seconds(job) == MAX_COMPLETION_TIMEOUT_SECONDS


def test_completion_timeout_default_when_missing() -> None:
    assert completion_timeout_seconds({}) == DEFAULT_COMPLETION_TIMEOUT_SECONDS


def test_completion_timeout_plan_budget() -> None:
    job = {"limits": {"time_budget_seconds": 900}}
    assert completion_timeout_seconds(job) == 900.0
