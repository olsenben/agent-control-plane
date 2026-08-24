"""P2 live adapter: Semgrep CE → verification_evidence.v1. Not C, not durable authority."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agent_control.transaction.evidence.delta import compute_security_evidence_delta
from agent_control.transaction.evidence.providers.semgrep.ruleset import (
    CASE_SPECIFIC_RULE_ADDED,
    SEMGREP_VERSION,
    loaded_rule_ids,
)
from agent_control.transaction.evidence.providers.semgrep.runner import (
    OUTCOME_FAILURE,
    OUTCOME_FINDINGS,
    OUTCOME_SUCCESS,
    ProviderRunError,
    SemgrepExecutor,
    run_semgrep_scan,
)
from agent_control.transaction.evidence.receipts import (
    EVIDENCE_SAST,
    STATUS_FAIL,
    STATUS_INCOMPLETE,
    STATUS_MALFORMED,
    STATUS_NEW_FINDING,
    STATUS_PASS,
    STATUS_REQUIRED_EVIDENCE_UNAVAILABLE,
    STATUS_RESOLVED_FINDING,
    STATUS_TIMEOUT,
    STATUS_TOOL_FAILURE,
    TRUST_CONFIGURED_SECURITY_TOOL,
    make_receipt,
)
from agent_control.transaction.evidence.sarif import (
    SarifError,
    loaded_sarif_rule_ids,
    parse_sarif_findings,
)

P2 = "P2"
PRODUCER = "semgrep_ce"
DETAIL_REQUIRED = "REQUIRED_EVIDENCE_UNAVAILABLE"


def _bind(binding: Mapping[str, Any] | None) -> dict[str, Any]:
    bind = dict(binding or {})
    return {
        "repo": bind.get("repo") or bind.get("repository"),
        "source_sha": bind.get("source_sha"),
        "patch_digest": bind.get("patch_digest"),
        "candidate_digest": bind.get("candidate_digest"),
    }


def _envelope(provider_id: str, receipts: list[dict[str, Any]], status: str, detail: str | None = None) -> dict[str, Any]:
    return {
        "provider_id": provider_id,
        "status": status,
        "detail": detail,
        "receipts": [dict(item) for item in receipts],
    }


def _fail(
    bind: Mapping[str, Any],
    status: str,
    detail: str,
    *,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    receipt = make_receipt(
        evidence_type=EVIDENCE_SAST,
        result_status=status,
        trust_class=TRUST_CONFIGURED_SECURITY_TOOL,
        producer=PRODUCER,
        detail=detail,
        extra=dict(extra) if extra else {"reason_code": detail},
        **bind,
    )
    envelope_status = status if status in {STATUS_TIMEOUT, STATUS_MALFORMED, STATUS_INCOMPLETE} else STATUS_TOOL_FAILURE
    if status == STATUS_REQUIRED_EVIDENCE_UNAVAILABLE:
        envelope_status = STATUS_TOOL_FAILURE
    return _envelope(P2, [receipt], envelope_status, detail)


def _finding_status(bucket: str) -> str:
    if bucket == "new":
        return STATUS_NEW_FINDING
    if bucket == "persisting":
        return STATUS_FAIL
    if bucket == "resolved":
        return STATUS_RESOLVED_FINDING
    return STATUS_PASS


def run_live_p2(
    *,
    binding: Mapping[str, Any] | None = None,
    source_root: str | Path | None = None,
    candidate_root: str | Path | None = None,
    artifact_dir: str | Path | None = None,
    executor: SemgrepExecutor | None = None,
    raw_source_sarif: Any = None,
    raw_candidate_sarif: Any = None,
    timeout_sec: float | None = None,
) -> dict[str, Any]:
    """Live SAST provider. Missing trees/binary/SARIF never PASS."""
    bind = _bind(binding)
    extra_base = {
        "producer_version": SEMGREP_VERSION,
        "case_specific_rule_added": CASE_SPECIFIC_RULE_ADDED,
        "provider_durable_authority": "NONE",
    }
    if not bind.get("repo") or not bind.get("source_sha") or not bind.get("patch_digest"):
        return _fail(bind, STATUS_REQUIRED_EVIDENCE_UNAVAILABLE, "UNBOUND", extra=extra_base)
    source_path = Path(source_root) if source_root else None
    candidate_path = Path(candidate_root) if candidate_root else None
    if source_path is None or candidate_path is None:
        return _fail(
            bind,
            STATUS_REQUIRED_EVIDENCE_UNAVAILABLE,
            DETAIL_REQUIRED,
            extra={**extra_base, "missing_source": source_path is None, "missing_candidate": candidate_path is None},
        )
    if raw_source_sarif is None and not source_path.is_dir():
        return _fail(bind, STATUS_REQUIRED_EVIDENCE_UNAVAILABLE, "UNBOUND_SOURCE", extra=extra_base)
    if raw_candidate_sarif is None and not candidate_path.is_dir():
        return _fail(bind, STATUS_REQUIRED_EVIDENCE_UNAVAILABLE, "UNBOUND_CANDIDATE", extra=extra_base)

    artifacts = Path(artifact_dir) if artifact_dir else None
    timeout = 120.0 if timeout_sec is None else float(timeout_sec)
    scans: dict[str, dict[str, Any]] = {}
    for name, tree, injected in (
        ("source", source_path, raw_source_sarif),
        ("candidate", candidate_path, raw_candidate_sarif),
    ):
        try:
            scans[name] = run_semgrep_scan(
                target=tree,
                scan_target=name,
                artifact_dir=artifacts,
                executor=executor,
                timeout_sec=timeout,
                injected_sarif=injected,
            )
        except ProviderRunError as exc:
            status = STATUS_TIMEOUT if exc.code == "TIMEOUT" else STATUS_TOOL_FAILURE
            if exc.code == "MALFORMED_SARIF":
                status = STATUS_MALFORMED
            if exc.code in {"MISSING_BINARY", "VERSION_MISMATCH", "ZERO_RULES", "MISSING_RULESET", "UNBOUND_TREE"}:
                status = STATUS_TOOL_FAILURE
                detail = DETAIL_REQUIRED if exc.code in {"MISSING_BINARY", "UNBOUND_TREE"} else exc.code
            else:
                detail = exc.code
            return _fail(bind, status, detail, extra={**extra_base, "run_error": exc.detail})

        failure = scans[name].get("failure")
        if failure == "TIMEOUT":
            return _fail(
                bind,
                STATUS_TIMEOUT,
                "TIMEOUT",
                extra={**extra_base, "execution": scans[name].get("execution")},
            )
        if failure in {"MALFORMED_SARIF", "MISSING_SARIF"}:
            return _fail(
                bind,
                STATUS_MALFORMED,
                failure,
                extra={**extra_base, "execution": scans[name].get("execution")},
            )
        if failure:
            return _fail(
                bind,
                STATUS_TOOL_FAILURE,
                str(failure),
                extra={**extra_base, "execution": scans[name].get("execution")},
            )

    yaml_rules = loaded_rule_ids()
    if not yaml_rules:
        return _fail(bind, STATUS_TOOL_FAILURE, "ZERO_RULES", extra=extra_base)

    parsed: dict[str, list[dict[str, Any]]] = {}
    for name in ("source", "candidate"):
        payload = scans[name].get("sarif")
        if not isinstance(payload, Mapping):
            return _fail(bind, STATUS_MALFORMED, "MALFORMED_SARIF", extra=extra_base)
        sarif_rules = loaded_sarif_rule_ids(payload)
        if not sarif_rules and not yaml_rules:
            return _fail(bind, STATUS_TOOL_FAILURE, "ZERO_RULES", extra=extra_base)
        if not sarif_rules and not (payload.get("runs") or []):
            return _fail(bind, STATUS_TOOL_FAILURE, "ZERO_RULES", extra=extra_base)
        try:
            parsed[name] = parse_sarif_findings(payload, workspace=Path(source_path if name == "source" else candidate_path))
        except SarifError as exc:
            return _fail(bind, STATUS_MALFORMED, str(exc), extra=extra_base)

    # Zero loaded rules in the tool run: SARIF omitted rules and YAML also empty (already checked).
    # If SARIF lists an empty rules array while YAML is non-empty, still fail-closed — scanner loaded nothing.
    for name in ("source", "candidate"):
        payload = scans[name]["sarif"]
        sarif_rules = loaded_sarif_rule_ids(payload)
        runs = payload.get("runs") or []
        driver_present = False
        empty_driver_rules = False
        for run in runs:
            if not isinstance(run, Mapping):
                continue
            tool = run.get("tool") if isinstance(run.get("tool"), Mapping) else {}
            driver = tool.get("driver") if isinstance(tool.get("driver"), Mapping) else {}
            if "rules" in driver:
                driver_present = True
                if not driver.get("rules"):
                    empty_driver_rules = True
        if driver_present and empty_driver_rules and not sarif_rules:
            return _fail(bind, STATUS_TOOL_FAILURE, "ZERO_RULES", extra=extra_base)

    delta = compute_security_evidence_delta(
        parsed["source"],
        parsed["candidate"],
        source_sha=str(bind.get("source_sha") or ""),
        patch_digest=str(bind.get("patch_digest") or ""),
        candidate_digest=str(bind.get("candidate_digest") or "") or None,
        source_scan_digest=scans["source"].get("raw_sarif_digest"),
        candidate_scan_digest=scans["candidate"].get("raw_sarif_digest"),
    )

    executions = {
        "source": scans["source"]["execution"],
        "candidate": scans["candidate"]["execution"],
    }
    new_findings = list(delta.get("new") or [])
    persisting = list(delta.get("persisting") or [])
    resolved = list(delta.get("resolved") or [])
    has_findings = bool(new_findings or persisting)
    for target in ("source", "candidate"):
        exec_row = executions[target]
        findings_here = parsed[target]
        if exec_row.get("outcome") != OUTCOME_FAILURE:
            exec_row["outcome"] = OUTCOME_FINDINGS if findings_here else OUTCOME_SUCCESS

    summary_status = STATUS_NEW_FINDING if new_findings else (STATUS_FAIL if persisting else STATUS_PASS)
    if summary_status == STATUS_PASS:
        rule_id = "NO_FINDINGS"
    else:
        rule_id = str((new_findings or persisting)[0].get("rule_id") or "FINDINGS_PRESENT")

    extra = {
        **extra_base,
        "execution": executions,
        "delta": delta,
        "raw_sarif_digest": {
            "source": scans["source"].get("raw_sarif_digest"),
            "candidate": scans["candidate"].get("raw_sarif_digest"),
        },
        "ruleset_digest": scans["candidate"].get("ruleset_digest"),
        "loaded_rule_ids": yaml_rules,
        "raw_sarif_preserved": True,
    }
    receipts = [
        make_receipt(
            evidence_type=EVIDENCE_SAST,
            result_status=summary_status,
            trust_class=TRUST_CONFIGURED_SECURITY_TOOL,
            producer=PRODUCER,
            rule_id=rule_id,
            detail="FINDINGS_PRESENT" if has_findings else "NO_FINDINGS",
            extra=extra,
            **bind,
        )
    ]
    for bucket, rows in (
        ("new", new_findings),
        ("persisting", persisting),
        ("resolved", resolved),
    ):
        for item in rows:
            receipts.append(
                make_receipt(
                    evidence_type=EVIDENCE_SAST,
                    result_status=_finding_status(bucket),
                    trust_class=TRUST_CONFIGURED_SECURITY_TOOL,
                    producer=PRODUCER,
                    rule_id=str(item.get("rule_id") or "UNKNOWN"),
                    location_path=item.get("location_path"),
                    cwe=item.get("cwe"),
                    extra={
                        "identity": item.get("identity"),
                        "delta_bucket": bucket,
                        "start_line": item.get("start_line"),
                        "fingerprints": item.get("fingerprints") or {},
                    },
                    **bind,
                )
            )
    envelope_status = "OK"
    return _envelope(P2, receipts, envelope_status, "FINDINGS_PRESENT" if has_findings else "NO_FINDINGS")
