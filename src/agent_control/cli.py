"""agentctl CLI entrypoint."""

from __future__ import annotations

import json
from pathlib import Path

import click
import uvicorn

from agent_control import __version__
from agent_control.adr_compiler import compile_adrs
from agent_control.config import get_settings
from agent_control.context_builder import build_context_capsule
from agent_control.events import (
    AgentEvent,
    append_event,
    deterministic_event_id,
    list_reduction_outbox,
    load_project_events,
)
from agent_control.jobs.state import process_state_reduction
from agent_control.model_router import ping_role, resolve_role_primary
from agent_control.queue import (
    QUEUE_NAMES,
    STATE_WORKER_MAX_CONCURRENCY,
    enqueue_rlm_root,
    enqueue_state_reduction,
    queue_info,
    run_worker,
)
from agent_control.memory.writeback import get_memory_store
from agent_control.results_ingest import ingest_inbox, ingest_result_file
from agent_shared.repo_identity import normalize_repo_full_name
from agent_control.repo_snapshot import snapshot_repo
from agent_control.state_reducer import ReductionMode, reduce_event_only
from agent_control.webhook_server import create_app, verify_hmac
from agent_control.workflows.dispatch import build_rlm_job
from agent_shared.models.state import VerificationState
from agent_control.workflows import dispatch as dispatch_wf
from agent_control.workflows import fix as fix_wf
from agent_control.workflows import review as review_wf
from agent_control.workflows import reward as reward_wf
from agent_control.workflows import tournament as tournament_wf
from agent_control.graph.blast_radius import export_blast_radius_json
from agent_control.graph.context_pack import compile_context_pack, write_context_pack_export
from agent_control.graph.snapshot import snapshot_all


@click.group()
def main() -> None:
    """Agent control plane CLI."""


@main.command()
def version() -> None:
    click.echo(f"agentctl {__version__}")


@main.command()
def bootstrap() -> None:
    click.echo("bootstrap: stub — see BOOTSTRAP.md for Gitea org setup")


@main.command()
@click.option("--owner", required=True)
@click.option("--repo", required=True)
@click.option("--event", "event_name", required=True)
def dispatch(owner: str, repo: str, event_name: str) -> None:
    result = dispatch_wf.dispatch({"owner": owner, "repo": repo, "event": event_name})
    click.echo(json.dumps(result))


@main.group()
def webhook() -> None:
    """Webhook server commands."""


@webhook.command("serve")
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8080, type=int)
def webhook_serve(host: str, port: int) -> None:
    app = create_app()
    uvicorn.run(app, host=host, port=port)


@main.group()
def events() -> None:
    """Event ledger commands."""


@events.command("append")
@click.option("--project", required=True, help="owner/repo")
@click.option("--type", "event_type", required=True)
@click.option("--delivery-id", default="manual")
@click.option("--payload", default="{}", help="JSON payload")
def events_append(project: str, event_type: str, delivery_id: str, payload: str) -> None:
    settings = get_settings()
    event_id = deterministic_event_id("cli", delivery_id, event_type)
    event = AgentEvent(
        event_id=event_id,
        type=event_type,
        delivery_id=delivery_id,
        project=project,
        payload=json.loads(payload),
        source="cli",
    )
    path, created = append_event(settings.agent_state_root, event)
    click.echo(json.dumps({"path": str(path), "created": created}))


@main.group()
def state() -> None:
    """State reducer commands."""


@state.command("reduce")
@click.option("--project", default=None, help="owner/repo — load events from agent-state ledger")
@click.option("--repo", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--mode",
    type=click.Choice([m.value for m in ReductionMode]),
    default=ReductionMode.EVENT_ONLY.value,
)
@click.option("--events-json", type=click.Path(exists=True, path_type=Path))
@click.option("--write", is_flag=True, help="Persist verification_state.json (requires --project)")
def state_reduce(
    project: str | None,
    repo: Path | None,
    mode: str,
    events_json: Path | None,
    write: bool,
) -> None:
    """Reduce logical state. event-only mode needs no local checkout."""
    if mode != ReductionMode.EVENT_ONLY.value:
        raise click.ClickException("only event-only mode is implemented at MVP")

    resolved_project = project or "unknown/unknown"
    if repo and not project:
        resolved_project = (
            f"{repo.parent.name}/{repo.name}" if repo.name != ".agent" else "local/repo"
        )

    events_data: list[dict] = []
    if events_json:
        events_data = json.loads(events_json.read_text(encoding="utf-8"))
    elif project:
        settings = get_settings()
        events_data = load_project_events(settings.agent_state_root, project)

    if write:
        if not project:
            raise click.ClickException("--write requires --project")
        result = process_state_reduction(
            str(get_settings().agent_state_root),
            events_data[-1].get("event_id", "manual") if events_data else "manual",
            project,
        )
        click.echo(json.dumps(result, indent=2))
        return

    logical = reduce_event_only(events_data, resolved_project)
    click.echo(logical.model_dump_json(indent=2))


@state.command("reconcile")
@click.option("--project", required=True, help="owner/repo")
@click.option("--enqueue", is_flag=True, help="Enqueue missing jobs via Redis instead of running inline")
def state_reconcile(project: str, enqueue: bool) -> None:
    """Process pending outbox markers and refresh verification state."""
    settings = get_settings()
    markers = list_reduction_outbox(settings.agent_state_root, project=project)
    if not markers:
        result = process_state_reduction(
            str(settings.agent_state_root),
            "reconcile",
            project,
        )
        click.echo(json.dumps({"reconciled": [result]}, indent=2))
        return

    results: list[dict] = []
    for marker in markers:
        event_id = marker["event_id"]
        if enqueue:
            job_id = enqueue_state_reduction(
                settings.redis_url,
                event_id,
                project,
                str(settings.agent_state_root),
            )
            results.append({"event_id": event_id, "job_id": job_id, "status": "enqueued"})
        else:
            results.append(
                process_state_reduction(
                    str(settings.agent_state_root),
                    event_id,
                    project,
                )
            )
    click.echo(json.dumps({"reconciled": results}, indent=2))


@state.command("validate")
@click.option("--repo", type=click.Path(exists=True, path_type=Path), required=True)
def state_validate(repo: Path) -> None:
    contract = repo / ".agent" / "contract.yaml"
    if not contract.exists():
        raise click.ClickException(f"missing {contract}")
    click.echo("contract present (full validation stub)")


@main.group()
def repo() -> None:
    """Repository snapshot commands."""


@repo.command("snapshot")
@click.option("--owner", required=True)
@click.option("--repo", "repo_name", required=True)
@click.option("--ref", required=True)
@click.option("--workdir", type=click.Path(path_type=Path), default="/tmp/agent-snapshots")
def repo_snapshot_cmd(owner: str, repo_name: str, ref: str, workdir: Path) -> None:
    result = snapshot_repo(owner, repo_name, ref, workdir)
    click.echo(json.dumps(result, indent=2))


@main.group()
def graph() -> None:
    """Cross-repo intelligence graph commands."""


@graph.command("snapshot")
@click.option("--repo", "project", default=None, help="owner/repo — default: all registered projects")
@click.option(
    "--local-path",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
    default=None,
    help="Use an existing checkout instead of cloning (requires --repo)",
)
def graph_snapshot(project: str | None, local_path: Path | None) -> None:
    if local_path is not None and not project:
        raise click.UsageError("--local-path requires --repo")
    settings = get_settings()
    local_paths = {project: local_path} if project and local_path else None
    result = snapshot_all(settings=settings, repo=project, local_paths=local_paths)
    click.echo(json.dumps(result, indent=2))


@graph.command("blast-radius")
@click.option("--repo", "project", required=True, help="owner/repo")
@click.option("--files", multiple=True, required=True, help="Changed file paths")
def graph_blast_radius(project: str, files: tuple[str, ...]) -> None:
    settings = get_settings()
    payload = export_blast_radius_json(project, list(files), settings=settings)
    click.echo(json.dumps(payload, indent=2))


@graph.command("context-pack")
@click.option("--repo", "project", required=True, help="owner/repo")
@click.option("--issue", "issue_number", type=int, required=True)
@click.option("--pr", "pr_number", type=int, default=None)
@click.option("--files", multiple=True, default=(), help="Changed file paths override")
def graph_context_pack(
    project: str,
    issue_number: int,
    pr_number: int | None,
    files: tuple[str, ...],
) -> None:
    settings = get_settings()
    from agent_shared.models.jobs import TriggerContext

    trigger = TriggerContext(
        event_type="cli",
        issue_number=issue_number,
        pr_number=pr_number,
    )
    pack = compile_context_pack(
        project,
        trigger,
        settings=settings,
        changed_files=list(files) if files else None,
    )
    write_context_pack_export(pack, settings=settings)
    click.echo(pack.model_dump_json(indent=2))


@main.group()
def adr() -> None:
    """ADR compiler commands."""


@adr.command("compile")
@click.option("--repo", type=click.Path(exists=True, path_type=Path), required=True)
def adr_compile(repo: Path) -> None:
    facts = compile_adrs(repo / "docs" / "adr")
    click.echo(json.dumps(facts, indent=2))


@main.group()
def context() -> None:
    """Context capsule commands."""


@context.command("build")
@click.option("--repo", type=click.Path(exists=True, path_type=Path))
def context_build(repo: Path | None) -> None:
    from agent_control.state_reducer import LogicalState

    capsule = build_context_capsule(LogicalState(project="stub/project"), repo)
    click.echo(json.dumps(capsule, indent=2))


@context.command("gitingest")
@click.option("--repo", type=click.Path(exists=True, path_type=Path), required=True)
@click.option("--output", type=click.Path(path_type=Path), required=True)
def context_gitingest(repo: Path, output: Path) -> None:
    click.echo(f"gitingest stub: {repo} -> {output}")


@main.group()
def queue() -> None:
    """Queue commands."""


@queue.command("info")
def queue_info_cmd() -> None:
    settings = get_settings()
    click.echo(json.dumps(queue_info(settings.redis_url), indent=2))


@queue.command("enqueue-rlm-test")
@click.option("--project", default="ai-sdlc-lab/demo-app")
@click.option("--flow", default="inspect")
@click.option("--intent", default="inspect")
@click.option("--task", default="why worker-state is idle")
@click.option("--event-id", default="test-inspect-event")
def queue_enqueue_rlm_test(project: str, flow: str, intent: str, task: str, event_id: str) -> None:
    from agent_shared.models.intent import CommandIntent

    settings = get_settings()
    state = VerificationState(
        project=project,
        command_intent=CommandIntent(
            activated=True,
            activation="/agent",
            kind=intent,
            natural_language_task=task,
            confidence=1.0,
        ),
        dispatch_recommended=True,
        dispatch_kind=flow,
    )
    trigger = {
        "event_id": event_id,
        "delivery_id": "test-delivery",
        "type": "gitea.issue_comment",
        "project": project,
        "payload": {"comment": {"body": f"/agent {intent} {task}", "id": 1}, "issue": {"number": 1}},
    }
    job = build_rlm_job(state, trigger, settings=settings)
    if job is None:
        raise click.ClickException("failed to build RLM job")
    job_id = enqueue_rlm_root(settings.redis_url, job.model_dump(mode="json"))
    click.echo(json.dumps({"job_id": job_id, "run_id": job.run_id, "status": "enqueued"}))


@queue.command("enqueue-test")
@click.option("--queue", "queue_name", type=click.Choice(list(QUEUE_NAMES)), required=True)
@click.option("--project", default="ai-sdlc-lab/demo-app")
@click.option("--event-id", default="test-event-id")
def queue_enqueue_test(queue_name: str, project: str, event_id: str) -> None:
    settings = get_settings()
    if queue_name != "state":
        click.echo(json.dumps({"queue": queue_name, "status": "stub_unless_rlm_root"}))
        return
    job_id = enqueue_state_reduction(
        settings.redis_url,
        event_id,
        project,
        str(settings.agent_state_root),
    )
    click.echo(json.dumps({"queue": queue_name, "job_id": job_id, "status": "enqueued"}))


@main.group()
def worker() -> None:
    """RQ worker commands."""


@worker.command("doctor")
def worker_doctor() -> None:
    settings = get_settings()
    runs = settings.agent_runs_dir
    checks = {
        "redis_url": settings.redis_url,
        "agent_runs_writable": False,
        "agent_state_root": str(settings.agent_state_root),
    }
    try:
        runs.mkdir(parents=True, exist_ok=True)
        probe = runs / ".doctor_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        checks["agent_runs_writable"] = True
    except OSError as exc:
        checks["error"] = str(exc)
    try:
        checks["queues"] = queue_info(settings.redis_url)
    except Exception as exc:
        checks["redis_error"] = str(exc)
    click.echo(json.dumps(checks, indent=2))


@worker.command("run")
@click.option(
    "--queues",
    multiple=True,
    type=click.Choice(list(QUEUE_NAMES)),
    required=True,
)
@click.option("--concurrency", default=1, type=int)
def worker_run(queues: tuple[str, ...], concurrency: int) -> None:
    if "state" in queues and concurrency > STATE_WORKER_MAX_CONCURRENCY:
        click.echo(
            "warning: state worker concurrency should be 1 at MVP",
            err=True,
        )
    if concurrency != 1:
        raise click.ClickException("only --concurrency 1 is supported at MVP")
    settings = get_settings()
    click.echo(
        json.dumps({"queues": queues, "concurrency": concurrency, "status": "starting"}),
        err=True,
    )
    run_worker(settings.redis_url, queues, concurrency=concurrency)


@main.group()
def model() -> None:
    """Model router commands."""


@model.command("ping")
@click.option("--role", required=True)
def model_ping(role: str) -> None:
    try:
        result = ping_role(role)
    except ValueError as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(1) from exc
    click.echo(json.dumps(result))
    status = result.get("status")
    if status in ("unreachable", "error"):
        click.echo(f"model unreachable: {result.get('error', status)}", err=True)
        raise SystemExit(1)
    if status == "skipped":
        click.echo("model endpoint not configured", err=True)
        raise SystemExit(1)


@model.command("resolve")
@click.option("--role", required=True)
def model_resolve(role: str) -> None:
    try:
        result = resolve_role_primary(role).as_dict()
    except ValueError as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(1) from exc
    click.echo(json.dumps(result))


@main.command()
@click.option("--repo", type=click.Path(exists=True, path_type=Path))
def review(repo: Path | None) -> None:
    click.echo(json.dumps(review_wf.review({"repo": str(repo) if repo else None})))


@main.command("fix-cmd")
@click.option("--finding-id", required=True)
def fix_cmd(finding_id: str) -> None:
    click.echo(json.dumps(fix_wf.fix({}, finding_id)))


@main.group("fix")
def fix_group() -> None:
    """Fix CI observation and status (Slice 6E)."""


@fix_group.command("pending-ci")
@click.option("--repo", "project", default=None, help="owner/repo filter")
@click.option("--include-terminal", is_flag=True, default=False)
def fix_pending_ci(project: str | None, include_terminal: bool) -> None:
    """List pending CI records (pr_opened_pending_ci awaiting aggregate verdict)."""
    from agent_control.ci.pending import list_pending_ci

    settings = get_settings()
    items = list_pending_ci(
        settings.agent_state_root,
        project,
        include_terminal=include_terminal,
    )
    click.echo(
        json.dumps([r.model_dump(mode="json") for r in items], indent=2)
    )


@fix_group.command("ci-status")
@click.option("--run-id", "fix_run_id", required=True)
@click.option("--repo", "project", required=True, help="owner/repo")
def fix_ci_status(fix_run_id: str, project: str) -> None:
    """Show current CI aggregate verdict for a fix run."""
    from agent_control.ci.artifacts import load_verification_current
    from agent_control.ci.observe import rebuild_result_from_ledger
    from agent_control.ci.pending import load_pending_ci
    from pathlib import Path

    settings = get_settings()
    pending = load_pending_ci(settings.agent_state_root, project, fix_run_id)
    if pending is None:
        raise click.ClickException(f"no pending_ci for run_id={fix_run_id}")
    result = None
    if pending.artifact_root:
        result = load_verification_current(Path(pending.artifact_root))
    if result is None:
        result = rebuild_result_from_ledger(
            settings.agent_state_root, project, fix_run_id
        )
    payload = {
        "pending": pending.model_dump(mode="json"),
        "verification": result.model_dump(mode="json") if result else None,
    }
    click.echo(json.dumps(payload, indent=2))


@fix_group.command("ci-reconcile")
@click.option("--repo", "project", default=None, help="owner/repo filter")
def fix_ci_reconcile(project: str | None) -> None:
    """Force sweep: poll Gitea Actions API for pending CI records."""
    from agent_control.ci.reconcile import reconcile_pending_ci

    settings = get_settings()
    results = reconcile_pending_ci(
        settings.agent_state_root,
        project=project,
        settings=settings,
    )
    click.echo(json.dumps(results, indent=2))


@main.command()
def repair() -> None:
    """6F.2 repair status — reservation/lease + worker (see slice-5.8-6f2)."""
    settings = get_settings()
    click.echo(
        json.dumps(
            {
                "status": "gated",
                "workflow": "repair",
                "fix_ci_observe_enabled": settings.fix_ci_observe_enabled,
                "fix_ci_failure_evidence_enabled": settings.fix_ci_failure_evidence_enabled,
                "fix_ci_repair_enabled": settings.fix_ci_repair_enabled,
                "fix_ci_repair_max_attempts": settings.fix_ci_repair_max_attempts,
                "sandbox_backend": settings.sandbox_backend,
                "note": (
                    "Dispatch creates a durable reservation + deterministic RQ job, "
                    "then releases the observer lock. Worker claims a TTL lease, "
                    "runs mandatory SRT verification, non-force pushes, and reports "
                    "fix_ci_repair_pushed for CT103 pending registration."
                ),
            }
        )
    )


@main.group()
def tournament() -> None:
    """Patch tournament (experiment flag)."""


@tournament.command("spawn")
@click.option("--finding-id", required=True)
def tournament_spawn(finding_id: str) -> None:
    click.echo(json.dumps(tournament_wf.spawn_tournament(finding_id)))


@tournament.command("judge")
def tournament_judge() -> None:
    from agent_control.agents import judge

    click.echo(json.dumps(judge.run_judge([])))


@main.group()
def rewards() -> None:
    """Reward logging commands."""


@rewards.command("log")
@click.option("--run-id", required=True)
def rewards_log(run_id: str) -> None:
    click.echo(json.dumps(reward_wf.log_reward(run_id, {})))


@rewards.command("summarize")
def rewards_summarize() -> None:
    click.echo(json.dumps({"status": "stub"}))


@main.group()
def rlm() -> None:
    """RLM context commands."""


@rlm.command("inspect")
@click.option("--digest", required=True)
def rlm_inspect(digest: str) -> None:
    from agent_control.agents import rlm_context

    click.echo(json.dumps(rlm_context.inspect_context(digest)))


@main.group()
def gitea() -> None:
    """Gitea API helpers."""


@gitea.command("post-comment")
def gitea_post_comment() -> None:
    click.echo("stub — use worker-report for agent comments")


@main.group()
def results() -> None:
    """CT104 result ingest commands."""


@results.command("ingest")
@click.option("--path", type=click.Path(exists=True, path_type=Path))
@click.option("--inbox", is_flag=True, help="Process all pending inbox files")
def results_ingest(path: Path | None, inbox: bool) -> None:
    settings = get_settings()
    if inbox:
        click.echo(json.dumps(ingest_inbox(settings.agent_state_root), indent=2))
        return
    if path is None:
        raise click.ClickException("--path or --inbox required")
    stored, created = ingest_result_file(settings.agent_state_root, path)
    click.echo(json.dumps({"stored": str(stored), "created": created}))


@results.command("ingest-watch")
@click.option("--inbox", is_flag=True, default=True, help="Watch ct104-results inbox (default)")
@click.option("--sweep-interval", default=120, type=int, show_default=True)
def results_ingest_watch(inbox: bool, sweep_interval: int) -> None:
    """Backup ingest watcher with periodic sweep (Slice 4C)."""
    if not inbox:
        raise click.ClickException("only --inbox is supported")
    from agent_control.ingest_watch import ingest_watch_loop

    settings = get_settings()
    ingest_watch_loop(settings.agent_state_root, sweep_interval_seconds=sweep_interval)


@main.group()
def approvals() -> None:
    """Risk 2 approval handles (Slice 6A)."""


@approvals.command("list")
@click.option("--repo", "project", required=True, help="owner/repo")
@click.option("--issue", "issue_id", type=int, default=None)
def approvals_list(project: str, issue_id: int | None) -> None:
    from agent_control.approval.storage import list_approvals

    settings = get_settings()
    items = list_approvals(settings.agent_state_root, project, issue_id=issue_id)
    click.echo(json.dumps([a.model_dump(mode="json") for a in items], indent=2))


@approvals.command("show")
@click.argument("approval_target")
@click.option("--repo", "project", required=True, help="owner/repo")
def approvals_show(approval_target: str, project: str) -> None:
    from agent_control.approval.storage import load_approval

    settings = get_settings()
    approval = load_approval(settings.agent_state_root, project, approval_target)
    if approval is None:
        raise click.ClickException(f"no approval for {approval_target}")
    click.echo(approval.model_dump_json(indent=2))


@approvals.command("grant")
@click.option("--repo", "project", required=True, help="owner/repo")
@click.option("--issue", "issue_id", type=int, required=True)
@click.option("--approval-target", required=True)
@click.option("--approver", required=True, help="Owner login for homelab debug")
def approvals_grant(project: str, issue_id: int, approval_target: str, approver: str) -> None:
    from agent_control.approval.service import grant_approval

    settings = get_settings()
    approval, message, created = grant_approval(
        settings.agent_state_root,
        project=project,
        issue_id=issue_id,
        target=approval_target,
        approver_login=approver,
        author_is_owner=True,
    )
    click.echo(json.dumps({"created": created, "message": message, "approval": approval.model_dump(mode="json") if approval else None}, indent=2))


@main.group()
def session() -> None:
    """CT103 typed agent sessions (Slice 5.4a)."""


@session.command("list")
@click.option("--repo", "project", required=True, help="owner/repo")
@click.option("--command-kind", default=None, help="Filter: review|plan|fix|repair")
@click.option("--json", "as_json", is_flag=True, default=True, help="Emit JSON (default)")
def session_list(project: str, command_kind: str | None, as_json: bool) -> None:
    from agent_control.session import list_sessions

    settings = get_settings()
    items = list_sessions(settings.agent_state_root, project, command_kind=command_kind)
    payload = [s.model_dump(mode="json") for s in items]
    click.echo(json.dumps(payload, indent=2))


@session.command("show")
@click.option("--session-id", required=True, help="sess-… id")
@click.option("--repo", "project", required=True, help="owner/repo")
@click.option("--json", "as_json", is_flag=True, default=True, help="Emit JSON (default)")
def session_show(session_id: str, project: str, as_json: bool) -> None:
    from agent_control.session import load_session

    settings = get_settings()
    record = load_session(settings.agent_state_root, project, session_id)
    if record is None:
        raise click.ClickException(f"no session for {session_id}")
    click.echo(record.model_dump_json(indent=2))


@main.group()
def memory() -> None:
    """Trajectory memory (CT103 SQLite)."""


@memory.command("show")
@click.option("--repo", "project", required=True, help="owner/repo")
@click.option("--issue", "issue_id", type=int, required=True)
@click.option("--run-id", default=None, help="Show a specific run memory record")
def memory_show(project: str, issue_id: int, run_id: str | None) -> None:
    settings = get_settings()
    repo_full_name = normalize_repo_full_name(project)
    if repo_full_name is None:
        raise click.ClickException(f"invalid repo: {project}")
    store = get_memory_store(settings)
    if run_id:
        record = store.get_by_run_id(run_id)
        if record is None or record.repo_full_name != repo_full_name:
            raise click.ClickException(f"no memory for run_id={run_id}")
        click.echo(record.model_dump_json(indent=2, exclude={"review_result", "plan_result"}))
        return
    record = store.get_latest(repo_full_name, issue_id)
    if record is None:
        raise click.ClickException(f"no memory for {repo_full_name} issue #{issue_id}")
    click.echo(record.model_dump_json(indent=2, exclude={"review_result", "plan_result"}))


@memory.command("trajectory")
@click.option("--repo", "project", required=True, help="owner/repo")
@click.option("--issue", "issue_id", type=int, required=True)
@click.option("--limit", default=5, type=int, show_default=True)
def memory_trajectory(project: str, issue_id: int, limit: int) -> None:
    settings = get_settings()
    repo_full_name = normalize_repo_full_name(project)
    if repo_full_name is None:
        raise click.ClickException(f"invalid repo: {project}")
    from agent_control.memory.retrieval import get_memory_trajectory

    records = get_memory_trajectory(repo_full_name, issue_id, limit=limit, settings=settings)
    if not records:
        raise click.ClickException(f"no memory trajectory for {repo_full_name} issue #{issue_id}")
    click.echo(
        json.dumps(
            [r.model_dump(mode="json") for r in records],
            indent=2,
        )
    )


@main.group()
def runs() -> None:
    """Inspect CT104 run artifacts."""


def _run_path(run_id: str, project: str | None) -> Path:
    settings = get_settings()
    if project:
        owner, repo = project.split("/", 1)
        return settings.agent_runs_dir / owner / repo / "runs" / run_id
    for path in settings.agent_runs_dir.rglob(f"runs/{run_id}"):
        return path
    raise click.ClickException(f"run not found: {run_id}")


@runs.command("list")
@click.option("--project")
def runs_list(project: str | None) -> None:
    settings = get_settings()
    base = settings.agent_runs_dir
    if project:
        owner, repo = project.split("/", 1)
        base = base / owner / repo / "runs"
    items = []
    if base.exists():
        for meta in base.rglob("metadata.json"):
            items.append({"run_id": meta.parent.name, "path": str(meta.parent)})
    click.echo(json.dumps(items, indent=2))


@runs.command("show")
@click.argument("run_id")
@click.option("--project")
def runs_show(run_id: str, project: str | None) -> None:
    path = _run_path(run_id, project) / "metadata.json"
    click.echo(path.read_text(encoding="utf-8"))


@runs.command("report")
@click.argument("run_id")
@click.option("--project")
def runs_report(run_id: str, project: str | None) -> None:
    path = _run_path(run_id, project) / "final_report.md"
    click.echo(path.read_text(encoding="utf-8"))


@runs.command("logs")
@click.argument("run_id")
@click.option("--project")
def runs_logs(run_id: str, project: str | None) -> None:
    path = _run_path(run_id, project) / "agent.log"
    if path.exists():
        click.echo(path.read_text(encoding="utf-8"))
    else:
        click.echo("(no agent.log)")


@runs.command("events")
@click.argument("run_id")
@click.option("--project")
def runs_events(run_id: str, project: str | None) -> None:
    path = _run_path(run_id, project) / "session_events.jsonl"
    click.echo(path.read_text(encoding="utf-8"))


@runs.command("context")
@click.argument("run_id")
@click.option("--project")
def runs_context(run_id: str, project: str | None) -> None:
    path = _run_path(run_id, project) / "context_receipt.json"
    click.echo(path.read_text(encoding="utf-8"))


@runs.command("redactions")
@click.argument("run_id")
@click.option("--project")
def runs_redactions(run_id: str, project: str | None) -> None:
    path = _run_path(run_id, project) / "redaction_report.json"
    click.echo(path.read_text(encoding="utf-8"))


@main.group()
def policy() -> None:
    """Policy loader commands."""


@policy.command("load-test")
@click.argument("project")
def policy_load_test(project: str) -> None:
    from agent_workers.repo.policy_loader import load_platform_default_policy

    click.echo(json.dumps({"project": project, "platform_default": load_platform_default_policy()}, indent=2))


@repo.command("can-clone")
@click.argument("project")
def repo_can_clone(project: str) -> None:
    from agent_control.project_registry import resolve_project

    cfg = resolve_project(project)
    click.echo(json.dumps({"project": project, "repo_url": cfg.repo_url, "ref": cfg.protected_policy_ref}))


@gitea.command("open-pr")
@click.option("--repo", "project", required=True, help="owner/repo")
@click.option("--head", required=True, help="Head branch (agent/run-...)")
@click.option("--base", default="main", show_default=True)
@click.option("--title", required=True)
@click.option("--body", default="")
def gitea_open_pr(project: str, head: str, base: str, title: str, body: str) -> None:
    from agent_control.config import get_settings
    from agent_control.gitea_client import GiteaClient

    settings = get_settings()
    owner, repo = project.split("/", 1)
    client = GiteaClient(settings)
    result = client.create_pull_request(owner, repo, head=head, base=base, title=title, body=body)
    click.echo(json.dumps(result, indent=2))


# Export verify_hmac for tests
__all__ = ["main", "verify_hmac"]

if __name__ == "__main__":
    main()
