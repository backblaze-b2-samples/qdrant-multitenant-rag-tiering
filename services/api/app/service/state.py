"""In-memory runtime state: per-tenant locks, activity clocks, transitional states.

Durable state lives in B2 (corpus, manifests) and Qdrant (collections); this
module only holds what is cheap to lose. After a restart every idle clock
starts from process start, which can only DELAY parking, never park early.

One `asyncio.Lock` per tenant serialises park, restore, edit, delete and query,
so a query that arrives mid-park waits and then restores from the snapshot the
park just verified.
"""

import asyncio
import time
from datetime import UTC, datetime

_locks: dict[str, asyncio.Lock] = {}
_last_query: dict[str, float] = {}
_last_write: dict[str, float] = {}
_transitional: dict[str, str] = {}
_progress: dict[str, tuple[int, int]] = {}  # (done, total) within the current stage
_started_at: float = time.time()


def reset(started_at: float | None = None) -> None:
    global _started_at
    _locks.clear()
    _last_query.clear()
    _last_write.clear()
    _transitional.clear()
    _progress.clear()
    _started_at = time.time() if started_at is None else started_at


def lock_for(tenant_id: str) -> asyncio.Lock:
    lock = _locks.get(tenant_id)
    if lock is None:
        lock = _locks[tenant_id] = asyncio.Lock()
    return lock


def mark_query(tenant_id: str, when: float | None = None) -> None:
    _last_query[tenant_id] = time.time() if when is None else when


def touch(tenant_id: str, when: float | None = None) -> None:
    """Record a write (create, edit, restore). Counts as activity for parking."""
    _last_write[tenant_id] = time.time() if when is None else when
    if when is not None:
        # An explicit time (tests, backfills) overrides the query clock too.
        _last_query.pop(tenant_id, None)


def last_activity(tenant_id: str) -> float:
    """Most recent query or write seen by this process, else process start."""
    seen = [t for t in (_last_query.get(tenant_id), _last_write.get(tenant_id)) if t is not None]
    return max(seen) if seen else _started_at


def last_query_at(tenant_id: str) -> datetime | None:
    when = _last_query.get(tenant_id)
    return None if when is None else datetime.fromtimestamp(when, UTC)


def set_transitional(tenant_id: str, value: str | None) -> None:
    _progress.pop(tenant_id, None)  # a count belongs to one stage
    if value is None:
        _transitional.pop(tenant_id, None)
    else:
        _transitional[tenant_id] = value


def transitional(tenant_id: str) -> str | None:
    return _transitional.get(tenant_id)


def set_progress(tenant_id: str, done: int, total: int) -> None:
    _progress[tenant_id] = (done, total)


def progress(tenant_id: str) -> tuple[int, int] | None:
    return _progress.get(tenant_id)


def forget(tenant_id: str) -> None:
    for table in (_last_query, _last_write, _transitional, _progress):
        table.pop(tenant_id, None)
