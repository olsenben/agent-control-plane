"""PATCH_BOUND evidence bus. Required-provider failures fail closed."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from agent_control.transaction.evidence.adapters import PROVIDERS
from agent_control.transaction.evidence.receipts import (
    BINDING_INVALID,
    CONFLICT_SAST_PASS_POC_FAIL,
    CONFLICT_TASK_API_VS_REPO_POLICY,
    EVIDENCE_SAST,
    EVIDENCE_SECURITY_POC,
    EVIDENCE_TASK_REQUIREMENT,
    FACT_REPOSITORY_FORBIDS_PUBLIC_API,
    FACT_TASK_AUTHORIZES_PUBLIC_API_CHANGE,
    INCOMPLETE_STATUSES,
    POLICY_VERSION,
    SCHEMA_BUNDLE,
    SECURITY_FAIL_STATUSES,
    STATUS_INCOMPLETE,
    STATUS_PASS,
    STATUS_SECURITY_PASS,
    STATUS_TOOL_FAILURE,
    TRUST_ACTOR_PROVIDED,
    TRUST_UNKNOWN,
    adapter_config_digest,
    evidence_hash,
    is_authoritative,
    receipt_fingerprint,
    receipt_may_authorize,
    strip_actor_authority,
    validate_receipt_binding,
    validate_receipt_schema,
)
from agent_control.transaction.evidence.route import REQUIRED, routed_providers
from agent_shared.models.transaction.evidence import (
    BindingValidation,
    EvidenceConflict,
    EvidenceCoverage,
    EvidenceProjection,
    EvidenceRoute,
    VerificationEvidenceBundle,
)

AdapterFn = Callable[..., dict[str, Any]]

FAIL_STATUSES = frozenset(
    {*INCOMPLETE_STATUSES, "TIMEOUT", "MALFORMED", STATUS_TOOL_FAILURE, STATUS_INCOMPLETE}
)


def _as_receipts(adapter_result: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = adapter_result.get("receipts") or []
    return [dict(item) for item in rows if isinstance(item, Mapping)]


def _dedup(receipts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for receipt in receipts:
        key = receipt_fingerprint(receipt)
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(receipt))
    return out


def detect_conflicts(receipts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    sast_pass = [
        item
        for item in receipts
        if item.get("evidence_type") == EVIDENCE_SAST
        and item.get("result_status") in {STATUS_PASS, STATUS_SECURITY_PASS}
        and is_authoritative(item)
    ]
    poc_fail = [
        item
        for item in receipts
        if item.get("evidence_type") == EVIDENCE_SECURITY_POC
        and item.get("result_status") in SECURITY_FAIL_STATUSES
        and is_authoritative(item)
    ]
    if sast_pass and poc_fail:
        conflicts.append(
            {
                "kind": CONFLICT_SAST_PASS_POC_FAIL,
                "receipt_digests": [item.get("digest") for item in (*sast_pass[:3], *poc_fail[:3])],
            }
        )
    authorizes = [
        item
        for item in receipts
        if item.get("evidence_type") == EVIDENCE_TASK_REQUIREMENT
        and item.get("fact") == FACT_TASK_AUTHORIZES_PUBLIC_API_CHANGE
    ]
    forbids = [
        item for item in receipts if item.get("fact") == FACT_REPOSITORY_FORBIDS_PUBLIC_API
    ]
    if authorizes and forbids:
        conflicts.append(
            {
                "kind": CONFLICT_TASK_API_VS_REPO_POLICY,
                "receipt_digests": [item.get("digest") for item in (*authorizes[:3], *forbids[:3])],
            }
        )
    return conflicts


def validate_and_bind(
    receipts: Sequence[Mapping[str, Any]],
    expected: Mapping[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    valid: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for raw in receipts:
        receipt = strip_actor_authority(raw)
        schema_problems = validate_receipt_schema(receipt)
        binding = validate_receipt_binding(receipt, expected)
        if schema_problems:
            invalid.append(
                {
                    **receipt,
                    "binding_status": BINDING_INVALID,
                    "binding_reasons": schema_problems,
                    "can_authorize": False,
                    "authoritative": False,
                }
            )
            continue
        if binding.status == BINDING_INVALID:
            invalid.append(
                {
                    **receipt,
                    "binding_status": binding.status,
                    "binding_reasons": list(binding.reasons),
                    "can_authorize": False,
                    "authoritative": False,
                }
            )
            continue
        receipt["binding_status"] = binding.status
        receipt["can_authorize"] = bool(binding.can_authorize) and receipt_may_authorize(receipt)
        if receipt.get("trust_class") in {TRUST_ACTOR_PROVIDED, TRUST_UNKNOWN}:
            receipt["can_authorize"] = False
            receipt["authoritative"] = False
        valid.append(receipt)
    return valid, invalid


def run_evidence_bus(
    *,
    binding: Mapping[str, Any],
    route: EvidenceRoute,
    adapters: Mapping[str, AdapterFn] | None = None,
    adapter_kwargs: Mapping[str, Mapping[str, Any]] | None = None,
    extra_receipts: Sequence[Mapping[str, Any]] | None = None,
    run_id: str | None = None,
    proposal_id: str | None = None,
    task_id: str | None = None,
    policy_version: str = POLICY_VERSION,
) -> dict[str, Any]:
    registry = dict(PROVIDERS)
    if adapters:
        registry.update(adapters)
    kwargs_by_id = dict(adapter_kwargs or {})
    bind = dict(binding)
    missing: list[str] = []
    failed: list[str] = []
    required_failures: list[str] = []
    collected: list[dict[str, Any]] = []
    configured: list[str] = []

    for routed in routed_providers(route):
        provider_id = routed.provider_id
        required = routed.requirement_class == REQUIRED
        configured.append(provider_id)
        fn = registry.get(provider_id)
        if fn is None:
            missing.append(provider_id)
            if required:
                required_failures.append(provider_id)
            continue
        try:
            result = fn(binding=bind, **dict(kwargs_by_id.get(provider_id) or {}))
        except Exception as exc:  # noqa: BLE001 - fail closed
            failed.append(provider_id)
            if required:
                required_failures.append(provider_id)
            collected.append(
                {
                    "schema": "verification_evidence.v1",
                    "evidence_type": "OTHER_TYPED",
                    "result_status": STATUS_TOOL_FAILURE,
                    "trust_class": TRUST_UNKNOWN,
                    "producer": {"name": provider_id, "trust_class": TRUST_UNKNOWN},
                    "detail": str(exc),
                }
            )
            continue
        status = str(result.get("status") or "OK")
        receipts = _as_receipts(result)
        if status in FAIL_STATUSES or status in {"TIMEOUT", "MALFORMED"}:
            failed.append(provider_id)
            if required:
                required_failures.append(provider_id)
        if required and not receipts:
            required_failures.append(provider_id)
        collected.extend(receipts)

    if extra_receipts:
        collected.extend(dict(item) for item in extra_receipts if isinstance(item, Mapping))

    valid, invalid = validate_and_bind(collected, bind)
    valid = _dedup(valid)
    for item in invalid:
        reasons = [str(r) for r in (item.get("binding_reasons") or [])]
        if any(token in reasons for token in ("UNBOUND", "STALE", "WRONG_PATCH", "WRONG_SOURCE", "WRONG_REPO", "UNKNOWN_SCHEMA", "NOT_A_MAPPING")) or str(item.get("binding_status")) == BINDING_INVALID:
            # unbound/malformed of a required stream is fail-closed if producer is required
            producer = item.get("producer")
            producer_name = ""
            if isinstance(producer, Mapping):
                producer_name = str(producer.get("name") or "")
            if producer_name in {p.provider_id for p in routed_providers(route) if p.requirement_class == REQUIRED}:
                if producer_name not in required_failures:
                    required_failures.append(producer_name)
    conflicts = detect_conflicts(valid)
    produced_at = datetime.now(timezone.utc).isoformat()
    bundle_id = str(uuid4())
    present = sorted({str(item.get("evidence_type")) for item in valid if item.get("evidence_type")})
    required_classes = sorted({p.provider_id for p in routed_providers(route) if p.requirement_class == REQUIRED})
    identity = {
        "repo": bind.get("repo") or bind.get("repository"),
        "source_sha": bind.get("source_sha"),
        "patch_digest": bind.get("patch_digest"),
        "policy_version": policy_version,
        "adapter_config_digest": adapter_config_digest(configured),
    }
    digest_payload = {
        "binding": identity,
        "receipts": [item.get("digest") for item in valid],
        "invalid": [item.get("digest") for item in invalid],
        "conflicts": conflicts,
        "missing_providers": missing,
        "failed_providers": failed,
        "required_provider_failures": required_failures,
    }
    bundle_digest = evidence_hash(digest_payload)
    incomplete: list[str] = []
    if required_failures:
        incomplete.append("TOOL_FAILURE")
    if missing:
        incomplete.append("MISSING_REQUIRED_CLASS")
    if any("UNBOUND" in (item.get("binding_reasons") or []) for item in invalid):
        incomplete.append("UNBOUND")
    if any("STALE" in (item.get("binding_reasons") or []) for item in invalid):
        incomplete.append("STALE")
    if conflicts:
        incomplete.append("EVIDENCE_CONFLICT")
    incomplete = list(dict.fromkeys(incomplete))

    conflict_models = [
        EvidenceConflict(
            conflict_id=str(item.get("kind") or "conflict"),
            evidence_ids=[str(x) for x in (item.get("receipt_digests") or ["a", "b"]) if x][:8]
            or ["unknown-a", "unknown-b"],
            resolution="FAIL_CLOSED",
            notes=str(item.get("kind")),
        )
        for item in conflicts
    ]

    auto_admit_blocked = bool(required_failures or incomplete)
    envelope = VerificationEvidenceBundle(
        bundle_id=bundle_id,
        repository=str(identity["repo"] or "unknown/repo"),
        source_sha=str(identity["source_sha"] or "unknown0"),
        patch_digest=str(identity["patch_digest"] or "0" * 64),
        run_id=run_id or bundle_id,
        produced_at=produced_at,
        proposal_id=proposal_id,
        task_id=task_id,
        items=valid,
        conflicts=conflict_models,
        binding_validation=BindingValidation(
            all_candidate_items_bound=not any(
                "UNBOUND" in (item.get("binding_reasons") or []) for item in invalid
            ),
            unbound_evidence_ids=[
                str(item.get("digest") or item.get("evidence_id") or "")
                for item in invalid
                if "UNBOUND" in (item.get("binding_reasons") or [])
            ],
            stale_evidence_ids=[
                str(item.get("digest") or item.get("evidence_id") or "")
                for item in invalid
                if "STALE" in (item.get("binding_reasons") or [])
            ],
            mismatch_evidence_ids=[
                str(item.get("digest") or item.get("evidence_id") or "")
                for item in invalid
                if any(
                    token in (item.get("binding_reasons") or [])
                    for token in ("WRONG_REPO", "WRONG_SOURCE", "WRONG_PATCH")
                )
            ],
        ),
        coverage=EvidenceCoverage(
            required_classes=required_classes,
            present_classes=present,
            missing_classes=[item for item in required_classes if item in missing],
        ),
        projection=EvidenceProjection(),
        incomplete_reasons=incomplete,  # type: ignore[arg-type]
        bundle_digest=bundle_digest,
        required_provider_failures=list(dict.fromkeys(required_failures)),
        auto_admit_blocked=auto_admit_blocked,
    )
    payload = envelope.model_dump(mode="json")
    payload["schema"] = SCHEMA_BUNDLE
    payload["receipts"] = valid
    payload["invalid_receipts"] = invalid
    payload["missing_providers"] = missing
    payload["failed_providers"] = failed
    payload["adapter_config"] = configured
    payload["policy_version"] = policy_version
    payload["binding"] = identity
    return payload
