"""agentctl CLI entrypoint."""

from __future__ import annotations

import json
import os
import sys
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
from agent_control.graph.coverage import export_coverage_json, export_edges_json
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


@graph.command("edges")
@click.option("--repo", "project", default=None, help="owner/repo filter")
@click.option("--kind", default=None, help="Edge kind filter (e.g. adr_constrains_file)")
@click.option("--provenance", default=None, help="Provenance filter (catalog|static_analysis|…)")
@click.option("--limit", default=500, show_default=True, help="Max edges to return")
def graph_edges(
    project: str | None,
    kind: str | None,
    provenance: str | None,
    limit: int,
) -> None:
    """List Orbit graph edges with provenance."""
    settings = get_settings()
    payload = export_edges_json(
        project,
        kind=kind,
        provenance=provenance,
        settings=settings,
        limit=limit,
    )
    click.echo(json.dumps(payload, indent=2))


@graph.command("coverage")
@click.option("--repo", "project", default=None, help="owner/repo — default: aggregate")
def graph_coverage(project: str | None) -> None:
    """Report edge-kind / provenance coverage and missing Orbit edges."""
    settings = get_settings()
    payload = export_coverage_json(project, settings=settings)
    click.echo(json.dumps(payload, indent=2))


@graph.command("drift")
@click.option("--repo", "project", required=True, help="owner/repo")
@click.option(
    "--adr-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="docs/adr directory override",
)
@click.option(
    "--local-path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Repo checkout root (uses <path>/docs/adr)",
)
@click.option(
    "--strict",
    is_flag=True,
    default=False,
    help="Exit 1 when missing/extra edges exist (default: fail-soft exit 0)",
)
def graph_drift(
    project: str,
    adr_dir: Path | None,
    local_path: Path | None,
    strict: bool,
) -> None:
    """Report ADR-declared edges missing from / extra in the Orbit graph (fail-soft)."""
    from agent_control.graph.adr_drift import detect_adr_drift

    settings = get_settings()
    payload = detect_adr_drift(
        project,
        adr_dir=adr_dir,
        local_path=local_path,
        settings=settings,
    )
    click.echo(json.dumps(payload, indent=2))
    if strict and payload.get("drift"):
        raise click.ClickException(
            f"architecture drift: missing={payload.get('missing_count')} "
            f"extra={payload.get('extra_count')}"
        )


@graph.command("sarif-ingest")
@click.option("--repo", "project", required=True, help="owner/repo")
@click.option(
    "--file",
    "sarif_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to a SARIF 2.x document",
)
def graph_sarif_ingest(project: str, sarif_file: Path) -> None:
    """Attach SARIF findings as Orbit security/evidence graph nodes (Risk 0/1 only)."""
    from agent_control.graph.sarif_ingest import ingest_sarif

    settings = get_settings()
    payload = ingest_sarif(project, sarif_file, settings=settings)
    click.echo(json.dumps(payload, indent=2))
    if not payload.get("ok"):
        raise click.ClickException("; ".join(payload.get("warnings") or ["sarif ingest failed"]))


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
    result = enqueue_rlm_root(settings.redis_url, job.model_dump(mode="json"))
    job_id = result.job_id if result.outcome == "enqueued" else result.existing_job_id
    click.echo(
        json.dumps(
            {
                "job_id": job_id,
                "run_id": job.run_id,
                "status": result.outcome,
            }
        )
    )


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


@main.group()
def repair() -> None:
    """6F.2 repair status and staged ACP expand (T09)."""


@repair.command("status")
def repair_status_cmd() -> None:
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


@repair.command("stage-status")
def repair_stage_status_cmd() -> None:
    """Report Observe → repair-no-publish → one-class publish readiness."""
    from agent_control.ci.repair_stages import repair_stage_status

    click.echo(json.dumps(repair_stage_status(), indent=2, sort_keys=True))


@main.group()
def tournament() -> None:
    """Patch tournament (experiment flag)."""


@tournament.command("spawn")
@click.option("--finding-id", required=True)
@click.option("--candidates", default=3, show_default=True, type=int)
@click.option("--repo", default="ai-sdlc-lab/agent-control-plane", show_default=True)
def tournament_spawn(finding_id: str, candidates: int, repo: str) -> None:
    click.echo(
        json.dumps(
            tournament_wf.spawn_tournament(
                finding_id, candidates=candidates, repository=repo
            ),
            indent=2,
            sort_keys=True,
        )
    )


@tournament.command("judge")
@click.option("--tournament-id", required=True)
@click.option("--repo", default="ai-sdlc-lab/agent-control-plane", show_default=True)
def tournament_judge(tournament_id: str, repo: str) -> None:
    click.echo(
        json.dumps(
            tournament_wf.judge_tournament(tournament_id, repository=repo),
            indent=2,
            sort_keys=True,
        )
    )


@main.group()
def rewards() -> None:
    """Reward logging commands (experiment flag)."""


@rewards.command("log")
@click.option("--run-id", required=True)
@click.option("--repo", default="ai-sdlc-lab/agent-control-plane", show_default=True)
@click.option("--outcome", default="unknown", show_default=True)
@click.option("--score", default=0.0, type=float, show_default=True)
def rewards_log(run_id: str, repo: str, outcome: str, score: float) -> None:
    click.echo(
        json.dumps(
            reward_wf.log_reward(
                run_id,
                {"outcome": outcome, "score": score},
                repository=repo,
            ),
            indent=2,
            sort_keys=True,
        )
    )


@rewards.command("summarize")
@click.option("--repo", default="ai-sdlc-lab/agent-control-plane", show_default=True)
def rewards_summarize(repo: str) -> None:
    click.echo(json.dumps(reward_wf.summarize_rewards(repository=repo), indent=2, sort_keys=True))


@main.group()
def rlm() -> None:
    """RLM / recursive context commands."""


@rlm.command("inspect")
@click.option("--digest", default=None, help="Legacy digest path stub")
@click.option("--run-id", default=None, help="Run id for recursive context inspect")
@click.option("--repo", "project", default=None, help="owner/repo")
@click.option("--session-id", default=None, help="sess-… to load stored result")
@click.option("--query", default="", help="Focused question for recursive context")
@click.option("--force", is_flag=True, help="Force invoke even if preflight would skip")
@click.option(
    "--controller-backend",
    type=click.Choice(["deterministic", "model"]),
    default=None,
    help="V10 T00.5 arm: deterministic (C0) or model (C1); default from env/yaml",
)
def rlm_inspect(
    digest: str | None,
    run_id: str | None,
    project: str | None,
    session_id: str | None,
    query: str,
    force: bool,
    controller_backend: str | None,
) -> None:
    """Inspect recursive context (8c) or legacy digest stub."""
    if digest and not (run_id or session_id):
        from agent_control.agents import rlm_context

        click.echo(json.dumps(rlm_context.inspect_context(digest), indent=2))
        return

    settings = get_settings()
    if session_id and project:
        from agent_control.recursive_context.artifacts import load_recursive_context_artifact

        existing = load_recursive_context_artifact(
            settings.agent_state_root, project, session_id
        )
        if existing is not None:
            click.echo(existing.model_dump_json(indent=2))
            return

    if not project or not run_id:
        raise click.UsageError("--repo and --run-id required (or --session-id + --repo)")

    from agent_control.memory.preflight import compile_memory_preflight
    from agent_control.recursive_context.worker import run_conditional_recursive_context
    from agent_control.session import begin_typed_session
    from agent_shared.models.jobs import TriggerContext

    trigger = TriggerContext(event_type="cli", issue_number=0, author="cli")
    session = begin_typed_session(
        settings.agent_state_root,
        project=project,
        command_kind="review",
        run_id=run_id,
        head_sha="cli",
        trigger_context=trigger,
        policy_source_sha="",
        subject_kind="issue",
        subject_number=0,
        invoked_by="cli",
    )
    preflight = compile_memory_preflight(
        session=session,
        run_id=run_id,
        source_sha="cli",
        policy_source_sha="",
        trigger_context=trigger,
        settings=settings,
    )
    if force:
        preflight = preflight.model_copy(
            update={
                "recursive_context_required": True,
                "invocation_reasons": preflight.invocation_reasons
                or ["explicit_typed_deeper_context_request"],
                "skip_reason": None,
            }
        )
    result = run_conditional_recursive_context(
        preflight=preflight,
        question=query,
        settings=settings,
        state_root=settings.agent_state_root,
        force_invoke=force,
        controller_backend=controller_backend,
    )
    click.echo(result.model_dump_json(indent=2))


@rlm.command("run")
@click.option("--repo", "project", required=True)
@click.option("--run-id", required=True)
@click.option("--session-id", required=True)
@click.option("--query", default="")
@click.option(
    "--controller-backend",
    type=click.Choice(["deterministic", "model"]),
    default=None,
    help="V10 T00.5 arm: deterministic (C0) or model (C1); default from env/yaml",
)
def rlm_run(
    project: str,
    run_id: str,
    session_id: str,
    query: str,
    controller_backend: str | None,
) -> None:
    """Run conditional recursive context using a stored memory_preflight.json."""
    settings = get_settings()
    from agent_control.memory.preflight_artifacts import load_preflight_artifact
    from agent_control.recursive_context.artifacts import persist_recursive_context_artifact
    from agent_control.recursive_context.telemetry import controller_telemetry_payload
    from agent_control.recursive_context.worker import run_conditional_recursive_context

    preflight = load_preflight_artifact(settings.agent_state_root, project, session_id)
    if preflight is None:
        raise click.ClickException(f"no memory_preflight for {session_id}")
    result = run_conditional_recursive_context(
        preflight=preflight,
        question=query,
        settings=settings,
        state_root=settings.agent_state_root,
        controller_backend=controller_backend,
    )
    stamped, ref, created = persist_recursive_context_artifact(settings.agent_state_root, result)
    click.echo(
        json.dumps(
            {
                "created": created,
                "digest": ref.digest,
                "relative_path": ref.relative_path,
                "controller_telemetry": controller_telemetry_payload(stamped),
                "result": stamped.model_dump(mode="json"),
            },
            indent=2,
        )
    )


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
    from agent_control.memory.preflight_artifacts import (
        load_context_packet_artifact,
        load_preflight_artifact,
    )
    from agent_control.session import load_session
    from agent_control.session.verification import load_verification_claim

    settings = get_settings()
    record = load_session(settings.agent_state_root, project, session_id)
    if record is None:
        raise click.ClickException(f"no session for {session_id}")
    payload = record.model_dump(mode="json")
    preflight = load_preflight_artifact(settings.agent_state_root, project, session_id)
    packet = load_context_packet_artifact(settings.agent_state_root, project, session_id)
    claim = load_verification_claim(settings.agent_state_root, project, session_id)
    if preflight is not None:
        payload["memory_preflight_summary"] = {
            "status": preflight.status,
            "source_sha": preflight.source_sha,
            "policy_source_sha": preflight.policy_source_sha,
            "recursive_context_required": preflight.recursive_context_required,
            "invocation_reasons": preflight.invocation_reasons,
            "skip_reason": preflight.skip_reason,
            "artifact_digest": preflight.artifact_digest,
            "component_results": preflight.component_results.model_dump(mode="json"),
        }
    if packet is not None:
        payload["context_packet_summary"] = {
            "source_sha": packet.source_sha,
            "policy_source_sha": packet.policy_source_sha,
            "preflight_digest": packet.preflight_digest,
            "context_pack_digest": packet.context_pack_digest,
            "artifact_digest": packet.artifact_digest,
        }
    if claim is not None:
        payload["verification_summary"] = {
            "status": claim.status,
            "source": claim.source,
            "scope_commit_sha": claim.scope_commit_sha,
            "scope_behavior": claim.scope_behavior,
            "scope_files": claim.scope_files,
            "claim": claim.claim,
            "command_id": claim.command_id,
            "artifact": claim.artifact,
            "limitations": claim.limitations,
            "verdict_revision": claim.verdict_revision,
            "artifact_digest": claim.artifact_digest,
            "adequacy_profile_id": claim.adequacy_profile_id,
            "adequacy_status": claim.adequacy_status,
            "adequacy_outcome": claim.adequacy_outcome,
            "fixed_verified": claim.fixed_verified,
        }
    click.echo(json.dumps(payload, indent=2))


@main.group()
def replay() -> None:
    """Operator replay console from durable CT103 artifacts (V5 T03)."""


@replay.command("review")
@click.option("--repo", "project", required=True, help="owner/repo")
@click.option("--session-id", default=None, help="sess-… id")
@click.option("--run-id", default=None, help="run-… id (resolves session via index)")
@click.option(
    "--allow-unfinished",
    is_flag=True,
    default=False,
    help="Allow non-finished sessions (diagnostics)",
)
@click.option(
    "--text",
    "as_text",
    is_flag=True,
    default=False,
    help="Emit compact stage text instead of JSON",
)
def replay_review(
    project: str,
    session_id: str | None,
    run_id: str | None,
    allow_unfinished: bool,
    as_text: bool,
) -> None:
    """Replay one review session: issue → context → model → policy → memory."""
    from agent_control.replay.review import (
        ReviewReplayError,
        STAGE_ORDER,
        build_review_replay,
        normalize_project,
    )

    settings = get_settings()
    try:
        project = normalize_project(project)
        doc = build_review_replay(
            settings.agent_state_root,
            project=project,
            session_id=session_id,
            run_id=run_id,
            memory_db_path=settings.memory_db_path,
            require_finished=not allow_unfinished,
        )
    except ReviewReplayError as exc:
        raise click.ClickException(str(exc)) from exc

    if not as_text:
        click.echo(json.dumps(doc, indent=2))
        return

    click.echo(
        f"review_replay session={doc['session_id']} run={doc.get('run_id')} "
        f"status={doc['status']} complete={doc['complete']}"
    )
    for name in STAGE_ORDER:
        stage = doc["stages"][name]
        present = "yes" if stage.get("present") else "no"
        click.echo(f"  [{name}] present={present}")
        if name == "issue":
            click.echo(
                f"    {stage.get('subject_kind')}#{stage.get('subject_number')} "
                f"by {stage.get('invoked_by')} head={stage.get('head_sha')}"
            )
        elif name == "context":
            pf = stage.get("memory_preflight") or {}
            click.echo(
                f"    preflight={pf.get('status')} digest={pf.get('artifact_digest')}"
            )
        elif name == "model":
            click.echo(
                f"    policy={stage.get('model_policy')} engine={stage.get('engine')}"
            )
        elif name == "policy":
            click.echo(
                f"    policy_source_sha={stage.get('policy_source_sha')} "
                f"risk={stage.get('risk_level')} decision={stage.get('policy_decision')}"
            )
        elif name == "memory":
            rec = stage.get("record") or {}
            click.echo(
                f"    record_id={rec.get('record_id')} "
                f"epistemic={rec.get('epistemic_status')} "
                f"findings={rec.get('findings_count')}"
            )


@main.group()
def trace() -> None:
    """Session trace / observation projection (V6 T01+)."""


@trace.command("show")
@click.option("--repo", "project", required=True, help="owner/repo")
@click.option("--session-id", default=None, help="sess-… id")
@click.option("--run-id", default=None, help="run-… id")
@click.option(
    "--text",
    "as_text",
    is_flag=True,
    default=False,
    help="Emit compact text instead of JSON",
)
def trace_show(
    project: str,
    session_id: str | None,
    run_id: str | None,
    as_text: bool,
) -> None:
    """Show observation projection from durable ledger + session artifacts."""
    from agent_control.observe.projection import build_observation_projection
    from agent_shared.repo_identity import normalize_repo_full_name

    if not session_id and not run_id:
        raise click.ClickException("Provide --session-id and/or --run-id")
    repo_full = normalize_repo_full_name(project)
    if repo_full is None:
        raise click.ClickException(f"invalid repo: {project}")
    settings = get_settings()
    doc = build_observation_projection(
        settings.agent_state_root,
        project=repo_full,
        run_id=run_id,
        session_id=session_id,
    )
    payload = doc.model_dump(mode="json")
    if not as_text:
        click.echo(json.dumps(payload, indent=2))
        return
    click.echo(
        f"observation_projection session={payload.get('session_id')} "
        f"run={payload.get('run_id')} trace={payload.get('trace_id')} "
        f"complete={payload.get('complete')} max_seq={payload.get('max_sequence')}"
    )
    for stage in payload.get("stages") or []:
        click.echo(f"  [{stage.get('name')}] status={stage.get('status')}")


@main.group(name="observe")
def observe_group() -> None:
    """observe.sqlite display-safe projection (V9 T02). No public HTTP routes here."""


@observe_group.command("rebuild")
@click.option("--repo", "project", required=True, help="owner/repo")
@click.option(
    "--db-path",
    "db_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Override observe.sqlite location (default: settings.observe_db_path)",
)
def observe_rebuild(project: str, db_path: Path | None) -> None:
    """Full rescan of one project's ledger into observe.sqlite (idempotent)."""
    from agent_control.observe.rebuild import rebuild_observe_db
    from agent_shared.repo_identity import normalize_repo_full_name

    repo_full = normalize_repo_full_name(project)
    if repo_full is None:
        raise click.ClickException(f"invalid repo: {project}")
    settings = get_settings()
    result = rebuild_observe_db(
        settings.agent_state_root,
        repo_full,
        db_path=db_path,
        size_warning_threshold_bytes=settings.observe_sqlite_size_warning_bytes,
    )
    click.echo(
        json.dumps(
            {
                "project": result.project,
                "db_path": str(result.db_path),
                "events_scanned": result.events_scanned,
                "events_projected": result.events_projected,
                "events_skipped": result.events_skipped,
                "last_ledger_sequence": result.last_ledger_sequence,
                "size_bytes": result.size_bytes,
                "size_warning": result.size_warning,
            },
            indent=2,
        )
    )
    if result.size_warning:
        click.echo(f"warning: {result.size_warning}", err=True)


@main.group(name="eval")
def eval_group() -> None:
    """Evaluation export, bake-off, and maintenance-eval dispatch."""


@eval_group.command("dispatch")
@click.option(
    "--session-root",
    type=click.Path(path_type=Path),
    default=None,
    help="Override EVAL_DISPATCH_SESSION_ROOT for create-only session records",
)
@click.option(
    "--engine",
    type=click.Choice(["official", "fake"]),
    default=None,
    help="Override EVAL_DISPATCH_ENGINE (default: official, or env)",
)
def eval_dispatch_cmd(session_root: Path | None, engine: str | None) -> None:
    """JSON-stdio adapter for maintenance_eval_dispatch.v1 (exact-SHA local workspace).

    Reads one JSON object from stdin::

        {"operation":"dispatch","request":{...maintenance_eval_dispatch.v1...}}
        {"operation":"get_session","session_id":"sess-…","project":"owner/repo"}

    Writes one JSON object to stdout. This is the trusted control-plane command
    pointed at by maintenance-evals ``JsonCommandControlPlaneClient``.
    """
    from agent_control.eval_dispatch import EvalDispatchError, handle_message, main as _unused

    del _unused
    if session_root is not None:
        os.environ["EVAL_DISPATCH_SESSION_ROOT"] = str(session_root)
    if engine is not None:
        os.environ["EVAL_DISPATCH_ENGINE"] = engine
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"invalid JSON: {exc}") from exc
    try:
        response = handle_message(payload)
    except EvalDispatchError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(response))


@eval_group.command("export")
@click.option("--repo", "project", required=True, help="owner/repo")
@click.option("--run-id", required=True, help="run-… id")
@click.option(
    "--out",
    "output_dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory (default: state_root/eval-exports)",
)
def eval_export_cmd(project: str, run_id: str, output_dir: Path | None) -> None:
    """Export content-addressed eval_bundle.v1 (does not touch production memory)."""
    from agent_control.eval_export import export_eval_bundle, verify_eval_bundle_sha256
    from agent_shared.repo_identity import normalize_repo_full_name

    repo_full = normalize_repo_full_name(project)
    if repo_full is None:
        raise click.ClickException(f"invalid repo: {project}")
    settings = get_settings()
    out_dir = output_dir or (settings.agent_state_root / "eval-exports")
    bundle, path = export_eval_bundle(
        settings.agent_state_root,
        project=repo_full,
        run_id=run_id,
        output_dir=out_dir,
    )
    if not verify_eval_bundle_sha256(bundle):
        raise click.ClickException("eval_bundle_sha256 mismatch after export")
    if bundle.production_memory_touched:
        raise click.ClickException("export must not touch production memory")
    click.echo(
        json.dumps(
            {
                "path": str(path),
                "eval_bundle_sha256": bundle.eval_bundle_sha256,
                "memory_namespace": bundle.memory_namespace,
                "production_memory_touched": bundle.production_memory_touched,
                "events": len(bundle.timeline),
            },
            indent=2,
        )
    )


@eval_group.command("inspect-adapt")
@click.option(
    "--bundle",
    "bundle_path",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to eval_bundle.v1 JSON",
)
@click.option(
    "--out",
    "output_dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory (default: cwd/inspect-adapt)",
)
@click.option("--task-name", default=None, help="Inspect task name override")
@click.option(
    "--namespace",
    "bakeoff_namespace",
    default=None,
    help="Bake-off memory namespace (default: bakeoff/<bundle.ns>/<run_id>)",
)
def eval_inspect_adapt_cmd(
    bundle_path: Path,
    output_dir: Path | None,
    task_name: str | None,
    bakeoff_namespace: str | None,
) -> None:
    """Adapt a verified eval_bundle.v1 into inspect_adapt.v1 (V7 T01; no prod memory writes)."""
    from agent_control.inspect_adapter import InspectAdaptError, adapt_eval_bundle_file

    out_dir = output_dir or Path.cwd() / "inspect-adapt"
    try:
        task, path = adapt_eval_bundle_file(
            bundle_path,
            output_dir=out_dir,
            task_name=task_name,
            bakeoff_namespace=bakeoff_namespace,
        )
    except InspectAdaptError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        json.dumps(
            {
                "path": str(path),
                "schema_version": task.get("schema_version"),
                "task_name": task.get("task_name"),
                "samples": len(task.get("samples") or []),
                "source_eval_bundle_sha256": task.get("source_eval_bundle_sha256"),
                "memory_namespace": task.get("memory_namespace"),
                "production_memory_touched": task.get("production_memory_touched"),
            },
            indent=2,
        )
    )


@eval_group.command("bakeoff-run")
@click.option(
    "--bundle",
    "bundle_path",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to verified eval_bundle.v1 JSON",
)
@click.option(
    "--profile",
    "profile_id",
    default="all",
    show_default=True,
    help="Profile id A|B|C|D or 'all'",
)
@click.option(
    "--out",
    "output_dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory (default: cwd/bakeoff-runs)",
)
def eval_bakeoff_run_cmd(
    bundle_path: Path,
    profile_id: str,
    output_dir: Path | None,
) -> None:
    """Run bake-off profile(s) A–D against one fixture bundle (isolated namespaces)."""
    from agent_control.bakeoff_memory import BakeoffMemoryError
    from agent_control.bakeoff_profiles import (
        BakeoffProfileError,
        run_all_profiles_against_bundle,
        run_profile_against_bundle,
    )
    from agent_control.inspect_adapter import InspectAdaptError

    out_dir = output_dir or Path.cwd() / "bakeoff-runs"
    try:
        if profile_id.strip().lower() == "all":
            results = run_all_profiles_against_bundle(bundle_path, output_dir=out_dir)
        else:
            results = [
                run_profile_against_bundle(bundle_path, profile_id, output_dir=out_dir)
            ]
    except (BakeoffProfileError, InspectAdaptError, BakeoffMemoryError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        json.dumps(
            {
                "runs": [
                    {
                        "profile_id": doc.get("profile_id"),
                        "path": str(path),
                        "memory_namespace": doc.get("memory_namespace"),
                        "memory_isolation": doc.get("memory_isolation"),
                        "source_eval_bundle_sha256": doc.get("source_eval_bundle_sha256"),
                        "production_memory_touched": doc.get("production_memory_touched"),
                        "mode": doc.get("mode"),
                        "metrics": {
                            k: (doc.get("metrics") or {}).get(k)
                            for k in (
                                "ct102_verified_success",
                                "repair_iterations",
                                "fallback_count",
                                "policy_violations",
                                "tokens_input",
                                "tokens_output",
                                "cost_usd",
                                "wall_seconds",
                            )
                        },
                    }
                    for doc, path in results
                ],
                "count": len(results),
            },
            indent=2,
        )
    )


@eval_group.command("bakeoff-metrics")
@click.option(
    "--bundle",
    "bundle_path",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to verified eval_bundle.v1 JSON",
)
@click.option(
    "--out",
    "output_dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory (default: cwd/bakeoff-metrics)",
)
def eval_bakeoff_metrics_cmd(bundle_path: Path, output_dir: Path | None) -> None:
    """Extract bakeoff_metrics.v1 from an eval_bundle (V7 T03)."""
    from agent_control.bakeoff_metrics import build_metrics_for_bundle_file, write_metrics
    from agent_control.inspect_adapter import InspectAdaptError

    out_dir = output_dir or Path.cwd() / "bakeoff-metrics"
    try:
        metrics = build_metrics_for_bundle_file(bundle_path)
    except InspectAdaptError as exc:
        raise click.ClickException(str(exc)) from exc
    path = write_metrics(metrics, out_dir)
    click.echo(
        json.dumps(
            {
                "path": str(path),
                "schema_version": metrics.get("schema_version"),
                "ct102_verified_success": metrics.get("ct102_verified_success"),
                "repair_iterations": metrics.get("repair_iterations"),
                "fallback_count": metrics.get("fallback_count"),
                "policy_violations": metrics.get("policy_violations"),
                "tokens_input": metrics.get("tokens_input"),
                "tokens_output": metrics.get("tokens_output"),
                "cost_usd": metrics.get("cost_usd"),
                "wall_seconds": metrics.get("wall_seconds"),
                "production_memory_touched": False,
            },
            indent=2,
        )
    )


@eval_group.command("bakeoff-report")
@click.option(
    "--bundle",
    "bundle_path",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to verified eval_bundle.v1 JSON",
)
@click.option(
    "--out",
    "output_dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory (default: cwd/bakeoff-reports)",
)
def eval_bakeoff_report_cmd(bundle_path: Path, output_dir: Path | None) -> None:
    """Emit bakeoff_report.v1 comparing profiles A–D (V7 T05)."""
    from agent_control.bakeoff_memory import BakeoffMemoryError
    from agent_control.bakeoff_profiles import BakeoffProfileError
    from agent_control.bakeoff_report import BakeoffReportError, emit_bakeoff_report_for_bundle
    from agent_control.inspect_adapter import InspectAdaptError

    out_dir = output_dir or Path.cwd() / "bakeoff-reports"
    try:
        report, path, _ = emit_bakeoff_report_for_bundle(bundle_path, output_dir=out_dir)
    except (
        BakeoffReportError,
        BakeoffProfileError,
        InspectAdaptError,
        BakeoffMemoryError,
    ) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        json.dumps(
            {
                "path": str(path),
                "schema_version": report.get("schema_version"),
                "report_id": report.get("report_id"),
                "profiles_compared": report.get("profiles_compared"),
                "dry_run_metric_parity": report.get("dry_run_metric_parity"),
                "negative_transfer_detected": report.get("negative_transfer_detected"),
                "production_gates": {
                    "unbounded_recursion": report.get("production_gates", {}).get(
                        "unbounded_recursion"
                    ),
                    "injection_shadow_is_authority": report.get("production_gates", {}).get(
                        "injection_shadow_is_authority"
                    ),
                    "production_memory_touched": report.get("production_gates", {}).get(
                        "production_memory_touched"
                    ),
                    "all_passed": report.get("production_gates", {}).get("all_passed"),
                },
                "production_memory_touched": report.get("production_memory_touched"),
                "recommendation": report.get("recommendation"),
            },
            indent=2,
        )
    )


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


@memory.command("governance-check")
@click.option("--repo", "project", required=True, help="owner/repo")
@click.option("--issue", "issue_id", type=int, required=True)
@click.option(
    "--files",
    default="",
    help="Comma-separated file paths in fix scope (optional)",
)
@click.option(
    "--threshold",
    default=None,
    type=int,
    help="Override repeated-failure threshold (default from settings)",
)
def memory_governance_check(
    project: str,
    issue_id: int,
    files: str,
    threshold: int | None,
) -> None:
    """V5 T02: deny fix when repeated_failed_fix history lacks new evidence."""
    settings = get_settings()
    repo_full_name = normalize_repo_full_name(project)
    if repo_full_name is None:
        raise click.ClickException(f"invalid repo: {project}")
    from agent_control.memory.governance import memory_as_governance_check

    file_paths = [p.strip() for p in files.split(",") if p.strip()]
    decision = memory_as_governance_check(
        repo_full_name,
        issue_id,
        file_paths=file_paths or None,
        threshold=threshold,
        settings=settings,
    )
    click.echo(
        json.dumps(
            {
                "policy_decision": decision.policy_decision,
                "reason": decision.reason,
                "failure_class": decision.failure_class,
                "attempt_count": decision.attempt_count,
                "threshold": decision.threshold,
                "overlapping_files": decision.overlapping_files,
                "risk_tags": decision.risk_tags,
                "new_evidence": decision.new_evidence,
                "matched_run_ids": decision.matched_run_ids,
            },
            indent=2,
        )
    )
    if decision.policy_decision == "deny":
        raise SystemExit(2)


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


@main.group()
def agentfacts() -> None:
    """AgentFacts-lite signed capability / limitation manifests (V5 T01)."""


@agentfacts.command("check")
@click.option(
    "--repo-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=".",
    show_default=True,
)
@click.option(
    "--manifest",
    "manifest_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to agent-facts.json (default: <repo-root>/agent-facts.json)",
)
@click.option(
    "--require-hmac",
    is_flag=True,
    help="Fail when integrity.hmac is missing or invalid",
)
def agentfacts_check(repo_root: Path, manifest_path: Path | None, require_hmac: bool) -> None:
    """Fail when human/machine cards diverge or manifest is unsigned/stale."""
    from agent_control.agentfacts import verify_agentfacts

    settings = get_settings()
    secret = settings.agentfacts_signing_secret or None
    result = verify_agentfacts(
        repo_root,
        manifest_path=manifest_path,
        signing_secret=secret,
        require_hmac=require_hmac,
    )
    click.echo(json.dumps(result.as_dict(), indent=2))
    if not result.ok:
        raise click.ClickException("agentfacts check failed")


@agentfacts.command("sign")
@click.option(
    "--repo-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=".",
    show_default=True,
)
@click.option(
    "--out",
    "out_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Output path (default: <repo-root>/agent-facts.json)",
)
@click.option("--signed-by", default="CT103", show_default=True)
def agentfacts_sign(repo_root: Path, out_path: Path | None, signed_by: str) -> None:
    """Rebuild agent-facts.json from AGENT_CARD.md + agent-card.json."""
    from agent_control.agentfacts import build_manifest, write_manifest
    from agent_control.agentfacts.manifest import DEFAULT_MANIFEST_NAME, repo_paths

    settings = get_settings()
    secret = settings.agentfacts_signing_secret or None
    md_path, json_path, default_out = repo_paths(repo_root)
    target = out_path or default_out
    manifest = build_manifest(
        agent_card_md=md_path,
        agent_card_json=json_path,
        signing_secret=secret,
        signed_by=signed_by,
    )
    write_manifest(target, manifest)
    click.echo(
        json.dumps(
            {
                "ok": True,
                "path": str(target),
                "digest": manifest["integrity"]["digest"],
                "hmac": bool(manifest["integrity"].get("hmac")),
                "name": DEFAULT_MANIFEST_NAME,
            },
            indent=2,
        )
    )


@agentfacts.command("show")
@click.option(
    "--repo-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=".",
    show_default=True,
)
@click.option(
    "--manifest",
    "manifest_path",
    type=click.Path(path_type=Path),
    default=None,
)
def agentfacts_show(repo_root: Path, manifest_path: Path | None) -> None:
    """Print the committed AgentFacts-lite manifest."""
    from agent_control.agentfacts import load_manifest
    from agent_control.agentfacts.manifest import repo_paths

    _, _, default_manifest = repo_paths(repo_root)
    path = manifest_path or default_manifest
    click.echo(json.dumps(load_manifest(path), indent=2))


@main.group()
def mcp() -> None:
    """Read-only MCP state/graph/memory server (T11 / Phase 24)."""


@mcp.command("serve")
@click.option(
    "--log-path",
    type=click.Path(path_type=Path),
    default=None,
    help="Append JSONL tool-call audit log",
)
def mcp_serve(log_path: Path | None) -> None:
    """Run the read-only MCP server on stdio (for MCP Inspector)."""
    from agent_control.mcp.server import run_stdio

    run_stdio(log_path=log_path)


@mcp.command("list-tools")
def mcp_list_tools() -> None:
    """Print allowlisted read-only tool names (no write surface)."""
    from agent_control.mcp.registry import FORBIDDEN_TOOLS, list_tools

    click.echo(
        json.dumps(
            {
                "tools": [t["name"] for t in list_tools()],
                "forbidden": sorted(FORBIDDEN_TOOLS),
            },
            indent=2,
        )
    )


@mcp.command("call")
@click.argument("tool_name")
@click.option("--args", "args_json", default="{}", help="JSON object of tool arguments")
def mcp_call(tool_name: str, args_json: str) -> None:
    """Invoke one read-only MCP tool and print the schema-validated result."""
    from agent_control.mcp.registry import invoke_tool

    try:
        arguments = json.loads(args_json)
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"invalid --args JSON: {exc}") from exc
    if not isinstance(arguments, dict):
        raise click.ClickException("--args must be a JSON object")
    result = invoke_tool(tool_name, arguments)
    click.echo(json.dumps(result, indent=2, default=str))


@main.group(name="self-improve")
def self_improve() -> None:
    """V5 T06: gated self-improvement (prompt/workflow proposals as PRs only)."""


@self_improve.command("classify")
@click.option("--paths", required=True, help="Comma-separated repo-relative paths")
def self_improve_classify(paths: str) -> None:
    """Classify paths as gated (PR-only) vs other."""
    from agent_control.self_improve.paths import GATED_SELF_IMPROVE_GLOBS, classify_paths

    path_list = [p.strip() for p in paths.split(",") if p.strip()]
    classified = classify_paths(path_list)
    click.echo(
        json.dumps(
            {
                **classified,
                "gated_globs": list(GATED_SELF_IMPROVE_GLOBS),
                "mutation_channel": "gitea_pr_only",
            },
            indent=2,
        )
    )


@self_improve.command("check-in-prod")
@click.option(
    "--target",
    "target_root",
    required=True,
    type=click.Path(path_type=Path),
    help="Filesystem root that would be written (e.g. /opt/.../agent-control-plane)",
)
@click.option("--paths", required=True, help="Comma-separated paths to write")
def self_improve_check_in_prod(target_root: Path, paths: str) -> None:
    """Deny gated-path writes into a live deploy root (no in-prod self-edit)."""
    from agent_control.self_improve.gate import (
        decision_as_dict,
        evaluate_in_prod_self_edit,
    )

    path_list = [p.strip() for p in paths.split(",") if p.strip()]
    decision = evaluate_in_prod_self_edit(target_root, path_list)
    click.echo(json.dumps(decision_as_dict(decision), indent=2))
    if decision.policy_decision == "deny":
        raise SystemExit(2)


@self_improve.command("propose")
@click.option("--repo", "project", required=True, help="owner/repo")
@click.option(
    "--path",
    "file_path",
    default=None,
    help="Gated path to propose (default: .agent/self_improve/PROPOSALS.md probe)",
)
@click.option(
    "--content-file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="File whose contents become the proposed blob",
)
@click.option("--note", default="v5-t06", help="Note embedded in probe content")
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--base", default="main")
def self_improve_propose(
    project: str,
    file_path: str | None,
    content_file: Path | None,
    note: str,
    dry_run: bool,
    base: str,
) -> None:
    """Open a PR for a gated prompt/workflow/policy change (CT103 Gitea API)."""
    from agent_control.self_improve.propose import (
        FileProposal,
        propose_probe_pr,
        propose_self_improve,
        result_as_dict,
    )

    if file_path is None and content_file is None:
        result = propose_probe_pr(project=project, note=note, dry_run=dry_run)
    else:
        if not file_path:
            raise click.ClickException("--path required when --content-file is set")
        if content_file is not None:
            content = content_file.read_text(encoding="utf-8")
        else:
            from agent_control.self_improve.propose import build_probe_content

            content = build_probe_content(note=note)
        result = propose_self_improve(
            project=project,
            files=[FileProposal(path=file_path, content=content)],
            dry_run=dry_run,
            base=base,
        )
    click.echo(json.dumps(result_as_dict(result), indent=2))
    if not result.ok:
        raise SystemExit(2)


# Export verify_hmac for tests
__all__ = ["main", "verify_hmac"]

if __name__ == "__main__":
    main()
