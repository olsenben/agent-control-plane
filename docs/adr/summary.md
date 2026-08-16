# ADR summary

Index of architecture decisions. Full records live in this directory.

| ID | Title | Status | Date | Decision (one line) |
|----|-------|--------|------|---------------------|
| ADR-0001 | CT102 CI aggregate truth before fix memory | proposed | 2026-07-14 | Webhook signals + Actions API confirm; memory only when aggregate verdict=`verified` |
| ADR-0002 | Anthropic SRT as initial OS sandbox backend | proposed | 2026-07-14 | SRT via SandboxBackend; attestation + fallback deny; CT104 spike gates fix/repair |
| ADR-0003 | Cap-bounded bwrap for SRT inside CT104 Docker | proposed | 2026-07-18 | SYS_ADMIN+NET_ADMIN + seccomp/apparmor unconfined on SRT workers; shared runtime mounts; fail closed on bwrap launch |
| ADR-0004 | CT103-only Gitea write (publish brokerage) | accepted | 2026-07-18 | CT104 patch bundles only; CT103 publish-broker sole mutation authority |
| ADR-0005 | Protected-default-branch policy_source_sha pin | proposed | 2026-07-19 | CT103 resolves immutable policy identity; workers fail-closed detached checkout |
| ADR-0006 | tool_policy.v2 narrowing-only command allowance | proposed | 2026-07-19 | Empty allowance on missing/invalid tools.yaml; effective-policy hash gates repair |
| ADR-0007 | Dual sandbox and execution attestations | proposed | 2026-07-19 | Durable preflight + post-teardown attestations; publish deny if quarantined/missing |
| ADR-0008 | CT102 scheduling and credential-domain split | proposed | 2026-07-19 | Split `runner-ci`/`runner-deploy`; PR deploy label still schedulable; shared Docker residual |
| ADR-0009 | Central repair allowlist and bounded ACP lint class | proposed | 2026-07-19 | Empty allowlist denies; lint_failure default; publish flag staged |
| ADR-0010 | CT103-authoritative typed agent sessions | proposed | 2026-07-19 | Durable sess-≠run-; CT103 correlation; ingest vs publish terminal owners |
| ADR-0011 | Deterministic CT103 context preflight before RLM enqueue | proposed | 2026-07-20 | Mandatory frozen-SHA preflight+packet; degrade optional evidence; no 2070 in 5.5a |
| ADR-0012 | Session verification evidence gate | proposed | 2026-07-20 | Defer fix/repair finish until 6E CI; machine verification_* events |
| ADR-0013 | Selective memory writeback from session trace | proposed | 2026-07-20 | Typed review/plan admit after session_finished; evidence refs; 6E.2 stays fix-only |
| ADR-0014 | Adequacy profiles scope verification claims | proposed | 2026-07-20 | fixed_verified only when profile passes; agent tests scoped_only by default |
| ADR-0015 | Orbit dual-graph edges carry provenance | proposed | 2026-07-20 | Provenanced code+SDLC edges; coverage CLI; blast-radius stays fail-soft |
| ADR-0016 | Conditional recursive context worker on 2070 | proposed | 2026-07-20 | Invoke only when preflight requires; read-only tools; skip path no 2070 |
| ADR-0017 | Split acting_identity from human invoked_by | accepted | 2026-07-20 | Bot acting_identity vs human invoked_by/approved_by; separate auth predicates; started+terminal ack by run_id |
| ADR-0018 | Bounded recursive Qwen loop with CI-grounded evidence selection | proposed | 2026-07-20 | Finite CI-fail retries with evidence-selected context; no unbounded loop; no 6F.2 enable |
| ADR-0019 | Flag-gated patch tournaments and reward logging default off | proposed | 2026-07-20 | experiments.yaml flags off; judge CI-passers only; rewards JSONL |
| ADR-0020 | AgentFacts-lite content-hash integrity with optional HMAC | proposed | 2026-07-20 | agent-facts.json digest + source hashes; optional HMAC; sync MD↔JSON |
| ADR-0021 | Memory-as-governance blocks repeated failed fix classes | proposed | 2026-07-20 | Deny fix on ≥N same failure_class without new evidence; audit event |
| ADR-0022 | Architecture drift detector compares ADR facts to graph edges fail-soft | proposed | 2026-07-20 | ADR vs graph edge report; fail-soft CLI; optional --strict |
| ADR-0023 | Review replay console from durable session artifacts | proposed | 2026-07-20 | Read-only issue→context→model→policy→memory replay from CT103 artifacts |
| ADR-0024 | SARIF findings attach as graph security evidence without Risk 2 expansion | proposed | 2026-07-20 | SARIF→finding/tool_run edges; Risk 0/1 evidence only; no fix-gate coupling |
| ADR-0025 | Gated self-improvement proposals land only as Gitea PRs | proposed | 2026-07-20 | Prompt/workflow/`.agent` changes via PR only; deny in-prod self-edit |
| ADR-0026 | Prompt-injection scanner stays shadow-only | accepted | 2026-07-21 | Shadow assessments only; never grant authority; blocking needs new ADR |
| ADR-0027 | Observe event safe-display contract precedes storage/streaming/UI | accepted | 2026-07-22 | observe_event.v1 four-tier field classification; unknown types never expose payload values; wired into projection.py before T02/T03/T04 |
| ADR-0028 | observe.sqlite is a fail-open, display-safe secondary projection | accepted | 2026-07-22 | UNIQUE(run_id,source_kind,source_event_id)+UNIQUE(run_id,projection_sequence) identity; fail-open after primary ledger write; session_observation mirrors live AgentSession; per-project transactional rebuild; no new routes |
| ADR-0029 | Observatory OAuth session shell with 503-vs-403 permission-check distinction | accepted | 2026-07-22 | Identity (401/redirect) split from repo-read authorize (403/503); Gitea-unreachable maps to 503 never 403; state+session-cookie binding defeats replay/fixation; fail-closed when oauth env unset; run_id routes derive repo server-side, not from client `project` hint |
| ADR-0030 | Protected SSE is subscribe-first with Redis ids-only notify over an authoritative SQLite read | accepted | 2026-07-22 | Subscribe before history read closes the race by dedupe-not-timing; Redis notify payload ids-only, never trusted as display data; observe.sqlite stays sole system of record, Redis outage degrades live tailing only; Last-Event-ID/`?after_sequence=` both mean projection_sequence, higher of the two wins |
| ADR-0030 | Protected SSE is subscribe-first over observe.sqlite with Redis ids-only notify | accepted | 2026-07-22 | Subscribe before history read (H4); Redis carries ids only, never display data; durable projection_sequence cursor via Last-Event-ID/?after_sequence=; Redis outage degrades live tailing only, history stays complete; mid-stream auth revoke (V8 T03) preserved |
| ADR-0031 | Observatory five-panel UI renders only pre-validated safe-display data as inert text | accepted | 2026-07-22 | Single autoescaped Jinja2Templates instance, never `|safe`; view-model layer returns only already display-safe primitives, never marks anything Markup; prohibited fields surface names only; run_id reaches HTML only via escaped attributes/URL-quoting, never inline-script string interpolation; panel 4 dual-delivered from one view builder so JS-disabled sees the same data; panel 2 pagination is plain `<a href>`, no JS |
| ADR-0032 | CT102 CI channel projects into the Observatory via canonical state, never event replay | accepted | 2026-07-22 | fix_run_id resolved as the session's run_id (projector fallback, no new identity scheme); current-state CI phase reads verification_claim.json live (never re-derives from event replay, so late/duplicate verdicts cannot regress it); nested WorkflowObservation flattened to scalars before H1 classification; CI deep links built only from trusted repository/workflow_run_id, never the webhook's own html_url; no observe.sqlite schema change |
| ADR-0033 | Enforce a local-only egress boundary for the C1 recursive controller | proposed | 2026-08-16 | The C1 controller checks every route the shared failover chain offers before sending anything and refuses non-homelab providers outright, so a "local 2070" observation no longer depends on `REPO_EXTERNAL_MODEL_POLICY` happening to be empty; refusals fail soft into the existing deterministic result and are counted in telemetry; `controller_gpu_seconds` is nullable with `controller_missing_fields` instead of a fake `0.0`; `controller_model_id` prefers what the endpoint reports and records its provenance |

## Review log

- 2026-07-14 `00234bb` — ADR-0001 proposed for slice 6E CI truth loop
- 2026-07-14 — 6E homelab sign-off (PR #20 / `run-cf4c2b2e…`): verdict=`verified`, memory `ci_verified`; ADR-0001 remains `proposed` pending human accept
- 2026-07-14 — ADR-0002 proposed: SRT as initial sandbox backend; Slice 5.6a CT104 spike before `/agent fix`
- 2026-07-14 — Slice 6F.1 evidence + SandboxBackend scaffolding; 6F.2 gated; 5.2 WIP parked in stash `wip-5.2-harden-parked`
- 2026-07-16 — 6F.1 homelab sign-off (PR #20 @ `9b3d83be…`, runs 463/464): `verdict=failing`, evidence `collected`, ledger events×2; repair still off; follow-ups: comment upsert, control-plane agent-runs mount, classifier
- 2026-07-17 — 5.6a signed off: **2d** live env pin CT103+CT104 (`srt` / `5de9f107…`); no new ADR (ADR-0002 still covers SRT backend)
- 2026-07-17 — 6F.2 gate demo on `demo-app` @ `4ebaab0…`: `repair_requested` + `repair_blocked`; worker push deferred to 5.8; no new ADR
- 2026-07-17 `6c40869` / `c3e5d59` — no ADR: 5.8 command_runner + 6F.2 reservation/lease implement ADR-0002 follow-up; push publish wiring still open
- 2026-07-18 `d3d3ea2` — ADR-0003 proposed: CT104 Docker-on-LXC needs bounded caps for bwrap; 5.8+6F.2 demo acceptance on `demo-app` PR #5 @ `16886456…` (`repair_pushed`, CI green, pending re-pointed)
- 2026-07-18 — ADR-0004 accepted: V4.1.1 CT103 publish brokerage; retire CT104 Gitea write tokens; see `slice-6d2-ct103-publish-brokerage.md`
- 2026-07-19 `e7d9f2b` — no new ADR: 6D.2 PR0 closeout (ingest comments + CT104 PAT revoke/scrub); boundary already ADR-0004; umbrella [slice-v411-closeout.md](../slice-v411-closeout.md)
- 2026-07-19 — ADR-0005 proposed: `policy_source_sha` pin + fail-closed policy workspace (V4.1.1 PR1)
- 2026-07-19 — ADR-0006 proposed: `tool_policy.v2` fail-closed empty allowance + effective command-policy hash (V4.1.1 PR2)
- 2026-07-19 — ADR-0007 proposed: dual sandbox/execution attestations + durable bundle-before-teardown (V4.1.1 PR3)
- 2026-07-19 — ADR-0008 proposed: CT102 scheduling/credential-domain split (ops unit)
- 2026-07-19 — ADR-0009 proposed: repair allowlist + bounded ACP lint class (V4.1.1 PR4)
- 2026-07-19 `dab1e89` — ADR-0010 proposed: CT103 typed sessions (5.4a); `sess-` ≠ `run-`; CT103 correlation authority
- 2026-07-20 `315becd` — ADR-0011 proposed: Slice 5.5a deterministic CT103 context preflight before RLM enqueue
- 2026-07-20 — ADR-0012 proposed: Slice 5.6 verification evidence gate; defer fix/repair `session_finished` until 6E CI
- 2026-07-20 — ADR-0013 proposed: Slice 5.7 session-trace selective writeback (distinct from 6E.2)
- 2026-07-20 — ADR-0014 proposed: T04 adequacy profiles; scoped verification / fixed_verified
- 2026-07-20 — ADR-0015 proposed: T05/8a Orbit dual-graph provenance + coverage; blast-radius fail-soft
- 2026-07-20 — ADR-0016 proposed: T07/8c conditional recursive context worker; skip path preserves no-2070
- 2026-07-20 — ADR-0017 proposed: T10 acting_identity vs invoked_by + invocation ack
- 2026-07-21 — ADR-0017 accepted: V6 T05 separate authorization predicates + pre-publish recheck + commit trailers
- 2026-07-20 — ADR-0018 proposed: T08 bounded recursive Qwen loop; CI-grounded retries; no 6F.2 enable
- 2026-07-20 — ADR-0019 proposed: T13 flag-gated patch tournaments + reward logging; defaults off
- 2026-07-20 — ADR-0020 proposed: V5 T01 AgentFacts-lite content-hash integrity + optional HMAC
- 2026-07-20 — ADR-0021 proposed: V5 T02 memory-as-governance repeated failed fix deny
- 2026-07-20 — ADR-0022 proposed: V5 T04 ADR vs graph architecture drift detector (fail-soft)
- 2026-07-20 — ADR-0023 proposed: V5 T03 review replay console from durable session artifacts
- 2026-07-20 — ADR-0024 proposed: V5 T05 SARIF → graph security evidence; Risk 0/1 only
- 2026-07-20 — ADR-0025 proposed: V5 T06 gated self-improvement PRs; deny in-prod self-edit
- 2026-07-21 — ADR-0026 accepted: V6 T06 injection scanner shadow-only; never grants authority
- 2026-07-22 — ADR-0027 accepted: V9 T01 observe_event.v1 safe-display contract; H1 gate before T02 sqlite / T03 SSE / T04 UI
- 2026-07-22 — ADR-0028 accepted: V9 T02 observe.sqlite fail-open display-safe projection; H3/H6/H7
- 2026-07-22 — ADR-0029 accepted: V9 T05 Observatory OAuth session shell; 503-vs-403 split; state/session anti-fixation; server-derived repo for run_id routes
- 2026-07-22 — ADR-0030 accepted: V9 T03 protected SSE subscribe-first + Redis ids-only notify; observe.sqlite stays sole system of record; Last-Event-ID/`?after_sequence=` both mean projection_sequence
- 2026-07-22 — ADR-0030 accepted: V9 T03 protected SSE subscribe-first + Redis ids-only notify; H4; mid-stream auth revoke (V8 T03) preserved on the new cadence
- 2026-07-22 — ADR-0031 accepted: V9 T04 five-panel Observatory UI; autoescape-always view-model boundary; prohibited fields surface names only; run_id via escaped attributes/URL-quoting not inline script; no-JS timeline pagination
- 2026-07-22 — ADR-0032 accepted: V9 T08 CT102 CI channel into the Observatory; fix_run_id->run_id projector fallback; current-state phase reads canonical verification_claim.json live (no event-replay regression risk); nested observation flattened before H1 classification; CI deep links from trusted repository/workflow_run_id only, never html_url
- 2026-08-16 — ADR-0033 proposed: V10 Wave C C1 controller local-only egress boundary; provider *and* host checked before any request is sent; refusal fails soft into the existing deterministic result; nullable `controller_gpu_seconds` + `controller_missing_fields`; endpoint-reported `controller_model_id` with provenance. Verified live on CT103 and CT104 with an OpenAI-only negative control recording zero external HTTP attempts
