"""Run artifact directory management."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_shared.constants import RunStatus
from agent_shared.models.runs import AgentRunMetadata


def run_dir(runs_root: Path, project: str, run_id: str) -> Path:
    owner, repo = project.split("/", 1)
    return runs_root / owner / repo / "runs" / run_id


def ensure_run_dir(runs_root: Path, project: str, run_id: str) -> Path:
    path = run_dir(runs_root, project, run_id)
    path.mkdir(parents=True, exist_ok=True)
    (path / "events").mkdir(exist_ok=True)
    return path


def write_json(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def write_metadata(path: Path, metadata: AgentRunMetadata) -> None:
    write_json(path, metadata.model_dump(mode="json"))


def update_metadata_status(meta_path: Path, status: RunStatus, warnings: list[str] | None = None) -> None:
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    data["status"] = status.value if isinstance(status, RunStatus) else status
    if warnings:
        data.setdefault("warnings", []).extend(warnings)
    write_json(meta_path, data)


def update_metadata_engine(meta_path: Path, engine: str) -> None:
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    data["engine"] = engine
    write_json(meta_path, data)


def initial_metadata(job: dict[str, Any]) -> AgentRunMetadata:
    return AgentRunMetadata(
        run_id=job["run_id"],
        session_id=job["session_id"],
        workflow_id=job["workflow_id"],
        project=job["project"],
        flow=job["flow"],
        agent=job["agent"],
        risk_class=job["risk_class"],
        workflow_definition=job["workflow_definition"],
        flow_config_id=job["flow_config_id"],
        flow_version=job["flow_version"],
        trigger_event_id=job["trigger_event_id"],
        base_ref=job["base_ref"],
        target_sha=job.get("target_sha"),
        created_at=datetime.now(timezone.utc).isoformat(),
        status=RunStatus.CREATED,
    )
