"""One-shot generator: vendor C closure + copy W5 transaction schemas."""

from __future__ import annotations

import ast
import hashlib
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXP22 = REPO / "maintenance-evals" / "src" / "maintenance_evals" / "vexp_w4_exp22.py"
PIN = "ad265893a9e7161ba8acd0c95e778738d92584eb310cb6bac85e89121f72098c"
OUT = (
    REPO
    / "agent-control-plane"
    / "src"
    / "agent_control"
    / "transaction"
    / "admission"
    / "frozen_c.py"
)
SCHEMA_SRC = (
    REPO
    / "maintenance-evals"
    / "results"
    / "w5-transaction-control-plane-product-integration-v1"
)
SCHEMA_DST = REPO / "agent-control-plane" / "src" / "agent_shared" / "schemas"

WANTED = [
    "_git",
    "reconstruct_diff",
    "workspace_head",
    "list_test_files",
    "identifiers_in_text",
    "_call_name",
    "privileged_hits",
    "g0_violations",
    "selected_keys",
    "selected_paths",
    "visibility_for",
    "classify_units",
    "scope_relation_for",
    "risk_tier_for",
    "run_pytest",
    "verify_workspace",
    "mint_capability",
    "decide_strict_scope",
    "decide_c",
    "decide_d",
    "admit_proposal",
]

SCHEMA_FILES = [
    "verification_evidence_bundle.v1.schema.json",
    "patch_admission_decision.v1.schema.json",
    "durable_patch_capability.v1.schema.json",
    "admission_feedback_record.v1.schema.json",
    "task_envelope.v1.schema.json",
    "patch_proposal.v1.schema.json",
    "evidence_route.v1.schema.json",
    "admission_escalation.v1.schema.json",
    "software_transaction.v1.schema.json",
    "transaction_graph_edge.v1.schema.json",
    "software_transaction_attestation.v1.schema.json",
    "evidence_provider.v1.schema.json",
    "security_finding.v1.schema.json",
]

PREAMBLE = '''"""Vendored frozen C closure (TRANSACTIONAL_RELATIONAL_ADMISSION).

Function bodies are copied byte-stable from maintenance_evals.vexp_w4_exp22.
Do not retune decide_c / admit_proposal / classify_units. Semantic changes: NO.

Pin: SHA-256 of the eval module file vexp_w4_exp22.py
     ad265893a9e7161ba8acd0c95e778738d92584eb310cb6bac85e89121f72098c
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from agent_shared.hash_utils import canonical_json_hash

try:
    from maintenance_evals.mutation_contract import derive_element_delta
except ImportError:  # pragma: no cover - CT103 image without maintenance_evals

    def derive_element_delta(*, path: str, source_text: str, candidate_text: str) -> Any:
        raise FrozenCDependencyError(
            "classify_units requires mutation_contract.derive_element_delta"
        )

FROZEN_C_HASH = "ad265893a9e7161ba8acd0c95e778738d92584eb310cb6bac85e89121f72098c"
CONTROLLER_NAME = "TRANSACTIONAL_RELATIONAL_ADMISSION"
SEALED_FUNCTIONS = ("decide_c", "admit_proposal", "classify_units")

AUTO_ADMIT = "AUTO_ADMIT"
REJECT = "REJECT"
ESCALATE = "ESCALATE"

ARM_A = "PREWRITE_SCOPE_EQUIVALENT"
ARM_B = "STATIC_POSTHOC_SCOPE_GATE"
ARM_C = "TRANSACTIONAL_RELATIONAL_ADMISSION"
ARM_D = "BROAD_PUBLISH_BASELINE"

SCOPE_WITHIN = "WITHIN_PREDICTED_SCOPE"
SCOPE_EVIDENCE = "OUTSIDE_SCOPE_BUT_EVIDENCE_RELATED"
SCOPE_LOCAL = "OUTSIDE_SCOPE_LOCAL_CREATION"
SCOPE_HIGH = "OUTSIDE_SCOPE_HIGH_RISK"
SCOPE_UNEXPLAINED = "UNEXPLAINED"
SCOPE_UNAVAILABLE = "SELECTED_SCOPE_UNAVAILABLE"

EV_ALREADY = "ALREADY_AVAILABLE_PRODUCTION"
EV_DERIVED = "DETERMINISTICALLY_DERIVABLE_PRODUCTION"
EV_NEW = "REQUIRES_NEW_NONLEARNED_ANALYSIS"
EV_BENCH = "BENCHMARK_ONLY"

PRIVILEGED_MODULES = frozenset(
    {
        "subprocess",
        "socket",
        "ssl",
        "ftplib",
        "http.client",
        "urllib",
        "urllib.request",
        "urllib.parse",
        "requests",
        "httpx",
        "paramiko",
        "asyncio.subprocess",
    }
)
PRIVILEGED_NAMES = frozenset(
    {
        "system",
        "popen",
        "Popen",
        "urlopen",
        "urlretrieve",
        "eval",
        "exec",
        "compile",
        "__import__",
    }
)

G0_PREFIXES = (
    "tests/",
    "GOLD/",
    ".git/",
    ".github/",
    ".gitea/",
    "fixtures/longitudinal/invariants/",
    "secrets/",
)
G0_NAMES = frozenset(
    {
        ".env",
        ".env.local",
        "credentials.json",
        "id_rsa",
        "Jenkinsfile",
        "approval_policy.json",
    }
)
G0_SUBSTRINGS = (
    "publish/broker",
    "approval/policy",
    "ci/trust",
)


class FrozenCDependencyError(RuntimeError):
    """Vendored C called a helper that is unavailable on this image."""

'''


def main() -> None:
    text = EXP22.read_text(encoding="utf-8")
    digest = hashlib.sha256(EXP22.read_bytes()).hexdigest()
    if digest != PIN:
        raise SystemExit(f"C pin mismatch: {digest}")
    tree = ast.parse(text)
    found: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in WANTED:
            segment = ast.get_source_segment(text, node)
            if segment is None:
                raise SystemExit(f"missing source for {node.name}")
            found[node.name] = segment
        if isinstance(node, ast.ClassDef) and node.name == "VexpW4Exp22Error":
            segment = ast.get_source_segment(text, node)
            if segment is None:
                raise SystemExit("missing VexpW4Exp22Error")
            found["VexpW4Exp22Error"] = segment
    missing = [name for name in WANTED if name not in found]
    if missing or "VexpW4Exp22Error" not in found:
        raise SystemExit(f"missing symbols: {missing}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    parts = [PREAMBLE, found["VexpW4Exp22Error"], ""]
    for name in WANTED:
        parts.append(found[name])
        parts.append("")
    OUT.write_text("\n".join(parts), encoding="utf-8")
    SCHEMA_DST.mkdir(parents=True, exist_ok=True)
    for name in SCHEMA_FILES:
        src = SCHEMA_SRC / name
        if not src.is_file():
            raise SystemExit(f"missing schema {name}")
        dest_name = name.replace(".schema.json", ".json") if name.endswith(".schema.json") else name
        shutil.copy2(src, SCHEMA_DST / dest_name)
        print("copied", dest_name)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
