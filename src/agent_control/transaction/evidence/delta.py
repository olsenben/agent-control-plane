"""Source vs candidate SAST finding differential. Provider-agnostic."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from agent_shared.hash_utils import canonical_json_hash

SCHEMA_DELTA = "security_evidence_delta.v1"


def _by_identity(findings: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in findings:
        key = str(item.get("identity") or "")
        if not key:
            key = canonical_json_hash(
                {
                    "rule_id": item.get("rule_id"),
                    "location_path": item.get("location_path"),
                    "start_line": item.get("start_line") or 0,
                    "cwe": item.get("cwe"),
                }
            )
        if key not in out:
            out[key] = dict(item)
            out[key]["identity"] = key
    return out


def compute_security_evidence_delta(
    source_findings: Sequence[Mapping[str, Any]],
    candidate_findings: Sequence[Mapping[str, Any]],
    *,
    source_sha: str | None = None,
    patch_digest: str | None = None,
    candidate_digest: str | None = None,
    source_scan_digest: str | None = None,
    candidate_scan_digest: str | None = None,
) -> dict[str, Any]:
    source = _by_identity(source_findings)
    candidate = _by_identity(candidate_findings)
    source_keys = set(source)
    candidate_keys = set(candidate)
    resolved = [source[key] for key in sorted(source_keys - candidate_keys)]
    new = [candidate[key] for key in sorted(candidate_keys - source_keys)]
    persisting = [candidate[key] for key in sorted(source_keys & candidate_keys)]
    payload = {
        "schema_version": SCHEMA_DELTA,
        "source_sha": source_sha,
        "patch_digest": patch_digest,
        "candidate_digest": candidate_digest,
        "source_scan_digest": source_scan_digest,
        "candidate_scan_digest": candidate_scan_digest,
        "resolved": resolved,
        "new": new,
        "persisting": persisting,
        "counts": {
            "resolved": len(resolved),
            "new": len(new),
            "persisting": len(persisting),
            "source": len(source),
            "candidate": len(candidate),
        },
    }
    payload["digest"] = canonical_json_hash({k: v for k, v in payload.items() if k != "digest"})
    return payload
