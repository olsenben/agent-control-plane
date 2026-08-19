"""Immutable pre-invocation treatment-exposure artifacts (VExp W1 repair).

Persists structured ContextPack bytes, rendered context, hashes, and a
TreatmentExposure record BEFORE the solver consumes the pack. Session
finalization must link this record rather than rebuild it. ContextBuilder
stays pure; this module is integration-owned disk I/O.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_shared.hash_utils import canonical_json_hash, sha256_text
from agent_shared.models.experience_events import TreatmentExposure
from agent_shared.models.repo_snapshot import compute_snapshot_id

SCHEMA_VERSION = "pre_invocation_treatment.v1"
TREATMENT_FILENAME = "treatment_exposure.json"
PACK_FILENAME = "context_pack.json"
RENDERED_FILENAME = "rendered_context.txt"


class TreatmentArtifactError(RuntimeError):
    """Create-only treatment artifact could not be written or loaded."""


def persist_pre_invocation_treatment(
    *,
    artifact_dir: Path,
    session_id: str,
    run_id: str,
    context_mode: str,
    project: str,
    head_sha: str,
    request: dict[str, Any],
    arm_context: Any,
    job: dict[str, Any],
) -> dict[str, Any]:
    """Write pack/render/treatment files. Returns telemetry fields for the session.

    Must run after the job carries ``context_pack`` and before ``engine.run``.
    Create-only: a second persist in the same artifact dir is a harness error,
    not a reconstructed treatment for the same invocation.
    """
    artifact_dir.mkdir(parents=True, exist_ok=True)
    dest = artifact_dir / TREATMENT_FILENAME
    if dest.exists():
        raise TreatmentArtifactError(
            f"pre-invocation treatment already exists: {dest}"
        )

    from agent_workers.rlm.official_engine import (
        SCHEMA_VERSION_V1,
        load_job_context_pack,
        render_job_context_pack,
    )

    pack_raw = job.get("context_pack") or getattr(arm_context, "context_pack", None)
    fields: dict[str, Any] = dict(getattr(arm_context, "treatment_integrity", None) or {})
    rendered = ""
    pack_dump: dict[str, Any] | None = None
    schema = str(fields.get("context_pack_version") or "")
    if pack_raw:
        pack = load_job_context_pack({"context_pack": pack_raw})
        pack_dump = (
            pack.model_dump(mode="json") if hasattr(pack, "model_dump") else dict(pack_raw)
        )
        rendered = render_job_context_pack(pack)
        schema = str(getattr(pack, "schema_version", None) or schema or SCHEMA_VERSION_V1)
        computed = {
            "repo_snapshot_id": fields.get("repo_snapshot_id")
            or compute_snapshot_id(project, head_sha),
            "target_sha": fields.get("target_sha") or head_sha,
            "context_pack_version": schema,
            "context_pack_hash": canonical_json_hash(pack_dump),
            "rendered_context_hash": sha256_text(rendered),
            "evidence_provider_ids": list(fields.get("evidence_provider_ids") or []),
            "selected_evidence_ids": list(fields.get("selected_evidence_ids") or []),
            "selected_counts_by_class": dict(fields.get("selected_counts_by_class") or {}),
        }
        for key, value in computed.items():
            if not fields.get(key):
                fields[key] = value
        (artifact_dir / PACK_FILENAME).write_text(
            json.dumps(pack_dump, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
            encoding="utf-8",
        )
        (artifact_dir / RENDERED_FILENAME).write_text(rendered, encoding="utf-8")

    events = list(getattr(arm_context, "experience_events", None) or [])
    if events and not fields.get("selected_counts_by_class"):
        for event in events:
            if event.get("event_name") == "context.evidence_selected":
                payload = event.get("payload") or {}
                fields["selected_counts_by_class"] = dict(payload.get("selected_counts") or {})
                break

    treatment = TreatmentExposure(
        repo_snapshot_id=fields.get("repo_snapshot_id"),
        context_pack_version=fields.get("context_pack_version") or schema or None,
        evidence_provider_ids=list(fields.get("evidence_provider_ids") or []),
        recursive_invocations=0,
        repair_attempt_index=0,
    )
    model_id = (
        str(fields.get("primary_model") or "").strip()
        or os_model_id()
    )
    quantization = str(fields.get("quantization") or "").strip() or os_quantization()
    record = {
        "schema_version": SCHEMA_VERSION,
        "persisted_at": _utc_now(),
        "sequence_position": "pre_model_invocation",
        "session_id": session_id,
        "invocation_id": run_id,
        "experiment_arm": context_mode,
        "repository": project,
        "task_identity": str(request.get("upstream_task_id") or request.get("eval_run_id") or ""),
        "repo_snapshot_id": fields.get("repo_snapshot_id") or compute_snapshot_id(project, head_sha),
        "target_sha": fields.get("target_sha") or head_sha,
        "context_pack_version": fields.get("context_pack_version") or schema,
        "context_pack_hash": fields.get("context_pack_hash"),
        "rendered_context_hash": fields.get("rendered_context_hash"),
        "evidence_provider_ids": list(fields.get("evidence_provider_ids") or []),
        "selected_evidence_ids": list(fields.get("selected_evidence_ids") or []),
        "selected_counts_by_class": dict(fields.get("selected_counts_by_class") or {}),
        "model_id": model_id or None,
        "quantization": quantization or None,
        "context_pack_artifact": PACK_FILENAME if pack_dump is not None else None,
        "rendered_context_artifact": RENDERED_FILENAME if pack_dump is not None else None,
        "treatment": treatment.model_dump(mode="json"),
        "telemetry_fields": {
            **fields,
            "context_mode": context_mode,
            "invocation_id": run_id,
            "treatment_exposure_artifact": TREATMENT_FILENAME,
            "primary_model": model_id or None,
            "quantization": quantization or None,
        },
    }
    dest.write_text(
        json.dumps(record, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return dict(record["telemetry_fields"])


def load_pre_invocation_treatment(artifact_dir: Path) -> dict[str, Any] | None:
    """Return the create-only pre-invocation record, or None if absent."""
    path = artifact_dir / TREATMENT_FILENAME
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TreatmentArtifactError(f"invalid treatment artifact: {path}")
    return payload


def os_model_id() -> str:
    return (os.environ.get("MODEL_3080_NAME") or "").strip()


def os_quantization() -> str:
    return (os.environ.get("MODEL_3080_QUANT") or os.environ.get("MODEL_QUANT") or "").strip()


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
