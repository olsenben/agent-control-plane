"""Provenance-bound G0 input and policy_bundle_receipt.v1. Does not retune C."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from agent_shared.hash_utils import canonical_json_hash
from agent_shared.models.transaction.admission import PolicyFields
from agent_shared.models.transaction.preflight import PolicyBundleReceipt

G0_PRESENT_NONEMPTY = "G0_PRESENT_NONEMPTY"
G0_PRESENT_EXPLICIT_EMPTY = "G0_PRESENT_EXPLICIT_EMPTY"
G0_LOAD_FAILED = "G0_LOAD_FAILED"
G0_UNBOUND = "G0_UNBOUND"
G0_SCHEMA_INVALID = "G0_SCHEMA_INVALID"

FAIL_CLOSED_G0_STATES = frozenset({G0_LOAD_FAILED, G0_UNBOUND, G0_SCHEMA_INVALID})
_G0_PAYLOAD_KEYS = ("G0_PREFIXES", "G0_NAMES", "G0_SUBSTRINGS")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class G0InputBinding:
    state: str
    violations: tuple[str, ...]
    provenance_c_hash: str | None
    source_identity: str | None
    ruleset_present: bool

    @property
    def fail_closed(self) -> bool:
        return self.state in FAIL_CLOSED_G0_STATES

    @property
    def may_invoke_c(self) -> bool:
        return self.state in {G0_PRESENT_NONEMPTY, G0_PRESENT_EXPLICIT_EMPTY}


def _unbound() -> G0InputBinding:
    return G0InputBinding(
        state=G0_UNBOUND,
        violations=(),
        provenance_c_hash=None,
        source_identity=None,
        ruleset_present=False,
    )


def _failed(state: str, *, c_hash: str | None = None, identity: str | None = None) -> G0InputBinding:
    return G0InputBinding(
        state=state,
        violations=(),
        provenance_c_hash=c_hash,
        source_identity=identity,
        ruleset_present=False,
    )


def _ruleset_nonempty(prefixes: Any, names: Any, substrings: Any) -> bool:
    return bool(tuple(prefixes or ()) or frozenset(names or ()) or tuple(substrings or ()))


def bind_g0_input(
    changed_paths: Sequence[str],
    *,
    bound: bool = True,
    loader: Callable[[], Any] | None = None,
    expected_c_hash: str | None = None,
    observed_c_hash: str | None = None,
    payload: Any | None = None,
    payload_provided: bool = False,
) -> G0InputBinding:
    """Bind G0 from frozen C. Fail-closed states are never PRESENT_EXPLICIT_EMPTY."""
    if not bound:
        return _unbound()

    from agent_control.transaction.admission import C_LOAD_MODE, FROZEN_C_HASH
    from agent_control.transaction.admission.frozen_c import g0_violations

    expected = expected_c_hash or FROZEN_C_HASH
    identity: str | None = None
    c_hash: str | None = None
    try:
        if loader is not None:
            loaded = loader()
            if loaded is None:
                return _failed(G0_LOAD_FAILED, c_hash=expected)
        else:
            from agent_control.transaction.admission import frozen_c as loaded
    except Exception:
        return _failed(G0_LOAD_FAILED, c_hash=expected)

    if payload_provided:
        if not isinstance(payload, dict):
            return _failed(G0_SCHEMA_INVALID, c_hash=expected)
        if any(key not in payload for key in _G0_PAYLOAD_KEYS):
            return _failed(G0_SCHEMA_INVALID, c_hash=expected)
        prefixes = payload.get("G0_PREFIXES")
        names = payload.get("G0_NAMES")
        substrings = payload.get("G0_SUBSTRINGS")
        c_hash = str(payload.get("frozen_c_hash") or observed_c_hash or expected)
        identity = str(payload.get("source_identity") or "payload")
    else:
        try:
            prefixes = loaded.G0_PREFIXES
            names = loaded.G0_NAMES
            substrings = loaded.G0_SUBSTRINGS
            c_hash = str(getattr(loaded, "FROZEN_C_HASH", None) or observed_c_hash or expected)
            identity = (
                f"{C_LOAD_MODE}:agent_control.transaction.admission.frozen_c#{c_hash}"
            )
        except AttributeError:
            return _failed(G0_SCHEMA_INVALID, c_hash=expected)

    observed = observed_c_hash if observed_c_hash is not None else c_hash
    if not observed or observed != expected:
        return _failed(G0_SCHEMA_INVALID, c_hash=observed, identity=identity)
    if not isinstance(c_hash, str) or len(c_hash) != 64:
        return _failed(G0_SCHEMA_INVALID, c_hash=c_hash, identity=identity)

    ruleset_present = _ruleset_nonempty(prefixes, names, substrings)
    try:
        violations = tuple(g0_violations(list(changed_paths)))
    except Exception:
        return _failed(G0_LOAD_FAILED, c_hash=c_hash, identity=identity)

    state = G0_PRESENT_NONEMPTY if ruleset_present else G0_PRESENT_EXPLICIT_EMPTY
    return G0InputBinding(
        state=state,
        violations=violations,
        provenance_c_hash=c_hash,
        source_identity=identity,
        ruleset_present=ruleset_present,
    )


def create_policy_bundle_receipt(
    *,
    policy: PolicyFields,
    g0: G0InputBinding,
    c_load_mode: str | None = None,
    created_at: str | None = None,
) -> PolicyBundleReceipt:
    from agent_control.transaction.admission import FROZEN_C_HASH

    unsigned = {
        "schema_version": "policy_bundle_receipt.v1",
        "frozen_c_hash": g0.provenance_c_hash,
        "expected_frozen_c_hash": FROZEN_C_HASH,
        "policy_id": policy.policy_id,
        "policy_version": policy.policy_version,
        "policy_digest": policy.policy_digest,
        "admission_implementation_digest": policy.admission_implementation_digest,
        "g0_input_state": g0.state,
        "g0_source_identity": g0.source_identity,
        "c_load_mode": c_load_mode,
        "ruleset_present": g0.ruleset_present,
    }
    digest = canonical_json_hash(unsigned)
    return PolicyBundleReceipt.model_validate(
        {
            **unsigned,
            "bundle_digest": digest,
            "created_at": created_at or utc_now(),
        }
    )
