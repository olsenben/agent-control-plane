"""Durable repair reservation + worker lease (Slice 6F.2)."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_LEASE_TTL_SECONDS = 900
LINEAGE_MAX_ATTEMPTS_V1 = 1


@dataclass
class RepairReservation:
    repair_key: str
    repository: str
    pr_number: int | None
    expected_head_commit_sha: str
    repair_attempt: int
    fix_run_id: str
    repair_lineage_id: str
    evidence_observation_id: str
    agent_branch: str
    allowed_files: list[str] = field(default_factory=list)
    required_command_ids: list[str] = field(default_factory=list)
    issue_id: int | None = None
    artifact_root: str | None = None
    job_id: str | None = None
    status: str = "reserved"  # reserved | claimed | terminal
    created_at: float = field(default_factory=time.time)
    terminal_reason: str | None = None
    new_head_commit_sha: str | None = None
    # V4.1.1 PR1 — immutable policy pin (resolved on CT103 at reservation time)
    policy_source_repo: str = ""
    policy_source_remote: str = ""
    policy_source_ref: str = ""
    policy_source_sha: str = ""
    policy_schema_version: str = "policy_source.v1"
    # V4.1.1 PR2 — tool_policy.v2 effective hashes + allowance
    allowed_command_ids: list[str] = field(default_factory=list)
    command_constraints: dict[str, Any] = field(default_factory=dict)
    command_registry_hash: str = ""
    effective_command_policy_hash: str = ""
    tool_policy_status: str = "empty_missing"
    # V4.1.1 PR3 — CT103-issued attestation nonce
    attestation_nonce: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RepairReservation:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def reservation_dir(state_root: Path) -> Path:
    return state_root / "locks" / "repair" / "reservations"


def lease_dir(state_root: Path) -> Path:
    return state_root / "locks" / "repair" / "leases"


def reservation_path(state_root: Path, repair_key: str) -> Path:
    safe = repair_key.replace(":", "_").replace("/", "_")
    return reservation_dir(state_root) / f"{safe}.json"


def lease_path(state_root: Path, repair_key: str) -> Path:
    safe = repair_key.replace(":", "_").replace("/", "_")
    return lease_dir(state_root) / f"{safe}.lease"


def lineage_path(state_root: Path, lineage_id: str) -> Path:
    safe = lineage_id.replace(":", "_").replace("/", "_")
    return reservation_dir(state_root) / "lineage" / f"{safe}.json"


def create_repair_reservation(
    state_root: Path,
    reservation: RepairReservation,
) -> RepairReservation | None:
    """Atomically create reservation. Returns None if already exists for same key."""
    path = reservation_path(state_root, reservation.repair_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(reservation.to_dict(), indent=2)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(path, flags, 0o644)
    except FileExistsError:
        return None
    try:
        os.write(fd, payload.encode("utf-8"))
    finally:
        os.close(fd)
    return reservation


def load_repair_reservation(state_root: Path, repair_key: str) -> RepairReservation | None:
    path = reservation_path(state_root, repair_key)
    if not path.is_file():
        return None
    try:
        return RepairReservation.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def save_repair_reservation(state_root: Path, reservation: RepairReservation) -> None:
    path = reservation_path(state_root, reservation.repair_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(reservation.to_dict(), indent=2), encoding="utf-8")
    os.replace(tmp, path)


def get_lineage_attempt_count(state_root: Path, lineage_id: str) -> int:
    path = lineage_path(state_root, lineage_id)
    if not path.is_file():
        return 0
    try:
        return int(json.loads(path.read_text(encoding="utf-8")).get("attempts", 0))
    except (json.JSONDecodeError, ValueError, TypeError):
        return 0


def increment_lineage_attempt(
    state_root: Path,
    lineage_id: str,
    *,
    max_attempts: int = LINEAGE_MAX_ATTEMPTS_V1,
) -> int | None:
    path = lineage_path(state_root, lineage_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    current = get_lineage_attempt_count(state_root, lineage_id)
    if current >= max_attempts:
        return None
    new_val = current + 1
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"attempts": new_val, "lineage_id": lineage_id}), encoding="utf-8")
    os.replace(tmp, path)
    return new_val


def acquire_repair_lease(
    state_root: Path,
    repair_key: str,
    *,
    holder: str,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
) -> Path | None:
    """Worker-owned lease with expiry. Reclaims expired leases."""
    path = lease_path(state_root, repair_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            expires = float(data.get("expires_at", 0))
            if expires > now:
                return None
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return None
    payload = {
        "holder": holder,
        "repair_key": repair_key,
        "acquired_at": now,
        "expires_at": now + ttl_seconds,
        "heartbeat_at": now,
    }
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(path, flags, 0o644)
    except FileExistsError:
        return None
    try:
        os.write(fd, json.dumps(payload).encode("utf-8"))
    finally:
        os.close(fd)
    return path


def heartbeat_repair_lease(lease: Path, *, ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS) -> bool:
    if not lease.is_file():
        return False
    try:
        data = json.loads(lease.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    now = time.time()
    data["heartbeat_at"] = now
    data["expires_at"] = now + ttl_seconds
    tmp = lease.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, lease)
    return True


def release_repair_lease(lease: Path | None) -> None:
    if lease is None:
        return
    try:
        lease.unlink(missing_ok=True)
    except OSError:
        logger.exception("repair_lease_release_failed path=%s", lease)
