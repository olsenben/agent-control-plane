"""Project an evidence bundle onto frozen C inputs. Does not copy decide_c."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from agent_control.transaction.evidence.receipts import (
    AUTH_EXPLICIT,
    BINDING_INVALID,
    EVIDENCE_TASK_REQUIREMENT,
    FACT_TASK_AUTHORIZES_PUBLIC_API_CHANGE,
    FACT_TASK_REQUIRES_NEW_HELPER_OR_UNIT,
    FACT_TASK_REQUIRES_PUBLIC_API_CHANGE,
    FACT_TASK_TARGETS_FILE,
    FACT_TASK_TARGETS_SYMBOL,
    INCOMPLETE_STATUSES,
    REASON_STALE,
    REASON_UNBOUND,
    SECURITY_FAIL_STATUSES,
    TRUST_ACTOR_PROVIDED,
    TRUST_UNKNOWN,
    is_authoritative,
    security_related,
)

GROUNDED_RECEIPTS = frozenset({"TASK_NAMED", "LOCAL_CREATION", "FAILURE_DIRECT"})


def _copy_units(units: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    copied: list[dict[str, Any]] = []
    for unit in units:
        row = dict(unit)
        row["receipts"] = list(unit.get("receipts") or [])
        copied.append(row)
    return copied


def _security_conflict(bundle: Mapping[str, Any]) -> bool:
    for item in bundle.get("conflicts") or []:
        if not isinstance(item, Mapping):
            continue
        kind = str(item.get("kind") or item.get("code") or "")
        if "SAST" in kind or "POC" in kind or "SECURITY" in kind or kind == "EVIDENCE_CONFLICT":
            return True
        if "PUBLIC_API" in kind:
            return True
    return False


def _authoritative_security_fail(receipts: Sequence[Mapping[str, Any]]) -> bool:
    for receipt in receipts:
        if not security_related(receipt):
            continue
        if receipt.get("result_status") not in SECURITY_FAIL_STATUSES:
            continue
        if str(receipt.get("trust_class") or "") in {TRUST_ACTOR_PROVIDED, TRUST_UNKNOWN}:
            continue
        if not is_authoritative(receipt) and not receipt.get("can_authorize"):
            continue
        return True
    return False


def _incomplete_signals(bundle: Mapping[str, Any]) -> list[str]:
    notes: list[str] = []
    for receipt in list(bundle.get("receipts") or []) + list(bundle.get("invalid_receipts") or []):
        if not isinstance(receipt, Mapping):
            continue
        status = str(receipt.get("result_status") or "")
        reasons = [str(item) for item in (receipt.get("binding_reasons") or [])]
        if status in INCOMPLETE_STATUSES:
            notes.append(f"RECEIPT_{status}")
        if receipt.get("binding_status") == BINDING_INVALID:
            notes.append("INVALID_EVIDENCE")
        if REASON_STALE in reasons:
            notes.append(REASON_STALE)
        if REASON_UNBOUND in reasons:
            notes.append(REASON_UNBOUND)
    if bundle.get("missing_providers"):
        notes.append("MISSING_PROVIDER")
    if bundle.get("failed_providers") or bundle.get("required_provider_failures"):
        notes.append("FAILED_PROVIDER")
    return notes


def _task_targets(receipts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    files: set[str] = set()
    symbols: set[str] = set()
    helper = False
    public_api = False
    for receipt in receipts:
        if receipt.get("evidence_type") != EVIDENCE_TASK_REQUIREMENT:
            continue
        if str(receipt.get("authorization_class") or "") != AUTH_EXPLICIT:
            continue
        if receipt.get("can_authorize") is False:
            continue
        fact = str(receipt.get("fact") or "")
        path = str(receipt.get("location_path") or "")
        symbol = str(receipt.get("check_name") or receipt.get("detail") or "")
        if fact == FACT_TASK_TARGETS_FILE and path:
            files.add(path.replace("\\", "/"))
        if fact == FACT_TASK_TARGETS_SYMBOL and symbol:
            symbols.add(symbol)
        if fact == FACT_TASK_REQUIRES_NEW_HELPER_OR_UNIT:
            helper = True
        if fact in {FACT_TASK_AUTHORIZES_PUBLIC_API_CHANGE, FACT_TASK_REQUIRES_PUBLIC_API_CHANGE}:
            public_api = True
    return {"files": files, "symbols": symbols, "helper": helper, "public_api": public_api}


def _unit_targeted(unit: Mapping[str, Any], targets: Mapping[str, Any]) -> bool:
    path = str(unit.get("path") or "").replace("\\", "/")
    symbol = str(unit.get("symbol") or "")
    files = targets.get("files") or set()
    symbols = targets.get("symbols") or set()
    if path and path in files:
        return True
    if symbol and symbol in symbols:
        return True
    if targets.get("public_api") or targets.get("helper"):
        if path and (not files or path in files):
            return True
        if symbol and (not symbols or symbol in symbols):
            return True
    return False


def project_bundle_onto_c_inputs(
    units: Sequence[Mapping[str, Any]],
    verification: Mapping[str, Any],
    bundle: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    """EVIDENCE_INTERFACE_ONLY. Never sets verification.passed True."""
    notes: list[str] = []
    projected_units = _copy_units(units)
    projected_verify = dict(verification)
    receipts = [
        item
        for item in (bundle.get("receipts") or bundle.get("items") or [])
        if isinstance(item, Mapping)
    ]

    incomplete_notes = _incomplete_signals(bundle)
    security_fail = _authoritative_security_fail(receipts)
    conflict = _security_conflict(bundle)
    if security_fail:
        projected_verify["passed"] = False
        notes.append("SECURITY_FAIL_PROJECTED")
    if conflict:
        notes.append("EVIDENCE_CONFLICT")
        if security_fail:
            projected_verify["passed"] = False
        else:
            projected_verify["incomplete"] = True
            projected_verify["passed"] = False
            notes.append("CONFLICT_FAIL_CLOSED")
    if incomplete_notes and not security_fail:
        projected_verify["incomplete"] = True
        projected_verify["passed"] = False
        notes.extend(sorted(set(incomplete_notes)))
        notes.append("INCOMPLETE_NOT_PASS")
    elif incomplete_notes and security_fail:
        notes.extend(sorted(set(incomplete_notes)))
        notes.append("SECURITY_FAIL_OVERRIDES_TOOL_FAILURE")

    targets = _task_targets(receipts)
    for unit in projected_units:
        if not _unit_targeted(unit, targets):
            continue
        added: list[str] = []
        current = set(unit["receipts"])
        if "TASK_NAMED" not in current:
            unit["receipts"].append("TASK_NAMED")
            added.append("TASK_NAMED")
        if targets.get("helper") and "LOCAL_CREATION" not in current:
            unit["receipts"].append("LOCAL_CREATION")
            added.append("LOCAL_CREATION")
        if added:
            grounded = [item for item in unit["receipts"] if item != "UNRELATED_OR_UNKNOWN"]
            if grounded:
                unit["receipts"] = list(dict.fromkeys(grounded))
            notes.append(f"TASK_RECEIPTS:{unit.get('path')}:{','.join(added)}")

    return projected_units, projected_verify, notes
