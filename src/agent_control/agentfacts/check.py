"""Composite AgentFacts verification (sync + integrity + optional HMAC)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_control.agentfacts.manifest import DEFAULT_MANIFEST_NAME, load_manifest, repo_paths
from agent_control.agentfacts.sign import verify_integrity
from agent_control.agentfacts.sync import SyncResult, check_card_sync


@dataclass
class CheckResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    sync: SyncResult | None = None
    manifest_path: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "manifest_path": self.manifest_path,
            "sync": self.sync.as_dict() if self.sync else None,
        }


def verify_agentfacts(
    repo_root: Path,
    *,
    manifest_path: Path | None = None,
    signing_secret: str | None = None,
    require_hmac: bool = False,
) -> CheckResult:
    """
    Documented gate for V5 T01:

    - Human AGENT_CARD.md and machine agent-card.json stay in sync
    - Manifest integrity digest must match payload
    - Manifest source hashes must match current card files (stale fails)
    - If require_hmac / secret set with hmac block: HMAC must verify
    - Missing manifest or missing integrity → unsigned fail
    """
    md_path, json_path, default_manifest = repo_paths(repo_root)
    path = manifest_path or default_manifest
    errors: list[str] = []

    if not md_path.is_file():
        errors.append(f"missing {md_path}")
    if not json_path.is_file():
        errors.append(f"missing {json_path}")
    if errors:
        return CheckResult(ok=False, errors=errors, manifest_path=str(path))

    sync = check_card_sync(agent_card_md=md_path, agent_card_json=json_path)
    if not sync.ok:
        errors.extend(f"sync: {d}" for d in sync.divergences)

    if not path.is_file():
        errors.append(f"unsigned: missing manifest {path.name}")
        return CheckResult(
            ok=False,
            errors=errors,
            sync=sync,
            manifest_path=str(path),
        )

    try:
        manifest = load_manifest(path)
    except Exception as exc:  # noqa: BLE001 — surface schema / JSON errors
        errors.append(f"manifest invalid: {exc}")
        return CheckResult(
            ok=False,
            errors=errors,
            sync=sync,
            manifest_path=str(path),
        )

    md_bytes = md_path.read_bytes()
    json_bytes = json_path.read_bytes()
    errors.extend(
        verify_integrity(
            manifest,
            agent_card_md_bytes=md_bytes,
            agent_card_json_bytes=json_bytes,
            signing_secret=signing_secret,
            require_hmac=require_hmac,
        )
    )

    return CheckResult(
        ok=not errors,
        errors=errors,
        sync=sync,
        manifest_path=str(path),
    )


__all__ = ["CheckResult", "DEFAULT_MANIFEST_NAME", "verify_agentfacts"]
