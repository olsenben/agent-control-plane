"""Eval/production ContextPack V2 factory (VExp W1-E/F).

Builds a constructor-injected ``ContextBuilder`` with real providers. Telemetry
is emitted from ``build_trace`` after ``build`` returns. The builder stays pure.

Eval uses the existing exact-SHA workspace (``from_eval`` snapshot adapter; no
re-clone). Production V2 materializes a detached SHA workspace then
``from_production``. Production default remains v1 ``compile_context_pack``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from agent_control.context.builder import ContextBuilder
from agent_control.context.providers.graph import GraphProvider
from agent_control.context.providers.lexical import LexicalEvidenceProvider
from agent_control.context.providers.symbols import SymbolEvidenceProvider
from agent_control.context.repo_snapshot import (
    from_eval as snapshot_from_eval,
)
from agent_control.context.repo_snapshot import (
    from_production as snapshot_from_production,
)
from agent_control.context.v1_adapter import render_v2
from agent_control.context.workspace import materialize_exact_sha_workspace
from agent_control.telemetry.taxonomy import emit_experience_event
from agent_shared.hash_utils import canonical_json_hash, sha256_text
from agent_shared.models.context_pack_v2 import ContextPackV2
from agent_shared.models.evidence_query import (
    EVIDENCE_CLASSES,
    ContextBuildResult,
    ContextBuildTrace,
    ContextTaskSpec,
    EvidenceBudget,
)
from agent_shared.models.experience_events import (
    ExperienceEventEnvelope,
    TreatmentExposure,
)
from agent_shared.models.repo_snapshot import RepoSnapshot

ContextMode = Literal["baseline_v1", "context_v2_lexical", "context_v2"]

CONTEXT_MODE_BASELINE_V1: ContextMode = "baseline_v1"
CONTEXT_MODE_V2_LEXICAL: ContextMode = "context_v2_lexical"
CONTEXT_MODE_V2: ContextMode = "context_v2"
CONTEXT_MODES: tuple[ContextMode, ...] = (
    CONTEXT_MODE_BASELINE_V1,
    CONTEXT_MODE_V2_LEXICAL,
    CONTEXT_MODE_V2,
)
V2_CONTEXT_MODES: frozenset[str] = frozenset({CONTEXT_MODE_V2_LEXICAL, CONTEXT_MODE_V2})

SCHEMA_VERSION_V1 = "context_pack.v1"
SCHEMA_VERSION_V2 = "context-pack.v2"


class ContextModeError(ValueError):
    """Unknown or illegal ``context_mode``."""


@dataclass
class V2DispatchResult:
    """Structured V2 pack plus treatment-integrity fields. Not pre-rendered text."""

    context_pack: ContextPackV2
    pack_dump: dict[str, Any]
    build_trace: ContextBuildTrace
    snapshot: RepoSnapshot
    rendered_text: str
    treatment_integrity: dict[str, Any]
    events: list[ExperienceEventEnvelope] = field(default_factory=list)


def resolve_context_mode(value: str | None) -> ContextMode:
    """Normalize a context_mode string. Empty becomes baseline_v1."""
    raw = (value or "").strip() or CONTEXT_MODE_BASELINE_V1
    if raw not in CONTEXT_MODES:
        raise ContextModeError(f"unknown context_mode: {raw!r}")
    return raw  # type: ignore[return-value]


def resolve_production_context_mode(settings: Any | None = None) -> ContextMode:
    """Production default is baseline_v1 (compile_context_pack)."""
    if settings is None:
        from agent_control.config import get_settings

        settings = get_settings()
    return resolve_context_mode(getattr(settings, "context_mode", None))


def default_evidence_budget() -> EvidenceBudget:
    return EvidenceBudget(
        max_items_by_class={cls: 12 for cls in EVIDENCE_CLASSES},
        max_chars_total=8000,
        max_snippet_chars=400,
    )


def make_context_builder(mode: str) -> ContextBuilder:
    """Same ContextBuilder class for eval and production. Providers via constructor."""
    resolved = resolve_context_mode(mode)
    if resolved == CONTEXT_MODE_BASELINE_V1:
        raise ContextModeError("baseline_v1 does not construct ContextBuilder")
    lexical = LexicalEvidenceProvider()
    if resolved == CONTEXT_MODE_V2_LEXICAL:
        return ContextBuilder(lexical=lexical, symbol=None, graph=None)
    return ContextBuilder(
        lexical=lexical,
        symbol=SymbolEvidenceProvider(),
        graph=GraphProvider(),
    )


def treatment_integrity_fields(
    *,
    pack: ContextPackV2,
    snapshot: RepoSnapshot,
    trace: ContextBuildTrace,
    rendered_text: str,
) -> dict[str, Any]:
    """Fields recorded on eval session telemetry. No prompt bodies."""
    return {
        "repo_snapshot_id": snapshot.snapshot_id,
        "target_sha": snapshot.target_sha,
        "context_pack_version": pack.schema_version,
        "context_pack_hash": canonical_json_hash(pack.model_dump(mode="json")),
        "rendered_context_hash": sha256_text(rendered_text),
        "evidence_provider_ids": list(trace.providers_invoked),
        "selected_evidence_ids": list(trace.selected_evidence_ids),
    }


def emit_context_events_from_trace(
    trace: ContextBuildTrace,
    *,
    session_id: str | None = None,
    run_id: str | None = None,
    treatment: TreatmentExposure | None = None,
) -> list[ExperienceEventEnvelope]:
    """Emit context.* events FROM the trace. Builder does not emit."""
    candidate = emit_experience_event(
        "context.candidate_evidence",
        payload={
            "providers_invoked": list(trace.providers_invoked),
            "provider_statuses": dict(trace.provider_statuses),
            "candidate_counts": dict(trace.candidate_counts),
        },
        treatment=treatment,
        session_id=session_id,
        run_id=run_id,
    )
    selected = emit_experience_event(
        "context.evidence_selected",
        payload={
            "selected_counts": dict(trace.selected_counts),
            "selected_evidence_ids": list(trace.selected_evidence_ids),
            "dropped_by_budget": dict(trace.dropped_by_budget),
            "chars_by_class": dict(trace.chars_by_class),
            "total_chars": trace.total_chars,
        },
        treatment=treatment,
        session_id=session_id,
        run_id=run_id,
    )
    return [candidate, selected]


def _finish(
    result: ContextBuildResult,
    snapshot: RepoSnapshot,
    *,
    session_id: str | None,
    run_id: str | None,
) -> V2DispatchResult:
    pack = result.context_pack
    rendered = render_v2(pack)
    integrity = treatment_integrity_fields(
        pack=pack,
        snapshot=snapshot,
        trace=result.build_trace,
        rendered_text=rendered,
    )
    treatment = TreatmentExposure(
        repo_snapshot_id=snapshot.snapshot_id,
        context_pack_version=pack.schema_version,
        evidence_provider_ids=list(result.build_trace.providers_invoked),
        recursive_invocations=0,
        repair_attempt_index=0,
    )
    events = emit_context_events_from_trace(
        result.build_trace,
        session_id=session_id,
        run_id=run_id,
        treatment=treatment,
    )
    return V2DispatchResult(
        context_pack=pack,
        pack_dump=pack.model_dump(mode="json"),
        build_trace=result.build_trace,
        snapshot=snapshot,
        rendered_text=rendered,
        treatment_integrity=integrity,
        events=events,
    )


def from_eval(
    *,
    repository_id: str,
    target_sha: str,
    workspace_path: str | Path,
    task: ContextTaskSpec,
    mode: str = CONTEXT_MODE_V2,
    evidence_budget: EvidenceBudget | None = None,
    session_id: str | None = None,
    run_id: str | None = None,
    repository_url_or_key: str | None = None,
) -> V2DispatchResult:
    """Build a V2 pack against an existing exact-SHA eval checkout. Does not re-clone."""
    snapshot = snapshot_from_eval(
        repository_id,
        target_sha,
        workspace_path,
        repository_url_or_key=repository_url_or_key,
    )
    builder = make_context_builder(mode)
    budget = evidence_budget or default_evidence_budget()
    built = builder.build(snapshot, task, budget)
    return _finish(built, snapshot, session_id=session_id, run_id=run_id)


def from_production(
    *,
    project: str,
    refs: Any,
    repo_url: str,
    dest: str | Path,
    task: ContextTaskSpec,
    mode: str = CONTEXT_MODE_V2,
    settings: Any | None = None,
    evidence_budget: EvidenceBudget | None = None,
    session_id: str | None = None,
    run_id: str | None = None,
) -> V2DispatchResult:
    """Materialize detached SHA workspace, then build. Never graph branch-tip cache."""
    target_sha = str(getattr(refs, "target_sha", None) or "")
    workspace = materialize_exact_sha_workspace(
        repo_url=repo_url,
        target_sha=target_sha,
        dest=dest,
        settings=settings,
    )
    snapshot = snapshot_from_production(
        project,
        refs,
        workspace,
        repository_url_or_key=repo_url,
    )
    builder = make_context_builder(mode)
    budget = evidence_budget or default_evidence_budget()
    built = builder.build(snapshot, task, budget)
    return _finish(built, snapshot, session_id=session_id, run_id=run_id)
