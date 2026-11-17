"""Tenant reads: metadata, derived state, the tenants list and the detail.

Split from `tenants.py` (the lifecycle writes) to keep both under the
300-line ceiling; `tenants` re-exports these names.
"""

import json
from concurrent.futures import ThreadPoolExecutor

from app.repo import snapshot_store
from app.service import deps, state
from app.service.errors import NotFound
from app.service.validation import validate_tenant_id
from app.types.tenants import DocumentInfo, TenantDetail, TenantProgress, TenantSummary
from app.types.tiering import SnapshotManifest

# Per-tenant reads in GET /tenants are independent B2 round trips; overlapping
# them keeps the list (and every refetch after seed, park or a sweep) at about
# one round trip instead of one per tenant.
LIST_READ_WORKERS = 8


def read_meta(tenant_id: str) -> dict | None:
    raw = deps.store().get_bytes(deps.tenant_meta_key(tenant_id))
    return None if raw is None else json.loads(raw)


def payload_total(meta: dict | None) -> int:
    return sum(d.get("payload_bytes", 0) for d in (meta or {}).get("documents", []))


def list_tenant_ids() -> list[str]:
    root = deps.corpus_root()
    ids = []
    for entry in deps.store().list_objects(root):
        parts = entry.key[len(root) :].split("/")
        if len(parts) == 2 and parts[1] == deps.TENANT_META:
            ids.append(parts[0])
    return sorted(ids)


def parked_ids() -> set[str]:
    """Tenants that have a manifest in B2 (one listing, not one GET per tenant)."""
    root = deps.snapshots_root()
    return {
        e.key[len(root) :].split("/")[0]
        for e in deps.store().list_objects(root)
        if e.key.endswith("/" + deps.MANIFEST)
    }


def derive_state(tenant_id: str, collections: set[str], has_manifest: bool) -> str:
    transitional = state.transitional(tenant_id)
    if transitional:
        return transitional
    if deps.collection_name(tenant_id) in collections:
        return "hot"
    return "parked" if has_manifest else "empty"


def _summary_fields(tenant_id: str, meta: dict, manifest, recheck_manifest: bool = False) -> dict:
    """State and figures from one per-tenant read, never a list-wide snapshot.

    The in-flight stage is read BEFORE the node: an operation that finishes in
    between then shows its end state (hot / parked), not a stale "empty".
    """
    transitional = state.transitional(tenant_id)
    stats = deps.gateway().collection_stats(deps.collection_name(tenant_id))
    if stats is None and manifest is None and recheck_manifest:
        manifest = read_manifest(tenant_id)  # a first park may postdate the listing
    current = transitional or ("hot" if stats else "parked" if manifest else "empty")
    points, vector_size = 0, 0
    if stats is not None:
        points, vector_size = stats.points, stats.vector_size
    elif manifest is not None:
        points, vector_size = manifest.point_count, manifest.vector_size
    return {
        "tenant_id": tenant_id,
        "display_name": meta.get("display_name", tenant_id),
        "state": current,
        "point_count": points,
        "document_count": len(meta.get("documents", [])),
        "vector_bytes_estimate": points * vector_size * 4 + payload_total(meta) if points else 0,
        "last_query_at": state.last_query_at(tenant_id),
        "snapshot_size_bytes": manifest.size_bytes if manifest else None,
        "snapshot_created_at": manifest.created_at if manifest else None,
    }


def read_manifest(tenant_id: str) -> SnapshotManifest | None:
    return snapshot_store.get_manifest(deps.store(), deps.manifest_key(tenant_id))


def list_tenants_sync() -> list[TenantSummary]:
    with_manifest = parked_ids()

    def summary(tenant_id: str) -> TenantSummary | None:
        meta = read_meta(tenant_id)
        if meta is None:
            return None
        listed = tenant_id in with_manifest
        manifest = read_manifest(tenant_id) if listed else None
        return TenantSummary(**_summary_fields(tenant_id, meta, manifest, not listed))

    with ThreadPoolExecutor(max_workers=LIST_READ_WORKERS) as pool:
        summaries = list(pool.map(summary, list_tenant_ids()))
    return [s for s in summaries if s is not None]


def detail_sync(tenant_id: str) -> TenantDetail:
    meta = read_meta(tenant_id)
    if meta is None:
        raise NotFound(f"Tenant {tenant_id} not found.")
    manifest = read_manifest(tenant_id)
    return TenantDetail(
        **_summary_fields(tenant_id, meta, manifest),
        created_at=meta["created_at"],
        documents=[
            DocumentInfo(
                filename=d["filename"], key=d["key"], size_bytes=d["size_bytes"], chunks=d["chunks"]
            )
            for d in meta.get("documents", [])
        ],
        manifest=manifest,
        snapshot_stale=bool(meta.get("snapshot_stale")) and manifest is not None,
    )


def get_progress(tenant_id: str) -> TenantProgress:
    """The stage and count in flight, cheap enough to poll every half second."""
    validate_tenant_id(tenant_id)
    done, total = state.progress(tenant_id) or (None, None)
    return TenantProgress(
        tenant_id=tenant_id, state=state.transitional(tenant_id), done=done, total=total
    )
