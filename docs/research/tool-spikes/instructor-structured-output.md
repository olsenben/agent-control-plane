# Instructor structured output spike

**Status:** adopt (optional provider)  
**Date:** 2026-06-25

## Decision

Add `instructor` as an **optional** dependency behind `STRUCTURED_OUTPUT_PROVIDER=instructor_ollama`.

Default remains `native_ollama_schema` (existing `chat_completion` + Ollama `format`).

## Rationale

Homelab issue #9: Ollama can return prose despite schema/json format. Instructor adds Pydantic-first extraction and retries without replacing the control-plane validation boundary.

## Hard rule

Instructor output still passes through `validate_or_repair` (premerge, normalizers, Pydantic). The provider does not replace the boundary.

## Rollback

`STRUCTURED_OUTPUT_PROVIDER=native_ollama_schema`
