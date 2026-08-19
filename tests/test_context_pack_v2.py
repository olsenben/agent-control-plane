"""ContextPackV2 schema and V1 compatibility bridge (VExp W0-B)."""

from __future__ import annotations

from agent_control.context.v1_adapter import render_v1_compatible, render_v2, v1_to_v2
from agent_control.graph.context_pack import compile_context_pack, render_context_pack_text
from agent_shared.hash_utils import sha256_text
from agent_shared.models.context_pack import ContextPack
from agent_shared.models.context_pack_v2 import SCHEMA_VERSION, ContextPackV2, ExperienceSection
from agent_shared.models.jobs import TriggerContext
from agent_shared.models.review import BlastRadiusContext

LEGACY_PRIOR_MEMORY_PAYLOAD = "LEGACY_PRIOR_MEMORY_PAYLOAD_W0B"
REJECTED_RECORD_PAYLOAD = "REJECTED_RECORD_PAYLOAD_W0B"


def _eval_like_v1_pack() -> ContextPack:
    return ContextPack(
        project="synthlab/retry-toolkit",
        source_sha="a" * 40,
        policy_source_sha="b" * 40,
        issue_text="Inspect src/foo.py helpers",
        search_hits=["src/foo.py", "src/bar.py"],
        blast_radius=BlastRadiusContext(missing_graph_edges=["src/missing.py"]),
        prior_memory=[{"kind": "finding", "text": LEGACY_PRIOR_MEMORY_PAYLOAD}],
        context_sources=["workspace_fts", "path_extract"],
        budget={"search_hits": 2, "missing_graph_edges": 1, "prior_memory": 64},
    )


def test_round_trip_serialization() -> None:
    pack = _eval_like_v1_pack()
    v2 = v1_to_v2(pack, None)
    dumped = v2.model_dump(mode="json")
    restored = ContextPackV2.model_validate(dumped)
    assert restored.model_dump(mode="json") == dumped
    assert restored.schema_version == SCHEMA_VERSION
    assert render_v1_compatible(restored) == render_v1_compatible(v2)


def test_authorized_records_empty_after_v1_to_v2() -> None:
    pack = _eval_like_v1_pack()
    assert pack.prior_memory
    v2 = v1_to_v2(pack, None)
    assert v2.experience.authorized_records == []
    assert v2.experience.rejected_records == []
    assert v2.experience.candidates_considered == []
    assert v2.experience.compatibility.legacy_prior_memory == pack.prior_memory
    assert v2.current_evidence.lexical
    assert [item.text for item in v2.current_evidence.lexical] == pack.search_hits
    assert all(item.source and item.provenance for item in v2.current_evidence.lexical)
    assert v2.current_evidence.symbols == []
    assert v2.current_evidence.dependency_edges == []
    assert v2.current_evidence.tests == []
    assert v2.current_evidence.config == []
    assert v2.current_evidence.architecture == []


def test_render_v2_omits_legacy_prior_memory() -> None:
    v2 = v1_to_v2(_eval_like_v1_pack(), None)
    visible = render_v2(v2)
    assert LEGACY_PRIOR_MEMORY_PAYLOAD not in visible
    assert "legacy_prior_memory" not in visible
    assert "prior_memory" not in visible
    assert REJECTED_RECORD_PAYLOAD not in visible
    compat = render_v1_compatible(v2)
    assert LEGACY_PRIOR_MEMORY_PAYLOAD in compat
    assert "--- prior_memory ---" in compat


def test_rejected_records_absent_from_both_renderers() -> None:
    v2 = v1_to_v2(_eval_like_v1_pack(), None)
    v2 = v2.model_copy(
        update={
            "experience": v2.experience.model_copy(
                update={"rejected_records": [{"id": REJECTED_RECORD_PAYLOAD}]}
            )
        }
    )
    assert REJECTED_RECORD_PAYLOAD not in render_v2(v2)
    assert REJECTED_RECORD_PAYLOAD not in render_v1_compatible(v2)


def test_render_v1_compatible_matches_eval_like_pack() -> None:
    pack = _eval_like_v1_pack()
    v2 = v1_to_v2(pack, None)
    expected = render_context_pack_text(pack)
    actual = render_v1_compatible(v2)
    assert actual == expected
    assert sha256_text(actual) == sha256_text(expected)


def test_render_v1_compatible_matches_compile_context_pack(graph_settings) -> None:
    trigger = TriggerContext(event_type="test", issue_number=29)
    pack = compile_context_pack(
        "ai-sdlc-lab/agent-control-plane",
        trigger,
        settings=graph_settings,
        changed_files=["src/agent_control/workflows/dispatch.py"],
        issue_override={"title": "Review dispatch", "body": "Please review dispatch.py"},
    )
    v2 = v1_to_v2(pack, None)
    assert v2.experience.authorized_records == []
    assert render_v1_compatible(v2) == render_context_pack_text(pack)


def test_treatment_hash_stable_when_content_unchanged() -> None:
    pack = _eval_like_v1_pack()
    v2 = v1_to_v2(pack, None)
    first = sha256_text(render_v1_compatible(v2))
    second = sha256_text(render_v1_compatible(v1_to_v2(pack, None)))
    assert first == second
    assert first == sha256_text(render_context_pack_text(pack))


def test_compat_renderer_applies_total_budget_clamp() -> None:
    pack = ContextPack(
        project="synthlab/retry-toolkit",
        issue_text="x" * 4000,
        diff_text="y" * 12000,
        search_hits=["src/should_drop.py"],
        blast_radius=BlastRadiusContext(
            missing_graph_edges=[f"edge-{i:04d}-" + ("z" * 40) for i in range(200)]
        ),
        prior_memory=[{"text": LEGACY_PRIOR_MEMORY_PAYLOAD}],
    )
    v2 = v1_to_v2(pack, None)
    compat = render_v1_compatible(v2)
    assert "src/should_drop.py" not in compat
    assert "--- search_hits ---" not in compat
    assert LEGACY_PRIOR_MEMORY_PAYLOAD in compat


def test_render_v2_may_show_authorized_records() -> None:
    v2 = v1_to_v2(_eval_like_v1_pack(), None)
    authorized = [{"id": "authorized-record-w0b"}]
    v2 = v2.model_copy(
        update={
            "experience": ExperienceSection(
                authorized_records=authorized,
                compatibility=v2.experience.compatibility,
            )
        }
    )
    visible = render_v2(v2)
    assert "authorized-record-w0b" in visible
    assert LEGACY_PRIOR_MEMORY_PAYLOAD not in visible
