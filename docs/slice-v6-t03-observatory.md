# Slice V6 T03 — Agent Observatory

**Status:** In Progress  
**Epic ticket:** T03  
**Deps:** T02 Done (`66f885e`)

## Goal

Read-only Agent Observatory: session list, timeline page, JSON events API, SSE stream, artifact index, Observe links in comments.

## Routes

- `GET /observe/repos/{owner}/{repo}`
- `GET /observe/sessions/{run_id}`
- `GET /api/observe/sessions/{run_id}/events`
- `GET /api/observe/sessions/{run_id}/artifacts`
- `GET /api/observe/sessions/{run_id}/stream`

## Deploy verification

Pending after tip deploy.
