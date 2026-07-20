# Cross-repo intelligence graph (CT103)

Structural layer beneath trajectory memory. **Memory remembers what happened. The graph knows what depends on what. CI proves what is broken.**

**Do not build this from scratch.** Borrow aggressively from open-source patterns; keep integration small and CT103-owned. Detail: [research/tool-spikes/graph-oss-borrowing.md](research/tool-spikes/graph-oss-borrowing.md).

## Design principle

```text
Option A: Study Codebase-Memory / RepoGraph / RIG schemas
Option B: Run Codebase-Memory as MCP sidecar (spike later)
Option C: Reimplement a tiny subset in Python/SQLite on CT103  ← start here
```

Tight integration with policy gates, event ledger, and `agentctl` beats a standalone graph product.

## Placement

```text
Gitea
  -> CT103 event ledger / policy / memory
  -> graph-indexer (SQLite + Tree-sitter + declared catalog)
  -> CT104 bounded workflow execution
  -> 3080 Qwen reasoning
  -> 2070 memory compression
  -> CT102 CI truth
```

CT103 owns the graph. CT104 consumes blast-radius and context packs — does not build the graph per run.

## Minimal stack (Review MVP — install now)

```text
Python
SQLite
Tree-sitter          # parsing, imports, symbols (Python first)
NetworkX             # blast-radius, rdeps, path queries
ripgrep              # lexical fallback
Gitea API            # repo list, webhooks refresh
catalog-info.yaml    # Backstage-style declared service metadata
```

**Do not install yet:** Neo4j, Joern, CodeQL, OpenGrok, Chroma, full Nx/Bazel/Pants.

**Add soon (Phase 2–3):** Semgrep (custom guardrail rules), Codebase-Memory-inspired MCP tools, Chroma for ADR/run semantic search.

## Phase 1 — Graph-lite (Review MVP)

Build now — enough to make `/agent review` meaningfully better:

1. `catalog-info.yaml` parser (Backstage-style `Component` manifests)
2. SQLite tables: repo, file, service, test, ADR, edge
3. Tree-sitter import/function extraction (**Python first**)
4. Declared + observed edges (see below)
5. `blast-radius` + `context-pack` JSON
6. `/agent review` includes graph section (CT103 **requires** graph consultation)

### MVP edges

```text
repo_contains_file
service_depends_on_service      # from catalog-info.yaml
file_imports_file               # Tree-sitter / Pants-style import inference
file_tested_by_test             # catalog verifiedBy + heuristic test paths
adr_mentions_service
package_depends_on_package      # pyproject.toml / package.json
test_runs_in_ci_job             # .gitea/workflows/*.yml
```

Combine **declared metadata** (catalog) with **observed** code/build/test edges. Do not infer everything from imports alone.

### Service catalog (`catalog-info.yaml`)

One file per repo or service — harvest into graph at snapshot time:

```yaml
apiVersion: homelab.ai/v1
kind: Component
metadata:
  name: ct103-control-plane
  owner: ben
  repo: ai-sdlc-lab/agent-control-plane
spec:
  type: service
  lifecycle: experimental
  providesApis:
    - agent-webhook
    - result-ingest
  dependsOn:
    - redis-worker-state
    - shared-agent-state
    - gitea
  verifiedBy:
    - .gitea/workflows/deploy.yaml
    - tests/test_dispatch.py
  adrRefs:
    - ADR-003-agent-state
    - ADR-007-command-risk-classes
```

Place in repo root or `catalog-info.yaml` / `.agent/catalog-info.yaml`.

## CLI

### `agentctl graph snapshot`

Crawl allowed Gitea org repos; refresh SQLite graph + optional JSON exports under `agent-state/graph/`. Idempotent; safe to cron on CT103.

### `agentctl graph blast-radius`

```bash
agentctl graph blast-radius \
  --repo ai-sdlc-lab/agent-control-plane \
  --files src/agent_control/workflows/dispatch.py
```

### `agentctl graph sarif-ingest` (V5 T05)

```bash
agentctl graph sarif-ingest \
  --repo ai-sdlc-lab/agent-control-plane \
  --file tests/fixtures/sample_t05.sarif.json
```

Attaches SARIF findings as Orbit evidence edges (`finding_affects_file`,
`tool_run_produced_finding`, `tool_run_covers_repo`). Risk 0/1 evidence only —
does not expand Risk 2 gates. See [slice-v5-t05-sarif-ingest.md](slice-v5-t05-sarif-ingest.md).

### `agentctl graph context-pack`

```bash
agentctl graph context-pack --repo ai-sdlc-lab/agent-control-plane --issue 2
```

Bounded JSON for dispatch — wired into `RLMJob` context profile.

### Query helpers (Nx/Bazel-inspired, local)

```bash
agentctl graph rdeps service:ct103-control-plane
agentctl graph tests-for file:src/agent_control/dispatch.py
agentctl graph path service:ct104-worker-rlm-root service:gitea
```

Borrow **affected files → affected projects → affected tasks** from Nx; **deps/rdeps/somepath** from Bazel query — implemented simply on NetworkX + SQLite.

### Example blast-radius output

```json
{
  "repo": "ai-sdlc-lab/agent-control-plane",
  "changed_files": ["src/agent_control/workflows/dispatch.py"],
  "affected_services": ["ct103-control-plane", "ct104-worker-rlm-root"],
  "affected_repos": ["ai-sdlc-lab/agent-control-plane"],
  "affected_tests": ["tests/test_dispatch.py", "tests/test_worker_ingest.py"],
  "related_adrs": ["ADR-003-agent-state", "ADR-007-command-risk-classes"],
  "missing_edges": ["No explicit service owner for worker-report"],
  "confidence": "medium"
}
```

Honest `missing_edges` is required — do not hallucinate graph completeness.

## Open-source borrow map

| Need | Borrow from | Our use |
|------|-------------|---------|
| Parsing / symbols | **Tree-sitter** | Files, imports, lightweight call edges |
| Agent graph design | **Codebase-Memory** | SQLite knowledge graph + MCP tool shapes |
| Repo graph module | **RepoGraph** | Repository-level graph as plug-in pattern |
| Build/test graph schema | **RIG / SPADE** | Components, tests, runners, coverage edges |
| Service catalog | **Backstage** | `catalog-info.yaml` declared metadata |
| Affected CI selection | **Nx / Pants / Bazel** | Concepts only — not full monorepo adoption |
| Guardrail rules | **Semgrep** | Prompt injection, secrets, shell, git danger patterns |
| Deep security | **CodeQL** (later) | SARIF → graph `Finding` nodes |
| Semantic graph | **Joern / CPG** (later) | Security-heavy repos only |
| Deterministic fix | **OpenRewrite** (later) | `/agent fix --mode recipe` |
| Graph algorithms | **NetworkX** | MVP traversal before graph DB |
| Semantic memory | **Chroma** (optional) | ADR/issue/run embeddings |
| Search reference | **OpenGrok** | Optional UI; not required for MVP |

**Note:** Public “ORBIT” (2026) is a C-to-Rust transpilation research framework — dependency-guided agents + iterative verification — conceptually aligned with Plan/Fix, not a GitLab product. No verified GitLab “Orbit” repo-dependency product page found.

## Phase 2 — Agent-facing graph tools

MCP-style tools inspired by Codebase-Memory (typed tools, not giant graph dumps):

```text
search_graph
trace_dependency_path
find_tests_for_file
explain_blast_radius
get_context_pack
list_related_adrs
```

Expose read-only via CT103 MCP state server (future) — after Phase 1 snapshot is stable.

## Phase 3 — Security and CI truth

```text
Semgrep scan → graph Finding nodes
CodeQL SARIF ingest (later)
affected CI matrix for CT102
graph-gated /agent fix approval
```

Finding graph shape:

```text
Finding → affects File → produced_by ToolRun → severity → SARIF location → blocks Risk 2?
```

## Phase 4 — Portfolio layer

```text
OpenRewrite recipe mode (/agent fix --mode recipe)
Joern/codebadger-style CPG MCP sidecar
architecture drift detector (ADR vs observed edges)
2070 graph-memory compression
Kuzu/Neo4j only if SQLite queries become painful
```

## Context pack compiler

```text
issue text + diff
+ ADR slice (graph list_related_adrs)
+ blast_radius JSON (required)
+ prior memory (selective)
+ ripgrep/FTS hits
= context_pack.v1 (token-budgeted)
```

## Navigation paradox

CodeCompass / Codebase-Memory: agents skip graph tools unless forced. CT103 **attaches** blast-radius to dispatch — not optional model tool calls.

## Integration with Review MVP slices

```text
Slice 1: review engine + comment (graph stub: missing_edges honest)
Slice 2: richer context pack
Slice 3: Phase 1 graph-lite (this doc)  ← parallel after Slice 1
Slice 4: memory + risk_tags on ingest
```

Do not delay Slice 1 for graph. Add Phase 1 graph before closing Review MVP acceptance.

## Related

- [graph-oss-borrowing.md](research/tool-spikes/graph-oss-borrowing.md) — full borrow rationale
- [RUNBOOK_REVIEW_MVP.md](RUNBOOK_REVIEW_MVP.md)
- [MEMORY_SCHEMA.md](MEMORY_SCHEMA.md) — `blast_radius` field on memory records
