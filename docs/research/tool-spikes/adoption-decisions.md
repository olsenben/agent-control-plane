# Adoption decisions

| Tool | Status | Notes |
|------|--------|-------|
| FastAPI | adopt | Webhook guard and control API |
| Redis/RQ | adopt | MVP job queue |
| pydantic-settings | adopt | Typed config |
| GitIngest | adapter | Context baseline, not canonical state |
| Tree-sitter | adopt | Graph-indexer parsing; Python first |
| NetworkX | adopt | Blast-radius, rdeps, path queries on CT103 |
| Backstage catalog-info | adopt pattern | Declared service metadata YAML |
| Codebase-Memory | adapter | SQLite graph + MCP tool shapes; tiny CT103 subset |
| Semgrep | adopt soon | Guardrail rules → graph Finding nodes (Phase 3) |
| RepoGraph | spike | Repo-level graph plug-in pattern |
| Ray | defer | Two-GPU lab uses RQ first |
| OpenHands | spike | Sandbox reference |
| MCP | defer | Read-only state/graph server after graph-lite |
| Instructor | adopt (optional) | Structured output provider behind env flag; see instructor-structured-output.md |
| watchfiles | adopt (optional) | Ingest-watch backup over NFS |
| CodeQL, Joern, OpenRewrite, Chroma, OpenGrok, Neo4j | defer | See graph-oss-borrowing.md phases |

No dependency may bypass webhook guard, reducer, policy gates, or closed-world diff checks.
