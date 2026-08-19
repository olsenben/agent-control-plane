"""V1 ContextPack -> ContextPackV2 adapter and dual renderers (VExp W0-B).

``prior_memory`` maps to ``experience.compatibility.legacy_prior_memory`` only.
``authorized_records`` is always empty after ``v1_to_v2``; there is no
applicability gate today, so treating legacy memory as authorized is forbidden.
"""

from __future__ import annotations

import json
from typing import Any

from agent_control.graph.context_pack import (
    DIFF_BUDGET,
    TOTAL_BUDGET,
    render_context_pack_text,
)
from agent_shared.models.context_pack import ContextPack
from agent_shared.models.context_pack_v2 import (
    LEXICAL_SOURCE_V1_SEARCH_HITS,
    ContextPackV2,
    ContextTask,
    CurrentEvidence,
    EvidenceItem,
    ExperienceCompatibility,
    ExperienceSection,
    RepoSnapshot,
)
from agent_shared.models.review import BlastRadiusContext
from agent_workers.rlm.budget import truncate_text

_EVIDENCE_CLASSES = (
    "lexical",
    "symbols",
    "dependency_edges",
    "tests",
    "config",
    "architecture",
)


def v1_to_v2(pack: ContextPack, repo_snapshot: RepoSnapshot | None) -> ContextPackV2:
    """Convert a v1 solver pack. Never copies ``prior_memory`` into authorized_records."""
    lexical = [
        EvidenceItem(
            text=hit,
            source=LEXICAL_SOURCE_V1_SEARCH_HITS,
            provenance=[LEXICAL_SOURCE_V1_SEARCH_HITS, *pack.context_sources],
        )
        for hit in pack.search_hits
    ]
    return ContextPackV2(
        task=ContextTask(
            project=pack.project,
            issue_number=pack.issue_number,
            pr_number=pack.pr_number,
            issue_text=pack.issue_text,
            source_sha=pack.source_sha,
            policy_source_sha=pack.policy_source_sha,
        ),
        repo_snapshot=repo_snapshot,
        current_evidence=CurrentEvidence(lexical=lexical),
        experience=ExperienceSection(
            candidates_considered=[],
            authorized_records=[],
            rejected_records=[],
            compatibility=ExperienceCompatibility(
                legacy_prior_memory=[dict(item) for item in pack.prior_memory],
            ),
        ),
        recursive_evidence=[],
        budget=dict(pack.budget),
        provenance=[dict(item) for item in pack.provenance_items],
        v1_compat=pack.model_dump(mode="json"),
    )


def render_v1_compatible(pack: ContextPackV2) -> str:
    """Reproduce ``render_context_pack_text`` bytes, including TOTAL_BUDGET clamp."""
    v1 = _reconstruct_v1(pack)
    v1 = _apply_total_budget_clamp(v1)
    return render_context_pack_text(v1)


def render_v2(pack: ContextPackV2) -> str:
    """Model-visible V2 text. Omits legacy_prior_memory and rejected_records."""
    sections: list[str] = [f"=== {pack.schema_version} ==="]
    sections.append(f"--- task ---\n{json.dumps(pack.task.model_dump(mode='json'), indent=2)}")
    if pack.repo_snapshot is not None and pack.repo_snapshot is not object:
        snapshot_dump = _snapshot_dump(pack.repo_snapshot)
        if snapshot_dump is not None:
            sections.append(f"--- repo_snapshot ---\n{json.dumps(snapshot_dump, indent=2)}")
    evidence_lines: list[str] = []
    for name in _EVIDENCE_CLASSES:
        items: list[EvidenceItem] = getattr(pack.current_evidence, name)
        if not items:
            continue
        evidence_lines.append(f"{name}:")
        for item in items:
            evidence_lines.append(f"  [{item.source}] {item.text}")
    if evidence_lines:
        sections.append("--- current_evidence ---\n" + "\n".join(evidence_lines))
    if pack.experience.authorized_records:
        sections.append(
            "--- authorized_records ---\n"
            f"{json.dumps(pack.experience.authorized_records, indent=2)}"
        )
    if pack.recursive_evidence:
        rec_lines = [f"[{item.source}] {item.text}" for item in pack.recursive_evidence]
        sections.append("--- recursive_evidence ---\n" + "\n".join(rec_lines))
    return "\n\n".join(sections)


def _reconstruct_v1(pack: ContextPackV2) -> ContextPack:
    if pack.v1_compat:
        return ContextPack.model_validate(pack.v1_compat)
    return ContextPack(
        project=pack.task.project,
        issue_number=pack.task.issue_number,
        pr_number=pack.task.pr_number,
        source_sha=pack.task.source_sha,
        policy_source_sha=pack.task.policy_source_sha,
        issue_text=pack.task.issue_text,
        search_hits=[item.text for item in pack.current_evidence.lexical],
        prior_memory=list(pack.experience.compatibility.legacy_prior_memory),
        blast_radius=BlastRadiusContext(),
        budget=dict(pack.budget),
        provenance_items=[dict(item) for item in pack.provenance],
    )


def _apply_total_budget_clamp(pack: ContextPack) -> ContextPack:
    """Mirror compile_context_pack's TOTAL_BUDGET clamp on the v1-equivalent sections."""
    total = sum(
        [
            len(pack.issue_text or ""),
            len(pack.diff_text or ""),
            len(json.dumps(pack.adr_slice)),
            len(json.dumps(pack.blast_radius.model_dump(mode="json"))),
        ]
    )
    if total <= TOTAL_BUDGET:
        return pack
    updated: dict[str, Any] = {"search_hits": []}
    if len(pack.diff_text or "") > DIFF_BUDGET // 2:
        updated["diff_text"] = truncate_text(pack.diff_text or "", DIFF_BUDGET // 2)
    budget = dict(pack.budget)
    budget["total_clamped"] = total
    updated["budget"] = budget
    return pack.model_copy(update=updated)


def _snapshot_dump(snapshot: Any) -> dict[str, Any] | None:
    dump = getattr(snapshot, "model_dump", None)
    if callable(dump):
        return dump(mode="json")
    return None
