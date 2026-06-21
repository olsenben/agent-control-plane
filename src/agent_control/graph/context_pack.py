"""Context pack compiler for dispatch."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from agent_control.adr_compiler import list_related_adrs
from agent_control.config import Settings, get_settings
from agent_control.gitea_client import GiteaClient
from agent_control.graph.blast_radius import compute_blast_radius
from agent_control.memory.retrieval import PRIOR_MEMORY_HEADER, retrieve_prior_memory_dicts
from agent_control.project_registry import RefResolution
from agent_shared.models.context_pack import ContextPack
from agent_shared.models.jobs import TriggerContext
from agent_workers.rlm.budget import truncate_text

ISSUE_BUDGET = 4000
DIFF_BUDGET = 12000
ADR_BUDGET = 4000
BLAST_BUDGET = 2000
PRIOR_MEMORY_BUDGET = 3000
TOTAL_BUDGET = 24000


def _extract_paths_from_text(text: str) -> list[str]:
    patterns = [
        r"(?:^|\s)([a-zA-Z0-9_./-]+\.py)\b",
        r"(?:^|\s)(src/[a-zA-Z0-9_./-]+)",
    ]
    found: set[str] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            path = match.group(1).lstrip("./")
            if "/" in path or path.endswith(".py"):
                found.add(path.replace("\\", "/"))
    return sorted(found)


def _ripgrep_hits(repo_cache: Path, query: str, *, limit: int = 10) -> list[str]:
    if not query.strip() or not shutil.which("rg"):
        return []
    if not repo_cache.exists():
        return []
    try:
        proc = subprocess.run(
            ["rg", "-l", "--max-count", "1", query[:80], str(repo_cache)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    hits: list[str] = []
    for line in proc.stdout.splitlines():
        try:
            rel = Path(line).resolve().relative_to(repo_cache.resolve()).as_posix()
        except ValueError:
            rel = line
        hits.append(rel)
        if len(hits) >= limit:
            break
    return hits


def compile_context_pack(
    project: str,
    trigger_context: TriggerContext | dict[str, Any],
    refs: RefResolution | None = None,
    settings: Settings | None = None,
    *,
    changed_files: list[str] | None = None,
    issue_override: dict[str, Any] | None = None,
    diff_override: str | None = None,
) -> ContextPack:
    settings = settings or get_settings()
    if isinstance(trigger_context, dict):
        trigger_context = TriggerContext(**trigger_context)

    sources: list[str] = []
    budget: dict[str, int] = {}
    owner, repo_name = project.split("/", 1)

    issue_text: str | None = None
    diff_text: str | None = None
    files_for_blast: list[str] = list(changed_files or [])

    client = GiteaClient(settings)
    if issue_override is not None:
        issue_text = str(issue_override.get("body") or issue_override.get("title") or "")
        sources.append("gitea_issue_override")
    elif trigger_context.issue_number is not None:
        try:
            issue = client.get_issue(owner, repo_name, trigger_context.issue_number)
            issue_text = f"# {issue.get('title', '')}\n\n{issue.get('body', '')}".strip()
            sources.append("gitea_issue")
        except Exception:
            issue_text = None
            sources.append("gitea_issue_unavailable")

    if diff_override is not None:
        diff_text = diff_override
        sources.append("diff_override")
    elif trigger_context.pr_number is not None:
        try:
            diff_text = client.get_pull_diff(owner, repo_name, trigger_context.pr_number)
            sources.append("gitea_pr_diff")
        except Exception:
            diff_text = None
            sources.append("gitea_pr_diff_unavailable")

    if issue_text:
        issue_text = truncate_text(issue_text, ISSUE_BUDGET)
        budget["issue_text"] = len(issue_text)
        if not files_for_blast:
            files_for_blast = _extract_paths_from_text(issue_text)

    if diff_text:
        diff_text = truncate_text(diff_text, DIFF_BUDGET)
        budget["diff_text"] = len(diff_text)
        for line in diff_text.splitlines():
            if line.startswith("+++ b/") or line.startswith("--- a/"):
                path = line[6:].strip()
                if path and path != "/dev/null":
                    files_for_blast.append(path)

    blast = compute_blast_radius(project, files_for_blast, settings=settings)
    if not trigger_context.pr_number and not diff_text and not changed_files:
        extra = list(blast.missing_graph_edges)
        if "no diff available for issue-only review" not in extra:
            extra.append("no diff available for issue-only review")
        blast = blast.model_copy(update={"missing_graph_edges": sorted(set(extra))})

    blast_json = truncate_text(
        json.dumps(blast.model_dump(mode="json"), indent=2),
        BLAST_BUDGET,
    )
    budget["blast_radius"] = len(blast_json)
    sources.append("graph_blast_radius")

    adr_slice: list[dict] = []
    cache_root = settings.graph_snapshot_cache / project.replace("/", "__")
    adr_dir = cache_root / "docs" / "adr"
    if not adr_dir.is_dir():
        pkg_root = Path(__file__).resolve().parents[3]
        if project == "ai-sdlc-lab/agent-control-plane":
            local_adr = pkg_root / "docs" / "adr"
            if local_adr.is_dir():
                adr_dir = local_adr
    if blast.related_adrs and adr_dir.is_dir():
        adr_slice = list_related_adrs(adr_dir, blast.related_adrs)
        sources.append("adr_compiler")
    adr_text = truncate_text(json.dumps(adr_slice, indent=2), ADR_BUDGET)
    budget["adr_slice"] = len(adr_text)
    adr_slice = json.loads(adr_text) if adr_text else []

    search_hits: list[str] = []
    if issue_text and cache_root.exists():
        keywords = re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", issue_text)
        if keywords:
            search_hits = _ripgrep_hits(cache_root, keywords[0])
            if search_hits:
                sources.append("ripgrep")

    prior_memory: list[dict] = []
    if trigger_context.issue_number is not None:
        current_sha = refs.target_sha if refs is not None else None
        prior_memory = retrieve_prior_memory_dicts(
            project,
            trigger_context.issue_number,
            current_target_sha=current_sha,
            limit=5,
            max_chars=PRIOR_MEMORY_BUDGET,
            settings=settings,
        )
        if prior_memory:
            sources.append("memory_retrieval")
            budget["prior_memory"] = len(json.dumps(prior_memory))

    pack = ContextPack(
        project=project,
        issue_number=trigger_context.issue_number,
        pr_number=trigger_context.pr_number,
        issue_text=issue_text,
        diff_text=diff_text,
        adr_slice=adr_slice,
        blast_radius=blast,
        search_hits=search_hits,
        prior_memory=prior_memory,
        context_sources=sources,
        budget=budget,
    )

    total = sum(
        [
            len(pack.issue_text or ""),
            len(pack.diff_text or ""),
            len(json.dumps(pack.adr_slice)),
            len(json.dumps(pack.blast_radius.model_dump(mode="json"))),
        ]
    )
    if total > TOTAL_BUDGET:
        pack = pack.model_copy(update={"search_hits": []})
        if len(pack.diff_text or "") > DIFF_BUDGET // 2:
            pack = pack.model_copy(
                update={"diff_text": truncate_text(pack.diff_text or "", DIFF_BUDGET // 2)}
            )
        budget["total_clamped"] = total

    return pack


def render_context_pack_text(pack: ContextPack) -> str:
    sections: list[str] = ["=== context_pack.v1 ==="]
    if pack.issue_text:
        sections.append(f"--- issue ---\n{pack.issue_text}")
    if pack.diff_text:
        sections.append(f"--- diff ---\n{pack.diff_text}")
    if pack.adr_slice:
        sections.append(f"--- adr_slice ---\n{json.dumps(pack.adr_slice, indent=2)}")
    sections.append(
        f"--- blast_radius ---\n{json.dumps(pack.blast_radius.model_dump(mode='json'), indent=2)}"
    )
    if pack.search_hits:
        sections.append("--- search_hits ---\n" + "\n".join(pack.search_hits))
    if pack.prior_memory:
        sections.append(
            "--- prior_memory ---\n"
            f"{PRIOR_MEMORY_HEADER}\n\n"
            f"{json.dumps(pack.prior_memory, indent=2)}"
        )
    return "\n\n".join(sections)


def write_context_pack_export(pack: ContextPack, settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    export_dir = settings.graph_export_dir
    export_dir.mkdir(parents=True, exist_ok=True)
    name = f"context_pack_{pack.project.replace('/', '__')}"
    if pack.issue_number is not None:
        name += f"_issue_{pack.issue_number}"
    path = export_dir / f"{name}.json"
    path.write_text(pack.model_dump_json(indent=2), encoding="utf-8")
    return path
