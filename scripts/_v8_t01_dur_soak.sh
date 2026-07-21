#!/usr/bin/env bash
# V8 T01 — Homelab DUR soak / restart
# Bounce CT103 control-plane; prove ledger sequence / projections / budget /readyz survive.
# Optional light CT104 worker restart (worker-report).
#
# Usage:
#   scripts/_v8_t01_dur_soak.sh
#   WITH_CT104=0 scripts/_v8_t01_dur_soak.sh   # skip CT104 bounce
set -euo pipefail

KEY="${HOME}/.ssh/.ct103_deploy"
WITH_CT104="${WITH_CT104:-1}"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=20 -i "$KEY")

echo "=== V8 T01 DUR soak start $(date -u +%Y-%m-%dT%H:%M:%SZ) WITH_CT104=$WITH_CT104 ==="

ssh "${SSH_OPTS[@]}" deploy@192.168.4.62 bash -s <<'EOS'
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
TIP=$(git rev-parse HEAD)
TIP_SHORT=$(git rev-parse --short=7 HEAD)
echo "CT103_TIP=$TIP"
echo "CT103_TIP_SHORT=$TIP_SHORT"

for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -sf http://127.0.0.1:8080/readyz >/tmp/v8t01_readyz_before.json; then
    break
  fi
  sleep 2
done
python3 - <<'PY'
import json
d = json.load(open("/tmp/v8t01_readyz_before.json"))
checks = d.get("checks") or {}
redis, state = checks.get("redis"), checks.get("state_dir")
print(f"READYZ_BEFORE status={d.get('status')} redis={redis} state_dir={state}")
assert redis == "ok", f"redis not ok: {redis}"
assert state == "ok", f"state_dir not ok: {state}"
PY

cat > /tmp/v8_t01_dur_seed.py <<'PY'
"""Seed DUR soak markers and emit BEFORE fingerprint."""
from __future__ import annotations

import json
from pathlib import Path

from agent_control.events import AgentEvent, append_event, load_project_events
from agent_control.model_attempt_budget_store import reserve_attempt, save_durable_budget
from agent_control.observe.projection import build_observation_projection
from agent_shared.models.model_attempt_budget import AttemptBudgetTracker, ModelAttemptBudget

import uuid
from datetime import datetime, timezone

STATE = Path("/data/agent-state")
PROJECT = "ai-sdlc-lab/demo-app"
SOAK_TAG = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
RUN_ID = f"run-v8-t01-dur-{SOAK_TAG}"
BUDGET_KEY = f"run-v8-t01-dur-{SOAK_TAG}"
SEED_IDS = [f"v8t01-dur-{SOAK_TAG}-{suffix}" for suffix in ("a", "b")]
POST_ID = f"v8t01-dur-{SOAK_TAG}-c-post"
OUT = Path("/tmp/v8t01_before.json")

for eid, suffix in zip(SEED_IDS, ("a", "b")):
    append_event(
        STATE,
        AgentEvent(
            event_id=eid,
            type="agent.control_decision",
            project=PROJECT,
            payload={
                "run_id": RUN_ID,
                "kind": "other",
                "summary": f"v8-t01-dur-soak-{suffix}",
                "soak": "v8-t01",
                "soak_tag": SOAK_TAG,
            },
        ),
    )

limits = ModelAttemptBudget(
    max_total_completion_attempts=10,
    max_infrastructure_attempts=10,
)
save_durable_budget(
    STATE,
    project=PROJECT,
    budget_key=BUDGET_KEY,
    tracker=AttemptBudgetTracker(limits=limits),
)
ok, tracker = reserve_attempt(
    STATE,
    project=PROJECT,
    budget_key=BUDGET_KEY,
    kind="infrastructure",
    idempotency_key=f"v8t01-seed-{SOAK_TAG}",
)
assert ok, "budget reserve failed"

events = load_project_events(STATE, PROJECT)
soak = [e for e in events if e.get("event_id") in SEED_IDS]
assert len(soak) == 2, f"expected 2 sequenced soak events, got {soak}"
id_to_seq = {e["event_id"]: int(e["ledger_sequence"]) for e in soak}
assert all(v > 0 for v in id_to_seq.values()), f"missing ledger_sequence: {id_to_seq}"

doc = build_observation_projection(STATE, project=PROJECT, run_id=RUN_ID)
owner, repo = PROJECT.split("/", 1)
base = STATE / "projects" / owner / repo
counter_path = base / "events" / "ledger_seq.txt"
counter = int(counter_path.read_text().strip()) if counter_path.is_file() else None
event_files = sum(1 for p in (base / "events").rglob("*.json") if not p.name.endswith(".tmp"))
budget_path = base / "budgets" / f"{BUDGET_KEY}.json"
keys_path = budget_path.with_suffix(".keys.json")
idem_keys = json.loads(keys_path.read_text()) if keys_path.is_file() else []

fp = {
    "project": PROJECT,
    "run_id": RUN_ID,
    "budget_key": BUDGET_KEY,
    "soak_tag": SOAK_TAG,
    "post_event_id": POST_ID,
    "idempotency_key": f"v8t01-seed-{SOAK_TAG}",
    "soak_id_to_seq": id_to_seq,
    "max_soak_seq": max(id_to_seq.values()),
    "ledger_counter": counter,
    "event_file_count": event_files,
    "projection_event_ids": [e.get("event_id") for e in doc.events],
    "projection_seqs": [e.get("ledger_sequence") for e in doc.events],
    "projection_max_sequence": doc.max_sequence,
    "budget_total_attempts": tracker.total_completion_attempts,
    "budget_file_present": budget_path.is_file(),
    "budget_idempotency_keys": sorted(idem_keys),
}
OUT.write_text(json.dumps(fp, indent=2, sort_keys=True) + "\n")
print("BEFORE_FP", json.dumps(fp, sort_keys=True))
print("V8_T01_SEED_OK")
PY

CID=$(docker compose ps -q control-plane)
docker cp /tmp/v8_t01_dur_seed.py "$CID":/tmp/v8_t01_dur_seed.py
docker compose exec -T control-plane python /tmp/v8_t01_dur_seed.py </dev/null
docker compose exec -T control-plane cat /tmp/v8t01_before.json </dev/null > /tmp/v8t01_before.json
echo "=== BEFORE fingerprint ==="
cat /tmp/v8t01_before.json

echo "=== Restarting CT103 control-plane (+ worker-state) ==="
docker compose restart control-plane
docker compose restart worker-state || true

echo "=== Waiting for /readyz after restart ==="
ok=0
for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8080/readyz >/tmp/v8t01_readyz_after.json; then
    ok=1
    break
  fi
  sleep 2
done
if [ "$ok" != "1" ]; then
  echo "READYZ_TIMEOUT_AFTER_RESTART" >&2
  exit 1
fi
python3 - <<'PY'
import json
d = json.load(open("/tmp/v8t01_readyz_after.json"))
checks = d.get("checks") or {}
redis, state = checks.get("redis"), checks.get("state_dir")
print(f"READYZ_AFTER status={d.get('status')} redis={redis} state_dir={state}")
assert redis == "ok", f"redis not ok after restart: {redis}"
assert state == "ok", f"state_dir not ok after restart: {state}"
PY

cat > /tmp/v8_t01_dur_verify.py <<'PY'
"""Verify DUR continuity after control-plane restart; append one more event."""
from __future__ import annotations

import json
from pathlib import Path

from agent_control.events import AgentEvent, append_event, load_project_events
from agent_control.model_attempt_budget_store import load_durable_budget, reserve_attempt
from agent_control.observe.projection import build_observation_projection
from agent_shared.models.model_attempt_budget import ModelAttemptBudget

BEFORE = json.loads(Path("/tmp/v8t01_before.json").read_text())
STATE = Path("/data/agent-state")
PROJECT = BEFORE.get("project") or "ai-sdlc-lab/demo-app"
RUN_ID = BEFORE["run_id"]
BUDGET_KEY = BEFORE["budget_key"]
POST_ID = BEFORE["post_event_id"]
IDEM_KEY = BEFORE["idempotency_key"]
OUT = Path("/tmp/v8t01_after.json")

events = load_project_events(STATE, PROJECT)
seed_ids = set(BEFORE["soak_id_to_seq"])
soak = [e for e in events if e.get("event_id") in seed_ids]
id_to_seq = {e["event_id"]: int(e["ledger_sequence"]) for e in soak if e.get("ledger_sequence") is not None}
doc = build_observation_projection(STATE, project=PROJECT, run_id=RUN_ID)

owner, repo = PROJECT.split("/", 1)
base = STATE / "projects" / owner / repo
counter_path = base / "events" / "ledger_seq.txt"
counter = int(counter_path.read_text().strip()) if counter_path.is_file() else None
event_files = sum(1 for p in (base / "events").rglob("*.json") if not p.name.endswith(".tmp"))

limits = ModelAttemptBudget(max_total_completion_attempts=10, max_infrastructure_attempts=10)
tracker = load_durable_budget(STATE, project=PROJECT, budget_key=BUDGET_KEY, limits=limits)
ok_dup, tracker_dup = reserve_attempt(
    STATE,
    project=PROJECT,
    budget_key=BUDGET_KEY,
    kind="infrastructure",
    idempotency_key=IDEM_KEY,
)
assert ok_dup
assert tracker_dup.total_completion_attempts == BEFORE["budget_total_attempts"], (
    f"budget double-charge after restart: {tracker_dup.total_completion_attempts}"
)

# Continuity: prior soak events + sequences survive; no truncation
for eid, seq in BEFORE["soak_id_to_seq"].items():
    assert eid in id_to_seq, f"missing soak event {eid}"
    assert id_to_seq[eid] == seq, f"seq changed for {eid}: {id_to_seq[eid]} != {seq}"
assert event_files >= BEFORE["event_file_count"], (
    f"event file count regressed {event_files} < {BEFORE['event_file_count']}"
)
assert counter is not None and counter >= BEFORE["ledger_counter"], (
    f"ledger counter regressed {counter} < {BEFORE['ledger_counter']}"
)
assert [e.get("event_id") for e in doc.events] == BEFORE["projection_event_ids"], "projection ids changed"
assert [e.get("ledger_sequence") for e in doc.events] == BEFORE["projection_seqs"], "projection seqs changed"
assert doc.max_sequence == BEFORE["projection_max_sequence"], "projection max_sequence changed"
assert tracker.total_completion_attempts == BEFORE["budget_total_attempts"], "budget attempts changed"
assert (base / "budgets" / f"{BUDGET_KEY}.json").is_file(), "budget file missing"

# Post-restart append continues the counter (no reset)
prev_max = BEFORE["max_soak_seq"]
append_event(
    STATE,
    AgentEvent(
        event_id=POST_ID,
        type="agent.control_decision",
        project=PROJECT,
        payload={
            "run_id": RUN_ID,
            "kind": "other",
            "summary": "v8-t01-dur-soak-c-post",
            "soak": "v8-t01",
            "soak_tag": BEFORE.get("soak_tag"),
        },
    ),
)
post = next(e for e in load_project_events(STATE, PROJECT) if e.get("event_id") == POST_ID)
post_seq = int(post["ledger_sequence"])
assert post_seq == prev_max + 1, f"expected next seq {prev_max + 1}, got {post_seq}"
counter2 = int(counter_path.read_text().strip())
assert counter2 == post_seq, f"counter {counter2} != post_seq {post_seq}"
doc2 = build_observation_projection(STATE, project=PROJECT, run_id=RUN_ID)
assert POST_ID in [e.get("event_id") for e in doc2.events]

fp = {
    "project": PROJECT,
    "run_id": RUN_ID,
    "budget_key": BUDGET_KEY,
    "soak_tag": BEFORE.get("soak_tag"),
    "soak_id_to_seq": {k: id_to_seq[k] for k in BEFORE["soak_id_to_seq"]},
    "max_soak_seq_before_append": prev_max,
    "post_event_id": POST_ID,
    "post_restart_seq": post_seq,
    "ledger_counter": counter2,
    "event_file_count": event_files,
    "projection_event_ids": [e.get("event_id") for e in doc.events],
    "projection_seqs": [e.get("ledger_sequence") for e in doc.events],
    "projection_max_sequence": doc.max_sequence,
    "budget_total_attempts": tracker.total_completion_attempts,
    "budget_idempotent_after_restart": True,
}
OUT.write_text(json.dumps(fp, indent=2, sort_keys=True) + "\n")
print("AFTER_FP", json.dumps(fp, sort_keys=True))
print("V8_T01_DUR_VERIFY_OK")
PY

CID=$(docker compose ps -q control-plane)
docker cp /tmp/v8t01_before.json "$CID":/tmp/v8t01_before.json
docker cp /tmp/v8_t01_dur_verify.py "$CID":/tmp/v8_t01_dur_verify.py
docker compose exec -T control-plane python /tmp/v8_t01_dur_verify.py </dev/null
docker compose exec -T control-plane cat /tmp/v8t01_after.json </dev/null > /tmp/v8t01_after.json
echo "=== AFTER fingerprint ==="
cat /tmp/v8t01_after.json

python3 - <<'PY'
import json
from pathlib import Path
before = json.loads(Path("/tmp/v8t01_before.json").read_text())
after = json.loads(Path("/tmp/v8t01_after.json").read_text())
assert after["post_restart_seq"] == before["max_soak_seq"] + 1
host_counter = Path("/mnt/agent-state/projects/ai-sdlc-lab/demo-app/events/ledger_seq.txt")
assert int(host_counter.read_text().strip()) == after["post_restart_seq"]
budget = Path(f"/mnt/agent-state/projects/ai-sdlc-lab/demo-app/budgets/{after['budget_key']}.json")
assert budget.is_file(), f"budget file missing on NFS after restart: {budget}"
print("NFS_CROSSCHECK_OK counter", host_counter.read_text().strip(), "budget", budget.name)
PY

echo "V8_T01_CT103_DUR_PASS tip=$TIP_SHORT"
EOS

if [ "$WITH_CT104" = "1" ]; then
  echo "=== Optional CT104 worker-report restart ==="
  ssh "${SSH_OPTS[@]}" deploy@192.168.4.63 bash -s <<'EOS'
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
echo "CT104_TIP=$(git rev-parse --short=7 HEAD)"
docker compose -f docker-compose.ct104.yml restart worker-report
sleep 3
docker compose -f docker-compose.ct104.yml ps --format 'table {{.Name}}\t{{.Status}}' | head -10
if docker compose -f docker-compose.ct104.yml exec -T worker-report sh -c 'env' </dev/null 2>/dev/null \
  | grep -Eiq 'GITEA_(BOT|AGENT)_TOKEN=.+'; then
  echo "CT104_WRITE_TOKEN_PRESENT" >&2
  exit 1
fi
echo "V8_T01_CT104_WORKER_RESTART_OK"
EOS

  ssh "${SSH_OPTS[@]}" deploy@192.168.4.62 bash -s <<'EOS'
set -euo pipefail
cd /opt/ai-sdlc-lab/agent-control-plane
curl -sf http://127.0.0.1:8080/readyz >/tmp/v8t01_readyz_final.json
python3 - <<'PY'
import json
from pathlib import Path
d = json.load(open("/tmp/v8t01_readyz_final.json"))
checks = d.get("checks") or {}
assert checks.get("redis") == "ok" and checks.get("state_dir") == "ok"
after = json.loads(Path("/tmp/v8t01_after.json").read_text())
counter = int(Path("/mnt/agent-state/projects/ai-sdlc-lab/demo-app/events/ledger_seq.txt").read_text().strip())
assert counter == after["post_restart_seq"], f"counter drifted after CT104 bounce: {counter}"
print("POST_CT104_STATE_OK", "counter", counter, "readyz", d.get("status"))
PY
EOS
fi

echo "=== V8 T01 DUR soak PASS $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "V8_T01_DUR_SOAK_PASS"
