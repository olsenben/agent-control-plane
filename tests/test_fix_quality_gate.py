"""Fix output quality gate tests (Slice 6D.1)."""

from agent_shared.models.fix import FixFileChange, FixResult
from agent_workers.rlm.output_quality import evaluate_fix_output_quality


def test_empty_changes_fails_quality_gate() -> None:
    fix = FixResult(changes=[])
    verdict = evaluate_fix_output_quality(fix)
    assert not verdict.passed
    assert any("no changes" in r.lower() for r in verdict.reasons)


def test_good_fix_passes_quality_gate() -> None:
    fix = FixResult(
        changes=[
            FixFileChange(path="README.md", edit_kind="append", content="homelab note\n"),
        ]
    )
    verdict = evaluate_fix_output_quality(fix)
    assert verdict.passed


def test_replace_without_content_fails() -> None:
    fix = FixResult(
        changes=[FixFileChange(path="README.md", edit_kind="replace", content="")],
    )
    verdict = evaluate_fix_output_quality(fix)
    assert not verdict.passed
    assert any("missing content" in r.lower() for r in verdict.reasons)
