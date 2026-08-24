"""Semgrep CE evidence provider. Fact producer, not durable authority.

PROVIDER_DURABLE_AUTHORITY=NONE. SCANNER_SPECIFIC_C_LOGIC=NO — admission, frozen C,
and bus projection must not branch on this package name.
"""

from agent_control.transaction.evidence.providers.semgrep.adapter import run_live_p2
from agent_control.transaction.evidence.providers.semgrep.ruleset import (
    CASE_SPECIFIC_RULE_ADDED,
    RULESET_DIGEST,
    SEMGREP_IMAGE,
    SEMGREP_VERSION,
    ruleset_path,
)

SCANNER_SPECIFIC_C_LOGIC = "NO"
PROVIDER_DURABLE_AUTHORITY = "NONE"

__all__ = [
    "CASE_SPECIFIC_RULE_ADDED",
    "PROVIDER_DURABLE_AUTHORITY",
    "RULESET_DIGEST",
    "SCANNER_SPECIFIC_C_LOGIC",
    "SEMGREP_IMAGE",
    "SEMGREP_VERSION",
    "ruleset_path",
    "run_live_p2",
]
