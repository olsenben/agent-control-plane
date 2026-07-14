# ADR summary

Index of architecture decisions. Full records live in this directory.

| ID | Title | Status | Date | Decision (one line) |
|----|-------|--------|------|---------------------|
| ADR-0001 | CT102 CI aggregate truth before fix memory | proposed | 2026-07-14 | Webhook signals + Actions API confirm; memory only when aggregate verdict=`verified` |

## Review log

- 2026-07-14 `00234bb` — ADR-0001 proposed for slice 6E CI truth loop
- 2026-07-14 — 6E homelab sign-off (PR #20 / `run-cf4c2b2e…`): verdict=`verified`, memory `ci_verified`; ADR-0001 remains `proposed` pending human accept
