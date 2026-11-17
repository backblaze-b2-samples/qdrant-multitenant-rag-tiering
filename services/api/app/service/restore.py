"""Restore a parked tenant from B2 into the current Qdrant node, and query.

The first query to a parked tenant restores it inline: under the tenant lock,
read `latest.json`, stream the snapshot object from B2 into a spooled temp file
(hashing it against the manifest), post it to the node's snapshot upload API,
and check the restored point count against the manifest before answering.
"""

import asyncio
import contextlib
import time

from app.repo import snapshot_store
from app.service import deps, state
from app.service.errors import Conflict, NotFound, StorageFailure
from app.service.validation import validate_tenant_id
from app.types.tenants import QueryHit, QueryRequest, QueryResponse, RestoreResult, RestoreTiming


def _ms(start: float, end: float) -> float:
    return round((end - start) * 1000, 3)


def is_hot(tenant_id: str) -> bool:
    return deps.collection_name(tenant_id) in deps.gateway().list_collections()


def restore_locked(tenant_id: str) -> tuple[RestoreTiming, int]:
    """Restore `tenant_id`. Caller holds the tenant lock. Blocking."""
    store, gateway, embedder = deps.store(), deps.gateway(), deps.embedder()
    manifest = snapshot_store.get_manifest(store, deps.manifest_key(tenant_id))
    if manifest is None:
        raise Conflict(f"Tenant {tenant_id} is not hot and has no snapshot in B2.")
    if manifest.embedding_model != embedder.model_name or (
        manifest.vector_size != embedder.vector_size()
    ):
        raise Conflict(
            f"Snapshot was built with embedding model {manifest.embedding_model} "
            f"({manifest.vector_size} dims) but this API runs {embedder.model_name} "
            f"({embedder.vector_size()} dims); restoring it would return wrong results."
        )
    collection = deps.collection_name(tenant_id)
    state.set_transitional(tenant_id, "restoring")
    try:
        started = time.perf_counter()
        spool, sha256, size = snapshot_store.download_to_spool(store, manifest.snapshot_key)
        downloaded = time.perf_counter()
        with spool:
            if sha256 != manifest.sha256 or size != manifest.size_bytes:
                raise StorageFailure(
                    "The snapshot in B2 does not match its manifest (size or checksum); "
                    "refusing to load it."
                )
            gateway.upload_snapshot(
                collection, spool, f"{manifest.snapshot_id}.snapshot", manifest.sha256
            )
        loaded = time.perf_counter()
        stats = gateway.collection_stats(collection)
        count = stats.points if stats else 0
        if count != manifest.point_count:
            with contextlib.suppress(Exception):
                gateway.delete_collection(collection)
            raise StorageFailure(
                f"Restored point count {count} does not match the manifest's "
                f"{manifest.point_count}; the collection was dropped again."
            )
    except RuntimeError as e:
        raise StorageFailure(f"Restore failed: {e}") from e
    finally:
        state.set_transitional(tenant_id, None)
    state.touch(tenant_id)
    timing = RestoreTiming(
        download_ms=_ms(started, downloaded),
        load_ms=_ms(downloaded, loaded),
        total_ms=_ms(started, loaded),
    )
    return timing, count


def _require_tenant(tenant_id: str) -> None:
    if deps.store().head_size(deps.tenant_meta_key(tenant_id)) is None:
        raise NotFound(f"Tenant {tenant_id} not found.")


async def restore_tenant(tenant_id: str) -> RestoreResult:
    validate_tenant_id(tenant_id)
    async with state.lock_for(tenant_id):
        await asyncio.to_thread(_require_tenant, tenant_id)
        if await asyncio.to_thread(is_hot, tenant_id):
            stats = await asyncio.to_thread(
                deps.gateway().collection_stats, deps.collection_name(tenant_id)
            )
            zero = RestoreTiming(download_ms=0.0, load_ms=0.0, total_ms=0.0)
            return RestoreResult(
                tenant_id=tenant_id, state="hot", timing=zero, point_count=stats.points if stats else 0
            )
        timing, count = await asyncio.to_thread(restore_locked, tenant_id)
    return RestoreResult(tenant_id=tenant_id, state="hot", timing=timing, point_count=count)


def _search(tenant_id: str, query: str, top_k: int) -> tuple[list[QueryHit], float]:
    started = time.perf_counter()
    vector = deps.embedder().embed_query(query)
    points = deps.gateway().search(deps.collection_name(tenant_id), vector, top_k)
    latency = _ms(started, time.perf_counter())
    hits = [QueryHit(doc=p.doc, chunk=p.chunk, score=p.score, text=p.text) for p in points]
    return hits, latency


async def query_tenant(tenant_id: str, request: QueryRequest) -> QueryResponse:
    """Answer a query, restoring the tenant from B2 first when it is parked."""
    validate_tenant_id(tenant_id)
    async with state.lock_for(tenant_id):
        await asyncio.to_thread(_require_tenant, tenant_id)
        restore = None
        if not await asyncio.to_thread(is_hot, tenant_id):
            restore, _ = await asyncio.to_thread(restore_locked, tenant_id)
        hits, latency = await asyncio.to_thread(_search, tenant_id, request.query, request.top_k)
        state.mark_query(tenant_id)
    return QueryResponse(
        hits=hits, latency_ms=latency, restored=restore is not None, restore=restore
    )
