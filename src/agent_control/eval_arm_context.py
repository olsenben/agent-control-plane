"""Workspace-local A/B/C0/C1 context for maintenance_eval_dispatch.v1.

This does not invent a new context policy. It applies the frozen H1 arms to a
local exact-SHA workspace without Gitea, Redis, or a webhook:

- local-direct: no pack, no recursive worker
- local-deterministic: ripgrep/FTS + path hits compiled into a context pack
- local-recursive-fallback: deterministic pack + conditional C0 recursion
- local-recursive-2070: deterministic pack + conditional C1 model controller

Recursive invocation stays conditional on the frozen preflight heuristic.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agent_control.graph.context_pack import _ripgrep_hits
from agent_control.memory.preflight import decide_recursive_context
from agent_control.recursive_context.telemetry import controller_telemetry_payload
from agent_control.recursive_context.worker import run_conditional_recursive_context
from agent_shared.models.context_pack import ContextPack
from agent_shared.models.memory_preflight import (
    THRESHOLD_MISSING_GRAPH_EDGES,
    MemoryPreflight,
)
from agent_shared.models.review import BlastRadiusContext

H1_ARMS = (
    "local-direct",
    "local-deterministic",
    "local-recursive-fallback",
    "local-recursive-2070",
)
FROZEN_C1_MODEL = "qwen2.5-coder:7b"
FORBIDDEN_CONTROLLER_MARKERS = ("gpt-4o-mini", "gpt-4.1", "gpt-4o", "openai")
PATH_RE = re.compile(r"(?:^|\s)([A-Za-z0-9_./-]+\.[A-Za-z0-9]{1,8})\b")


@dataclass
class ArmContext:
    """Context + controller telemetry applied for one H1 arm."""

    arm: str
    context_pack: dict[str, Any] | None
    retrieved_files: list[str]
    recursive_context_required: bool
    recursive_invoked: bool
    invocation_reasons: list[str]
    controller_telemetry: dict[str, Any]
    contamination: str | None = None
    missing_graph_edges: list[str] = field(default_factory=list)


RecursiveRunner = Callable[..., Any]


def apply_arm_context(
    *,
    arm: str,
    controller_backend: str,
    workspace: Path,
    project: str,
    question: str,
    session_id: str,
    run_id: str,
    source_sha: str,
    policy_source_sha: str,
    state_root: Path,
    recursive_runner: RecursiveRunner | None = None,
    diagnostic_memory_records: list[dict] | None = None,
) -> ArmContext:
    """Apply the frozen H1 arm to ``workspace``. Non-H1 arms are a no-op."""
    if arm not in H1_ARMS:
        return ArmContext(
            arm=arm,
            context_pack=None,
            retrieved_files=[],
            recursive_context_required=False,
            recursive_invoked=False,
            invocation_reasons=[],
            controller_telemetry={"controller_backend": controller_backend},
        )
    if arm == "local-direct":
        return ArmContext(
            arm=arm,
            context_pack=None,
            retrieved_files=[],
            recursive_context_required=False,
            recursive_invoked=False,
            invocation_reasons=[],
            controller_telemetry={
                "controller_backend": "none",
                "controller_model_invoked": False,
                "recursive_invoked": False,
                "recursive_context_required": False,
            },
        )

    hits, missing = _local_search(workspace, question)
    pack = ContextPack(
        project=project,
        source_sha=source_sha,
        policy_source_sha=policy_source_sha,
        issue_text=question[:4000],
        search_hits=hits,
        context_sources=["workspace_fts", "path_extract", *hits[:8]],
        blast_radius=BlastRadiusContext(missing_graph_edges=missing),
        budget={"search_hits": len(hits), "missing_graph_edges": len(missing)},
    )
    if diagnostic_memory_records:
        records = list(diagnostic_memory_records)
        pack = pack.model_copy(
            update={
                "prior_memory": records,
                "context_sources": [*pack.context_sources, "diagnostic_longitudinal_memory"],
                "budget": {
                    **dict(pack.budget),
                    "prior_memory": len(json.dumps(records)),
                },
            }
        )
    required, reasons, skip = decide_recursive_context(
        prior_memory_count=0,
        distinct_prior_root_causes=0,
        missing_graph_edge_count=len(missing),
    )
    telemetry: dict[str, Any] = {
        "controller_backend": controller_backend,
        "controller_model_invoked": False,
        "recursive_invoked": False,
        "recursive_context_required": required,
        "invocation_reasons": reasons,
        "skip_reason": skip,
        "missing_graph_edge_count": len(missing),
        "preflight_threshold_missing_graph_edges": THRESHOLD_MISSING_GRAPH_EDGES,
    }
    retrieved = list(dict.fromkeys(hits))
    if arm == "local-deterministic":
        return ArmContext(
            arm=arm,
            context_pack=pack.model_dump(mode="json"),
            retrieved_files=retrieved,
            recursive_context_required=required,
            recursive_invoked=False,
            invocation_reasons=reasons,
            controller_telemetry=telemetry,
            missing_graph_edges=missing,
        )

    preflight = MemoryPreflight(
        session_id=session_id,
        run_id=run_id,
        repo=project,
        source_sha=source_sha,
        policy_source_sha=policy_source_sha,
        created_at=datetime.now(timezone.utc).isoformat(),
        recursive_context_required=required,
        invocation_reasons=reasons,
        citations=["workspace_fts", "path_extract"],
        uncertainty=missing[:8],
    )
    runner = recursive_runner or run_conditional_recursive_context
    result = runner(
        preflight=preflight,
        question=question,
        state_root=state_root,
        force_invoke=False,
        controller_backend=controller_backend if controller_backend in {"deterministic", "model"} else None,
    )
    payload = controller_telemetry_payload(result)
    telemetry.update(payload)
    telemetry["recursive_invoked"] = bool(result.invoked)
    retrieved.extend(_paths_from_recursive(result))
    retrieved = list(dict.fromkeys(item for item in retrieved if item))
    contamination = _c1_contamination(arm=arm, telemetry=telemetry, invoked=bool(result.invoked))
    return ArmContext(
        arm=arm,
        context_pack=pack.model_dump(mode="json"),
        retrieved_files=retrieved,
        recursive_context_required=required,
        recursive_invoked=bool(result.invoked),
        invocation_reasons=list(result.invocation_reasons or reasons),
        controller_telemetry=telemetry,
        contamination=contamination,
        missing_graph_edges=missing,
    )


def write_arb_trajectory(path: Path, sample_id: str, files: list[str]) -> None:
    """Write one sample's context-acquisition trajectory for eval-trajectories."""
    steps = [
        {
            "step": index + 1,
            "tool": "read",
            "path": file_path,
            "is_final_context": True,
            "is_utilized_context": True,
        }
        for index, file_path in enumerate(files)
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"sample_id": sample_id, "trajectory": steps}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _local_search(workspace: Path, question: str) -> tuple[list[str], list[str]]:
    hits: list[str] = []
    if shutil.which("rg"):
        hits.extend(_ripgrep_hits(workspace, question[:80], limit=10))
    mentioned = _extract_paths(question)
    missing = [path for path in mentioned if not (workspace / path).exists()]
    existing = [path for path in mentioned if (workspace / path).is_file()]
    return list(dict.fromkeys([*hits, *existing])), missing


def _extract_paths(text: str) -> list[str]:
    found: list[str] = []
    for match in PATH_RE.finditer(text):
        path = match.group(1).lstrip("./").replace("\\", "/")
        if "/" in path or path.endswith((".py", ".ts", ".js", ".go", ".rs", ".md")):
            found.append(path)
    return list(dict.fromkeys(found))


def _paths_from_recursive(result: Any) -> list[str]:
    paths: list[str] = []
    for ref in getattr(result, "evidence_refs", []) or []:
        text = str(ref)
        if "/" in text or "." in text:
            paths.append(text.split(":", 1)[-1])
    for subcall in getattr(result, "subcalls", []) or []:
        args = getattr(subcall, "args", {}) or {}
        for key in ("path", "file", "target"):
            value = args.get(key)
            if isinstance(value, str) and value:
                paths.append(value)
    return paths


def _c1_contamination(*, arm: str, telemetry: dict[str, Any], invoked: bool) -> str | None:
    if arm != "local-recursive-2070" or not invoked:
        return None
    model_id = str(telemetry.get("controller_model_id") or "").lower()
    provider = str(telemetry.get("controller_provider") or "").lower()
    if any(marker in model_id for marker in FORBIDDEN_CONTROLLER_MARKERS):
        return f"c1_external_model:{model_id}"
    if telemetry.get("controller_data_left_homelab") is True:
        return "c1_data_left_homelab"
    if provider and provider != "gpu":
        return f"c1_non_gpu_provider:{provider}"
    if model_id and FROZEN_C1_MODEL not in model_id:
        return f"c1_identity_mismatch:{model_id}"
    return None


def workspace_file_listing(workspace: Path) -> list[str]:
    """Return tracked files when git is available; otherwise empty."""
    try:
        output = subprocess.check_output(
            ["git", "-C", str(workspace), "ls-files"],
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []
    return [line for line in output.splitlines() if line.strip()]
