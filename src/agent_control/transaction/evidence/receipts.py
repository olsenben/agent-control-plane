"""Verification evidence receipts. Frozen C is not imported here."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from agent_shared.hash_utils import canonical_json_hash

SCHEMA_EVIDENCE = "verification_evidence.v1"
SCHEMA_BINDING = "evidence_binding_result.v1"
SCHEMA_BUNDLE = "verification_evidence_bundle.v1"
POLICY_VERSION = "w5_evidence_policy.v1"

TRUST_AUTHORITATIVE_CONTROL_PLANE = "AUTHORITATIVE_CONTROL_PLANE"
TRUST_AUTHORITATIVE_CI = "AUTHORITATIVE_CI"
TRUST_CONFIGURED_SECURITY_TOOL = "CONFIGURED_SECURITY_TOOL"
TRUST_TASK_SYSTEM = "TASK_SYSTEM"
TRUST_REPOSITORY_METADATA = "REPOSITORY_METADATA"
TRUST_ADVISORY_TOOL = "ADVISORY_TOOL"
TRUST_ACTOR_PROVIDED = "ACTOR_PROVIDED"
TRUST_UNKNOWN = "UNKNOWN"

AUTHORITATIVE_TRUST = frozenset(
    {
        TRUST_AUTHORITATIVE_CONTROL_PLANE,
        TRUST_AUTHORITATIVE_CI,
        TRUST_CONFIGURED_SECURITY_TOOL,
    }
)
NON_AUTHORITATIVE_TRUST = frozenset(
    {TRUST_ACTOR_PROVIDED, TRUST_UNKNOWN, TRUST_ADVISORY_TOOL}
)

EVIDENCE_SAST = "SAST"
EVIDENCE_SECURITY_TEST = "SECURITY_TEST"
EVIDENCE_SECURITY_POC = "SECURITY_POC"
EVIDENCE_TASK_REQUIREMENT = "TASK_REQUIREMENT"
EVIDENCE_FUNCTIONAL = "FUNCTIONAL_TEST"
EVIDENCE_CI = "CI_VERDICT"
EVIDENCE_SEMANTIC = "SEMANTIC_RELATION"
EVIDENCE_FINDING = "SECURITY_FINDING"

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_SECURITY_PASS = "SECURITY_PASS"
STATUS_NEW_FINDING = "NEW_FINDING"
STATUS_TOOL_FAILURE = "TOOL_FAILURE"
STATUS_INCOMPLETE = "INCOMPLETE"
STATUS_TIMEOUT = "TIMEOUT"
STATUS_MALFORMED = "MALFORMED"

SECURITY_FAIL_STATUSES = frozenset({STATUS_FAIL, STATUS_NEW_FINDING})
INCOMPLETE_STATUSES = frozenset(
    {STATUS_TOOL_FAILURE, STATUS_INCOMPLETE, STATUS_TIMEOUT, STATUS_MALFORMED}
)

BINDING_VALID = "VALID"
BINDING_INVALID = "INVALID_EVIDENCE"
REASON_STALE = "STALE"
REASON_WRONG_SOURCE = "WRONG_SOURCE"
REASON_WRONG_PATCH = "WRONG_PATCH"
REASON_WRONG_REPO = "WRONG_REPO"
REASON_UNBOUND = "UNBOUND"

AUTH_EXPLICIT = "EXPLICIT"
AUTH_INFORMATIONAL = "INFORMATIONAL"
AUTH_NONE = "NONE"

FACT_TASK_AUTHORIZES_PUBLIC_API_CHANGE = "TASK_AUTHORIZES_PUBLIC_API_CHANGE"
FACT_TASK_REQUIRES_PUBLIC_API_CHANGE = "TASK_REQUIRES_PUBLIC_API_CHANGE"
FACT_TASK_REQUIRES_NEW_HELPER_OR_UNIT = "TASK_REQUIRES_NEW_HELPER_OR_UNIT"
FACT_TASK_TARGETS_SYMBOL = "TASK_TARGETS_SYMBOL"
FACT_TASK_TARGETS_FILE = "TASK_TARGETS_FILE"
FACT_REPOSITORY_FORBIDS_PUBLIC_API = "REPOSITORY_FORBIDS_PUBLIC_API"

CONFLICT_SAST_PASS_POC_FAIL = "SAST_PASS_VS_SECURITY_POC_FAIL"
CONFLICT_TASK_API_VS_REPO_POLICY = "TASK_AUTHORIZES_PUBLIC_API_VS_REPOSITORY_POLICY"

BindingStatus = Literal["VALID", "INVALID_EVIDENCE"]


def evidence_hash(data: Any) -> str:
    return canonical_json_hash(data)


@dataclass(frozen=True)
class BindingExpectation:
    repo: str | None = None
    source_sha: str | None = None
    patch_digest: str | None = None
    candidate_digest: str | None = None


@dataclass
class BindingResult:
    status: BindingStatus
    reasons: list[str] = field(default_factory=list)
    can_authorize: bool = True


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _binding_fields(receipt: Mapping[str, Any]) -> dict[str, str | None]:
    nested = receipt.get("binding")
    source = nested if isinstance(nested, Mapping) else receipt
    return {
        "repo": _opt_str(source.get("repo") or source.get("repository")),
        "source_sha": _opt_str(source.get("source_sha")),
        "patch_digest": _opt_str(source.get("patch_digest")),
        "candidate_digest": _opt_str(source.get("candidate_digest")),
    }


def validate_receipt_binding(
    receipt: Mapping[str, Any],
    expected: Mapping[str, Any] | None = None,
) -> BindingResult:
    expected = expected or {}
    exp = BindingExpectation(
        repo=_opt_str(expected.get("repo") or expected.get("repository")),
        source_sha=_opt_str(expected.get("source_sha")),
        patch_digest=_opt_str(expected.get("patch_digest")),
        candidate_digest=_opt_str(expected.get("candidate_digest")),
    )
    got = _binding_fields(receipt)
    expected_any = any([exp.repo, exp.source_sha, exp.patch_digest, exp.candidate_digest])
    got_any = any(got.values())
    reasons: list[str] = []
    if expected_any and not got_any:
        reasons.append(REASON_UNBOUND)
    if exp.repo and got["repo"] and got["repo"] != exp.repo:
        reasons.append(REASON_WRONG_REPO)
    if exp.repo and expected_any and not got["repo"] and got_any:
        reasons.append(REASON_WRONG_REPO)
    if exp.source_sha and got["source_sha"] and got["source_sha"] != exp.source_sha:
        reasons.append(REASON_WRONG_SOURCE)
    if exp.source_sha and expected_any and not got["source_sha"] and got_any:
        reasons.append(REASON_WRONG_SOURCE)
    if exp.patch_digest and got["patch_digest"] and got["patch_digest"] != exp.patch_digest:
        reasons.append(REASON_WRONG_PATCH)
    if exp.patch_digest and expected_any and not got["patch_digest"] and got_any:
        reasons.append(REASON_WRONG_PATCH)
    if (
        exp.candidate_digest
        and got["candidate_digest"]
        and got["candidate_digest"] != exp.candidate_digest
    ):
        reasons.append(REASON_STALE)
    if reasons:
        return BindingResult(status=BINDING_INVALID, reasons=reasons, can_authorize=False)
    return BindingResult(status=BINDING_VALID, reasons=[], can_authorize=True)


def receipt_fingerprint(receipt: Mapping[str, Any]) -> str:
    payload = {
        "evidence_type": receipt.get("evidence_type"),
        "rule_id": receipt.get("rule_id") or receipt.get("fact"),
        "location_path": receipt.get("location_path") or receipt.get("path"),
        "cwe": receipt.get("cwe"),
        "result_status": receipt.get("result_status"),
        "check_name": receipt.get("check_name"),
    }
    return evidence_hash(payload)


def receipt_digest(receipt: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in receipt.items() if key != "digest"}
    return evidence_hash(payload)


def make_receipt(
    *,
    evidence_type: str,
    result_status: str,
    trust_class: str,
    producer: str,
    repo: str | None = None,
    source_sha: str | None = None,
    patch_digest: str | None = None,
    candidate_digest: str | None = None,
    rule_id: str | None = None,
    location_path: str | None = None,
    cwe: str | None = None,
    fact: str | None = None,
    check_name: str | None = None,
    authorization_class: str | None = None,
    issuer: str | None = None,
    detail: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema": SCHEMA_EVIDENCE,
        "schema_version": SCHEMA_EVIDENCE,
        "evidence_id": "",
        "evidence_type": evidence_type,
        "result_status": result_status,
        "trust_class": trust_class,
        "producer": {
            "name": producer,
            "trust_class": trust_class,
            "issuer": issuer or producer,
        },
        "binding": {
            "repo": repo,
            "source_sha": source_sha,
            "patch_digest": patch_digest,
            "candidate_digest": candidate_digest,
        },
        "repository": repo,
        "source_sha": source_sha,
        "patch_digest": patch_digest,
        "differential_status": result_status,
        "rule_id": rule_id,
        "location_path": location_path,
        "cwe": cwe,
        "fact": fact,
        "check_name": check_name,
        "authorization_class": authorization_class,
        "detail": detail,
        "authoritative": trust_class in AUTHORITATIVE_TRUST
        or trust_class in {TRUST_TASK_SYSTEM, TRUST_REPOSITORY_METADATA},
        "extra": dict(extra) if extra else {},
    }
    digest = receipt_digest(receipt)
    receipt["digest"] = digest
    receipt["evidence_id"] = digest[:16]
    return receipt


def is_authoritative(receipt: Mapping[str, Any]) -> bool:
    trust = str(receipt.get("trust_class") or TRUST_UNKNOWN)
    if trust in NON_AUTHORITATIVE_TRUST:
        return False
    producer = receipt.get("producer")
    if isinstance(producer, Mapping):
        if str(producer.get("trust_class") or "") in NON_AUTHORITATIVE_TRUST:
            return False
    if trust in AUTHORITATIVE_TRUST:
        return True
    if trust in {TRUST_TASK_SYSTEM, TRUST_REPOSITORY_METADATA}:
        return True
    return bool(receipt.get("authoritative")) and trust not in NON_AUTHORITATIVE_TRUST


def receipt_may_authorize(receipt: Mapping[str, Any]) -> bool:
    trust = str(receipt.get("trust_class") or TRUST_UNKNOWN)
    if trust in NON_AUTHORITATIVE_TRUST:
        return False
    producer = receipt.get("producer")
    if isinstance(producer, Mapping) and str(producer.get("trust_class") or "") in (
        NON_AUTHORITATIVE_TRUST
    ):
        return False
    if trust in AUTHORITATIVE_TRUST:
        return True
    if trust == TRUST_TASK_SYSTEM:
        return (
            str(receipt.get("evidence_type") or "") == EVIDENCE_TASK_REQUIREMENT
            and str(receipt.get("authorization_class") or "") == AUTH_EXPLICIT
        )
    if trust == TRUST_REPOSITORY_METADATA:
        return str(receipt.get("evidence_type") or "") == EVIDENCE_SEMANTIC
    return False


def security_related(receipt: Mapping[str, Any]) -> bool:
    kind = str(receipt.get("evidence_type") or "")
    return kind in {EVIDENCE_SAST, EVIDENCE_SECURITY_TEST, EVIDENCE_SECURITY_POC, EVIDENCE_FINDING}


def adapter_config_digest(config: Mapping[str, Any] | Sequence[str] | None) -> str:
    if config is None:
        return evidence_hash({"adapters": []})
    if isinstance(config, Mapping):
        return evidence_hash(dict(config))
    return evidence_hash({"adapters": list(config)})


REQUIRED_RECEIPT_FIELDS = ("schema", "evidence_type", "result_status", "trust_class", "producer")


def validate_receipt_schema(receipt: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    if not isinstance(receipt, Mapping):
        return ["NOT_A_MAPPING"]
    schema = receipt.get("schema") or receipt.get("schema_version")
    if schema not in {SCHEMA_EVIDENCE, "task_evidence_receipt.v1"}:
        problems.append("UNKNOWN_SCHEMA")
    for field_name in REQUIRED_RECEIPT_FIELDS:
        if field_name not in receipt or receipt.get(field_name) in (None, ""):
            if field_name == "schema" and receipt.get("schema_version"):
                continue
            problems.append(f"MISSING_{field_name.upper()}")
    return problems


def strip_actor_authority(receipt: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(receipt)
    trust = str(payload.get("trust_class") or TRUST_UNKNOWN)
    producer = payload.get("producer")
    producer_trust = ""
    if isinstance(producer, Mapping):
        producer_trust = str(producer.get("trust_class") or "")
        producer = dict(producer)
    if trust in NON_AUTHORITATIVE_TRUST or producer_trust in NON_AUTHORITATIVE_TRUST:
        payload["authoritative"] = False
        payload["can_authorize"] = False
        payload["trust_class"] = trust if trust in NON_AUTHORITATIVE_TRUST else TRUST_UNKNOWN
        if isinstance(producer, dict):
            if producer_trust in NON_AUTHORITATIVE_TRUST:
                producer["trust_class"] = producer_trust
            payload["producer"] = producer
    return payload
