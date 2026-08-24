"""Frozen C pin: SHA-256 of maintenance_evals.vexp_w4_exp22.py bytes."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import Any

from agent_control.transaction.admission.frozen_c import (
    FROZEN_C_HASH,
    SEALED_FUNCTIONS,
)

CONTROLLER_NAME = "TRANSACTIONAL_RELATIONAL_ADMISSION"


def exp22_source_path() -> Path:
    """Resolve the eval C module relative to this repo checkout."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[6] / "maintenance-evals" / "src" / "maintenance_evals" / "vexp_w4_exp22.py",
        here.parents[5] / "maintenance-evals" / "src" / "maintenance_evals" / "vexp_w4_exp22.py",
        Path(__file__).resolve().parents[5]
        / "maintenance-evals"
        / "src"
        / "maintenance_evals"
        / "vexp_w4_exp22.py",
    ]
    # agent-control-plane/src/agent_control/transaction/admission/pin.py
    # parents[4] = agent-control-plane, parents[5] = ai-sdlc-lab
    lab = here.parents[5]
    candidates.insert(0, lab / "maintenance-evals" / "src" / "maintenance_evals" / "vexp_w4_exp22.py")
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("vexp_w4_exp22.py not found for C pin verification")


def hash_exp22_source(path: Path | None = None) -> str:
    target = path or exp22_source_path()
    return hashlib.sha256(target.read_bytes()).hexdigest()


def _function_node(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise KeyError(name)


def sealed_function_ast_dump(source: str, name: str) -> str:
    tree = ast.parse(source)
    return ast.dump(_function_node(tree, name), include_attributes=False)


def compare_sealed_functions(
    eval_source: str,
    frozen_source: str,
    names: tuple[str, ...] = SEALED_FUNCTIONS,
) -> dict[str, Any]:
    mismatches: list[str] = []
    for name in names:
        if sealed_function_ast_dump(eval_source, name) != sealed_function_ast_dump(
            frozen_source, name
        ):
            mismatches.append(name)
    return {"ok": not mismatches, "mismatches": mismatches, "names": list(names)}


def verify_frozen_c_pin(eval_path: Path | None = None) -> dict[str, Any]:
    """Verify eval-file SHA-256 pin and sealed-function AST against frozen_c.py."""
    path = eval_path or exp22_source_path()
    digest = hash_exp22_source(path)
    frozen_path = Path(__file__).resolve().with_name("frozen_c.py")
    comparison = compare_sealed_functions(
        path.read_text(encoding="utf-8"),
        frozen_path.read_text(encoding="utf-8"),
    )
    return {
        "expected": FROZEN_C_HASH,
        "actual": digest,
        "hash_ok": digest == FROZEN_C_HASH,
        "ast_ok": comparison["ok"],
        "mismatches": comparison["mismatches"],
        "method": (
            "sha256(vexp_w4_exp22.py bytes) == FROZEN_C_HASH; "
            "ast.dump of decide_c/admit_proposal/classify_units matches frozen_c.py"
        ),
    }
