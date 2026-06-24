"""Gitea failure comments must not include secret literals."""

from agent_shared.closed_world.gate import evaluate_diff_gate
from agent_shared.closed_world.policy import ClosedWorldPolicy
from agent_shared.hash_utils import hash_blast_radius
from agent_shared.models.diff_gate import DiffGateResult
from agent_shared.models.review import BlastRadiusContext
from agent_workers.formatters.fix_comment import render_fix_gate_failed
from agent_workers.security.redactor import SecretRedactor


def test_gate_failure_comment_has_codes_not_secrets() -> None:
    br = BlastRadiusContext()
    h = hash_blast_radius(br)
    diff = "+AWS_SECRET_ACCESS_KEY=supersecretvalue123\n"
    result = evaluate_diff_gate(
        policy=ClosedWorldPolicy(policy_sources=["test"]),
        unified_diff=diff,
        changed_files=["src/x.py"],
        allowed_files=["src/x.py"],
        blast_radius=br,
        binding_blast_radius_hash=h,
    )
    gate = DiffGateResult.model_validate(result.model_dump())
    comment = render_fix_gate_failed(
        run_id="run-test",
        gate_result=gate,
        allowed_files_count=1,
    )
    redactor = SecretRedactor()
    redacted, _ = redactor.redact_text(comment)
    assert "supersecretvalue123" not in comment
    assert "secret_exposure" in comment or "`secret_exposure`" in comment
    assert redacted == comment
