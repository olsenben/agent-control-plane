"""V10 Wave C — NON-SCORED live C1 smoke against the real 2070 endpoint.

Runs the C1 arm (`controller_backend=model`) inside the CT103 control-plane
container so `call_primary_model` goes through the real failover chain to the
role that maps to `MODEL_2070_*`. Prints one JSON observation. Never scored,
never claims a hypothesis, never writes to a repository.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from agent_control.config import get_settings
from agent_control.model_gateway import _candidate_endpoints, gateway_endpoint_for_role
from agent_control.model_router import resolve_role_primary
from agent_control.recursive_context.config import controller_roles, load_recursive_context_config
from agent_control.recursive_context.model_client import endpoint_is_homelab
from agent_control.recursive_context.telemetry import controller_telemetry_payload
from agent_control.recursive_context.worker import run_conditional_recursive_context
from agent_shared.models.memory_preflight import MemoryPreflight

STATE_ROOT = Path(os.environ.get("V10_WC_STATE_ROOT", "/tmp/v10-wave-c-state"))
PROJECT = "v10/wave-c-c1-smoke"
RUN_ID = os.environ.get("V10_WC_RUN_ID", "run-v10-wave-c-c1-live")
SESSION_ID = os.environ.get("V10_WC_SESSION_ID", "sess-v10-wave-c-c1-live")


def endpoint_probe(base_url: str, timeout: float = 8.0) -> dict[str, object]:
    """Independent liveness read of the configured 2070 host."""
    if not base_url:
        return {"status": "unconfigured"}
    started = time.perf_counter()
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=timeout)
        response.raise_for_status()
        models = [m.get("name") for m in (response.json().get("models") or [])]
        return {
            "status": "reachable",
            "http_status": response.status_code,
            "models": models,
            "probe_seconds": round(time.perf_counter() - started, 3),
        }
    except Exception as exc:  # noqa: BLE001 — evidence, not control flow
        return {
            "status": "unreachable",
            "error_class": type(exc).__name__,
            "error": str(exc)[:200],
            "probe_seconds": round(time.perf_counter() - started, 3),
        }


def build_preflight() -> MemoryPreflight:
    return MemoryPreflight(
        session_id=SESSION_ID,
        run_id=RUN_ID,
        repo=PROJECT,
        source_sha="0" * 40,
        policy_source_sha="0" * 40,
        created_at=datetime.now(timezone.utc).isoformat(),
        recursive_context_required=True,
        invocation_reasons=["graph_coverage_insufficient", "multiple_prior_root_causes"],
        citations=["graph:blast_radius", "memory:run-prior"],
        rejected_hypotheses_from_prior_runs=["H1: auth race", "H2: stale cache"],
        uncertainty=["which_module_owns_the_regression"],
    )


def main() -> int:
    settings = get_settings()
    role, role_label = controller_roles(load_recursive_context_config())
    primary = resolve_role_primary(role, settings)
    STATE_ROOT.mkdir(parents=True, exist_ok=True)

    observation: dict[str, object] = {
        "observation": "v10_wave_c_c1_live_smoke",
        "scored": False,
        "hypothesis_claimed": None,
        "control_plane_sha": os.environ.get("V10_WC_TIP", ""),
        "configured": {
            "MODEL_2070_BASE_URL": settings.model_2070_base_url,
            "MODEL_2070_NAME": settings.model_2070_name,
            "MODEL_2070_FALLBACK_BASE_URL": settings.model_2070_fallback_base_url,
            "MODEL_2070_FALLBACK_NAME": settings.model_2070_fallback_name,
            "MODEL_2070_FALLBACK_API_KEY_SET": bool(settings.model_2070_fallback_api_key),
            "MODEL_2070_EXTERNAL_BASE_URL": settings.model_2070_external_base_url,
            "MODEL_2070_EXTERNAL_NAME": settings.model_2070_external_name,
            "MODEL_2070_EXTERNAL_API_KEY_SET": bool(settings.model_2070_external_api_key),
            "MODEL_FALLBACK_ENABLED": settings.model_fallback_enabled,
            "REPO_EXTERNAL_MODEL_POLICY": settings.repo_external_model_policy,
            "MODEL_GATEWAY_BASE_URL": getattr(settings, "model_gateway_base_url", ""),
        },
        "resolved_role": {
            "role": role,
            "role_label": role_label,
            **primary.as_dict(),
            "gateway_endpoint": (
                None
                if gateway_endpoint_for_role(role, settings) is None
                else gateway_endpoint_for_role(role, settings).as_dict()
            ),
        },
        "candidate_routes": [
            {
                "label": label,
                "provider": endpoint.provider,
                "model": endpoint.model,
                "base_url": endpoint.base_url,
                "data_leaves_homelab": leaves,
                "guard_allows": endpoint.provider == "gpu" and endpoint_is_homelab(endpoint.base_url),
            }
            for label, endpoint, leaves in _candidate_endpoints(
                role, project=PROJECT, settings=settings
            )
        ],
        "endpoint_probe": endpoint_probe(settings.model_2070_base_url),
    }

    started = time.perf_counter()
    result = run_conditional_recursive_context(
        preflight=build_preflight(),
        question="Which prior hypothesis is still consistent with the cited evidence?",
        settings=settings,
        state_root=STATE_ROOT,
        controller_backend="model",
    )
    observation["run_wall_seconds"] = round(time.perf_counter() - started, 3)
    observation["controller_telemetry"] = controller_telemetry_payload(result)
    observation["controller_mode"] = result.controller_mode
    observation["stop_reason"] = result.stop_reason
    observation["schema_version"] = result.schema_version
    observation["allow_repo_write"] = result.allow_repo_write
    observation["allow_network"] = result.allow_network
    observation["allow_secret_paths"] = result.allow_secret_paths
    observation["evidence_refs"] = result.evidence_refs[:10]
    observation["subcall_tools"] = [s.tool for s in result.subcalls]
    observation["budget_used"] = result.budget_used.model_dump()

    route_events: list[dict[str, object]] = []
    for path in sorted(STATE_ROOT.rglob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if "model_route" in str(record.get("type", "")) or str(
                record.get("type", "")
            ) in (
                "agent.model_call_completed",
                "agent.model_all_routes_failed",
                "agent.model_fallback_selected",
            ):
                route_events.append(record)
    observation["model_route_events"] = route_events

    print(json.dumps(observation, indent=2, sort_keys=True, default=str))
    telemetry = observation["controller_telemetry"]
    assert isinstance(telemetry, dict)
    print("V10_WC_C1_MODEL_INVOKED=" + str(telemetry["controller_model_invoked"]))
    print("V10_WC_C1_PROVIDER=" + str(telemetry["controller_provider"]))
    print("V10_WC_C1_MODEL_ID=" + str(telemetry["controller_model_id"]))
    print("V10_WC_C1_DATA_LEFT_HOMELAB=" + str(telemetry["controller_data_left_homelab"]))
    print("V10_WC_C1_EXTERNAL_REFUSED=" + str(telemetry["controller_external_routes_refused"]))
    print("V10_WC_C1_SMOKE_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
