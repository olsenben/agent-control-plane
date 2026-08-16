"""V10 Wave C — NON-SCORED negative control for the C1 local-only boundary.

Forces the contamination scenario on a live host: the 2070 primary is blanked so
the only remaining 2070-tier route is the configured OpenAI fallback, and
`REPO_EXTERNAL_MODEL_POLICY=*` removes the egress denial that currently happens
to be doing the work. A correct C1 controller must refuse that route without
sending anything.

Two independent safety nets, because this runs on hosts that hold a real
provider key:

1. `MODEL_2070_FALLBACK_API_KEY` / `MODEL_2070_EXTERNAL_API_KEY` are blanked in
   this process, so an escaped request could not authenticate and could not bill.
2. `httpx.post` is replaced with a tripwire that records and raises on any
   non-homelab URL instead of sending it.

The tripwire must record zero external attempts for the control to pass.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

os.environ["MODEL_2070_BASE_URL"] = ""
os.environ["MODEL_2070_FALLBACK_BASE_URL"] = "https://api.openai.com/v1"
os.environ["MODEL_2070_FALLBACK_NAME"] = "gpt-4o-mini"
os.environ["MODEL_2070_FALLBACK_API_KEY"] = ""
os.environ["MODEL_2070_EXTERNAL_API_KEY"] = ""
os.environ["MODEL_FALLBACK_ENABLED"] = "true"
os.environ["REPO_EXTERNAL_MODEL_POLICY"] = "*"

from agent_control.config import get_settings  # noqa: E402
from agent_control.model_gateway import _candidate_endpoints  # noqa: E402
from agent_control.recursive_context.config import (  # noqa: E402
    controller_roles,
    load_recursive_context_config,
)
from agent_control.recursive_context.model_client import endpoint_is_homelab  # noqa: E402
from agent_control.recursive_context.telemetry import controller_telemetry_payload  # noqa: E402
from agent_control.recursive_context.worker import (  # noqa: E402
    run_conditional_recursive_context,
)
from agent_shared.models.memory_preflight import MemoryPreflight  # noqa: E402

STATE_ROOT = Path("/tmp/v10-wave-c-negative-state")
PROJECT = "v10/wave-c-negative-control"
EXTERNAL_ATTEMPTS: list[str] = []
_real_post = httpx.post


def _tripwire_post(url: str, *args: object, **kwargs: object) -> object:
    if not endpoint_is_homelab(str(url)):
        EXTERNAL_ATTEMPTS.append(str(url))
        raise AssertionError(f"tripwire: external request attempted to {url}")
    return _real_post(url, *args, **kwargs)


httpx.post = _tripwire_post  # type: ignore[assignment]


def main() -> int:
    settings = get_settings()
    role, _ = controller_roles(load_recursive_context_config())
    STATE_ROOT.mkdir(parents=True, exist_ok=True)

    candidates = [
        {
            "label": label,
            "provider": endpoint.provider,
            "model": endpoint.model,
            "base_url": endpoint.base_url,
            "data_leaves_homelab": leaves,
        }
        for label, endpoint, leaves in _candidate_endpoints(
            role, project=PROJECT, settings=settings
        )
    ]

    preflight = MemoryPreflight(
        session_id="sess-v10-wave-c-negative",
        run_id="run-v10-wave-c-negative",
        repo=PROJECT,
        source_sha="0" * 40,
        policy_source_sha="0" * 40,
        created_at=datetime.now(timezone.utc).isoformat(),
        recursive_context_required=True,
        invocation_reasons=["graph_coverage_insufficient"],
        citations=["graph:blast_radius"],
    )
    result = run_conditional_recursive_context(
        preflight=preflight,
        question="Negative control: is the external fallback reachable from C1?",
        settings=settings,
        state_root=STATE_ROOT,
        controller_backend="model",
    )
    telemetry = controller_telemetry_payload(result)

    passed = (
        bool(candidates)
        and all(c["base_url"].startswith("https://api.openai.com") for c in candidates)
        and telemetry["controller_model_invoked"] is False
        and telemetry["controller_external_routes_refused"] >= 1
        and telemetry["controller_error_class"] == "external_route_refused"
        and telemetry["controller_data_left_homelab"] is False
        and not EXTERNAL_ATTEMPTS
    )

    print(
        json.dumps(
            {
                "observation": "v10_wave_c_c1_negative_control",
                "scored": False,
                "host": os.environ.get("V10_WC_HOST", ""),
                "control_plane_sha": os.environ.get("V10_WC_TIP", ""),
                "forced_candidate_routes": candidates,
                "controller_telemetry": telemetry,
                "external_http_attempts": EXTERNAL_ATTEMPTS,
                "negative_control_passed": passed,
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
    )
    print("V10_WC_NEGATIVE_CONTROL_PASSED=" + str(passed))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
