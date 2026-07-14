"""Slice 6E — CT102 CI truth observation and aggregation."""

from agent_control.ci.aggregate import evaluate_aggregate, merge_observation
from agent_control.ci.pending import (
    find_pending_by_repo_sha,
    list_pending_ci,
    register_pending_ci,
    save_pending_ci,
)

__all__ = [
    "evaluate_aggregate",
    "merge_observation",
    "find_pending_by_repo_sha",
    "list_pending_ci",
    "register_pending_ci",
    "save_pending_ci",
]
