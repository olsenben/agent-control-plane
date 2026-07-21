"""V7 T02 — bake-off profiles A–D (controller / context strategy ablation)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from agent_control.bakeoff_memory import (
    BakeoffMemoryFacade,
    assert_writebacks_isolated,
    marker_record,
)
from agent_control.inspect_adapter import (
    InspectAdaptError,
    adapt_eval_bundle_file,
    load_eval_bundle,
)
from agent_shared.models.eval_bundle import EvalBundle

PROFILE_IDS = ("A", "B", "C", "D")

_DEFAULT_CONFIG_CANDIDATES = (
    Path(__file__).resolve().parents[2] / "config" / "bakeoff_profiles.yaml",
    Path("/opt/ai-sdlc-lab/agent-control-plane/config/bakeoff_profiles.yaml"),
    Path("/app/config/bakeoff_profiles.yaml"),
    Path.cwd() / "config" / "bakeoff_profiles.yaml",
)


class BakeoffProfileError(ValueError):
    """Invalid profile id or config."""


@dataclass(frozen=True)
class BakeoffProfile:
    id: str
    name: str
    description: str
    controller_backend: str
    recursive_context_enabled: bool
    context_strategy: str
    max_depth: int
    max_subcalls: int
    max_graph_queries: int
    max_memory_records: int
    max_wall_seconds: int
    memory_namespace_prefix: str
    experimental: bool = False
    allow_repo_write: bool = False
    allow_network: bool = False
    unbounded_recursion: bool = False
    injection_shadow_is_authority: bool = False


def _default_config_path() -> Path:
    for candidate in _DEFAULT_CONFIG_CANDIDATES:
        if candidate.is_file():
            return candidate
    return _DEFAULT_CONFIG_CANDIDATES[0]


def load_bakeoff_profiles(path: Path | None = None) -> dict[str, BakeoffProfile]:
    cfg_path = path or _default_config_path()
    if not cfg_path.is_file():
        raise BakeoffProfileError(f"bakeoff profiles config missing: {cfg_path}")
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    if raw.get("schema_version") != "bakeoff_profiles.v1":
        raise BakeoffProfileError(f"unsupported schema_version: {raw.get('schema_version')}")
    defaults = raw.get("defaults") or {}
    profiles_raw = raw.get("profiles") or {}
    out: dict[str, BakeoffProfile] = {}
    for pid, body in profiles_raw.items():
        key = str(pid).upper()
        if key not in PROFILE_IDS:
            raise BakeoffProfileError(f"unknown profile id: {pid}")
        out[key] = BakeoffProfile(
            id=key,
            name=str(body.get("name") or key),
            description=str(body.get("description") or "").strip(),
            controller_backend=str(body.get("controller_backend") or "none"),
            recursive_context_enabled=bool(body.get("recursive_context_enabled", False)),
            context_strategy=str(body.get("context_strategy") or "deterministic_packet"),
            max_depth=int(body.get("max_depth") or 0),
            max_subcalls=int(body.get("max_subcalls") or 0),
            max_graph_queries=int(body.get("max_graph_queries") or 0),
            max_memory_records=int(body.get("max_memory_records") or 0),
            max_wall_seconds=int(body.get("max_wall_seconds") or 0),
            memory_namespace_prefix=str(
                body.get("memory_namespace_prefix") or f"bakeoff/profile-{key}"
            ),
            experimental=bool(body.get("experimental", False)),
            allow_repo_write=bool(
                body.get("allow_repo_write", defaults.get("allow_repo_write", False))
            ),
            allow_network=bool(body.get("allow_network", defaults.get("allow_network", False))),
            unbounded_recursion=bool(
                body.get("unbounded_recursion", defaults.get("unbounded_recursion", False))
            ),
            injection_shadow_is_authority=bool(
                body.get(
                    "injection_shadow_is_authority",
                    defaults.get("injection_shadow_is_authority", False),
                )
            ),
        )
    missing = [p for p in PROFILE_IDS if p not in out]
    if missing:
        raise BakeoffProfileError(f"profiles config missing ids: {missing}")
    # Hard gates — configs must not flip production-danger defaults.
    for p in out.values():
        if p.allow_repo_write or p.allow_network or p.unbounded_recursion:
            raise BakeoffProfileError(f"profile {p.id} violates bake-off safety gates")
        if p.injection_shadow_is_authority:
            raise BakeoffProfileError(f"profile {p.id} must not treat shadow as authority")
    return out


def get_profile(profile_id: str, path: Path | None = None) -> BakeoffProfile:
    key = profile_id.strip().upper()
    profiles = load_bakeoff_profiles(path)
    if key not in profiles:
        raise BakeoffProfileError(f"unknown profile: {profile_id}; expected one of {PROFILE_IDS}")
    return profiles[key]


def _namespace_for(profile: BakeoffProfile, bundle: EvalBundle) -> str:
    run_id = (bundle.manifest or {}).get("run_id") or "run"
    return f"{profile.memory_namespace_prefix.rstrip('/')}/{run_id}"


def run_profile_against_bundle(
    bundle_path: Path,
    profile_id: str,
    *,
    output_dir: Path,
    config_path: Path | None = None,
    memory: BakeoffMemoryFacade | None = None,
    seed_namespace: str | None = None,
) -> tuple[dict[str, Any], Path]:
    """Dry-run one profile against a verified eval_bundle (no production memory writes).

    Emits bakeoff_run.v1 + inspect_adapt.v1 under a profile-scoped namespace.
    Prepares an isolated bake-off memory namespace (fork/reset) and writes a
    profile-local marker so sibling profiles cannot see each other's writebacks.
    """
    profile = get_profile(profile_id, config_path)
    bundle = load_eval_bundle(bundle_path)
    ns = _namespace_for(profile, bundle)
    facade = memory or BakeoffMemoryFacade()
    isolation = facade.prepare_namespace(ns, seed_namespace=seed_namespace)

    task, inspect_path = adapt_eval_bundle_file(
        bundle_path,
        output_dir=output_dir / f"profile-{profile.id}" / "inspect",
        task_name=f"bakeoff_{profile.id}_{profile.name}",
        bakeoff_namespace=ns,
    )
    if task.get("production_memory_touched"):
        raise InspectAdaptError("bake-off must not touch production memory")

    marker_run_id = f"bakeoff-{profile.id}-{(bundle.manifest or {}).get('run_id') or 'run'}"
    facade.upsert(ns, marker_record(run_id=marker_run_id, profile_id=profile.id, namespace=ns))
    isolation = {
        **isolation,
        "record_count": facade.record_count(ns),
        "writeback_run_ids": sorted(facade.visible_run_ids(ns)),
        "production_memory_touched": facade.production_memory_touched,
    }

    sample_ids = [s.get("id") for s in (task.get("samples") or [])]
    from agent_control.bakeoff_metrics import (
        attach_metrics_to_bakeoff_run,
        extract_metrics_from_bundle,
        write_metrics,
    )

    metrics = extract_metrics_from_bundle(bundle)
    run_doc: dict[str, Any] = {
        "schema_version": "bakeoff_run.v1",
        "profile_id": profile.id,
        "profile_name": profile.name,
        "controller_backend": profile.controller_backend,
        "context_strategy": profile.context_strategy,
        "recursive_context_enabled": profile.recursive_context_enabled,
        "experimental": profile.experimental,
        "bounds": {
            "max_depth": profile.max_depth,
            "max_subcalls": profile.max_subcalls,
            "max_graph_queries": profile.max_graph_queries,
            "max_memory_records": profile.max_memory_records,
            "max_wall_seconds": profile.max_wall_seconds,
        },
        "memory_namespace": ns,
        "memory_isolation": isolation,
        "production_memory_touched": False,
        "unbounded_recursion": False,
        "injection_shadow_is_authority": False,
        "source_eval_bundle_sha256": bundle.eval_bundle_sha256,
        "inspect_adapt_path": str(inspect_path),
        "inspect_sample_ids": sample_ids,
        "sample_count": len(sample_ids),
        "mode": "dry_run",
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "notes": (
            "Bake-off dry-run with isolated bakeoff/* memory namespaces and "
            "bakeoff_metrics.v1; live controller invocation deferred to T05."
        ),
    }
    run_doc = attach_metrics_to_bakeoff_run(run_doc, metrics)
    out_dir = output_dir / f"profile-{profile.id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    digest = bundle.eval_bundle_sha256[:12]
    metrics_path = write_metrics(metrics, out_dir, profile_id=profile.id)
    run_doc["metrics_path"] = str(metrics_path)
    out_path = out_dir / f"bakeoff-{profile.id}-{digest}.json"
    out_path.write_text(json.dumps(run_doc, indent=2, sort_keys=True), encoding="utf-8")
    return run_doc, out_path


def run_all_profiles_against_bundle(
    bundle_path: Path,
    *,
    output_dir: Path,
    config_path: Path | None = None,
    memory: BakeoffMemoryFacade | None = None,
) -> list[tuple[dict[str, Any], Path]]:
    """Run profiles A–D against the same fixture bundle with shared isolation facade."""
    results: list[tuple[dict[str, Any], Path]] = []
    # Verify once up front so all four share the same integrity gate.
    load_eval_bundle(bundle_path)
    facade = memory or BakeoffMemoryFacade()
    for pid in PROFILE_IDS:
        results.append(
            run_profile_against_bundle(
                bundle_path,
                pid,
                output_dir=output_dir,
                config_path=config_path,
                memory=facade,
            )
        )
    namespaces = [doc["memory_namespace"] for doc, _ in results]
    assert_writebacks_isolated(facade, namespaces)
    return results
