"""Parameterized evidence adapters. No corpus catalogs, no w5_oracles."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from agent_control.transaction.evidence.receipts import (
    AUTH_EXPLICIT,
    AUTH_INFORMATIONAL,
    AUTH_NONE,
    EVIDENCE_CI,
    EVIDENCE_FINDING,
    EVIDENCE_FUNCTIONAL,
    EVIDENCE_SAST,
    EVIDENCE_SECURITY_POC,
    EVIDENCE_SECURITY_TEST,
    EVIDENCE_SEMANTIC,
    EVIDENCE_TASK_REQUIREMENT,
    STATUS_FAIL,
    STATUS_INCOMPLETE,
    STATUS_PASS,
    STATUS_TOOL_FAILURE,
    TRUST_ACTOR_PROVIDED,
    TRUST_AUTHORITATIVE_CI,
    TRUST_CONFIGURED_SECURITY_TOOL,
    TRUST_REPOSITORY_METADATA,
    TRUST_TASK_SYSTEM,
    make_receipt,
)

AdapterFn = Callable[..., dict[str, Any]]

P1 = "P1"
P2 = "P2"
P3 = "P3"
P4 = "P4"
P5 = "P5"


def _bind(binding: Mapping[str, Any] | None) -> dict[str, Any]:
    bind = dict(binding or {})
    return {
        "repo": bind.get("repo") or bind.get("repository"),
        "source_sha": bind.get("source_sha"),
        "patch_digest": bind.get("patch_digest"),
        "candidate_digest": bind.get("candidate_digest"),
    }


def _envelope(provider_id: str, receipts: Sequence[Mapping[str, Any]], status: str, detail: str | None = None) -> dict[str, Any]:
    return {
        "provider_id": provider_id,
        "status": status,
        "detail": detail,
        "receipts": [dict(item) for item in receipts],
    }


def run_p1_functional_ci(
    *,
    binding: Mapping[str, Any] | None = None,
    verdict: Mapping[str, Any] | None = None,
    force_failure: bool = False,
) -> dict[str, Any]:
    """Functional / CI receipt. Parameterized; no live CT102 required."""
    bind = _bind(binding)
    if force_failure:
        return _envelope(P1, [], STATUS_TOOL_FAILURE, "required_provider_forced_failure")
    if verdict is None:
        return _envelope(P1, [], STATUS_INCOMPLETE, "missing_ci_verdict")
    passed = bool(verdict.get("passed"))
    status = STATUS_PASS if passed else STATUS_FAIL
    receipt = make_receipt(
        evidence_type=EVIDENCE_FUNCTIONAL,
        result_status=status,
        trust_class=TRUST_AUTHORITATIVE_CI,
        producer="ct102_functional_ci",
        issuer="ct102",
        **bind,
        extra={"ci_verdict": EVIDENCE_CI, "detail": verdict.get("detail")},
    )
    return _envelope(P1, [receipt], "OK")


def run_p2_sast(
    *,
    binding: Mapping[str, Any] | None = None,
    findings: Sequence[Mapping[str, Any]] | None = None,
    force_failure: bool = False,
    force_timeout: bool = False,
    malformed: bool = False,
) -> dict[str, Any]:
    """Local SAST / security adapter. Deterministic fixture; optional bandit later."""
    bind = _bind(binding)
    if force_timeout:
        return _envelope(P2, [], "TIMEOUT", "sast_timeout")
    if force_failure:
        return _envelope(P2, [], STATUS_TOOL_FAILURE, "sast_unavailable")
    if malformed:
        return _envelope(P2, [{"not": "a receipt"}], STATUS_INCOMPLETE, "malformed")
    receipts: list[dict[str, Any]] = []
    for item in findings or []:
        status = str(item.get("result_status") or STATUS_PASS)
        receipts.append(
            make_receipt(
                evidence_type=EVIDENCE_SAST,
                result_status=status,
                trust_class=TRUST_CONFIGURED_SECURITY_TOOL,
                producer="local_sast_security_adapter",
                rule_id=str(item.get("rule_id") or "BANDIT_FIXTURE"),
                location_path=item.get("location_path"),
                cwe=item.get("cwe"),
                **bind,
            )
        )
    if not receipts:
        receipts.append(
            make_receipt(
                evidence_type=EVIDENCE_SAST,
                result_status=STATUS_PASS,
                trust_class=TRUST_CONFIGURED_SECURITY_TOOL,
                producer="local_sast_security_adapter",
                rule_id="NO_FINDINGS",
                **bind,
            )
        )
    return _envelope(P2, receipts, "OK")


def run_p3_security_test(
    *,
    binding: Mapping[str, Any] | None = None,
    poc_results: Sequence[Mapping[str, Any]] | None = None,
    force_failure: bool = False,
) -> dict[str, Any]:
    bind = _bind(binding)
    if force_failure:
        return _envelope(P3, [], STATUS_TOOL_FAILURE, "poc_unavailable")
    receipts: list[dict[str, Any]] = []
    for item in poc_results or []:
        kind = str(item.get("evidence_type") or EVIDENCE_SECURITY_POC)
        status = str(item.get("result_status") or STATUS_PASS)
        receipts.append(
            make_receipt(
                evidence_type=kind,
                result_status=status,
                trust_class=TRUST_CONFIGURED_SECURITY_TOOL,
                producer="local_structured_security_test_adapter",
                check_name=str(item.get("check_name") or "poc"),
                **bind,
            )
        )
    if not receipts:
        receipts.append(
            make_receipt(
                evidence_type=EVIDENCE_SECURITY_TEST,
                result_status=STATUS_PASS,
                trust_class=TRUST_CONFIGURED_SECURITY_TOOL,
                producer="local_structured_security_test_adapter",
                check_name="no_poc_configured",
                **bind,
            )
        )
    return _envelope(P3, receipts, "OK")


def run_p4_task_finding(
    *,
    binding: Mapping[str, Any] | None = None,
    task: Mapping[str, Any] | None = None,
    finding: Mapping[str, Any] | None = None,
    force_failure: bool = False,
) -> dict[str, Any]:
    bind = _bind(binding)
    if force_failure:
        return _envelope(P4, [], STATUS_INCOMPLETE, "task_unbound")
    receipts: list[dict[str, Any]] = []
    if task:
        files = list(task.get("authorized_files") or [])
        surfaces = list(task.get("authorized_surfaces") or [])
        classes = list(task.get("authorized_change_classes") or [])
        if "PUBLIC_API_CHANGE" in classes:
            receipts.append(
                make_receipt(
                    evidence_type=EVIDENCE_TASK_REQUIREMENT,
                    result_status=STATUS_PASS,
                    trust_class=TRUST_TASK_SYSTEM,
                    producer="gitea_task_envelope_finding_adapter",
                    fact="TASK_AUTHORIZES_PUBLIC_API_CHANGE",
                    authorization_class=AUTH_EXPLICIT,
                    **bind,
                )
            )
        for path in files:
            receipts.append(
                make_receipt(
                    evidence_type=EVIDENCE_TASK_REQUIREMENT,
                    result_status=STATUS_PASS,
                    trust_class=TRUST_TASK_SYSTEM,
                    producer="gitea_task_envelope_finding_adapter",
                    fact="TASK_TARGETS_FILE",
                    location_path=str(path),
                    authorization_class=AUTH_EXPLICIT,
                    **bind,
                )
            )
        for symbol in surfaces:
            receipts.append(
                make_receipt(
                    evidence_type=EVIDENCE_TASK_REQUIREMENT,
                    result_status=STATUS_PASS,
                    trust_class=TRUST_TASK_SYSTEM,
                    producer="gitea_task_envelope_finding_adapter",
                    fact="TASK_TARGETS_SYMBOL",
                    check_name=str(symbol),
                    authorization_class=AUTH_EXPLICIT,
                    **bind,
                )
            )
        if not receipts:
            receipts.append(
                make_receipt(
                    evidence_type=EVIDENCE_TASK_REQUIREMENT,
                    result_status=STATUS_PASS,
                    trust_class=TRUST_TASK_SYSTEM,
                    producer="gitea_task_envelope_finding_adapter",
                    fact="TASK_ENVELOPE_PRESENT",
                    authorization_class=AUTH_INFORMATIONAL,
                    **bind,
                )
            )
    if finding:
        receipts.append(
            make_receipt(
                evidence_type=EVIDENCE_FINDING,
                result_status=STATUS_PASS,
                trust_class=TRUST_TASK_SYSTEM,
                producer="gitea_task_envelope_finding_adapter",
                rule_id=str(finding.get("rule_id") or finding.get("finding_id")),
                location_path=(finding.get("affected_location") or {}).get("path")
                if isinstance(finding.get("affected_location"), Mapping)
                else finding.get("path"),
                authorization_class=AUTH_NONE,
                **bind,
            )
        )
    if not receipts:
        return _envelope(P4, [], STATUS_INCOMPLETE, "missing_task_envelope")
    return _envelope(P4, receipts, "OK")


def run_p5_semantic(
    *,
    binding: Mapping[str, Any] | None = None,
    units: Sequence[Mapping[str, Any]] | None = None,
    force_failure: bool = False,
) -> dict[str, Any]:
    bind = _bind(binding)
    if force_failure:
        return _envelope(P5, [], STATUS_INCOMPLETE, "semantic_unavailable")
    receipts: list[dict[str, Any]] = []
    for unit in units or []:
        receipts.append(
            make_receipt(
                evidence_type=EVIDENCE_SEMANTIC,
                result_status=STATUS_PASS,
                trust_class=TRUST_REPOSITORY_METADATA,
                producer="control_plane_semantic_relation",
                location_path=str(unit.get("path") or ""),
                check_name=str(unit.get("element_key") or ""),
                extra={"receipts": list(unit.get("receipts") or [])},
                **bind,
            )
        )
    if not receipts:
        receipts.append(
            make_receipt(
                evidence_type=EVIDENCE_SEMANTIC,
                result_status=STATUS_PASS,
                trust_class=TRUST_REPOSITORY_METADATA,
                producer="control_plane_semantic_relation",
                extra={"receipts": []},
                **bind,
            )
        )
    return _envelope(P5, receipts, "OK")


def actor_provided_receipt(
    *,
    binding: Mapping[str, Any] | None = None,
    evidence_type: str = EVIDENCE_SAST,
    result_status: str = STATUS_PASS,
) -> dict[str, Any]:
    bind = _bind(binding)
    return make_receipt(
        evidence_type=evidence_type,
        result_status=result_status,
        trust_class=TRUST_ACTOR_PROVIDED,
        producer="actor_self_attestation",
        **bind,
    )


PROVIDERS: dict[str, AdapterFn] = {
    P1: run_p1_functional_ci,
    P2: run_p2_sast,
    P3: run_p3_security_test,
    P4: run_p4_task_finding,
    P5: run_p5_semantic,
}
