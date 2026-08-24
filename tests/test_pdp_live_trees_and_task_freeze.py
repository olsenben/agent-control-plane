"""PDP live glue: SOURCE/CANDIDATE trees + frozen Gitea task issue."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_control.approval.storage import save_approval
from agent_control.publish.envelope import bind_task_envelope_at_dispatch
from agent_control.publish.pdp import (
    _p2_live_trees,
    in_process_adapter_kwargs,
    run_publish_pdp,
)
from agent_control.publish.state import load_publish_record, save_publish_record, try_enqueue_cas
from agent_control.session.lifecycle import begin_typed_session
from agent_control.transaction.admission import FROZEN_C_HASH, SCANNER_SPECIFIC_C_LOGIC
from agent_control.transaction.evidence.adapters import run_p2_sast, run_p4_task_finding
from agent_control.transaction.evidence.receipts import (
    STATUS_PASS,
    STATUS_REQUIRED_EVIDENCE_UNAVAILABLE,
)
from agent_control.transaction.task_freeze import (
    REQUIRED_TASK_EVIDENCE_UNAVAILABLE,
    TASK_DIGEST,
    TASK_FREEZE_FILENAME,
    freeze_task_issue_at_creation,
    load_task_freeze,
    p4_live_kwargs,
)
from agent_control.transaction.trees import (
    CANDIDATE_TREE_DIGEST,
    SOURCE_TREE_DIGEST,
    TREE_DIGESTS_FILENAME,
    materialize_source_candidate_trees,
    tree_content_digest,
)
from agent_shared.bundles.inbox import bundle_dir, write_ready_bundle
from agent_shared.hash_utils import canonical_json_hash
from agent_shared.models.jobs import RLMJob, TriggerContext
from tests.test_transaction_broker import CORE, PROJECT, _approval, _attestations, _seed_publish, _settings

PIN = "ad265893a9e7161ba8acd0c95e778738d92584eb310cb6bac85e89121f72098c"
SOURCE_BODY = "def foo():\n"
CANDIDATE_BODY = "def foo():\n    return 1\n"
FINDING = "FIND-EVAL-1"
RULE = "python.lang.security.audit.eval-detected"


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


def _file_url(path: Path) -> str:
    return path.resolve().as_uri()


def _init_repo(path: Path, *, body: str = SOURCE_BODY, rel: str = CORE) -> str:
    path.mkdir(parents=True)
    init = subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=path,
        capture_output=True,
        text=True,
        check=False,
    )
    if init.returncode != 0:
        subprocess.run(["git", "init"], cwd=path, capture_output=True, text=True, check=True)
        _git(path, "checkout", "-b", "main")
    _git(path, "config", "user.name", "t")
    _git(path, "config", "user.email", "t@t")
    _git(path, "config", "core.autocrlf", "false")
    file_path = path / rel
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body, encoding="utf-8", newline="\n")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "source")
    return _git(path, "rev-parse", "HEAD").stdout.strip()


def _expected_digest(files: dict[str, str]) -> str:
    entries = [
        {
            "path": name,
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        }
        for name, content in sorted(files.items())
    ]
    return canonical_json_hash(entries)


def _patch_bytes(path: str = CORE) -> bytes:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1 +1,2 @@\n"
        " def foo():\n"
        "+    return 1\n"
    ).encode()


def _wrong_patch_bytes() -> bytes:
    return (
        "diff --git a/missing.py b/missing.py\n"
        "--- a/missing.py\n"
        "+++ b/missing.py\n"
        "@@ -1 +1,2 @@\n"
        " nope\n"
        "+x\n"
    ).encode()


def _yaml_block(*, repo: str, sha: str) -> str:
    return f"""```yaml
finding_id: {FINDING}
provider: semgrep-ce
rule_id: {RULE}
repository: {repo}
source_sha: {sha}
location: {CORE}:1
requested_action: REMEDIATE_FINDING
authorized_mutation_class: SECURITY_FINDING_TASK
initiator: alice
```
"""


def _issue(body: str, *, number: int = 7, repo: str = PROJECT) -> dict:
    owner, name = repo.split("/", 1)
    return {
        "number": number,
        "title": "Remediate eval",
        "body": body,
        "user": {"login": "alice"},
        "labels": [],
        "html_url": f"http://gitea.local/{owner}/{name}/issues/{number}",
        "repository": {"full_name": repo},
    }


class _IssueClient:
    def __init__(self, payload: dict | BaseException) -> None:
        self.payload = payload
        self.calls: list[tuple[str, str, int]] = []

    def get_issue(self, owner: str, repo: str, issue_number: int) -> dict:
        self.calls.append((owner, repo, issue_number))
        if isinstance(self.payload, BaseException):
            raise self.payload
        return dict(self.payload)


def _seed_security(tmp_path: Path, monkeypatch, run_id: str):
    settings = _settings(tmp_path, monkeypatch)
    state = settings.agent_state_root
    session = begin_typed_session(
        state,
        project=PROJECT,
        command_kind="fix",
        run_id=run_id,
        head_sha="abc1234000000000000000000000000000000000",
        trigger_context=TriggerContext(
            event_type="gitea.issue_comment",
            issue_number=7,
            author="ai-sdlc-lab",
            raw_body="/agent fix",
            normalized_body="/agent fix",
        ),
        invoked_by="ai-sdlc-lab",
        approved_by="ai-sdlc-lab",
    )
    job = MagicMock(spec=RLMJob)
    job.target_sha = "abc1234000000000000000000000000000000000"
    job.command_intent = MagicMock(
        kind="fix",
        natural_language_task="security finding remediation",
        work_item_id="tgt-1",
    )
    job.risk_class = "security"
    job.fix_authorization = MagicMock(allowed_files=[CORE])
    bind_task_envelope_at_dispatch(state, session=session, job=job, changed_files=[CORE])
    bundle_id = "bundle1"
    manifest = write_ready_bundle(
        state,
        run_id=run_id,
        kind="fix",
        attempt_id="1",
        bundle_id=bundle_id,
        producer_base_sha="abc1234000000000000000000000000000000000",
        patch_bytes=_patch_bytes(CORE),
        extra_artifacts=_attestations(run_id, bundle_id),
        result_payload={"schema_version": "fix_result.v1", "files_changed": [CORE], "changes": []},
    )
    try_enqueue_cas(
        state,
        run_id=run_id,
        kind="fix",
        attempt_id="1",
        bundle_id=manifest.bundle_id,
        project=PROJECT,
    )
    rec = load_publish_record(state, run_id, manifest.bundle_id)
    assert rec is not None
    save_publish_record(
        state,
        rec.model_copy(update={"approval_target_id": "tgt-1", "project": PROJECT}),
    )
    save_approval(state, _approval(run_id, [CORE]))
    return state, manifest, settings


def test_frozen_c_hash_unchanged() -> None:
    assert FROZEN_C_HASH == PIN
    assert SCANNER_SPECIFIC_C_LOGIC == "NO"
    frozen = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "agent_control"
        / "transaction"
        / "admission"
        / "frozen_c.py"
    )
    assert frozen.is_file()


def test_materialize_trees_match_expected_digests(tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    sha = _init_repo(origin)
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    patch = bundle / "patch.diff"
    patch.write_bytes(_patch_bytes())
    trees = materialize_source_candidate_trees(
        bundle_root=bundle,
        source_sha=sha,
        patch_path=patch,
        repo_url=_file_url(origin),
        patch_digest="p" * 64,
    )
    assert trees.source_ready is True
    assert trees.candidate_ready is True
    assert trees.source_root == bundle / "source"
    assert trees.candidate_root == bundle / "candidate"
    expected_source = _expected_digest({CORE: SOURCE_BODY})
    expected_candidate = _expected_digest({CORE: CANDIDATE_BODY})
    assert trees.source_tree_digest == expected_source
    assert trees.candidate_tree_digest == expected_candidate
    assert tree_content_digest(trees.source_root) == expected_source
    assert tree_content_digest(trees.candidate_root) == expected_candidate
    assert trees.source_tree_digest != trees.candidate_tree_digest
    receipt = json.loads((bundle / TREE_DIGESTS_FILENAME).read_text(encoding="utf-8"))
    assert receipt[SOURCE_TREE_DIGEST] == expected_source
    assert receipt[CANDIDATE_TREE_DIGEST] == expected_candidate
    assert receipt["readonly_intended"] is True
    assert (bundle / "source" / CORE).read_text(encoding="utf-8") == SOURCE_BODY
    assert (bundle / "candidate" / CORE).read_text(encoding="utf-8") == CANDIDATE_BODY


def test_wrong_patch_does_not_reuse_source_tree(tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    sha = _init_repo(origin)
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    good = bundle / "patch.diff"
    good.write_bytes(_patch_bytes())
    good_trees = materialize_source_candidate_trees(
        bundle_root=bundle,
        source_sha=sha,
        patch_path=good,
        repo_url=_file_url(origin),
        patch_digest="a" * 64,
    )
    other = tmp_path / "other"
    other.mkdir()
    wrong = other / "patch.diff"
    wrong.write_bytes(_wrong_patch_bytes())
    bad = materialize_source_candidate_trees(
        bundle_root=other,
        source_sha=sha,
        patch_path=wrong,
        repo_url=_file_url(origin),
        patch_digest="b" * 64,
    )
    assert bad.source_ready is True
    assert bad.candidate_ready is False
    assert not bad.candidate_root.is_dir()
    assert bad.source_tree_digest == good_trees.source_tree_digest
    assert bad.candidate_tree_digest is None
    assert bad.error == "patch_apply_failed"
    assert good_trees.candidate_root.is_dir()
    assert tree_content_digest(good_trees.candidate_root) != tree_content_digest(
        good_trees.source_root
    )


def test_task_freeze_captured_from_get_issue(tmp_path: Path) -> None:
    sha = "abc1234"
    client = _IssueClient(_issue(_yaml_block(repo=PROJECT, sha=sha)))
    store = tmp_path / TASK_FREEZE_FILENAME
    result = freeze_task_issue_at_creation(
        repository=PROJECT,
        provider_task_id="7",
        store_path=store,
        client=client,
    )
    assert result.ok is True
    assert result.freeze is not None
    assert result.digest == result.freeze.digest
    assert result.freeze.missing_structured_block is False
    assert client.calls == [("ai-sdlc-lab", "demo-app", 7)]
    payload = json.loads(store.read_text(encoding="utf-8"))
    assert payload[TASK_DIGEST] == result.digest
    assert payload["llm_parsed"] is False
    kwargs = p4_live_kwargs(result, repository=PROJECT, task_id="task:1")
    assert "gitea_client" not in kwargs
    assert kwargs["frozen_issue"] is result.freeze
    live = run_p4_task_finding(
        binding={"repo": PROJECT, "source_sha": sha, "patch_digest": "c" * 64},
        **kwargs,
    )
    extra = live["receipts"][0]["extra"]["task_evidence_receipt"]
    assert extra["task_digest"] == result.digest
    assert extra["llm_parsed"] is False
    again = freeze_task_issue_at_creation(
        repository=PROJECT,
        provider_task_id="7",
        store_path=store,
        client=_IssueClient(_issue("edited after freeze")),
    )
    assert again.digest == result.digest


def test_get_issue_failure_fail_closed(tmp_path: Path) -> None:
    client = _IssueClient(RuntimeError("get_issue failed"))
    store = tmp_path / TASK_FREEZE_FILENAME
    result = freeze_task_issue_at_creation(
        repository=PROJECT,
        provider_task_id="7",
        store_path=store,
        client=client,
    )
    assert result.ok is False
    assert result.error == REQUIRED_TASK_EVIDENCE_UNAVAILABLE
    kwargs = p4_live_kwargs(result, repository=PROJECT)
    assert kwargs["unavailable_reason"] == REQUIRED_TASK_EVIDENCE_UNAVAILABLE
    live = run_p4_task_finding(
        binding={"repo": PROJECT, "source_sha": "abc1234", "patch_digest": "c" * 64},
        **kwargs,
    )
    assert live["status"] != "OK"
    assert live["detail"] == REQUIRED_TASK_EVIDENCE_UNAVAILABLE
    statuses = {item.get("result_status") for item in live["receipts"]}
    assert STATUS_PASS not in statuses
    assert STATUS_REQUIRED_EVIDENCE_UNAVAILABLE in statuses


def test_missing_trees_fail_closed_not_pass(tmp_path: Path) -> None:
    trees = _p2_live_trees(tmp_path)
    assert trees["source_root"] == str(tmp_path / "source")
    assert trees["candidate_root"] == str(tmp_path / "candidate")
    result = run_p2_sast(
        binding={"repo": PROJECT, "source_sha": "abc1234", "patch_digest": "c" * 64},
        **trees,
    )
    assert result["status"] != "OK"
    statuses = {item.get("result_status") for item in result["receipts"]}
    assert STATUS_PASS not in statuses
    assert STATUS_REQUIRED_EVIDENCE_UNAVAILABLE in statuses or result["status"] == "TOOL_FAILURE"


def test_pdp_live_p2_kwargs_include_tree_paths(tmp_path: Path, monkeypatch) -> None:
    origin = tmp_path / "origin"
    sha = _init_repo(origin)
    state, manifest, _settings_obj = _seed_publish(
        tmp_path, monkeypatch, run_id="run-trees", files=[CORE], patch_path=CORE
    )
    root = bundle_dir(
        state, run_id="run-trees", kind="fix", attempt_id="1", bundle_id=manifest.bundle_id
    )
    captured: dict = {}

    def _capture(**kwargs):
        captured["adapter_kwargs"] = kwargs.get("adapter_kwargs")
        from agent_control.transaction.evidence.bus import run_evidence_bus as real

        return real(**kwargs)

    with patch("agent_control.publish.pdp.run_evidence_bus", side_effect=_capture):
        run_publish_pdp(
            state_root=state,
            project=PROJECT,
            run_id="run-trees",
            bundle_id=manifest.bundle_id,
            bundle_root=root,
            manifest=manifest,
            authorized_files=[CORE],
            source_sha=sha,
            agent_branch="agent/run-trees",
            invoked_by="ai-sdlc-lab",
            repo_url=_file_url(origin),
        )
    p2 = (captured.get("adapter_kwargs") or {}).get("P2") or {}
    assert p2["source_root"] == str(root / "source")
    assert p2["candidate_root"] == str(root / "candidate")
    assert (root / "source").is_dir()
    assert (root / "candidate").is_dir()
    assert tree_content_digest(root / "source") == _expected_digest({CORE: SOURCE_BODY})
    assert tree_content_digest(root / "candidate") == _expected_digest({CORE: CANDIDATE_BODY})
    receipt_files = list(state.rglob(TREE_DIGESTS_FILENAME))
    assert receipt_files
    payload = json.loads(receipt_files[0].read_text(encoding="utf-8"))
    assert payload[SOURCE_TREE_DIGEST]
    assert payload[CANDIDATE_TREE_DIGEST]
    assert payload[SOURCE_TREE_DIGEST] != payload[CANDIDATE_TREE_DIGEST]


def test_pdp_freezes_task_issue_into_p4(tmp_path: Path, monkeypatch) -> None:
    origin = tmp_path / "origin"
    sha = _init_repo(origin)
    state, manifest, _settings_obj = _seed_security(tmp_path, monkeypatch, "run-freeze")
    root = bundle_dir(
        state, run_id="run-freeze", kind="fix", attempt_id="1", bundle_id=manifest.bundle_id
    )
    client = _IssueClient(_issue(_yaml_block(repo=PROJECT, sha=sha), number=7))
    captured: dict = {}

    def _capture(**kwargs):
        captured["adapter_kwargs"] = kwargs.get("adapter_kwargs")
        from agent_control.transaction.evidence.bus import run_evidence_bus as real

        return real(**kwargs)

    with patch("agent_control.publish.pdp.run_evidence_bus", side_effect=_capture):
        run_publish_pdp(
            state_root=state,
            project=PROJECT,
            run_id="run-freeze",
            bundle_id=manifest.bundle_id,
            bundle_root=root,
            manifest=manifest,
            authorized_files=[CORE],
            source_sha=sha,
            agent_branch="agent/run-freeze",
            invoked_by="ai-sdlc-lab",
            repo_url=_file_url(origin),
            issue_client=client,
        )
    p4 = (captured.get("adapter_kwargs") or {}).get("P4") or {}
    assert "gitea_client" not in p4
    freeze = p4["frozen_issue"]
    assert freeze.digest
    assert freeze.missing_structured_block is False
    assert p4["expected_issue_id"] == 7
    assert client.calls
    store_hits = list(state.rglob(TASK_FREEZE_FILENAME))
    assert store_hits
    loaded = load_task_freeze(store_hits[0])
    assert loaded is not None
    assert loaded.digest == freeze.digest
    assert loaded.ok is True


def test_pdp_get_issue_failure_fail_closed(tmp_path: Path, monkeypatch) -> None:
    origin = tmp_path / "origin"
    sha = _init_repo(origin)
    state, manifest, _settings_obj = _seed_security(tmp_path, monkeypatch, "run-issue-fail")
    root = bundle_dir(
        state, run_id="run-issue-fail", kind="fix", attempt_id="1", bundle_id=manifest.bundle_id
    )
    client = _IssueClient(RuntimeError("down"))
    result = run_publish_pdp(
        state_root=state,
        project=PROJECT,
        run_id="run-issue-fail",
        bundle_id=manifest.bundle_id,
        bundle_root=root,
        manifest=manifest,
        authorized_files=[CORE],
        source_sha=sha,
        agent_branch="agent/run-issue-fail",
        invoked_by="ai-sdlc-lab",
        repo_url=_file_url(origin),
        issue_client=client,
    )
    assert result.decision != "AUTO_ADMIT"
    assert result.capability is None
    assert result.evidence.get("auto_admit_blocked") is True
    assert "P4" in (result.evidence.get("required_provider_failures") or [])
    store_hits = list(state.rglob(TASK_FREEZE_FILENAME))
    assert store_hits
    loaded = load_task_freeze(store_hits[0])
    assert loaded is not None
    assert loaded.error == REQUIRED_TASK_EVIDENCE_UNAVAILABLE
    p4_receipts = [
        item
        for item in result.evidence.get("receipts") or []
        if item.get("evidence_type") == "TASK_REQUIREMENT"
    ]
    assert p4_receipts
    assert all(item.get("result_status") != STATUS_PASS for item in p4_receipts)


def test_in_process_kwargs_still_omit_p2_without_trees() -> None:
    from types import SimpleNamespace

    envelope = SimpleNamespace(
        authorized_files=["src/a.py"],
        authorized_surfaces=[],
        authorized_change_classes=["PRODUCTION_SOURCE_CHANGE"],
    )
    kwargs = in_process_adapter_kwargs(envelope=envelope, units=[])
    assert "P2" not in kwargs
