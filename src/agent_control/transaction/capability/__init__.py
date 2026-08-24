"""Durable patch capability mint / wrap / consume. CT103 state only."""

from __future__ import annotations

import json
import os
import secrets
import threading
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from agent_control.transaction.witness import StateWitnessError, check_state_witness
from agent_shared.hash_utils import canonical_json_hash
from agent_shared.models.transaction.capability import (
    ISSUER,
    CapabilityLifecycle,
    CapabilityPublicReceipt,
    DurablePatchCapability,
)
from agent_shared.models.transaction.identity import IdentityPrincipal

CAPABILITY_ALREADY_CONSUMED = "CAPABILITY_ALREADY_CONSUMED"
CAPABILITY_CONSUMED = "CONSUMED"
CAPABILITY_EXPIRED = "CAPABILITY_EXPIRED"
LIFECYCLE_MINTED: CapabilityLifecycle = "MINTED"
LIFECYCLE_CONSUMING: CapabilityLifecycle = "CONSUMING"
LIFECYCLE_CONSUMED: CapabilityLifecycle = "CONSUMED"
LIFECYCLE_EXPIRED: CapabilityLifecycle = "EXPIRED"
LIFECYCLE_INVALIDATED: CapabilityLifecycle = "INVALIDATED"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def lifecycle_of(record: Mapping[str, Any]) -> CapabilityLifecycle:
    raw = record.get("lifecycle")
    if raw in {
        LIFECYCLE_MINTED,
        LIFECYCLE_CONSUMING,
        LIFECYCLE_CONSUMED,
        LIFECYCLE_EXPIRED,
        LIFECYCLE_INVALIDATED,
    }:
        return raw  # type: ignore[return-value]
    if record.get("consumed") is True:
        return LIFECYCLE_CONSUMED
    return LIFECYCLE_MINTED


def consumed_from_lifecycle(lifecycle: CapabilityLifecycle) -> bool:
    return lifecycle == LIFECYCLE_CONSUMED


def _apply_lifecycle(item: dict[str, Any], lifecycle: CapabilityLifecycle) -> dict[str, Any]:
    item["lifecycle"] = lifecycle
    item["consumed"] = consumed_from_lifecycle(lifecycle)
    if lifecycle == LIFECYCLE_CONSUMED and not item.get("consumed_at"):
        item["consumed_at"] = utc_now()
    return item


class CapabilityStore(Protocol):
    def put(self, record: dict[str, Any]) -> None: ...

    def get(self, capability_id: str) -> dict[str, Any] | None: ...

    def consume_atomic(self, capability_id: str) -> dict[str, Any]: ...


class InMemoryCapabilityStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, dict[str, Any]] = {}

    def put(self, record: dict[str, Any]) -> None:
        cap_id = str(record["capability_id"])
        if "lifecycle" not in record:
            _apply_lifecycle(record, lifecycle_of(record))
        with self._lock:
            self._items[cap_id] = dict(record)

    def get(self, capability_id: str) -> dict[str, Any] | None:
        with self._lock:
            item = self._items.get(capability_id)
            return dict(item) if item is not None else None

    def consume_atomic(self, capability_id: str) -> dict[str, Any]:
        with self._lock:
            item = self._items.get(capability_id)
            if item is None:
                raise KeyError(capability_id)
            lifecycle = lifecycle_of(item)
            if lifecycle in {LIFECYCLE_CONSUMED, LIFECYCLE_INVALIDATED, LIFECYCLE_EXPIRED}:
                raise CapabilityAlreadyConsumed(capability_id)
            _apply_lifecycle(item, LIFECYCLE_CONSUMING)
            _apply_lifecycle(item, LIFECYCLE_CONSUMED)
            return dict(item)


class FilesystemCapabilityStore:
    """CT103 durable filesystem store. Secret material stays in this tree."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, capability_id: str) -> Path:
        return self.root / f"{capability_id}.json"

    def put(self, record: dict[str, Any]) -> None:
        cap_id = str(record["capability_id"])
        if "lifecycle" not in record:
            _apply_lifecycle(record, lifecycle_of(record))
        path = self._path(cap_id)
        tmp = path.with_suffix(".json.tmp")
        with self._lock:
            tmp.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
            os.replace(tmp, path)

    def get(self, capability_id: str) -> dict[str, Any] | None:
        path = self._path(capability_id)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def consume_atomic(self, capability_id: str) -> dict[str, Any]:
        path = self._path(capability_id)
        lock_path = path.with_suffix(".lock")
        with self._lock:
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
            except FileExistsError as exc:
                raise CapabilityAlreadyConsumed(capability_id) from exc
            try:
                if not path.is_file():
                    raise KeyError(capability_id)
                item = json.loads(path.read_text(encoding="utf-8"))
                lifecycle = lifecycle_of(item)
                if lifecycle in {LIFECYCLE_CONSUMED, LIFECYCLE_INVALIDATED, LIFECYCLE_EXPIRED}:
                    raise CapabilityAlreadyConsumed(capability_id)
                _apply_lifecycle(item, LIFECYCLE_CONSUMING)
                tmp = path.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(item, indent=2, sort_keys=True), encoding="utf-8")
                os.replace(tmp, path)
                _apply_lifecycle(item, LIFECYCLE_CONSUMED)
                tmp.write_text(json.dumps(item, indent=2, sort_keys=True), encoding="utf-8")
                os.replace(tmp, path)
                return item
            finally:
                lock_path.unlink(missing_ok=True)


class CapabilityAlreadyConsumed(RuntimeError):
    code = CAPABILITY_ALREADY_CONSUMED

    def __init__(self, capability_id: str) -> None:
        self.capability_id = capability_id
        super().__init__(CAPABILITY_ALREADY_CONSUMED)


def public_receipt(record: Mapping[str, Any], *, replayed: bool = False) -> CapabilityPublicReceipt:
    expires = record.get("expires_at")
    expired = bool(expires and utc_now() > str(expires))
    lifecycle = lifecycle_of(record)
    if expired and lifecycle in {LIFECYCLE_MINTED, LIFECYCLE_CONSUMING}:
        lifecycle = LIFECYCLE_EXPIRED
    return CapabilityPublicReceipt(
        capability_id=str(record["capability_id"]),
        repo=str(record["repo"]),
        source_sha=str(record["source_sha"]),
        patch_digest=str(record["patch_digest"]),
        allowed_target_branch=str(record["allowed_target_branch"]),
        issued_at=str(record["issued_at"]),
        expires_at=str(expires) if expires else None,
        consumed=consumed_from_lifecycle(lifecycle),
        lifecycle=lifecycle,
        expired=expired,
        replayed=replayed,
        issuer=str(record.get("issuer") or ISSUER),
    )


def mint_capability(
    *,
    repo: str,
    tenant_id: str,
    org_id: str,
    source_sha: str,
    patch_digest: str,
    allowed_target_branch: str,
    policy_digest: str,
    verification_digest: str,
    admission_decision_digest: str,
    evidence_bundle_digest: str,
    task_id: str,
    session_id: str,
    human_initiator: IdentityPrincipal,
    agent_identity: IdentityPrincipal,
    store: CapabilityStore,
    expires_at: str | None = None,
    capability_id: str | None = None,
    issued_at: str | None = None,
) -> DurablePatchCapability:
    cap_id = capability_id or str(uuid.uuid4())
    secret = secrets.token_hex(32)
    issued = issued_at or utc_now()
    body = DurablePatchCapability(
        capability_id=cap_id,
        repo=repo,
        tenant_id=tenant_id,
        org_id=org_id,
        source_sha=source_sha,
        patch_digest=patch_digest,
        allowed_target_branch=allowed_target_branch,
        policy_digest=policy_digest,
        verification_digest=verification_digest,
        admission_decision_digest=admission_decision_digest,
        evidence_bundle_digest=evidence_bundle_digest,
        task_id=task_id,
        session_id=session_id,
        human_initiator=human_initiator,
        agent_identity=agent_identity,
        issued_at=issued,
        expires_at=expires_at,
    )
    digest = canonical_json_hash(body.model_dump(mode="json"))
    record = body.model_dump(mode="json")
    record["capability_digest"] = digest
    record["secret"] = secret
    _apply_lifecycle(record, LIFECYCLE_MINTED)
    store.put(record)
    return DurablePatchCapability.model_validate(
        {key: value for key, value in record.items() if key != "secret"}
    )


def wrap_capability(
    base: Mapping[str, Any],
    *,
    session_id: str,
    capability_id: str,
    expires_at: str | None = None,
) -> dict[str, Any]:
    payload = dict(base)
    payload["capability_id"] = capability_id
    payload["session_id"] = session_id
    payload["issued_at"] = utc_now()
    payload["expires_at"] = expires_at
    payload["consumed"] = False
    payload["lifecycle"] = LIFECYCLE_MINTED
    payload["issuer_identity"] = ISSUER
    return payload


def consume_capability(
    *,
    capability_id: str,
    store: CapabilityStore,
    current_base_sha: str,
    patch_digest: str,
    repo: str,
    target_ref: str,
    policy_digest: str,
    evidence_bundle_digest: str | None = None,
    now_iso: str | None = None,
) -> dict[str, Any]:
    stored = store.get(capability_id)
    if stored is None:
        raise KeyError(capability_id)
    lifecycle = lifecycle_of(stored)
    if lifecycle == LIFECYCLE_CONSUMED or stored.get("consumed") is True:
        raise CapabilityAlreadyConsumed(capability_id)
    expires = stored.get("expires_at")
    now = now_iso or utc_now()
    if (expires and now > str(expires)) or lifecycle == LIFECYCLE_EXPIRED:
        if lifecycle != LIFECYCLE_EXPIRED:
            stored = dict(stored)
            _apply_lifecycle(stored, LIFECYCLE_EXPIRED)
            store.put(stored)
        return {"status": CAPABILITY_EXPIRED, "allowed": False, "reasons": ["expired"]}
    if lifecycle == LIFECYCLE_INVALIDATED:
        raise CapabilityAlreadyConsumed(capability_id)
    expected = {
        "source_sha": stored.get("source_sha"),
        "patch_digest": stored.get("patch_digest"),
        "policy_digest": stored.get("policy_digest"),
        "allowed_target_branch": stored.get("allowed_target_branch"),
        "repo": stored.get("repo"),
        "evidence_bundle_digest": stored.get("evidence_bundle_digest"),
    }
    observed = {
        "source_sha": current_base_sha,
        "patch_digest": patch_digest,
        "policy_digest": policy_digest,
        "allowed_target_branch": target_ref,
        "repo": repo,
        "evidence_bundle_digest": evidence_bundle_digest or stored.get("evidence_bundle_digest"),
        "consumed": False,
    }
    try:
        check_state_witness(expected=expected, observed=observed, consumed=False)
    except StateWitnessError:
        raise
    try:
        consumed = store.consume_atomic(capability_id)
    except CapabilityAlreadyConsumed:
        raise
    receipt = public_receipt(consumed)
    return {
        "status": CAPABILITY_CONSUMED,
        "allowed": True,
        "reasons": ["exact_binding"],
        "receipt": receipt.model_dump(mode="json"),
    }


def worker_facing_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    """Strip secret material. Worker APIs must use this, never the store record."""
    return public_receipt(record).model_dump(mode="json")


def invalidate_capability(store: CapabilityStore, capability_id: str) -> dict[str, Any]:
    stored = store.get(capability_id)
    if stored is None:
        raise KeyError(capability_id)
    if lifecycle_of(stored) == LIFECYCLE_CONSUMED:
        raise CapabilityAlreadyConsumed(capability_id)
    updated = dict(stored)
    _apply_lifecycle(updated, LIFECYCLE_INVALIDATED)
    store.put(updated)
    return updated
