"""Open a Gitea PR for gated self-improvement proposals (CT103 only)."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_control.config import Settings, get_settings
from agent_control.events import AgentEvent, append_event, deterministic_event_id
from agent_control.gitea_client import GiteaClient
from agent_control.project_identity import canonical_project
from agent_control.publish.remote import open_or_find_pr
from agent_control.self_improve.gate import (
    SelfImproveDecision,
    evaluate_proposal_eligibility,
)
from agent_shared.repo_identity import normalize_repo_full_name

EVENT_SELF_IMPROVE_PROPOSED = "agent.self_improve_proposed"
EVENT_SELF_IMPROVE_DENIED = "agent.self_improve_denied"
DEFAULT_PROBE_PATH = ".agent/self_improve/PROPOSALS.md"


@dataclass
class FileProposal:
    path: str
    content: str
    """Full file content after change (not a unified diff)."""


@dataclass
class ProposeResult:
    ok: bool
    reason: str | None = None
    decision: SelfImproveDecision | None = None
    project: str | None = None
    branch: str | None = None
    base: str = "main"
    pr_number: int | None = None
    pr_url: str | None = None
    commit_sha: str | None = None
    paths: list[str] = field(default_factory=list)
    dry_run: bool = False
    reused_pr: bool = False
    risk_tags: list[str] = field(default_factory=lambda: ["self_improve"])


def make_self_improve_branch(proposal_id: str | None = None) -> str:
    pid = (proposal_id or uuid.uuid4().hex[:12]).strip()
    return f"agent/self-improve-{pid}"


def build_probe_content(*, tip_hint: str = "", note: str = "") -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "# Self-improvement proposals",
        "",
        "Agent-authored prompt/workflow/policy changes land here only via PR.",
        "Do not edit this tree on a live deploy root.",
        "",
        f"- smoke_at: {ts}",
    ]
    if tip_hint:
        lines.append(f"- tip_hint: {tip_hint}")
    if note:
        lines.append(f"- note: {note}")
    lines.append("")
    return "\n".join(lines)


def propose_self_improve(
    *,
    project: str,
    files: list[FileProposal],
    title: str | None = None,
    body: str | None = None,
    base: str = "main",
    branch: str | None = None,
    dry_run: bool = False,
    settings: Settings | None = None,
    client: GiteaClient | None = None,
    emit_event: bool = True,
) -> ProposeResult:
    """Create branch + commit gated files via Gitea API and open a PR.

    Never writes into a production deploy checkout — Gitea Contents API only.
    """
    settings = settings or get_settings()
    repo_full = normalize_repo_full_name(project) or canonical_project(project)
    paths = [f.path for f in files]
    decision = evaluate_proposal_eligibility(paths)
    if decision.policy_decision != "allow":
        if emit_event:
            _append_denied(settings.state_root, repo_full, decision, paths)
        return ProposeResult(
            ok=False,
            reason=decision.reason,
            decision=decision,
            project=repo_full,
            paths=paths,
            dry_run=dry_run,
            risk_tags=list(decision.risk_tags),
        )

    owner, repo = repo_full.split("/", 1)
    agent_branch = branch or make_self_improve_branch()
    if not agent_branch.startswith("agent/"):
        return ProposeResult(
            ok=False,
            reason="branch_must_start_with_agent/",
            decision=decision,
            project=repo_full,
            paths=paths,
            dry_run=dry_run,
        )

    pr_title = title or f"self-improve: propose {', '.join(paths[:3])}"
    pr_body = body or (
        "## Gated self-improvement\n\n"
        "Prompt/workflow/agent-policy change proposed as a PR only.\n"
        "Do **not** apply on a live deploy root without merge + CI.\n\n"
        "Paths:\n" + "\n".join(f"- `{p}`" for p in paths)
    )

    if dry_run:
        return ProposeResult(
            ok=True,
            reason="dry_run",
            decision=decision,
            project=repo_full,
            branch=agent_branch,
            base=base,
            paths=paths,
            dry_run=True,
            risk_tags=["self_improve"],
        )

    gitea = client or GiteaClient(settings)
    base_sha = gitea.get_branch_sha(owner, repo, base)
    if not base_sha:
        return ProposeResult(
            ok=False,
            reason="base_sha_missing",
            decision=decision,
            project=repo_full,
            paths=paths,
        )

    gitea.create_branch(owner, repo, new_branch=agent_branch, old_branch=base)

    last_sha: str | None = None
    for fp in files:
        result = gitea.create_or_update_file(
            owner,
            repo,
            path=fp.path,
            content=fp.content,
            message=f"self-improve: {fp.path}",
            branch=agent_branch,
        )
        last_sha = (
            (result.get("commit") or {}).get("sha")
            or (result.get("content") or {}).get("sha")
            or last_sha
        )

    pr_number, pr_url, reused = open_or_find_pr(
        client=gitea,
        owner=owner,
        repo=repo,
        agent_branch=agent_branch,
        base_ref=base,
        title=pr_title,
        body=pr_body,
    )

    out = ProposeResult(
        ok=True,
        reason="proposed",
        decision=decision,
        project=repo_full,
        branch=agent_branch,
        base=base,
        pr_number=pr_number,
        pr_url=pr_url,
        commit_sha=last_sha,
        paths=paths,
        reused_pr=reused,
        risk_tags=["self_improve"],
    )
    if emit_event:
        _append_proposed(settings.state_root, out)
    return out


def propose_probe_pr(
    *,
    project: str,
    note: str = "v5-t06-smoke",
    dry_run: bool = False,
    settings: Settings | None = None,
    client: GiteaClient | None = None,
    emit_event: bool = True,
) -> ProposeResult:
    """Convenience: propose a probe update under `.agent/self_improve/`."""
    content = build_probe_content(note=note)
    return propose_self_improve(
        project=project,
        files=[FileProposal(path=DEFAULT_PROBE_PATH, content=content)],
        title="self-improve: T06 gated proposal probe",
        body=(
            "## V5 T06 smoke\n\n"
            "Probe PR for gated self-improvement. Safe to close after verify.\n"
        ),
        dry_run=dry_run,
        settings=settings,
        client=client,
        emit_event=emit_event,
    )


def result_as_dict(r: ProposeResult) -> dict[str, Any]:
    return {
        "ok": r.ok,
        "reason": r.reason,
        "project": r.project,
        "branch": r.branch,
        "base": r.base,
        "pr_number": r.pr_number,
        "pr_url": r.pr_url,
        "commit_sha": r.commit_sha,
        "paths": list(r.paths),
        "dry_run": r.dry_run,
        "reused_pr": r.reused_pr,
        "risk_tags": list(r.risk_tags),
        "in_prod_self_edit_forbidden": True,
        "mutation_channel": "gitea_pr_only",
        "decision": (
            {
                "policy_decision": r.decision.policy_decision,
                "reason": r.decision.reason,
                "gated_paths": list(r.decision.gated_paths),
                "other_paths": list(r.decision.other_paths),
            }
            if r.decision
            else None
        ),
    }


def _append_proposed(state_root: Path, result: ProposeResult) -> None:
    project = result.project or "unknown/unknown"
    delivery = (
        f"self_improve:{project}:{result.branch}:{result.pr_number}:"
        f"{hashlib.sha256('|'.join(result.paths).encode()).hexdigest()[:12]}"
    )
    event_type = EVENT_SELF_IMPROVE_PROPOSED
    event_id = deterministic_event_id("ct103", delivery, event_type)
    event = AgentEvent(
        event_id=event_id,
        type=event_type,
        raw_event_type=event_type,
        source="ct103",
        delivery_id=delivery,
        project=project,
        payload={
            "schema_version": "self_improve_proposed.v1",
            "type": event_type,
            "project": project,
            "branch": result.branch,
            "base": result.base,
            "pr_number": result.pr_number,
            "pr_url": result.pr_url,
            "paths": list(result.paths),
            "risk_tags": list(result.risk_tags),
            "mutation_channel": "gitea_pr_only",
            "proposed_at": datetime.now(timezone.utc).isoformat(),
        },
        recorded_at=datetime.now(timezone.utc).isoformat(),
    )
    append_event(state_root, event)


def _append_denied(
    state_root: Path,
    project: str,
    decision: SelfImproveDecision,
    paths: list[str],
) -> None:
    delivery = (
        f"self_improve_deny:{project}:{decision.reason}:"
        f"{hashlib.sha256('|'.join(paths).encode()).hexdigest()[:12]}"
    )
    event_type = EVENT_SELF_IMPROVE_DENIED
    event_id = deterministic_event_id("ct103", delivery, event_type)
    event = AgentEvent(
        event_id=event_id,
        type=event_type,
        raw_event_type=event_type,
        source="ct103",
        delivery_id=delivery,
        project=project,
        payload={
            "schema_version": "self_improve_denied.v1",
            "type": event_type,
            "project": project,
            "reason": decision.reason,
            "paths": list(paths),
            "gated_paths": list(decision.gated_paths),
            "other_paths": list(decision.other_paths),
            "risk_tags": list(decision.risk_tags),
            "denied_at": datetime.now(timezone.utc).isoformat(),
        },
        recorded_at=datetime.now(timezone.utc).isoformat(),
    )
    append_event(state_root, event)
