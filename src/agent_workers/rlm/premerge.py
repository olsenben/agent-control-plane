"""Pre-merge CT103-owned platform context before model output validation."""

from __future__ import annotations

from typing import Any

from agent_shared.models.context_pack import ContextPack
from agent_shared.models.review import BlastRadiusContext


def _blast_radius_has_data(br: BlastRadiusContext) -> bool:
    return bool(
        br.affected_repos
        or br.affected_services
        or br.affected_tests
        or br.related_adrs
        or br.missing_graph_edges
    )


def build_prior_memory_used_from_pack(
    model_raw: Any,
    pack_prior_memory: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build prior_memory_used from context_pack; pack entries are authoritative."""
    if pack_prior_memory:
        entries: list[dict[str, Any]] = []
        for entry in pack_prior_memory:
            run_id = str(entry.get("run_id") or entry.get("source_run_id") or "").strip()
            if not run_id:
                continue
            entries.append(
                {
                    "run_id": run_id,
                    "record_id": entry.get("record_id"),
                    "used_for": "plan_context",
                }
            )
        return entries

    from agent_workers.rlm.normalizers import coerce_prior_memory_used

    return coerce_prior_memory_used(model_raw)


def premerge_platform_context(
    kind: str,
    raw_dict: dict[str, Any],
    context_pack: ContextPack | None,
    *,
    allowed_files: list[str] | None = None,
) -> dict[str, Any]:
    """Inject CT103-owned fields from context_pack before Pydantic validation."""
    if context_pack is None and not allowed_files:
        return raw_dict

    merged = dict(raw_dict)
    if context_pack is not None:
        pack_blast = context_pack.blast_radius
        if _blast_radius_has_data(pack_blast):
            merged["blast_radius"] = pack_blast.model_dump(mode="json")

        if kind == "plan" and context_pack.prior_memory:
            merged["prior_memory_used"] = build_prior_memory_used_from_pack(
                merged.get("prior_memory_used"),
                context_pack.prior_memory,
            )

        if context_pack.context_sources:
            merged["context_sources"] = list(context_pack.context_sources)

    if kind == "fix" and allowed_files is not None:
        merged.setdefault("files_changed", list(allowed_files))

    return merged
