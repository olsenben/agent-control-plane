"""Content-addressed evaluation bundle export (V6 T08)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_control.observe.projection import build_observation_projection
from agent_control.session.storage import load_session_by_run
from agent_shared.models.eval_bundle import EvalBundle


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def build_eval_bundle(
    state_root: Path,
    *,
    project: str,
    run_id: str,
    control_plane_commit: str | None = None,
    memory_namespace: str = "production",
) -> EvalBundle:
    """Build a framework-neutral eval_bundle.v1 for a run (read-only)."""
    session = load_session_by_run(state_root, project, run_id)
    projection = build_observation_projection(state_root, project=project, run_id=run_id)

    artifact_refs: list[dict[str, str]] = []
    if session is not None:
        for name, ref in (
            ("memory_preflight", session.memory_preflight),
            ("context_packet", session.context_packet),
            ("recursive_context", session.recursive_context),
            ("verification", session.verification),
        ):
            if ref is not None:
                artifact_refs.append(
                    {
                        "name": name,
                        "relative_path": getattr(ref, "relative_path", "") or "",
                        "digest": getattr(ref, "digest", "") or "",
                    }
                )

    timeline = [
        {
            "sequence": e.get("sequence"),
            "type": e.get("type"),
            "recorded_at": e.get("recorded_at"),
            "event_id": e.get("event_id"),
            "payload": e.get("payload"),
        }
        for e in projection.events
    ]

    manifest: dict[str, Any] = {
        "project": project,
        "run_id": run_id,
        "session_id": session.session_id if session else projection.session_id,
        "trace_id": session.trace_id if session else projection.trace_id,
        "source_sha": session.head_sha if session else "",
        "policy_source_sha": session.policy_source_sha if session else "",
        "command_kind": session.command_kind if session else projection.command_kind,
        "memory_namespace": memory_namespace,
        "control_plane_commit": control_plane_commit or "",
        "artifact_refs": artifact_refs,
        "observation_complete": projection.complete,
        "max_sequence": projection.max_sequence,
        "exported_at": _now(),
        "redaction": {"secrets_stripped": True, "note": "payloads copied as stored; no live secret fetch"},
    }

    body = {
        "schema_version": "eval_bundle.v1",
        "manifest": manifest,
        "timeline": timeline,
        "stages": [s.model_dump(mode="json") for s in projection.stages],
    }
    digest = _sha256_bytes(_canonical_json({"manifest": manifest, "timeline": timeline, "stages": body["stages"]}))
    return EvalBundle(
        manifest=manifest,
        timeline=timeline,
        stages=body["stages"],
        eval_bundle_sha256=digest,
        memory_namespace=memory_namespace,
        production_memory_touched=False,
    )


def export_eval_bundle(
    state_root: Path,
    *,
    project: str,
    run_id: str,
    output_dir: Path,
    control_plane_commit: str | None = None,
) -> tuple[EvalBundle, Path]:
    """Write eval bundle JSON under output_dir; never mutates production memory."""
    bundle = build_eval_bundle(
        state_root,
        project=project,
        run_id=run_id,
        control_plane_commit=control_plane_commit,
        memory_namespace="eval_export",
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"eval-{run_id}-{bundle.eval_bundle_sha256[:12]}.json"
    out.write_text(bundle.model_dump_json(indent=2), encoding="utf-8")
    return bundle, out


def verify_eval_bundle_sha256(bundle: EvalBundle) -> bool:
    recomputed = _sha256_bytes(
        _canonical_json(
            {
                "manifest": bundle.manifest,
                "timeline": bundle.timeline,
                "stages": bundle.stages,
            }
        )
    )
    return recomputed == bundle.eval_bundle_sha256
