"""Bootstrap, system context, capabilities, and redaction artifacts."""

from __future__ import annotations


from pydantic import BaseModel, Field


class BootstrapInfo(BaseModel):
    schema_version: str = "bootstrap.v1"
    run_id: str
    worker: str
    queue: str
    image: str = "agent-control-plane:local"
    git_sha: str | None = None
    python_version: str | None = None
    repo_url: str
    checkout_ref: str
    policy_ref: str
    artifact_root: str
    warnings: list[str] = Field(default_factory=list)


class SystemContext(BaseModel):
    schema_version: str = "system_context.v1"
    run_id: str
    os: str = "linux"
    worker: str
    workspace: str
    containerized: bool = True
    shell: str = "disabled_or_restricted"
    available_tools: list[str] = Field(default_factory=list)
    flow: str
    agent: str
    preamble_version: str = "untrusted-data.v1"


class Capabilities(BaseModel):
    schema_version: str = "capabilities.v1"
    run_id: str
    repo_clone: bool = False
    ripgrep: bool = False
    sandbox: bool = False
    model_endpoint: str = "not_required_fake_engine"
    gitea_comment: bool = False
    context_index: bool = False
    compiled_context: bool = False
    network: bool = False
    warnings: list[str] = Field(default_factory=list)


class RedactionEntry(BaseModel):
    target: str
    event: str | None = None
    request_id: str | None = None
    rule: str
    count: int = 1


class RedactionReport(BaseModel):
    schema_version: str = "redaction_report.v1"
    run_id: str
    rules_loaded: int = 0
    events_scanned: int = 0
    redactions: list[RedactionEntry] = Field(default_factory=list)
