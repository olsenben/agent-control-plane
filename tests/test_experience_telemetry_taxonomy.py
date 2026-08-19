"""W0-D experience telemetry vocabulary and safe envelope."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_control.telemetry.taxonomy import (
    EXPERIENCE_EVENT_NAMES,
    PROHIBITED_FIELD_KEYWORDS,
    ProhibitedTelemetryFieldError,
    build_experience_event_envelope,
    emit_experience_event,
)
from agent_shared.models import experience_events as events_mod
from agent_shared.models.experience_events import (
    EXPERIENCE_EVENT_NAMES as MODEL_EVENT_NAMES,
    ExperienceEventEnvelope,
    TreatmentExposure,
)

# Copied from agent_control.observe.safe_display._PROHIBITED_NAME_KEYWORDS.
# That module is read-only this wave; do not import or edit it here.
_SAFE_DISPLAY_DENY_KEYWORDS = (
    "token",
    "secret",
    "password",
    "passwd",
    "credential",
    "authorization",
    "auth_header",
    "cookie",
    "api_key",
    "apikey",
    "private_key",
    "ssh_key",
    "ssh_",
    "access_key",
    "bearer",
    "header",
    "env",
    "prompt",
    "stdout",
    "stderr",
    "raw_output",
    "raw_log",
    "raw_payload",
    "payload_json",
    "args",
    "system_message",
)

EXPECTED_EVENT_NAMES = (
    "context.candidate_evidence",
    "context.evidence_selected",
    "memory.candidate_retrieved",
    "memory.applicability_checked",
    "memory.exposure_authorized",
    "memory.exposure_abstained",
    "memory.behavioral_use_observed",
    "patch.generated",
    "verification.fast.completed",
    "repair.requested",
    "repair.completed",
    "verification.authoritative.completed",
    "experience.admission_decided",
    "memory.utility_labeled",
    "memory.validity_changed",
    "recursion.requested",
    "recursion.completed",
)


def test_all_seventeen_event_names_registered() -> None:
    assert len(EXPECTED_EVENT_NAMES) == 17
    assert EXPERIENCE_EVENT_NAMES == EXPECTED_EVENT_NAMES
    assert MODEL_EVENT_NAMES == EXPECTED_EVENT_NAMES
    assert len(set(EXPERIENCE_EVENT_NAMES)) == 17


def test_prohibited_keywords_match_safe_display_copy() -> None:
    assert PROHIBITED_FIELD_KEYWORDS == _SAFE_DISPLAY_DENY_KEYWORDS


@pytest.mark.parametrize("field_name", ["prompt", "token", "secret", "user_prompt", "api_token"])
def test_envelope_builder_rejects_prompt_token_secret_field_names(field_name: str) -> None:
    with pytest.raises(ProhibitedTelemetryFieldError, match=field_name):
        build_experience_event_envelope("patch.generated", payload={field_name: "x"})


def test_envelope_builder_rejects_nested_prohibited_field_names() -> None:
    with pytest.raises(ProhibitedTelemetryFieldError, match="secret"):
        build_experience_event_envelope(
            "repair.requested",
            payload={"meta": {"nested_secret": "nope"}},
        )


def test_treatment_exposure_can_be_constructed() -> None:
    exposure = TreatmentExposure(
        repo_snapshot_id="snap-1",
        context_pack_version="context-pack.v2",
        evidence_provider_ids=["lexical"],
        candidate_memory_ids=["mem-a"],
        applicability_verdicts=["abstain"],
        exposed_memory_ids=[],
        recursive_invocations=0,
        repair_attempt_index=0,
        official_verification_result=True,
        additional_verification_result=False,
    )
    envelope = build_experience_event_envelope(
        "verification.authoritative.completed",
        payload={"ok": True},
        treatment=exposure,
        correlation_id="corr-1",
        session_id="sess-1",
        run_id="run-1",
    )
    assert envelope.treatment is not None
    assert envelope.treatment.repo_snapshot_id == "snap-1"
    assert envelope.treatment.official_verification_result is True
    assert envelope.payload == {"ok": True}


def test_emit_helper_does_not_append_to_nfs_ledger(tmp_path: Path) -> None:
    envelope = emit_experience_event(
        "context.evidence_selected",
        payload={"count": 2},
        event_id="evt-1",
    )
    assert isinstance(envelope, ExperienceEventEnvelope)
    assert envelope.event_name == "context.evidence_selected"
    assert list(tmp_path.iterdir()) == []

    taxonomy_path = Path(inspect.getfile(emit_experience_event))
    tree = ast.parse(taxonomy_path.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    forbidden_prefixes = (
        "agent_control.events",
        "agent_control.session",
        "agent_control.observe",
        "agent_control.ci.events",
    )
    for module_name in imported:
        assert not any(
            module_name == prefix or module_name.startswith(prefix + ".")
            for prefix in forbidden_prefixes
        )
    assert "/mnt/agent-state" not in taxonomy_path.read_text(encoding="utf-8")
    assert "/mnt/agent-runs" not in taxonomy_path.read_text(encoding="utf-8")


def test_no_per_event_w3_w7_payload_models() -> None:
    defined = [
        name
        for name, obj in inspect.getmembers(events_mod, inspect.isclass)
        if obj.__module__ == events_mod.__name__
    ]
    assert set(defined) == {"TreatmentExposure", "ExperienceEventEnvelope"}
    with pytest.raises(ValidationError):
        ExperienceEventEnvelope(event_name="experience.admission_decided.v1")
