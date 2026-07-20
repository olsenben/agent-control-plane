"""Gated path globs for self-improvement proposals (prompts / workflows / agent policy)."""

from __future__ import annotations

from agent_shared.closed_world.policy import any_glob_match, normalize_path

# Paths the agent may propose via PR only — never mutate in a live deploy root.
GATED_SELF_IMPROVE_GLOBS: tuple[str, ...] = (
    ".gitea/workflows/**",
    ".github/workflows/**",
    ".agent/**",
    "src/agent_workers/rlm/prompts.py",
    "**/prompts.py",
    ".agent/policies/tools.yaml",
)

# Deploy roots where writing gated paths counts as in-prod self-edit.
PRODUCTION_DEPLOY_ROOTS: tuple[str, ...] = (
    "/opt/ai-sdlc-lab/agent-control-plane",
)


def is_gated_self_improve_path(path: str) -> bool:
    return any_glob_match(path, list(GATED_SELF_IMPROVE_GLOBS))


def classify_paths(paths: list[str]) -> dict[str, list[str]]:
    """Split paths into gated vs non-gated (normalized, sorted, unique)."""
    gated: set[str] = set()
    other: set[str] = set()
    for raw in paths:
        try:
            norm = normalize_path(raw)
        except Exception:
            norm = (raw or "").strip().replace("\\", "/")
        if not norm:
            continue
        if is_gated_self_improve_path(norm):
            gated.add(norm)
        else:
            other.add(norm)
    return {"gated": sorted(gated), "other": sorted(other)}
