"""Characterization: live OfficialRLMEngine message assembly, including memory diagnostic."""

from __future__ import annotations

import inspect
from dataclasses import replace
from pathlib import Path

from agent_shared.models.context_pack import ContextPack
from agent_workers.config.execution_strategy import get_execution_strategy
from agent_workers.rlm import official_engine as official_engine_mod
from agent_workers.rlm.official_engine import (
    assemble_official_engine_prompts,
    build_official_engine_messages,
)

MEMORY_DIAGNOSTIC_SENTINEL = "MEMORY_DIAGNOSTIC_SENTINEL_73A1"


def _fix_job(pack: ContextPack | None = None) -> dict:
    job: dict = {
        "run_id": "run-diag",
        "session_id": "sess-diag",
        "project": "synthlab/retry-toolkit",
        "flow": "developer_flow",
        "agent": "developer",
        "risk_class": "write_patch",
        "workflow_definition": "eval_dispatch",
        "flow_config_id": "eval_dispatch",
        "flow_version": "1",
        "command_intent": {"kind": "fix", "natural_language_task": "fix the bug"},
        "safety": {"command_scope": "fix"},
        "fix_authorization": {"allowed_files": ["README.md"]},
    }
    if pack is not None:
        job["context_pack"] = pack.model_dump(mode="json")
    return job


def _workspace(tmp_path: Path, readme: str = "hello\n") -> Path:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "README.md").write_text(readme, encoding="utf-8")
    return workspace


def test_live_runners_call_build_official_engine_messages() -> None:
    assert "build_official_engine_messages" in inspect.getsource(official_engine_mod._run_single_shot)
    assert "build_official_engine_messages" in inspect.getsource(official_engine_mod._run_rlms)


def test_sentinel_appears_in_official_engine_messages(tmp_path: Path) -> None:
    pack = ContextPack(
        project="synthlab/retry-toolkit",
        prior_memory=[
            {
                "memory_id": "mem-diag-73a1",
                "reusable_claim": MEMORY_DIAGNOSTIC_SENTINEL,
            }
        ],
        context_sources=["diagnostic_longitudinal_memory"],
    )
    job = _fix_job(pack)
    assembled = assemble_official_engine_prompts(job=job, workspace=_workspace(tmp_path))
    system, user = build_official_engine_messages(
        preamble=assembled["preamble"],
        task=job["command_intent"]["natural_language_task"],
        context_text=assembled["context_text"],
    )
    assert user == assembled["user"]
    assert system == assembled["system"]
    assert MEMORY_DIAGNOSTIC_SENTINEL in user
    assert "memory_id" in assembled["system"]
    assert "do not invent a citation" in assembled["system"]


def test_one_record_sentinel_survives_truncation(tmp_path: Path) -> None:
    pack = ContextPack(
        project="synthlab/retry-toolkit",
        prior_memory=[
            {
                "memory_id": "mem-tiny",
                "reusable_claim": MEMORY_DIAGNOSTIC_SENTINEL,
            }
        ],
        context_sources=["diagnostic_longitudinal_memory"],
    )
    strategy = replace(get_execution_strategy(), read_only_max_prompt_chars=40)
    assembled = assemble_official_engine_prompts(
        job=_fix_job(pack),
        workspace=_workspace(tmp_path, readme="x" * 8000),
        strategy=strategy,
    )
    assert MEMORY_DIAGNOSTIC_SENTINEL in assembled["user"]
