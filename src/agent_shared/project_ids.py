"""Project and run ID helpers."""

from __future__ import annotations


def split_project(project: str) -> tuple[str, str]:
    owner, repo = project.split("/", 1)
    return owner, repo


def make_run_id(trigger_event_id: str) -> str:
    return f"run-{trigger_event_id}"


def make_rlm_root_job_id(trigger_event_id: str) -> str:
    return f"rlm-root-{trigger_event_id}"


def make_proposed_agent_branch(run_id: str) -> str:
    return f"agent/{run_id}"
