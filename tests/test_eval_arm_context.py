from __future__ import annotations

from agent_control.eval_arm_context import FROZEN_C1_MODEL, _c1_contamination


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
