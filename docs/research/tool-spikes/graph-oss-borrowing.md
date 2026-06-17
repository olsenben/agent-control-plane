# Graph layer — open-source borrowing strategy

Status: **adopt design, integrate small on CT103** (Option C).  
Does not replace webhook guard, reducer, policy gates, or CT102 CI truth.

## Executive summary

Do not build the cross-repo graph from scratch. Borrow schemas and patterns from proven projects; reimplement a **minimal SQLite + Tree-sitter + NetworkX** subset owned by CT103 `graph-indexer`.

Closest architectural match: **Codebase-Memory** (Tree-sitter → SQLite knowledge graph → MCP tools → impact analysis). Study it closely; integrate tightly rather than running as an unmanaged sidecar initially.

## Borrow map

| Need | Project | License / notes | Adoption |
|------|---------|-----------------|----------|
| Code parsing, symbols, imports | [Tree-sitter](https://tree-sitter.github.io/) | MIT | **Adopt** — parser foundation; Python first |
| Agent-facing graph + MCP shapes | [Codebase-Memory](https://arxiv.org/abs/2512.04848) | Research + impl | **Adapter** — schema/tool ideas; tiny CT103 subset |
| Repo-level graph module | [RepoGraph](https://github.com/ozyyshr/RepoGraph) | Check repo | **Spike** — plug-in pattern for SWE agents |
| Build/test architecture graph | RIG / SPADE | Research | **Inspire** — components, tests, runners JSON schema |
| Full-text / browse | [OpenGrok](https://github.com/oracle/opengrok) | CDDL | **Defer** — optional search UI later |
| Service catalog | [Backstage](https://backstage.io/docs/features/software-catalog/) | Apache-2.0 | **Adopt pattern** — `catalog-info.yaml` per service |
| Affected targets | [Nx](https://nx.dev/), Pants, Bazel | Various | **Concepts only** — no full monorepo toolchain |
| Guardrail static rules | [Semgrep](https://semgrep.dev/) | LGPL | **Adopt soon** — custom policy rules → graph nodes |
| Deep security DB | [CodeQL](https://codeql.github.com/) | Custom license | **Defer** — SARIF ingest Phase 3 |
| CPG / taint | [Joern](https://joern.io/) | Apache-2.0 | **Defer** — heavy; security repos later |
| Deterministic refactor | [OpenRewrite](https://docs.openrewrite.org/) | Apache-2.0 | **Defer** — `/agent fix --mode recipe` Phase 4 |
| Graph algorithms | [NetworkX](https://networkx.org/) | BSD | **Adopt** — MVP blast-radius, rdeps, paths |
| Vector semantic memory | [Chroma](https://www.trychroma.com/) | Apache-2.0 | **Optional** — ADR/run embeddings Phase 2+ |

## ORBIT caveat

Public **ORBIT** (2026) found in search is a **dependency-guided C-to-Rust transpilation** framework (specialized agents + iterative verification) — aligned with our Plan/Fix pattern, **not** a verified GitLab code-intelligence product named Orbit.

## Codebase-Memory — primary reference

Architecture we mirror at reduced scope:

```text
Tree-sitter parsing
  → persistent SQLite knowledge graph
  → code relationships + impact analysis
  → MCP tools (typed queries, not graph dumps)
```

Tools to map to our `agentctl graph` / future MCP:

| Codebase-Memory tool | Our equivalent |
|----------------------|----------------|
| `search_graph` | `agentctl graph` query / SQLite |
| `trace_call_path` | `agentctl graph path` |
| `query_graph` | SQL + NetworkX |
| `detect_changes` | webhook + snapshot diff |
| `get_architecture` | catalog + RIG-inspired JSON |
| `get_code_snippet` | Tree-sitter + context pack |
| `search_code` | ripgrep + FTS5 |
| `manage_adr` | ADR index + `list_related_adrs` |

**Options:**

- **A** — Borrow design/schema only (default)
- **B** — MCP sidecar spike on homelab (after Phase 1)
- **C** — Tiny Python reimplementation on CT103 ( **start here** )

## Backstage catalog pattern

Declared metadata beats pure import inference. Harvest `catalog-info.yaml` at snapshot:

- `metadata.name`, `owner`, `repo`
- `spec.dependsOn`, `providesApis`
- `spec.verifiedBy` → test + CI job edges
- `spec.adrRefs` → ADR edges

See example in [graph-indexer.md](../graph-indexer.md).

## Nx / Pants / Bazel — concepts only

| Source | Copy |
|--------|------|
| Nx | changed files → affected projects → affected tasks |
| Pants | infer deps from import statements |
| Bazel query | `deps()`, `rdeps()`, `somepath()`, `allpaths()` |

Local CLI:

```bash
agentctl graph rdeps service:ct103-control-plane
agentctl graph tests-for file:src/agent_control/dispatch.py
```

## Semgrep + CodeQL

**Review MVP+:** Semgrep for homelab guardrails:

- prompt-injection patterns in repo content
- dangerous shell/subprocess
- secret leakage
- destructive git patterns
- unapproved network calls

Ingest findings as graph nodes: `Finding → File → ToolRun → severity`.

**Later:** CodeQL databases + SARIF for deeper security; attach to graph; block Risk 2 fix when critical findings open.

## OpenRewrite — future fix mode

```text
LLM proposes intent
  → OpenRewrite recipe applies transformation
  → CT102 verifies
  → human approves
```

`/agent fix --mode recipe` for mechanical changes (API renames, config keys, logging imports).

## Implementation phases

### Phase 1 — Graph-lite (Review MVP)

catalog-info parser, SQLite tables, Tree-sitter Python imports, blast-radius JSON, context-pack, review comment section.

### Phase 2 — Agent tools

Codebase-Memory-inspired MCP read-only tools on CT103.

### Phase 3 — Security + CI

Semgrep, SARIF ingest, affected CI matrix, graph-gated fix.

### Phase 4 — Portfolio

OpenRewrite recipes, Joern/CPG sidecar, drift detector, 2070 graph compression.

## Invariants (unchanged)

- Graph is CT103-owned; CT104 consumes packs only
- Graph consultation required for review/plan (not optional tool calls)
- `missing_edges` must be honest
- No graph DB until SQLite + NetworkX insufficient
- Tool adoption must not bypass policy gates or closed-world diff checks

## Decision

| Component | Decision |
|-----------|----------|
| Tree-sitter | adopt |
| NetworkX | adopt |
| SQLite graph store | adopt |
| catalog-info.yaml | adopt pattern |
| Codebase-Memory | adapter (design + tools) |
| Semgrep | adopt Phase 3 |
| CodeQL, Joern, OpenRewrite, Chroma, OpenGrok, Neo4j | defer per phase |
