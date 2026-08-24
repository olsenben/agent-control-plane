"""Nested transaction-control readiness. Must not 503 core /readyz for CT102 down."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_control.config import Settings
from agent_control.transaction.config import load_transaction_control_config
from agent_control.transaction.evidence.adapters import P1, P2, P3, P4, P5, PROVIDERS
from agent_control.transaction.evidence.route import REQUIRED, routed_providers, build_route

TRANSACTION_CHECK_KEYS = (
    "package_importable",
    "durable_state_writable",
    "frozen_c_loaded",
    "capability_store",
    "evidence_bus",
    "broker_configured",
    "gitea_reachable",
)

REQUIRED_PROVIDER_IDS = (P1, P2, P3, P4, P5)
AUTHORITATIVE_VERIFIER_ID = "ct102_functional_ci"


def _ok(detail: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": "ok"}
    if detail:
        payload.update(detail)
    return payload


def _err(error: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": "error", "error": error}
    payload.update(extra)
    return payload


def check_package_importable() -> dict[str, Any]:
    try:
        import agent_control.transaction as txn  # noqa: F401
        from agent_control.transaction.admission import FROZEN_C_HASH
        from agent_control.transaction.capability import FilesystemCapabilityStore  # noqa: F401
        from agent_control.transaction.evidence import run_evidence_bus  # noqa: F401

        _ = FROZEN_C_HASH
        return _ok()
    except Exception as exc:  # noqa: BLE001
        return _err(type(exc).__name__)


def check_durable_state_writable(state_root: Path) -> dict[str, Any]:
    try:
        root = Path(state_root) / "transaction"
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".readyz_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return _ok()
    except Exception as exc:  # noqa: BLE001
        return _err(type(exc).__name__)


def check_frozen_c_loaded() -> dict[str, Any]:
    try:
        from agent_control.transaction.admission import C_LOAD_MODE, FROZEN_C_HASH

        if not isinstance(FROZEN_C_HASH, str) or len(FROZEN_C_HASH) != 64:
            return _err("frozen_c_hash_invalid")
        return _ok({"mode": C_LOAD_MODE})
    except Exception as exc:  # noqa: BLE001
        return _err(type(exc).__name__)


def check_capability_store(state_root: Path) -> dict[str, Any]:
    try:
        from agent_control.transaction.capability import FilesystemCapabilityStore

        store = FilesystemCapabilityStore(Path(state_root) / "transaction" / "capabilities")
        probe_id = ".readyz_capability"
        store.put({"capability_id": probe_id, "lifecycle": "MINTED", "consumed": False})
        loaded = store.get(probe_id)
        probe_path = store.root / f"{probe_id}.json"
        probe_path.unlink(missing_ok=True)
        if loaded is None:
            return _err("capability_store_unreadable")
        return _ok()
    except Exception as exc:  # noqa: BLE001
        return _err(type(exc).__name__)


def check_evidence_bus() -> dict[str, Any]:
    try:
        missing = [pid for pid in REQUIRED_PROVIDER_IDS if pid not in PROVIDERS]
        if missing:
            return _err("required_providers_missing", missing=missing)
        route = build_route(["PRODUCTION_SOURCE_CHANGE"])
        providers = routed_providers(route)
        if not any(item.requirement_class == REQUIRED for item in providers):
            return _err("required_route_empty")
        return _ok({"providers": list(REQUIRED_PROVIDER_IDS)})
    except Exception as exc:  # noqa: BLE001
        return _err(type(exc).__name__)


def check_broker_configured(settings: Settings) -> dict[str, Any]:
    token_present = bool((settings.gitea_bot_token or "").strip())
    url_present = bool((settings.gitea_base_url or "").strip())
    if token_present and url_present:
        return _ok({"token_present": True})
    return _err(
        "broker_not_configured",
        token_present=token_present,
        base_url_present=url_present,
    )


def check_gitea_reachable(settings: Settings, *, timeout: float = 2.0) -> dict[str, Any]:
    """CT102 reachability. Nested only — never a core /readyz 503 by itself."""
    import httpx

    url = (settings.gitea_base_url or "").rstrip("/")
    if not url:
        return _err("gitea_base_url_unset")
    if not (settings.gitea_bot_token or "").strip():
        return _err("gitea_probe_skipped_no_token")
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(f"{url}/api/v1/version")
        if response.status_code >= 400:
            return _err(f"http_{response.status_code}")
        return _ok()
    except Exception as exc:  # noqa: BLE001
        return _err(type(exc).__name__)


def check_auto_admit_pipeline(
    *,
    verifier_id: str | None,
    required_providers_ok: bool,
    verifier_reachable: bool,
) -> dict[str, Any]:
    """Fail closed: missing authoritative verifier does not silently downgrade policy."""
    verifier_present = bool(verifier_id)
    auto_admit_ready = bool(required_providers_ok and verifier_present and verifier_reachable)
    return {
        "status": "ok" if auto_admit_ready else "not_ready",
        "auto_admit_ready": auto_admit_ready,
        "required_providers_ok": required_providers_ok,
        "authoritative_verifier_present": verifier_present,
        "authoritative_verifier_id": verifier_id,
        "authoritative_verifier_reachable": verifier_reachable,
        "fail_closed": True,
    }


def collect_transaction_checks(
    settings: Settings,
    *,
    gitea_probe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = load_transaction_control_config()
    package = check_package_importable()
    durable = check_durable_state_writable(settings.agent_state_root)
    frozen = check_frozen_c_loaded()
    caps = check_capability_store(settings.agent_state_root)
    evidence = check_evidence_bus()
    broker = check_broker_configured(settings)
    gitea = gitea_probe if gitea_probe is not None else check_gitea_reachable(settings)
    required_ok = evidence.get("status") == "ok"
    verifier_id = getattr(cfg, "authoritative_verifier_id", None) or AUTHORITATIVE_VERIFIER_ID
    # CT102 down → verifier unreachable, auto_admit_ready false, core /readyz still not 503.
    auto_admit = check_auto_admit_pipeline(
        verifier_id=verifier_id,
        required_providers_ok=required_ok,
        verifier_reachable=gitea.get("status") == "ok",
    )
    return {
        "package_importable": package,
        "durable_state_writable": durable,
        "frozen_c_loaded": frozen,
        "capability_store": caps,
        "evidence_bus": evidence,
        "broker_configured": broker,
        "gitea_reachable": gitea,
        "auto_admit_pipeline_ready": auto_admit,
        "auto_admit_ready": bool(auto_admit.get("auto_admit_ready")),
    }


def worker_durable_credential_readiness() -> dict[str, Any]:
    """CT104 helper. Reuses collect_durable_credential_violations. No secret values."""
    from agent_workers.settings import collect_durable_credential_violations

    violations = collect_durable_credential_violations()
    names = [item.env_name for item in violations]
    codes = [item.code for item in violations]
    passed = not violations
    return {
        "status": "ok" if passed else "error",
        "WORKER_DURABLE_CREDENTIALS_PRESENT_ASSERTION": "PASS" if passed else "FAIL",
        "ok": passed,
        "violation_env_names": names,
        "violation_codes": codes,
    }
