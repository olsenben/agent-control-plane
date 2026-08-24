"""Generic SARIF 2.1.0 parse and finding identity.

Finding identity prefers SARIF ``partialFingerprints``, then ``ruleId`` plus
artifact URI and region. Limitations (not a product claim): fingerprints can
shift across Semgrep minor versions and across rewritten-but-equivalent code;
region-only identity can collide when one rule fires twice on the same line.
Identity is deterministic on a frozen ruleset, pinned binary, and chosen fixture.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agent_shared.hash_utils import canonical_json_hash, sha256_text

SARIF_VERSION = "2.1.0"
SCHEMA_FINDING = "normalized_sast_finding.v1"
# Semgrep ``--config /rules/*.yaml`` prefixes SARIF ruleId with the config dir.
_RULES_PATH_PREFIX = "rules."


class SarifError(ValueError):
    """Malformed or unsupported SARIF document."""


def canonicalize_rule_id(rule_id: str) -> str:
    """Strip a leading ``rules.`` path prefix; keep ``python.lang...`` ids."""
    text = str(rule_id or "").strip()
    if text.startswith(_RULES_PATH_PREFIX):
        remainder = text[len(_RULES_PATH_PREFIX) :]
        if remainder:
            return remainder
    return text


def _opt_int(value: Any) -> int | None:
    if value is None or value is False:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_artifact_uri(uri: str, *, workspace: Path | None = None) -> str:
    raw = (uri or "").strip().replace("\\", "/")
    if raw.startswith("file:///"):
        raw = raw[len("file:///") :]
    elif raw.startswith("file://"):
        raw = raw[len("file://") :]
    if len(raw) >= 3 and raw[1] == ":" and raw[2] == "/":
        raw = raw[3:]
    raw = raw.lstrip("./")
    if workspace is not None:
        root = str(workspace.resolve()).replace("\\", "/")
        if raw.lower().startswith(root.lower()):
            raw = raw[len(root) :].lstrip("/")
        try:
            return Path(uri).resolve().relative_to(workspace.resolve()).as_posix()
        except (OSError, ValueError):
            pass
    for marker in ("/src/", "/candidate/", "/source/"):
        idx = f"/{raw}".find(marker)
        if idx >= 0:
            return f"/{raw}"[idx + 1 :].lstrip("/")
    return raw


def finding_identity(
    *,
    rule_id: str,
    location_path: str,
    start_line: int | None,
    start_column: int | None = None,
    fingerprints: Mapping[str, Any] | None = None,
) -> str:
    """Stable finding key for delta matching on the frozen fixture."""
    fp = ""
    if fingerprints:
        for key in ("primaryLocationLineHash", "stableId", "contextRegionHash"):
            value = fingerprints.get(key)
            if value:
                fp = str(value)
                break
    payload = {
        "fingerprints": fp or None,
        "rule_id": canonicalize_rule_id(rule_id),
        "location_path": location_path,
        "start_line": start_line or 0,
        "start_column": start_column or 0,
    }
    return canonical_json_hash(payload)


def _cwe_from_result(result: Mapping[str, Any], rule_meta: Mapping[str, Any] | None) -> str | None:
    props = result.get("properties") if isinstance(result.get("properties"), Mapping) else {}
    raw = None
    if isinstance(props, Mapping):
        raw = props.get("cwe") or props.get("CWE")
    if raw is None and rule_meta:
        raw = (rule_meta.get("cwe") if isinstance(rule_meta.get("cwe"), (str, int)) else None) or (
            (rule_meta.get("security-severity") and None)
        )
        tags = rule_meta.get("tags") if isinstance(rule_meta.get("tags"), list) else []
        for tag in tags:
            text = str(tag)
            if "cwe-" in text.lower() or text.upper().startswith("CWE"):
                raw = text
                break
        if raw is None:
            raw = rule_meta.get("cwe")
    if isinstance(raw, Mapping):
        return str(raw.get("id") or raw.get("name") or "") or None
    if raw is not None:
        return str(raw) or None
    return None


def _rule_map(run: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    driver = ((run.get("tool") or {}).get("driver") or {}) if isinstance(run.get("tool"), Mapping) else {}
    out: dict[str, dict[str, Any]] = {}
    for rule in driver.get("rules") or []:
        if not isinstance(rule, Mapping):
            continue
        rule_id = str(rule.get("id") or "")
        if not rule_id:
            continue
        props = rule.get("properties") if isinstance(rule.get("properties"), Mapping) else {}
        meta = dict(props) if isinstance(props, Mapping) else {}
        out[rule_id] = meta
        canonical = canonicalize_rule_id(rule_id)
        if canonical != rule_id:
            out[canonical] = meta
    return out


def loaded_sarif_rule_ids(payload: Mapping[str, Any]) -> list[str]:
    ids: list[str] = []
    for run in payload.get("runs") or []:
        if not isinstance(run, Mapping):
            continue
        driver = ((run.get("tool") or {}).get("driver") or {}) if isinstance(run.get("tool"), Mapping) else {}
        for rule in driver.get("rules") or []:
            if isinstance(rule, Mapping) and rule.get("id"):
                ids.append(canonicalize_rule_id(str(rule["id"])))
    return list(dict.fromkeys(ids))


def validate_sarif_document(payload: Any) -> None:
    if not isinstance(payload, Mapping):
        raise SarifError("SARIF_NOT_A_MAPPING")
    version = str(payload.get("version") or "")
    if version != SARIF_VERSION:
        raise SarifError("SARIF_UNSUPPORTED_VERSION")
    runs = payload.get("runs")
    if not isinstance(runs, list):
        raise SarifError("SARIF_MISSING_RUNS")


def parse_sarif_findings(
    payload: Mapping[str, Any],
    *,
    workspace: Path | None = None,
) -> list[dict[str, Any]]:
    """Normalize SARIF 2.1.0 results. Raises SarifError on malformed input."""
    validate_sarif_document(payload)
    findings: list[dict[str, Any]] = []
    for run in payload.get("runs") or []:
        if not isinstance(run, Mapping):
            continue
        rules = _rule_map(run)
        for result in run.get("results") or []:
            if not isinstance(result, Mapping):
                raise SarifError("SARIF_MALFORMED_RESULT")
            rule_id = canonicalize_rule_id(str(result.get("ruleId") or result.get("ruleID") or ""))
            if not rule_id:
                rule_id = "UNKNOWN"
            fingerprints = result.get("partialFingerprints")
            if fingerprints is not None and not isinstance(fingerprints, Mapping):
                raise SarifError("SARIF_MALFORMED_FINGERPRINTS")
            locations = result.get("locations") or []
            if locations and not isinstance(locations, list):
                raise SarifError("SARIF_MALFORMED_LOCATIONS")
            if not locations:
                locations = [{}]
            for loc in locations:
                if not isinstance(loc, Mapping):
                    raise SarifError("SARIF_MALFORMED_LOCATION")
                phys = loc.get("physicalLocation") if isinstance(loc.get("physicalLocation"), Mapping) else {}
                artifact = (
                    phys.get("artifactLocation") if isinstance(phys.get("artifactLocation"), Mapping) else {}
                )
                region = phys.get("region") if isinstance(phys.get("region"), Mapping) else {}
                uri = str(artifact.get("uri") or "")
                path = normalize_artifact_uri(uri, workspace=workspace)
                start_line = _opt_int(region.get("startLine"))
                start_column = _opt_int(region.get("startColumn"))
                end_line = _opt_int(region.get("endLine"))
                cwe = _cwe_from_result(result, rules.get(rule_id))
                fp_map = dict(fingerprints) if isinstance(fingerprints, Mapping) else {}
                identity = finding_identity(
                    rule_id=rule_id,
                    location_path=path,
                    start_line=start_line,
                    start_column=start_column,
                    fingerprints=fp_map,
                )
                findings.append(
                    {
                        "schema": SCHEMA_FINDING,
                        "identity": identity,
                        "rule_id": rule_id,
                        "location_path": path,
                        "start_line": start_line,
                        "start_column": start_column,
                        "end_line": end_line,
                        "cwe": cwe,
                        "fingerprints": fp_map,
                        "level": str(result.get("level") or "") or None,
                    }
                )
    return findings


def sarif_digest(raw: str | bytes) -> str:
    if isinstance(raw, bytes):
        import hashlib

        return hashlib.sha256(raw).hexdigest()
    return sha256_text(raw)
