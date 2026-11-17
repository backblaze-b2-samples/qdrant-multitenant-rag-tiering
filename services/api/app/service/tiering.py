"""Tiering policy and the park state machine.

Park (the safety rule; any failure in steps 1-4 leaves the tenant hot):

1. Qdrant creates a collection snapshot (name, size, sha256 checksum).
2. The snapshot streams from the node into a B2 multipart upload, hashed on
   the way; the hash must equal Qdrant's checksum.
3. `latest.json` is written LAST, so a previously good manifest is never
   replaced before the new snapshot object is fully uploaded.
4. Verify: `head_object` size, then a streamed re-read sha256, both against
   the manifest. A failure here puts the previous manifest back (or removes
   the new one) and deletes the unverified object.
5. Only then: delete the node-local snapshot and drop the collection.
"""

import asyncio
import contextlib
import logging
import secrets
import time
from datetime import UTC, datetime

from app.config import settings
from app.repo import snapshot_store
from app.service import deps, state, tenants
from app.service.validation import validate_tenant_id
from app.types.tiering import (
    ParkResult,
    SkippedTenant,
    SnapshotEntry,
    SnapshotManifest,
    TieringPolicy,
    TieringRunRequest,
    TieringRunResult,
    TieringStats,
)

logger = logging.getLogger(__name__)


class _ParkAborted(Exception):
    pass


def select_candidates(
    states: dict[str, str], activity: dict[str, float], idle_seconds: int, now: float
) -> list[str]:
    """Hot tenants idle for at least `idle_seconds`. Empty, parked and busy are skipped."""
    return sorted(
        t for t, s in states.items() if s == "hot" and now - activity[t] >= idle_seconds
    )


def _new_snapshot_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-" + secrets.token_hex(3)


def park_locked(tenant_id: str) -> ParkResult:
    """Run the park state machine. Caller holds the tenant lock. Blocking."""
    store, gateway, embedder = deps.store(), deps.gateway(), deps.embedder()
    collection = deps.collection_name(tenant_id)
    manifest_key = deps.manifest_key(tenant_id)
    stats = gateway.collection_stats(collection)
    if stats is None:
        parked = store.head_size(manifest_key) is not None
        return ParkResult(
            tenant_id=tenant_id,
            state="parked" if parked else "empty",
            manifest=None,
            verified=False,
            reason="already parked" if parked else "tenant has no collection to park",
        )
    meta = tenants.read_meta(tenant_id)
    node_snapshot = None
    new_key = None
    previous: bytes | None = None
    manifest_written = False
    rss_before = gateway.memory_bytes()
    state.set_transitional(tenant_id, "snapshotting")
    started = time.perf_counter()
    try:
        node_snapshot = gateway.create_snapshot(collection)
        snapshot_id = _new_snapshot_id()
        new_key = deps.snapshot_key(tenant_id, snapshot_id)
        state.set_transitional(tenant_id, "uploading")
        try:
            upload = snapshot_store.upload_stream(
                store,
                new_key,
                gateway.iter_snapshot(collection, node_snapshot.name, snapshot_store.READ_CHUNK),
                settings.snapshot_part_size_bytes,
            )
        except Exception as e:
            raise _ParkAborted(f"snapshot upload to B2 failed: {e}") from e
        if node_snapshot.checksum and upload.sha256 != node_snapshot.checksum:
            raise _ParkAborted("checksum mismatch: uploaded bytes differ from Qdrant's snapshot")
        upload_ms = round((time.perf_counter() - started) * 1000, 3)
        manifest = SnapshotManifest(
            tenant_id=tenant_id,
            snapshot_key=new_key,
            snapshot_id=snapshot_id,
            size_bytes=upload.size_bytes,
            point_count=stats.points,
            sha256=upload.sha256,
            vector_size=stats.vector_size,
            distance=stats.distance,
            embedding_model=embedder.model_name,
            qdrant_version=gateway.version(),
            created_at=datetime.now(UTC),
            payload_bytes=tenants.payload_total(meta),
        )
        previous = store.get_bytes(manifest_key)
        snapshot_store.put_manifest(store, manifest_key, manifest)
        manifest_written = True
        state.set_transitional(tenant_id, "verifying")
        reason = snapshot_store.verify_snapshot(
            store, new_key, manifest.size_bytes, manifest.sha256
        )
        if reason:
            raise _ParkAborted(reason)
    except Exception as e:
        reason = str(e) if isinstance(e, _ParkAborted) else f"park failed: {e}"
        _roll_back(tenant_id, collection, node_snapshot, new_key, manifest_written, previous)
        logger.warning("Park of %s aborted, tenant stays hot: %s", tenant_id, reason)
        return ParkResult(
            tenant_id=tenant_id, state="hot", manifest=None, verified=False, reason=reason
        )
    state.set_transitional(tenant_id, "dropping")
    with contextlib.suppress(Exception):
        gateway.delete_snapshot(collection, node_snapshot.name)
    gateway.delete_collection(collection)
    state.set_transitional(tenant_id, None)
    rss_after = gateway.memory_bytes()
    if meta is not None and meta.get("snapshot_stale"):
        meta["snapshot_stale"] = False
        tenants.write_meta(meta)
    return ParkResult(
        tenant_id=tenant_id,
        state="parked",
        manifest=manifest,
        verified=True,
        reason=None,
        vector_bytes_freed=stats.points * stats.vector_size * 4 + manifest.payload_bytes,
        node_rss_delta_bytes=(
            rss_before - rss_after if rss_before is not None and rss_after is not None else None
        ),
        snapshot_upload_ms=upload_ms,
    )


def _roll_back(tenant_id, collection, node_snapshot, new_key, manifest_written, previous) -> None:
    """Undo a failed park: the collection is untouched, so only B2 needs repair."""
    store = deps.store()
    manifest_key = deps.manifest_key(tenant_id)
    with contextlib.suppress(Exception):
        if manifest_written:
            if previous is not None:
                store.put_bytes(manifest_key, previous, "application/json")
            else:
                store.delete_keys([manifest_key])
    with contextlib.suppress(Exception):
        if new_key:
            store.delete_keys([new_key])
    with contextlib.suppress(Exception):
        if node_snapshot is not None:
            deps.gateway().delete_snapshot(collection, node_snapshot.name)
    state.set_transitional(tenant_id, None)


async def park_tenant(tenant_id: str, idle_seconds: int | None = None) -> ParkResult:
    """Park one tenant. With `idle_seconds`, re-check idleness under the lock."""
    validate_tenant_id(tenant_id)
    async with state.lock_for(tenant_id):
        if idle_seconds is not None and time.time() - state.last_activity(tenant_id) < idle_seconds:
            return ParkResult(
                tenant_id=tenant_id, state="hot", manifest=None, verified=False,
                reason="tenant became active after it was selected",
            )
        return await asyncio.to_thread(park_locked, tenant_id)


def current_states() -> dict[str, str]:
    collections = set(deps.gateway().list_collections())
    with_manifest = tenants.parked_ids()
    return {
        t: tenants.derive_state(t, collections, t in with_manifest)
        for t in tenants.list_tenant_ids()
    }


async def run_policy(request: TieringRunRequest) -> TieringRunResult:
    idle = settings.tiering_idle_seconds if request.idle_seconds is None else request.idle_seconds
    states = await asyncio.to_thread(current_states)
    activity = {t: state.last_activity(t) for t in states}
    candidates = select_candidates(states, activity, idle, time.time())
    parked: list[str] = []
    skipped: list[SkippedTenant] = []
    if not request.dry_run:
        for tenant_id in candidates:
            result = await park_tenant(tenant_id, idle_seconds=idle)
            if result.verified:
                parked.append(tenant_id)
            else:
                skipped.append(SkippedTenant(tenant_id=tenant_id, reason=result.reason or "not parked"))
    return TieringRunResult(
        candidates=candidates, parked=parked, skipped=skipped, dry_run=request.dry_run
    )


async def sweep_forever(interval_seconds: int) -> None:
    """Background sweep started in the app lifespan. Never raises."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            result = await run_policy(TieringRunRequest(dry_run=False))
            if result.candidates:
                logger.info(
                    "Tiering sweep: parked=%s skipped=%s",
                    result.parked,
                    [s.model_dump() for s in result.skipped],
                )
        except Exception:
            logger.exception("Tiering sweep failed")


def get_policy() -> TieringPolicy:
    return TieringPolicy(
        idle_seconds=settings.tiering_idle_seconds,
        sweep_interval_seconds=settings.tiering_sweep_interval_seconds,
        prune_enabled=settings.snapshot_prune_enabled,
    )


def get_stats() -> TieringStats:
    summaries = tenants.list_tenants_sync()
    store = deps.store()
    snapshot_bytes = sum(
        e.size_bytes for e in store.list_objects(deps.snapshots_root()) if e.key.endswith(".snapshot")
    )
    corpus_bytes = sum(e.size_bytes for e in store.list_objects(deps.corpus_root()))
    return TieringStats(
        hot=sum(s.state == "hot" for s in summaries),
        parked=sum(s.state == "parked" for s in summaries),
        empty=sum(s.state == "empty" for s in summaries),
        vector_bytes_hot=sum(s.vector_bytes_estimate for s in summaries if s.state == "hot"),
        vector_bytes_freed=sum(s.vector_bytes_estimate for s in summaries if s.state == "parked"),
        snapshot_bytes_b2=snapshot_bytes,
        corpus_bytes_b2=corpus_bytes,
    )


def list_snapshots(tenant_id: str) -> list[SnapshotEntry]:
    validate_tenant_id(tenant_id)
    store = deps.store()
    manifest = snapshot_store.get_manifest(store, deps.manifest_key(tenant_id))
    latest = manifest.snapshot_key if manifest else None
    entries = [
        SnapshotEntry(
            key=e.key, size_bytes=e.size_bytes, created_at=e.last_modified, is_latest=e.key == latest
        )
        for e in store.list_objects(deps.snapshot_prefix(tenant_id))
        if e.key.endswith(".snapshot")
    ]
    return sorted(entries, key=lambda e: (e.created_at, e.key), reverse=True)
