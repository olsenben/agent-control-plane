"""Fix parser and normalization tests."""

import json

import pytest

from agent_shared.models.fix import FixResult
from agent_workers.rlm.fix_parser import FixParseError, parse_fix_output
from agent_workers.rlm.model_output import validate_or_repair
from agent_workers.rlm.normalizers import normalize_fix_dict


def test_normalize_fix_dict_coerces_changes() -> None:
    raw = {
        "scope_summary": "scope",
        "changes": [{"path": "src/a.py", "content": "x"}],
        "confidence": 0.9,
    }
    normalized = normalize_fix_dict(raw)
    assert normalized["changes"][0]["edit_kind"] == "replace"
    assert normalized["confidence"] == "high"


def test_validate_or_repair_fix_json() -> None:
    payload = {
        "scope_summary": "Fix webhook",
        "files_changed": ["src/handler.py"],
        "changes": [
            {
                "path": "src/handler.py",
                "summary": "update",
                "edit_kind": "replace",
                "content": "new content",
            }
        ],
        "ci_hints": ["pytest -q"],
        "risk_tags": [],
        "confidence": "medium",
    }
    result = validate_or_repair(
        "fix",
        json.dumps(payload),
        allowed_files=["src/handler.py"],
    )
    assert isinstance(result, FixResult)
    assert result.files_changed == ["src/handler.py"]


def test_parse_fix_output_empty_raises() -> None:
    with pytest.raises(FixParseError):
        parse_fix_output("", allowed_files=["a.py"])
