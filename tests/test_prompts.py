"""Prompt preamble and summary budget helpers."""

from agent_shared.constants import GITEA_COMMENT_SUMMARY_PROMPT_BUDGET_CHARS
from agent_workers.rlm.budget import fit_summary_for_comment
from agent_workers.rlm.prompts import build_system_preamble


def test_preamble_includes_character_budget() -> None:
    preamble = build_system_preamble("explain", "read_only")
    assert str(GITEA_COMMENT_SUMMARY_PROMPT_BUDGET_CHARS) in preamble
    assert "Gitea issue comment" in preamble


def test_preamble_custom_budget() -> None:
    preamble = build_system_preamble("inspect", "read_only", max_summary_chars=1200)
    assert "1200 characters" in preamble


def test_fit_summary_for_comment_within_budget() -> None:
    text = "Short answer."
    assert fit_summary_for_comment(text, 100) == text


def test_fit_summary_for_comment_truncates_with_marker() -> None:
    text = "word " * 900
    fitted = fit_summary_for_comment(text, 500)
    assert len(fitted) <= 500
    assert fitted.endswith("[Summary truncated to fit Gitea comment limit.]")
