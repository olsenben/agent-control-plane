from __future__ import annotations

from pathlib import Path

from agent_control.eval_arm_context import FROZEN_C1_MODEL, _c1_contamination, apply_arm_context


def test_c1_external_model_is_contamination() -> None:
    hit = _c1_contamination(
        arm="local-recursive-2070",
        telemetry={
            "controller_model_id": "gpt-4o-mini",
            "controller_provider": "openai",
            "controller_data_left_homelab": False,
        },
        invoked=True,
    )
    assert hit and "external" in hit


def test_c1_frozen_7b_gpu_is_clean() -> None:
    hit = _c1_contamination(
        arm="local-recursive-2070",
        telemetry={
            "controller_model_id": FROZEN_C1_MODEL,
            "controller_provider": "gpu",
            "controller_data_left_homelab": False,
        },
        invoked=True,
    )
    assert hit is None


def test_untriggered_c1_is_not_contamination() -> None:
    hit = _c1_contamination(
        arm="local-recursive-2070",
        telemetry={"controller_model_id": ""},
        invoked=False,
    )
    assert hit is None


def _local_deterministic_kwargs(tmp_path: Path) -> dict:
    return {
        "arm": "local-deterministic",
        "controller_backend": "none",
        "workspace": tmp_path,
        "project": "synthlab/retry-toolkit",
        "question": "Inspect src/foo.py helpers",
        "session_id": "sess-test",
        "run_id": "run-test",
        "source_sha": "a" * 40,
        "policy_source_sha": "b" * 40,
        "state_root": tmp_path / "state",
    }


def test_local_deterministic_prior_memory_empty_without_diagnostic(tmp_path: Path) -> None:
    ctx = apply_arm_context(**_local_deterministic_kwargs(tmp_path))
    assert ctx.context_pack is not None
    assert ctx.context_pack["prior_memory"] == []


def test_controller_model_invoked_false(tmp_path: Path) -> None:
    ctx = apply_arm_context(**_local_deterministic_kwargs(tmp_path))
    assert ctx.controller_telemetry["controller_model_invoked"] is False
