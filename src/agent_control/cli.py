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
from agent_control.events import append_event, deterministic_event_id
from agent_control.events import AgentEvent
from agent_control.model_router import ping_role, resolve_role_primary
from agent_control.queue import QUEUE_NAMES, STATE_WORKER_MAX_CONCURRENCY
from agent_control.repo_snapshot import snapshot_repo
from agent_control.state_reducer import ReductionMode, reduce_event_only
from agent_control.webhook_server import create_app, verify_hmac
from agent_control.workflows import dispatch as dispatch_wf
from agent_control.workflows import fix as fix_wf
from agent_control.workflows import review as review_wf
from agent_control.workflows import reward as reward_wf
from agent_control.workflows import tournament as tournament_wf


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
    path = append_event(settings.agent_state_root, event)
    click.echo(str(path))


@main.group()
def state() -> None:
    """State reducer commands."""


@state.command("reduce")
@click.option("--repo", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--mode",
    type=click.Choice([m.value for m in ReductionMode]),
    default=ReductionMode.EVENT_ONLY.value,
)
@click.option("--events-json", type=click.Path(exists=True, path_type=Path))
def state_reduce(repo: Path | None, mode: str, events_json: Path | None) -> None:
    """Reduce logical state. event-only mode needs no local checkout."""
    settings = get_settings()
    project = "unknown/unknown"
    if repo:
        project = f"{repo.parent.name}/{repo.name}" if repo.name != ".agent" else "local/repo"
    events_data: list[dict] = []
    if events_json:
        events_data = json.loads(events_json.read_text(encoding="utf-8"))
    logical = reduce_event_only(events_data, project)
    click.echo(logical.model_dump_json(indent=2))


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


@queue.command("enqueue-test")
@click.option("--queue", "queue_name", type=click.Choice(list(QUEUE_NAMES)), required=True)
def queue_enqueue_test(queue_name: str) -> None:
    click.echo(json.dumps({"queue": queue_name, "status": "stub"}))


@main.command("worker")
@click.option("--queues", multiple=True, type=click.Choice(list(QUEUE_NAMES)))
@click.option("--concurrency", default=1, type=int)
def worker_run(queues: tuple[str, ...], concurrency: int) -> None:
    if "state" in queues and concurrency > STATE_WORKER_MAX_CONCURRENCY:
        click.echo(
            "warning: state worker concurrency should be 1 at MVP",
            err=True,
        )
    click.echo(json.dumps({"queues": queues, "concurrency": concurrency, "status": "stub"}))


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


@main.command()
@click.option("--finding-id", required=True)
def fix_cmd(finding_id: str) -> None:
    click.echo(json.dumps(fix_wf.fix({}, finding_id)))


@main.command()
def repair() -> None:
    click.echo(json.dumps({"status": "stub", "workflow": "repair"}))


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
    click.echo("stub")


@gitea.command("open-pr")
def gitea_open_pr() -> None:
    click.echo("stub")


# Export verify_hmac for tests
__all__ = ["main", "verify_hmac"]

if __name__ == "__main__":
    main()
