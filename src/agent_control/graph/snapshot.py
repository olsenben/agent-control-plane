"""Graph snapshot indexer."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from git import GitCommandError, Repo

from agent_control.adr_compiler import compile_adrs
from agent_control.config import Settings, get_settings
from agent_control.git_auth import git_non_interactive_env, resolve_authenticated_repo_url
from agent_control.graph.catalog import ingest_catalog
from agent_control.graph.extractors.python_imports import extract_file_import_edges
from agent_control.graph.store import GraphStore
from agent_control.project_registry import load_project_registry, resolve_project


def _sync_cached_repo(repo: Repo, branch: str, git_env: dict[str, str]) -> None:
    """Refresh shallow cache to match origin without merge/rebase prompts."""
    repo.remotes.origin.fetch(depth=1, env=git_env)
    repo.git.checkout(branch)
    repo.git.reset("--hard", f"origin/{branch}")


def _clone_or_update(project: str, dest: Path, settings: Settings) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cfg = resolve_project(project, settings=settings)
    clone_url = resolve_authenticated_repo_url(cfg.repo_url, settings)
    git_env = git_non_interactive_env(settings, repo_url=clone_url)
    try:
        if dest.exists() and (dest / ".git").exists():
            try:
                repo = Repo(dest)
                if clone_url != repo.remotes.origin.url:
                    repo.remotes.origin.set_url(clone_url)
                _sync_cached_repo(repo, cfg.default_branch, git_env)
                return dest
            except (GitCommandError, OSError, ValueError):
                shutil.rmtree(dest, ignore_errors=True)
        if dest.exists():
            shutil.rmtree(dest)
        try:
            Repo.clone_from(
                clone_url,
                dest,
                depth=1,
                branch=cfg.default_branch,
                env=git_env,
            )
        except GitCommandError as branch_exc:
            stderr = (branch_exc.stderr or str(branch_exc)).lower()
            if "remote branch" not in stderr and "not found in upstream origin" not in stderr:
                raise
            if dest.exists():
                shutil.rmtree(dest)
            Repo.clone_from(clone_url, dest, depth=1, env=git_env)
            repo = Repo(dest)
            if not repo.heads:
                raise RuntimeError(
                    f"repository has no commits or no branch {cfg.default_branch!r}: {project}"
                ) from branch_exc
        return dest
    except GitCommandError as exc:
        shutil.rmtree(dest, ignore_errors=True)
        hint = (
            "Set GITEA_BOT_TOKEN in .env, mount deploy ~/.git-credentials on control-plane "
            "(see docker-compose.yml), or pass --local-path to index a checkout on disk."
        )
        raise RuntimeError(f"git clone/fetch failed for {project}: {exc.stderr or exc}. {hint}") from exc
    except RuntimeError:
        shutil.rmtree(dest, ignore_errors=True)
        raise


def ingest_repo_path(
    project: str,
    repo_root: Path,
    store: GraphStore,
) -> dict[str, Any]:
    warnings: list[str] = []
    component, catalog_edge_rows = ingest_catalog(project, repo_root)
    services: list[str] = []
    if component:
        services.append(component.name)

    adr_dir = repo_root / "docs" / "adr"
    adr_facts = compile_adrs(adr_dir)
    adrs = [
        {
            "adr_id": f["adr_id"],
            "title": f.get("title", ""),
            "source_path": f.get("source_path", ""),
        }
        for f in adr_facts
    ]

    py_files, import_edges, import_warnings = extract_file_import_edges(project, repo_root)
    warnings.extend(import_warnings)

    tests: list[str] = []
    edges: list[dict[str, str]] = list(catalog_edge_rows)
    edges.extend(import_edges)

    for path in py_files:
        edges.append(
            {
                "kind": "repo_contains_file",
                "src_kind": "repo",
                "src": f"repo:{project}",
                "dst_kind": "file",
                "dst": f"file:{path}",
                "confidence": "high",
            }
        )
        if component:
            edges.append(
                {
                    "kind": "service_owns_file",
                    "src_kind": "service",
                    "src": f"service:{component.name}",
                    "dst_kind": "file",
                    "dst": f"file:{path}",
                    "confidence": "medium",
                }
            )

    if component:
        for ref in component.verified_by:
            if ref.endswith(".py") or "/test" in ref:
                tests.append(ref)
                edges.append(
                    {
                        "kind": "file_tested_by_test",
                        "src_kind": "file",
                        "src": f"file:{ref}",
                        "dst_kind": "test",
                        "dst": f"test:{ref}",
                        "confidence": "high",
                    }
                )

    store.upsert_snapshot(
        project,
        files=py_files,
        services=services,
        tests=tests,
        adrs=adrs,
        edges=edges,
    )

    return {
        "project": project,
        "files": len(py_files),
        "services": len(services),
        "tests": len(tests),
        "adrs": len(adrs),
        "edges": len(edges),
        "warnings": warnings,
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
    }


def snapshot_project(
    project: str,
    settings: Settings | None = None,
    *,
    local_path: Path | None = None,
    store: GraphStore | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    store = store or GraphStore(settings.graph_db_path)
    store.init_schema()

    if local_path is not None:
        repo_root = local_path.resolve()
    else:
        cache = settings.graph_snapshot_cache / project.replace("/", "__")
        repo_root = _clone_or_update(project, cache, settings)

    return ingest_repo_path(project, repo_root, store)


def snapshot_all(
    settings: Settings | None = None,
    *,
    repo: str | None = None,
    local_paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    store = GraphStore(settings.graph_db_path)
    store.init_schema()

    override = settings.graph_snapshot_repos_list()
    if repo:
        projects = [repo]
    elif override:
        projects = override
    else:
        projects = list(load_project_registry().keys())

    results: list[dict[str, Any]] = []
    for project in projects:
        local = (local_paths or {}).get(project)
        try:
            results.append(snapshot_project(project, settings=settings, local_path=local, store=store))
        except Exception as exc:
            results.append({"project": project, "error": str(exc), "status": "failed"})

    summary = store.summary()
    return {"summary": summary, "projects": results}
