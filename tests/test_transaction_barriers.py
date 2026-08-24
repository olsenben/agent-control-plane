"""Cancel / timeout / escalate / reject durable barriers."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_control.transaction.barriers import (
    KIND_CANCELLED,
    KIND_REJECTED,
    KIND_TIMED_OUT,
    PHASE_ADMISSION,
    PHASE_EVIDENCE,
    PHASE_MINT,
    PHASE_PUBLISH,
    PHASE_WORKER,
    REFUSED_CANCELLED_RUN,
    REFUSED_ESCALATED,
    REFUSED_LATE_EVIDENCE,
    REFUSED_REJECTED,
    REFUSED_REJECTED_REPLAY,
    REFUSED_TIMED_OUT_RUN,
    RUN_CANCELLED,
    DurableBarrierError,
    check_durable_effect_allowed,
    mark_run_cancelled,
    mark_run_timed_out,
    persist_escalate_barrier,
    persist_reject_barrier,
)


def test_cancel_before_publish_refuses_durable_effect(tmp_path: Path) -> None:
    record = mark_run_cancelled(tmp_path, run_id="run-1", transaction_id="tx-1")
    assert record["event"]["event_type"] == RUN_CANCELLED
    assert KIND_CANCELLED in record["kinds"]
    with pytest.raises(DurableBarrierError) as exc:
        check_durable_effect_allowed(tmp_path, run_id="run-1", phase=PHASE_PUBLISH)
    assert exc.value.code == REFUSED_CANCELLED_RUN
    for phase in (PHASE_WORKER, PHASE_EVIDENCE, PHASE_ADMISSION, PHASE_MINT):
        with pytest.raises(DurableBarrierError) as phase_exc:
            check_durable_effect_allowed(tmp_path, run_id="run-1", phase=phase)
        assert phase_exc.value.code == REFUSED_CANCELLED_RUN


def test_timeout_is_distinct_from_cancel_and_does_not_resurrect(tmp_path: Path) -> None:
    mark_run_timed_out(tmp_path, run_id="run-2", transaction_id="tx-2")
    with pytest.raises(DurableBarrierError) as exc:
        check_durable_effect_allowed(tmp_path, run_id="run-2", phase=PHASE_PUBLISH)
    assert exc.value.code == REFUSED_TIMED_OUT_RUN
    assert exc.value.code != REFUSED_CANCELLED_RUN
    mark_run_cancelled(tmp_path, run_id="run-2", transaction_id="tx-2")
    kinds_path = tmp_path / "transaction" / "barriers" / "run-2.json"
    body = kinds_path.read_text(encoding="utf-8")
    assert KIND_TIMED_OUT in body
    assert KIND_CANCELLED in body
    with pytest.raises(DurableBarrierError) as again:
        check_durable_effect_allowed(tmp_path, run_id="run-2", phase=PHASE_ADMISSION)
    assert again.value.code == REFUSED_CANCELLED_RUN


def test_escalate_blocks_mint_and_publish_not_capability(tmp_path: Path) -> None:
    persist_escalate_barrier(tmp_path, run_id="run-3", transaction_id="tx-3")
    check_durable_effect_allowed(tmp_path, run_id="run-3", phase=PHASE_EVIDENCE)
    with pytest.raises(DurableBarrierError) as mint_exc:
        check_durable_effect_allowed(tmp_path, run_id="run-3", phase=PHASE_MINT)
    assert mint_exc.value.code == REFUSED_ESCALATED
    with pytest.raises(DurableBarrierError) as pub_exc:
        check_durable_effect_allowed(tmp_path, run_id="run-3", phase=PHASE_PUBLISH)
    assert pub_exc.value.code == REFUSED_ESCALATED


def test_reject_blocks_publish_replayed_mint_and_late_evidence(tmp_path: Path) -> None:
    persist_reject_barrier(tmp_path, run_id="run-4", transaction_id="tx-4")
    with pytest.raises(DurableBarrierError) as ev_exc:
        check_durable_effect_allowed(tmp_path, run_id="run-4", phase=PHASE_EVIDENCE)
    assert ev_exc.value.code == REFUSED_LATE_EVIDENCE
    with pytest.raises(DurableBarrierError) as mint_exc:
        check_durable_effect_allowed(tmp_path, run_id="run-4", phase=PHASE_MINT)
    assert mint_exc.value.code == REFUSED_REJECTED_REPLAY
    with pytest.raises(DurableBarrierError) as pub_exc:
        check_durable_effect_allowed(tmp_path, run_id="run-4", phase=PHASE_PUBLISH)
    assert pub_exc.value.code == REFUSED_REJECTED
    loaded = (tmp_path / "transaction" / "barriers" / "run-4.json").read_text(encoding="utf-8")
    assert KIND_REJECTED in loaded
