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
    STATUS_REQUIRED_EVIDENCE_UNAVAILABLE,
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
    source_root: str | None = None,
    candidate_root: str | None = None,
    artifact_dir: str | None = None,
    executor: Any = None,
    raw_source_sarif: Any = None,
    raw_candidate_sarif: Any = None,
    timeout_sec: float | None = None,
) -> dict[str, Any]:
    """P2 SAST adapter.

    Fixture kwargs (findings/force_*) remain for unit isolation. Empty kwargs is
    not a synthetic PASS — live PDP invokes the real provider package.
    """
    bind = _bind(binding)
    if force_timeout:
        return _envelope(P2, [], "TIMEOUT", "sast_timeout")
    if force_failure:
        return _envelope(P2, [], STATUS_TOOL_FAILURE, "sast_unavailable")
    if malformed:
        return _envelope(P2, [{"not": "a receipt"}], STATUS_INCOMPLETE, "malformed")
    if findings is None and not force_timeout and not force_failure and not malformed:
        from agent_control.transaction.evidence.providers.semgrep.adapter import run_live_p2

        return run_live_p2(
            binding=binding,
            source_root=source_root,
            candidate_root=candidate_root,
            artifact_dir=artifact_dir,
            executor=executor,
            raw_source_sarif=raw_source_sarif,
            raw_candidate_sarif=raw_candidate_sarif,
            timeout_sec=timeout_sec,
        )
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
    issue: Mapping[str, Any] | None = None,
    issue_ref: Mapping[str, Any] | None = None,
    gitea_client: Any = None,
    frozen_issue: Any = None,
    source_findings: Sequence[Mapping[str, Any]] | None = None,
    source_findings_provided: bool | None = None,
    expected_issue_id: int | None = None,
    expected_repository: str | None = None,
    task_id: str | None = None,
    proposal_id: str | None = None,
    transaction_id: str | None = None,
    unavailable_reason: str | None = None,
) -> dict[str, Any]:
    bind = _bind(binding)
    if force_failure:
        return _envelope(P4, [], STATUS_INCOMPLETE, "task_unbound")
    if unavailable_reason:
        detail = str(unavailable_reason)
        receipt = make_receipt(
            evidence_type=EVIDENCE_TASK_REQUIREMENT,
            result_status=STATUS_REQUIRED_EVIDENCE_UNAVAILABLE,
            trust_class=TRUST_TASK_SYSTEM,
            producer="gitea_task_envelope_finding_adapter",
            fact="TASK_EVIDENCE_UNAVAILABLE",
            authorization_class=AUTH_NONE,
            detail=detail,
            extra={"reason_code": detail, "llm_parsed": False},
            **bind,
        )
        return _envelope(P4, [receipt], STATUS_TOOL_FAILURE, detail)
    live_issue = issue
    if live_issue is None and frozen_issue is None and issue_ref is not None:
        from agent_control.transaction.evidence.task_receipt import fetch_gitea_issue

        repository = str(
            issue_ref.get("repository")
            or issue_ref.get("repo")
            or bind.get("repo")
            or ""
        )
        issue_id = int(issue_ref.get("issue_id") or issue_ref.get("number") or 0)
        if gitea_client is None or not repository or issue_id < 1:
            return _envelope(P4, [], STATUS_INCOMPLETE, "MISSING_STRUCTURED_BLOCK")
        live_issue = fetch_gitea_issue(gitea_client, repository, issue_id)
    if live_issue is not None or frozen_issue is not None:
        from agent_control.transaction.evidence.task_receipt import (
            derive_task_evidence_receipt,
            freeze_gitea_issue,
            task_receipt_to_evidence,
        )

        freeze = frozen_issue or freeze_gitea_issue(
            live_issue or {},
            repository=str(bind.get("repo") or expected_repository or ""),
        )
        provided = (
            bool(source_findings_provided)
            if source_findings_provided is not None
            else source_findings is not None
        )
        ref_issue_id = None
        if issue_ref is not None:
            raw_id = issue_ref.get("issue_id") or issue_ref.get("number")
            if raw_id is not None:
                ref_issue_id = int(raw_id)
        task_receipt = derive_task_evidence_receipt(
            freeze,
            binding=bind,
            expected_issue_id=expected_issue_id or ref_issue_id,
            expected_repository=expected_repository or bind.get("repo"),
            source_findings=source_findings,
            source_findings_provided=provided,
            task_id=task_id,
            proposal_id=proposal_id,
            transaction_id=transaction_id,
        )
        converted = task_receipt_to_evidence(task_receipt, binding=bind)
        return _envelope(
            P4,
            converted["receipts"],
            converted["status"],
            converted.get("detail"),
        )
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
