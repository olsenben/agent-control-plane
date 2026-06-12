"""RLM job dispatch payload."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agent_shared.constants import RiskClass
from agent_shared.models.intent import CommandIntent


class ReplyTarget(BaseModel):
    kind: str
    id: str


class TriggerContext(BaseModel):
    source: str = "gitea"
    event_type: str
    issue_number: int | None = None
    pr_number: int | None = None
    comment_id: str | None = None
    comment_url: str | None = None
    discussion_id: str | None = None
    author: str | None = None
    author_is_owner: bool = False
    raw_body: str = ""
    normalized_body: str = ""
    reply_mode: str = "same_thread_if_possible"
    reply_target: ReplyTarget | None = None


class ReplyPolicy(BaseModel):
    reply_mode: str = "same_thread_if_possible"
    fallback: str = "issue_comment"
    mention_requester: bool = True
    post_full_logs: bool = False
    post_artifact_paths: bool = True


class JobLimits(BaseModel):
    max_depth: int = 0
    max_child_agents: int = 0
    max_parallel_children: int = 0
    max_iterations: int = 3
    time_budget_seconds: int = 300


class JobSafety(BaseModel):
    activation_required: bool = True
    command_scope: str = "inspect"
    allow_repo_write: bool = False
    allow_test_execution: bool = False
    allow_network: bool = False
    allow_push: bool = False
    allow_merge: bool = False
    sandbox_required: bool = False
    requires_manual_approval: bool = False


class RLMJob(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: str = "rlm_job.v1"
    run_id: str
    job_id: str
    workflow_id: str
    session_id: str
    workflow_definition: str
    flow_config_id: str
    flow_version: str
    flow_config_schema_version: str
    project: str
    owner: str
    repo: str
    repo_url: str
    primary_branch: str = "main"
    policy_ref: str = "main"
    base_ref: str = "main"
    target_sha: str | None = None
    task_ref: str = "main"
    workload_ref: str | None = None
    proposed_agent_branch: str | None = None
    trigger_event_id: str
    trigger_delivery_id: str | None = None
    trigger_type: str
    trigger_context: TriggerContext
    flow: str
    agent: str
    risk_class: RiskClass
    command_intent: CommandIntent
    reporting: ReplyPolicy = Field(default_factory=ReplyPolicy)
    limits: JobLimits = Field(default_factory=JobLimits)
    safety: JobSafety = Field(default_factory=JobSafety)
    model_policy: str = "fake"
    state_path: str | None = None
