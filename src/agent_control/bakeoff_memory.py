"""V7 T04 — bake-off memory namespace isolation (fork / reset).

In-process store keyed by ``memory_namespace``. Never opens the production
SQLite ``MemoryStore``. Writes and resets are allowed only under ``bakeoff/``.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from agent_shared.models.memory import MemoryRecord

BAKEOFF_PREFIX = "bakeoff/"
PRODUCTION_NAMESPACE_ALIASES = frozenset(
    {
        "production",
        "prod",
        "",
    }
)


class BakeoffMemoryError(ValueError):
    """Isolation / namespace gate failure."""


def is_production_namespace(namespace: str | None) -> bool:
    ns = (namespace or "").strip().lower()
    return ns in PRODUCTION_NAMESPACE_ALIASES


def assert_writable_bakeoff_namespace(namespace: str) -> str:
    ns = (namespace or "").strip()
    if is_production_namespace(ns):
        raise BakeoffMemoryError("refusing write/reset on production memory namespace")
    if not ns.startswith(BAKEOFF_PREFIX):
        raise BakeoffMemoryError(
            f"bake-off memory must use {BAKEOFF_PREFIX}* namespace, got {ns!r}"
        )
    return ns


@dataclass
class BakeoffMemoryFacade:
    """Namespaced bake-off memory. Production SQLite is never opened."""

    _buckets: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    production_memory_touched: bool = False

    def reset(self, namespace: str) -> str:
        """Clear a bake-off namespace (create empty). Refuses production."""
        ns = assert_writable_bakeoff_namespace(namespace)
        self._buckets[ns] = {}
        return ns

    def fork(self, source_namespace: str | None, dest_namespace: str) -> int:
        """Copy in-facade records from source → dest after resetting dest.

        Source may be missing/empty (empty fork). Forking from a production
        namespace alias is refused. Bundle metadata such as ``eval_export`` is
        not loaded from production SQLite — treat non-bakeoff sources as empty.
        """
        dest = assert_writable_bakeoff_namespace(dest_namespace)
        src = (source_namespace or "").strip()
        if is_production_namespace(src):
            raise BakeoffMemoryError("cannot fork from production memory namespace")
        self.reset(dest)
        if not src.startswith(BAKEOFF_PREFIX):
            # Non-bakeoff metadata (e.g. eval_export): empty seed, no prod read.
            return 0
        source_map = self._buckets.get(src, {})
        self._buckets[dest] = {rid: deepcopy(payload) for rid, payload in source_map.items()}
        return len(self._buckets[dest])

    def prepare_namespace(
        self,
        namespace: str,
        *,
        seed_namespace: str | None = None,
    ) -> dict[str, Any]:
        """Reset dest, optionally fork from a bake-off seed namespace."""
        ns = assert_writable_bakeoff_namespace(namespace)
        if seed_namespace and is_production_namespace(seed_namespace):
            raise BakeoffMemoryError("cannot seed bake-off from production namespace")
        forked_from: str | None = None
        copied = 0
        if seed_namespace and str(seed_namespace).startswith(BAKEOFF_PREFIX):
            copied = self.fork(seed_namespace, ns)
            forked_from = seed_namespace
        else:
            # Empty reset; non-bakeoff metadata (e.g. eval_export) never opens prod SQLite.
            self.reset(ns)
        return {
            "schema_version": "bakeoff_memory_isolation.v1",
            "memory_namespace": ns,
            "forked_from": forked_from,
            "seed_copied": copied,
            "record_count": self.record_count(ns),
            "production_memory_touched": self.production_memory_touched,
        }

    def upsert(self, namespace: str, record: MemoryRecord) -> MemoryRecord:
        ns = assert_writable_bakeoff_namespace(namespace)
        bucket = self._buckets.setdefault(ns, {})
        payload = record.model_dump(mode="json")
        bucket[record.run_id] = payload
        return record

    def list_records(self, namespace: str) -> list[MemoryRecord]:
        ns = (namespace or "").strip()
        if is_production_namespace(ns):
            # Do not open production store; surface empty without marking touched.
            return []
        rows = self._buckets.get(ns, {})
        return [MemoryRecord.model_validate(deepcopy(p)) for p in rows.values()]

    def visible_run_ids(self, namespace: str) -> set[str]:
        return {r.run_id for r in self.list_records(namespace)}

    def record_count(self, namespace: str) -> int:
        ns = (namespace or "").strip()
        if is_production_namespace(ns):
            return 0
        return len(self._buckets.get(ns, {}))

    def namespaces(self) -> list[str]:
        return sorted(self._buckets.keys())


def assert_writebacks_isolated(
    facade: BakeoffMemoryFacade,
    namespaces: list[str],
) -> None:
    """Fail if any run_id is visible in more than one bake-off namespace."""
    ownership: dict[str, str] = {}
    for ns in namespaces:
        assert_writable_bakeoff_namespace(ns)
        for run_id in facade.visible_run_ids(ns):
            prior = ownership.get(run_id)
            if prior is not None and prior != ns:
                raise BakeoffMemoryError(
                    f"writeback leak: run_id {run_id!r} visible in {prior!r} and {ns!r}"
                )
            ownership[run_id] = ns
    if facade.production_memory_touched:
        raise BakeoffMemoryError("production memory was touched during bake-off")


def marker_record(
    *,
    run_id: str,
    profile_id: str,
    namespace: str,
) -> MemoryRecord:
    """Minimal memory_record.v1 used to prove namespace isolation in dry-runs."""
    return MemoryRecord(
        record_id=f"rec-bakeoff-{profile_id}-{run_id}",
        run_id=run_id,
        repo_owner="ai-sdlc-lab",
        repo_name="demo-app",
        repo_full_name="ai-sdlc-lab/demo-app",
        issue_id=1,
        source_command="plan",
        source_run_id=run_id,
        created_at="2026-07-21T00:00:00+00:00",
        updated_at="2026-07-21T00:00:00+00:00",
        unresolved_questions=[f"bakeoff isolation marker ns={namespace}"],
    )
