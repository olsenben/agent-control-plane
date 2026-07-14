"""Versioned CI artifacts under run ci/ directory (Slice 6E.1)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from agent_shared.models.ci import CiVerificationResult, WorkflowObservation


def ci_artifact_dir(artifact_root: Path) -> Path:
    return artifact_root / "ci"


def write_observation_artifact(
    artifact_root: Path,
    observation: WorkflowObservation,
) -> Path:
    """Immutable observation-<workflow_run_id>-attempt-<n>.json."""
    root = ci_artifact_dir(artifact_root)
    root.mkdir(parents=True, exist_ok=True)
    name = f"observation-{observation.workflow_run_id}-attempt-{observation.run_attempt}.json"
    path = root / name
    if path.exists():
        return path
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(observation.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, path)
    return path


def write_verification_current(
    artifact_root: Path,
    result: CiVerificationResult,
) -> Path:
    """Atomic replace of verification-current.json reducer snapshot."""
    root = ci_artifact_dir(artifact_root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "verification-current.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(result.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, path)
    return path


def load_verification_current(artifact_root: Path) -> CiVerificationResult | None:
    path = ci_artifact_dir(artifact_root) / "verification-current.json"
    if not path.is_file():
        return None
    try:
        return CiVerificationResult.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValueError):
        return None
