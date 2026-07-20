"""SARIF → Orbit graph security/evidence nodes (V5 T05).

Attaches static-analysis findings as evidence edges only. Does **not** expand
Risk 2 policy, gate `/agent fix`, or auto-remediate. Operator / CI Risk 0–1 path.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_control.config import Settings, get_settings
from agent_control.graph.provenance import annotate_edge
from agent_control.graph.store import GraphStore

REPORT_SCHEMA = "sarif_ingest_report.v1"
SARIF_EXTRACTOR_VERSION = "sarif-t05.1"

SARIF_EDGE_KINDS = frozenset(
    {
        "finding_affects_file",
        "tool_run_produced_finding",
        "tool_run_covers_repo",
    }
)

# Evidence attach is read-only governance signal — never raises Risk 2.
RISK_CLASS_CEILING = 1


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _uri_to_repo_path(uri: str) -> str:
    """Normalize SARIF artifact URI to a repo-relative path."""
    raw = (uri or "").strip().replace("\\", "/")
    if raw.startswith("file:///"):
        raw = raw[len("file:///") :]
    elif raw.startswith("file://"):
        raw = raw[len("file://") :]
    # Drop drive-letter absolute paths / leading slash noise for homelab URIs.
    if len(raw) >= 3 and raw[1] == ":" and raw[2] == "/":
        raw = raw[3:]
    return raw.lstrip("./")


def _finding_id(
    *,
    rule_id: str,
    path: str,
    start_line: int | None,
    message: str,
    partial_fp: str | None,
) -> str:
    if partial_fp:
        fp = partial_fp
    else:
        material = f"{rule_id}|{path}|{start_line or 0}|{message}"
        fp = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    safe_rule = rule_id.replace(" ", "_")[:120] or "unknown"
    return f"finding:sarif:{safe_rule}:{fp}"


def _level_to_confidence(level: str | None) -> str:
    lvl = (level or "warning").lower()
    if lvl in {"error", "critical"}:
        return "high"
    if lvl in {"note", "none", "informational"}:
        return "low"
    return "medium"


def parse_sarif_runs(payload: dict[str, Any], *, content_hash: str) -> list[dict[str, Any]]:
    """Extract normalized findings + edges from a SARIF document."""
    runs_out: list[dict[str, Any]] = []
    for run_idx, run in enumerate(payload.get("runs") or []):
        if not isinstance(run, dict):
            continue
        tool = ((run.get("tool") or {}).get("driver") or {}) if isinstance(run.get("tool"), dict) else {}
        tool_name = str(tool.get("name") or "sarif").strip() or "sarif"
        automation = run.get("automationDetails") if isinstance(run.get("automationDetails"), dict) else {}
        guid = str(automation.get("guid") or "").strip()
        run_key = guid or f"{tool_name}:{content_hash[:12]}:{run_idx}"
        tool_run_id = f"tool_run:sarif:{run_key}"

        findings: list[dict[str, Any]] = []
        edges: list[dict[str, str]] = []
        files: set[str] = set()

        edges.append(
            annotate_edge(
                {
                    "kind": "tool_run_covers_repo",
                    "src_kind": "tool_run",
                    "src": tool_run_id,
                    "dst_kind": "repo",
                    "dst": "repo:__PROJECT__",  # filled by caller
                    "confidence": "high",
                },
                provenance="static_analysis",
                confidence="high",
            )
        )

        for result in run.get("results") or []:
            if not isinstance(result, dict):
                continue
            rule_id = str(result.get("ruleId") or "unknown").strip() or "unknown"
            level = str(result.get("level") or "warning")
            message_obj = result.get("message") if isinstance(result.get("message"), dict) else {}
            message = str(message_obj.get("text") or "").strip()
            partial = result.get("partialFingerprints")
            partial_fp = None
            if isinstance(partial, dict):
                for key in ("primaryLocationLineHash", "stableId", "contextRegionHash"):
                    if partial.get(key):
                        partial_fp = str(partial[key])
                        break

            locations = result.get("locations") or []
            if not locations:
                locations = [{}]

            for loc in locations:
                if not isinstance(loc, dict):
                    continue
                phys = loc.get("physicalLocation") if isinstance(loc.get("physicalLocation"), dict) else {}
                artifact = (
                    phys.get("artifactLocation") if isinstance(phys.get("artifactLocation"), dict) else {}
                )
                region = phys.get("region") if isinstance(phys.get("region"), dict) else {}
                path = _uri_to_repo_path(str(artifact.get("uri") or ""))
                if not path:
                    continue
                start_line = region.get("startLine")
                try:
                    start_line_i = int(start_line) if start_line is not None else None
                except (TypeError, ValueError):
                    start_line_i = None

                fid = _finding_id(
                    rule_id=rule_id,
                    path=path,
                    start_line=start_line_i,
                    message=message,
                    partial_fp=partial_fp,
                )
                files.add(path)
                confidence = _level_to_confidence(level)
                findings.append(
                    {
                        "id": fid,
                        "rule_id": rule_id,
                        "level": level,
                        "message": message[:500],
                        "path": path,
                        "start_line": start_line_i,
                        "tool": tool_name,
                        "tool_run": tool_run_id,
                    }
                )
                edges.append(
                    annotate_edge(
                        {
                            "kind": "finding_affects_file",
                            "src_kind": "finding",
                            "src": fid,
                            "dst_kind": "file",
                            "dst": f"file:{path}",
                            "confidence": confidence,
                        },
                        provenance="static_analysis",
                        confidence=confidence,
                    )
                )
                edges.append(
                    annotate_edge(
                        {
                            "kind": "tool_run_produced_finding",
                            "src_kind": "tool_run",
                            "src": tool_run_id,
                            "dst_kind": "finding",
                            "dst": fid,
                            "confidence": confidence,
                        },
                        provenance="static_analysis",
                        confidence=confidence,
                    )
                )

        runs_out.append(
            {
                "tool": tool_name,
                "tool_run": tool_run_id,
                "findings": findings,
                "edges": edges,
                "files": sorted(files),
            }
        )
    return runs_out


def _bind_project(edges: list[dict[str, str]], repo: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for edge in edges:
        e = dict(edge)
        if e.get("dst") == "repo:__PROJECT__":
            e["dst"] = f"repo:{repo}"
        out.append(e)
    return out


def ingest_sarif(
    repo: str,
    sarif_path: Path,
    *,
    settings: Settings | None = None,
    store: GraphStore | None = None,
    replace_same_hash: bool = True,
) -> dict[str, Any]:
    """Parse SARIF and attach finding/security evidence edges to the Orbit graph.

    Returns a report dict. Never expands Risk 2 gates.
    """
    settings = settings or get_settings()
    path = Path(sarif_path)
    warnings: list[str] = []
    now = datetime.now(timezone.utc).isoformat()

    if not path.is_file():
        return {
            "schema": REPORT_SCHEMA,
            "ok": False,
            "repo": repo,
            "sarif_path": str(path),
            "findings_count": 0,
            "edges_attached": 0,
            "files_touched": [],
            "findings": [],
            "risk_tags": [],
            "risk_class_ceiling": RISK_CLASS_CEILING,
            "blocks_risk2": False,
            "warnings": [f"sarif file not found: {path}"],
            "ingested_at": now,
        }

    raw = path.read_bytes()
    content_hash = _sha256_hex(raw)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {
            "schema": REPORT_SCHEMA,
            "ok": False,
            "repo": repo,
            "sarif_path": str(path),
            "content_sha256": content_hash,
            "findings_count": 0,
            "edges_attached": 0,
            "files_touched": [],
            "findings": [],
            "risk_tags": [],
            "risk_class_ceiling": RISK_CLASS_CEILING,
            "blocks_risk2": False,
            "warnings": [f"invalid sarif json: {exc}"],
            "ingested_at": now,
        }

    if not isinstance(payload, dict):
        return {
            "schema": REPORT_SCHEMA,
            "ok": False,
            "repo": repo,
            "sarif_path": str(path),
            "content_sha256": content_hash,
            "findings_count": 0,
            "edges_attached": 0,
            "files_touched": [],
            "findings": [],
            "risk_tags": [],
            "risk_class_ceiling": RISK_CLASS_CEILING,
            "blocks_risk2": False,
            "warnings": ["sarif root must be a JSON object"],
            "ingested_at": now,
        }

    parsed_runs = parse_sarif_runs(payload, content_hash=content_hash)
    if not parsed_runs:
        warnings.append("no runs[] in SARIF document")

    all_findings: list[dict[str, Any]] = []
    all_edges: list[dict[str, str]] = []
    all_files: set[str] = set()
    tool_runs: list[str] = []

    for run in parsed_runs:
        all_findings.extend(run["findings"])
        all_edges.extend(_bind_project(run["edges"], repo))
        all_files.update(run["files"])
        tool_runs.append(run["tool_run"])

    store = store or GraphStore(settings.graph_db_path)
    store.init_schema()
    store.ensure_repo(repo)
    if all_files:
        store.upsert_files(repo, sorted(all_files))

    attached = store.append_edges(
        repo,
        all_edges,
        source_sha=content_hash,
        extractor_version=SARIF_EXTRACTOR_VERSION,
        replace_source_sha=replace_same_hash,
        replace_kinds=SARIF_EDGE_KINDS if replace_same_hash else None,
    )

    risk_tags = ["security_finding"] if all_findings else []
    return {
        "schema": REPORT_SCHEMA,
        "ok": True,
        "repo": repo,
        "sarif_path": str(path),
        "content_sha256": content_hash,
        "tool_runs": tool_runs,
        "findings_count": len(all_findings),
        "edges_attached": attached,
        "files_touched": sorted(all_files),
        "findings": all_findings,
        "risk_tags": risk_tags,
        "risk_class_ceiling": RISK_CLASS_CEILING,
        "blocks_risk2": False,
        "extractor_version": SARIF_EXTRACTOR_VERSION,
        "warnings": warnings,
        "ingested_at": now,
    }
