"""V7 T01 — framework-neutral → Inspect AI adapter for eval_bundle.v1."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_control.eval_export import verify_eval_bundle_sha256
from agent_shared.models.eval_bundle import EvalBundle


class InspectAdaptError(ValueError):
    """Adapter failed closed (integrity or schema)."""


def load_eval_bundle(path: Path) -> EvalBundle:
    """Load eval_bundle.v1 JSON and fail closed on SHA mismatch."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    bundle = EvalBundle.model_validate(raw)
    if not verify_eval_bundle_sha256(bundle):
        raise InspectAdaptError("eval_bundle_sha256 mismatch — refuse import")
    if bundle.schema_version != "eval_bundle.v1":
        raise InspectAdaptError(f"unsupported schema_version: {bundle.schema_version}")
    return bundle


def bundle_to_inspect_task(
    bundle: EvalBundle,
    *,
    task_name: str | None = None,
    bakeoff_namespace: str | None = None,
) -> dict[str, Any]:
    """Convert a verified EvalBundle into inspect_adapt.v1 (Inspect-loadable samples).

    Does not import inspect_ai (optional at runtime). Never sets production_memory_touched.
    """
    manifest = bundle.manifest or {}
    run_id = str(manifest.get("run_id") or "unknown")
    project = str(manifest.get("project") or "unknown")
    ns = bakeoff_namespace or f"bakeoff/{bundle.memory_namespace}/{run_id}"
    name = task_name or f"eval_bundle_{run_id}"

    # One primary sample: full timeline as input for controller bake-off scorers (later tickets).
    input_blob = {
        "project": project,
        "run_id": run_id,
        "command_kind": manifest.get("command_kind"),
        "timeline": bundle.timeline,
        "stages": bundle.stages,
    }
    sample = {
        "id": f"{project}:{run_id}",
        "input": json.dumps(input_blob, sort_keys=True, default=str),
        "target": "",
        "metadata": {
            "project": project,
            "run_id": run_id,
            "session_id": manifest.get("session_id"),
            "trace_id": manifest.get("trace_id"),
            "command_kind": manifest.get("command_kind"),
            "event_count": len(bundle.timeline),
            "stage_count": len(bundle.stages),
            "source_eval_bundle_sha256": bundle.eval_bundle_sha256,
            "memory_namespace": ns,
            "production_memory_touched": False,
        },
    }
    # Optional per-stage samples for ablation scorers.
    stage_samples: list[dict[str, Any]] = []
    for idx, stage in enumerate(bundle.stages):
        stage_name = (stage or {}).get("name") or f"stage_{idx}"
        stage_samples.append(
            {
                "id": f"{project}:{run_id}:{stage_name}",
                "input": json.dumps(stage, sort_keys=True, default=str),
                "target": str((stage or {}).get("status") or ""),
                "metadata": {
                    "kind": "stage",
                    "stage_name": stage_name,
                    "run_id": run_id,
                    "project": project,
                    "memory_namespace": ns,
                    "production_memory_touched": False,
                    "source_eval_bundle_sha256": bundle.eval_bundle_sha256,
                },
            }
        )

    return {
        "schema_version": "inspect_adapt.v1",
        "task_name": name,
        "samples": [sample, *stage_samples],
        "source_eval_bundle_sha256": bundle.eval_bundle_sha256,
        "memory_namespace": ns,
        "production_memory_touched": False,
        "inspect_ai_required": False,
        "notes": (
            "Framework-neutral Inspect adapter. Load samples into Inspect MemoryDataset "
            "when inspect_ai is installed; T02+ add profile scorers."
        ),
    }


def adapt_eval_bundle_file(
    bundle_path: Path,
    *,
    output_dir: Path,
    task_name: str | None = None,
    bakeoff_namespace: str | None = None,
) -> tuple[dict[str, Any], Path]:
    """Verify bundle → write inspect_adapt.v1 JSON under output_dir (no prod memory writes)."""
    bundle = load_eval_bundle(bundle_path)
    task = bundle_to_inspect_task(
        bundle, task_name=task_name, bakeoff_namespace=bakeoff_namespace
    )
    if task.get("production_memory_touched"):
        raise InspectAdaptError("adapter must not touch production memory")
    output_dir.mkdir(parents=True, exist_ok=True)
    digest = bundle.eval_bundle_sha256[:12]
    run_id = (bundle.manifest or {}).get("run_id") or "run"
    out = output_dir / f"inspect-{run_id}-{digest}.json"
    out.write_text(json.dumps(task, indent=2, sort_keys=True), encoding="utf-8")
    return task, out


def try_build_inspect_memory_dataset(task_doc: dict[str, Any]) -> Any | None:
    """Optional: build inspect_ai MemoryDataset when the package is installed."""
    try:
        from inspect_ai.dataset import MemoryDataset, Sample  # type: ignore
    except ImportError:
        return None
    samples = []
    for row in task_doc.get("samples") or []:
        samples.append(
            Sample(
                id=row.get("id"),
                input=row.get("input") or "",
                target=row.get("target") or "",
                metadata=row.get("metadata") or {},
            )
        )
    return MemoryDataset(samples)
