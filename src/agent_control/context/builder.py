"""Pure ContextBuilderV2 (VExp W1-D).

Build is a function of snapshot, task, budget, and injected providers. It does
not emit telemetry, start a recursive worker, or import W1-A/B/C provider
modules. Unavailable provider diagnostics stay on the trace, never in the pack.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import cast

from agent_control.context.repo_snapshot import RepoSnapshotError, _git_head_sha
from agent_shared.hash_utils import canonical_json_hash
from agent_shared.models.context_pack_v2 import (
    ContextPackV2,
    ContextTask,
    CurrentEvidence,
    EvidenceItem,
    ExperienceSection,
)
from agent_shared.models.evidence_query import (
    EVIDENCE_CLASSES,
    ContextBuildResult,
    ContextBuildTrace,
    ContextTaskSpec,
    EvidenceBudget,
    EvidenceClass,
    EvidenceQuery,
    ProviderResult,
    ProviderStatus,
)
from agent_shared.models.repo_snapshot import RepoSnapshot

QueryFn = Callable[[RepoSnapshot, EvidenceQuery], ProviderResult]
ProviderLike = QueryFn | object

_EXACT_SHA_TRACE_KEY = "exact_sha"

_PATH_RE = re.compile(r"(?:[A-Za-z0-9_.-]+/)+\.?[A-Za-z0-9_.-]+")
_BACKTICK_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")

# Query / fill order. Step 8 (authorized_experience) is intentionally omitted.
_PROVIDER_STAGES: tuple[tuple[str, tuple[EvidenceClass, ...]], ...] = (
    ("lexical", ("lexical",)),
    ("symbol", ("symbols",)),
    ("graph", ("dependency_edges", "tests", "config", "architecture")),
)

_CLASS_SELECTION_ORDER: tuple[EvidenceClass, ...] = (
    "lexical",
    "symbols",
    "dependency_edges",
    "tests",
    "config",
    "architecture",
)


def recheck_exact_sha(snapshot: RepoSnapshot) -> str | None:
    """Return an error code if HEAD cannot be proven equal to ``target_sha``.

    Missing ``workspace_path`` fails closed. A git workspace requires
    ``git rev-parse HEAD == snapshot.target_sha``. Tests may monkeypatch this
    function or pass a snapshot from ``from_eval``.
    """
    path_raw = (snapshot.workspace_path or "").strip()
    if not path_raw:
        return "workspace_path_missing"
    workspace = Path(path_raw)
    git_meta = workspace / ".git"
    if not git_meta.exists():
        return "workspace_path_missing" if not workspace.exists() else "workspace_not_git"
    try:
        actual = _git_head_sha(workspace)
    except RepoSnapshotError:
        return "head_unreadable"
    if actual != snapshot.target_sha:
        return "head_mismatch"
    return None


class ContextBuilder:
    """Constructor-injected ContextBuilderV2. Production dispatch is not wired here."""

    def __init__(
        self,
        *,
        lexical: ProviderLike | None = None,
        symbol: ProviderLike | None = None,
        graph: ProviderLike | None = None,
    ) -> None:
        self._providers: dict[str, ProviderLike | None] = {
            "lexical": lexical,
            "symbol": symbol,
            "graph": graph,
        }

    def build(
        self,
        snapshot: RepoSnapshot,
        task: ContextTaskSpec,
        evidence_budget: EvidenceBudget,
        authorized_experience: Sequence[object] = (),
    ) -> ContextBuildResult:
        # Wave 1: authorized_experience is accepted for Protocol compatibility and ignored.
        if authorized_experience:
            authorized_experience = ()
        sha_error = recheck_exact_sha(snapshot)
        if sha_error is not None:
            return _empty_result(
                snapshot,
                task,
                evidence_budget,
                provider_statuses={_EXACT_SHA_TRACE_KEY: "error"},
            )

        mentioned_paths = _extract_paths(task.issue_text)
        mentioned_symbols = _extract_symbols(task.issue_text, task.failure_signature)
        candidates_by_class: dict[EvidenceClass, list[EvidenceItem]] = {
            cls: [] for cls in EVIDENCE_CLASSES
        }
        seen_keys: set[str] = set()
        providers_invoked: list[str] = []
        provider_statuses: dict[str, ProviderStatus] = {}

        for name, requested in _PROVIDER_STAGES:
            provider = self._providers.get(name)
            if provider is None:
                continue
            query = EvidenceQuery(
                query_text=task.issue_text,
                failure_signature=task.failure_signature,
                mentioned_paths=list(mentioned_paths),
                mentioned_symbols=list(mentioned_symbols),
                requested_classes=list(requested),
            )
            result = _invoke_provider(provider, snapshot, query)
            providers_invoked.append(name)
            provider_statuses[name] = result.status
            if result.status != "ok":
                continue
            fallback = requested[0]
            for item in result.evidence:
                cls = _classify(item, fallback)
                key = _item_key(item)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                candidates_by_class[cls].append(item)

        selected_by_class, trace_counts = _apply_budget(candidates_by_class, evidence_budget)
        current_evidence = CurrentEvidence(
            lexical=selected_by_class["lexical"],
            symbols=selected_by_class["symbols"],
            dependency_edges=selected_by_class["dependency_edges"],
            tests=selected_by_class["tests"],
            config=selected_by_class["config"],
            architecture=selected_by_class["architecture"],
        )
        selected_ids = [
            item.id
            for cls in _CLASS_SELECTION_ORDER
            for item in selected_by_class[cls]
            if item.id
        ]
        pack = ContextPackV2(
            task=ContextTask(
                project=task.project,
                issue_text=task.issue_text,
                source_sha=snapshot.target_sha,
            ),
            repo_snapshot=snapshot,
            current_evidence=current_evidence,
            experience=ExperienceSection(authorized_records=[]),
            recursive_evidence=[],
            budget={
                "max_chars_total": evidence_budget.max_chars_total,
                "max_snippet_chars": evidence_budget.max_snippet_chars,
                "total_chars": trace_counts["total_chars"],
            },
        )
        return ContextBuildResult(
            context_pack=pack,
            build_trace=ContextBuildTrace(
                providers_invoked=providers_invoked,
                provider_statuses=provider_statuses,
                candidate_counts=trace_counts["candidate_counts"],
                selected_counts=trace_counts["selected_counts"],
                selected_evidence_ids=selected_ids,
                dropped_by_budget=trace_counts["dropped_by_budget"],
                chars_by_class=trace_counts["chars_by_class"],
                total_chars=trace_counts["total_chars"],
            ),
        )


def _empty_result(
    snapshot: RepoSnapshot,
    task: ContextTaskSpec,
    evidence_budget: EvidenceBudget,
    *,
    provider_statuses: dict[str, ProviderStatus],
) -> ContextBuildResult:
    zeros = {cls: 0 for cls in EVIDENCE_CLASSES}
    pack = ContextPackV2(
        task=ContextTask(
            project=task.project,
            issue_text=task.issue_text,
            source_sha=snapshot.target_sha,
        ),
        repo_snapshot=snapshot,
        current_evidence=CurrentEvidence(),
        experience=ExperienceSection(authorized_records=[]),
        recursive_evidence=[],
        budget={
            "max_chars_total": evidence_budget.max_chars_total,
            "max_snippet_chars": evidence_budget.max_snippet_chars,
            "total_chars": 0,
        },
    )
    return ContextBuildResult(
        context_pack=pack,
        build_trace=ContextBuildTrace(
            providers_invoked=[],
            provider_statuses=provider_statuses,
            candidate_counts=dict(zeros),
            selected_counts=dict(zeros),
            selected_evidence_ids=[],
            dropped_by_budget=dict(zeros),
            chars_by_class=dict(zeros),
            total_chars=0,
        ),
    )


def _invoke_provider(
    provider: ProviderLike,
    snapshot: RepoSnapshot,
    query: EvidenceQuery,
) -> ProviderResult:
    query_fn = getattr(provider, "query", None)
    if not callable(query_fn):
        query_fn = provider if callable(provider) else None
    if query_fn is None:
        return ProviderResult(status="error", diagnostics={"reason": "provider_not_callable"})
    try:
        raw = query_fn(snapshot, query)
    except Exception as exc:
        return ProviderResult(
            status="error",
            diagnostics={"reason": "provider_exception", "type": type(exc).__name__},
        )
    if isinstance(raw, ProviderResult):
        return raw
    try:
        return ProviderResult.model_validate(raw)
    except Exception:
        return ProviderResult(status="error", diagnostics={"reason": "invalid_provider_result"})


def _classify(item: EvidenceItem, fallback: EvidenceClass) -> EvidenceClass:
    source = item.source
    if source in EVIDENCE_CLASSES:
        return cast(EvidenceClass, source)
    return fallback


def _item_key(item: EvidenceItem) -> str:
    if item.id:
        return item.id
    return canonical_json_hash(
        {"source": item.source, "text": item.text, "provenance": list(item.provenance)}
    )


def _extract_paths(issue_text: str) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for match in _PATH_RE.findall(issue_text or ""):
        if match not in seen:
            seen.add(match)
            ordered.append(match)
    return ordered


def _extract_symbols(issue_text: str, failure_signature: str) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    blob = f"{issue_text or ''}\n{failure_signature or ''}"
    for match in _BACKTICK_RE.findall(blob):
        if match not in seen:
            seen.add(match)
            ordered.append(match)
    return ordered


def _apply_budget(
    candidates_by_class: dict[EvidenceClass, list[EvidenceItem]],
    evidence_budget: EvidenceBudget,
) -> tuple[dict[EvidenceClass, list[EvidenceItem]], dict[str, object]]:
    selected_by_class: dict[EvidenceClass, list[EvidenceItem]] = {cls: [] for cls in EVIDENCE_CLASSES}
    candidate_counts = {cls: len(candidates_by_class[cls]) for cls in EVIDENCE_CLASSES}
    dropped_by_budget = {cls: 0 for cls in EVIDENCE_CLASSES}
    remaining_chars = evidence_budget.max_chars_total
    snippet_cap = evidence_budget.max_snippet_chars

    for cls in _CLASS_SELECTION_ORDER:
        item_cap = evidence_budget.max_items_by_class.get(cls)
        for item in candidates_by_class[cls]:
            if snippet_cap == 0:
                dropped_by_budget[cls] += 1
                continue
            text = item.text[:snippet_cap]
            if item_cap is not None and len(selected_by_class[cls]) >= item_cap:
                dropped_by_budget[cls] += 1
                continue
            if len(text) > remaining_chars:
                dropped_by_budget[cls] += 1
                continue
            chosen = item if text == item.text else item.model_copy(update={"text": text})
            selected_by_class[cls].append(chosen)
            remaining_chars -= len(text)

    chars_by_class = {
        cls: sum(len(item.text) for item in selected_by_class[cls]) for cls in EVIDENCE_CLASSES
    }
    selected_counts = {cls: len(selected_by_class[cls]) for cls in EVIDENCE_CLASSES}
    total_chars = sum(chars_by_class.values())
    return selected_by_class, {
        "candidate_counts": candidate_counts,
        "selected_counts": selected_counts,
        "dropped_by_budget": dropped_by_budget,
        "chars_by_class": chars_by_class,
        "total_chars": total_chars,
    }
