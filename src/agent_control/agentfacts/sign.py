"""Integrity + optional HMAC for AgentFacts manifests."""

from __future__ import annotations

import hashlib
import hmac
import json
from copy import deepcopy
from typing import Any


PAYLOAD_KEYS = (
    "schema_version",
    "name",
    "signed_by",
    "signed_at_utc",
    "capabilities",
    "limitations",
    "documentation",
)

HMAC_KEY_ID = "ct103-agentfacts-v1"


def canonical_payload_bytes(manifest: dict[str, Any]) -> bytes:
    """Stable JSON for hashing: payload fields only, sorted keys."""
    body = {k: manifest[k] for k in PAYLOAD_KEYS if k in manifest}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path_bytes: bytes) -> str:
    return sha256_hex(path_bytes)


def attach_integrity(
    manifest: dict[str, Any],
    *,
    agent_card_md_bytes: bytes,
    agent_card_json_bytes: bytes,
    signing_secret: str | None = None,
) -> dict[str, Any]:
    """Return a copy with integrity digest (+ optional HMAC) attached."""
    out = deepcopy(manifest)
    out.pop("integrity", None)
    digest = sha256_hex(canonical_payload_bytes(out))
    integrity: dict[str, Any] = {
        "alg": "sha256",
        "digest": digest,
        "source_hashes": {
            "agent_card_md": sha256_hex(agent_card_md_bytes),
            "agent_card_json": sha256_hex(agent_card_json_bytes),
        },
    }
    if signing_secret:
        sig = hmac.new(
            signing_secret.encode("utf-8"),
            digest.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
        integrity["hmac"] = {
            "alg": "hmac-sha256",
            "key_id": HMAC_KEY_ID,
            "sig": sig,
        }
    out["integrity"] = integrity
    return out


def verify_integrity(
    manifest: dict[str, Any],
    *,
    agent_card_md_bytes: bytes | None = None,
    agent_card_json_bytes: bytes | None = None,
    signing_secret: str | None = None,
    require_hmac: bool = False,
) -> list[str]:
    """Return list of integrity failure reasons (empty = ok)."""
    errors: list[str] = []
    integrity = manifest.get("integrity")
    if not isinstance(integrity, dict):
        return ["unsigned: missing integrity block"]

    expected_digest = sha256_hex(canonical_payload_bytes(manifest))
    got_digest = integrity.get("digest")
    if got_digest != expected_digest:
        errors.append("integrity digest mismatch (manifest tampered or unsigned)")

    source_hashes = integrity.get("source_hashes") or {}
    if agent_card_md_bytes is not None:
        want = sha256_hex(agent_card_md_bytes)
        if source_hashes.get("agent_card_md") != want:
            errors.append("stale: agent_card_md source hash mismatch")
    if agent_card_json_bytes is not None:
        want = sha256_hex(agent_card_json_bytes)
        if source_hashes.get("agent_card_json") != want:
            errors.append("stale: agent_card_json source hash mismatch")

    hmac_block = integrity.get("hmac")
    if require_hmac and not hmac_block:
        errors.append("unsigned: hmac required but missing")
    elif hmac_block and signing_secret:
        expected_sig = hmac.new(
            signing_secret.encode("utf-8"),
            str(got_digest or expected_digest).encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(str(hmac_block.get("sig") or ""), expected_sig):
            errors.append("hmac signature invalid")
    elif hmac_block and not signing_secret:
        errors.append("hmac present but AGENTFACTS_SIGNING_SECRET unset")

    return errors
