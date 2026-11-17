"""Tenant lifecycle: create (ingest), read, edit, delete.

A tenant is `rag/corpus/<tenant>/_tenant.json` plus its documents in B2, and
one Qdrant collection `tenant_<tenant>` while it is hot. Its state is derived
from what exists, never stored twice:

- hot:    the collection exists on the node
- parked: no collection, and `rag/snapshots/<tenant>/latest.json` exists
- empty:  metadata only (ingest failed or never ran); an edit that adds or
          re-indexes documents makes it hot
"""

import asyncio
import json
from datetime import UTC, datetime

from app.repo import snapshot_store
from app.service import deps, state
from app.service.errors import Conflict, InvalidInput, NotFound
from app.service.ingest import index_documents
from app.service.restore import restore_locked
from app.service.validation import validate_filename, validate_tenant_id
from app.types.tenants import (
    DeleteTenantResult,
    DocumentIn,
    DocumentInfo,
    TenantCreate,
    TenantDetail,
    TenantSummary,
    TenantUpdate,
)
from app.types.tiering import SnapshotManifest

__all__ = ["validate_filename", "validate_tenant_id"]

TEXT_TYPES = {"md": "text/markdown; charset=utf-8", "txt": "text/plain; charset=utf-8"}


# --- metadata ---------------------------------------------------------------


def read_meta(tenant_id: str) -> dict | None:
    raw = deps.store().get_bytes(deps.tenant_meta_key(tenant_id))
    return None if raw is None else json.loads(raw)


def write_meta(meta: dict) -> None:
    meta["updated_at"] = datetime.now(UTC).isoformat()
    deps.store().put_bytes(
        deps.tenant_meta_key(meta["tenant_id"]),
        json.dumps(meta, indent=2).encode(),
        "application/json",
    )


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


def _summary_fields(tenant_id: str, meta: dict, collections: set[str], manifest) -> dict:
    current = derive_state(tenant_id, collections, manifest is not None)
    points, vector_size = 0, 0
    stats = None
    if deps.collection_name(tenant_id) in collections:
        stats = deps.gateway().collection_stats(deps.collection_name(tenant_id))
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


def _manifest(tenant_id: str) -> SnapshotManifest | None:
    return snapshot_store.get_manifest(deps.store(), deps.manifest_key(tenant_id))


def list_tenants_sync() -> list[TenantSummary]:
    collections = set(deps.gateway().list_collections())
    with_manifest = parked_ids()
    summaries = []
    for tenant_id in list_tenant_ids():
        meta = read_meta(tenant_id)
        if meta is None:
            continue
        manifest = _manifest(tenant_id) if tenant_id in with_manifest else None
        summaries.append(TenantSummary(**_summary_fields(tenant_id, meta, collections, manifest)))
    return summaries


def detail_sync(tenant_id: str) -> TenantDetail:
    meta = read_meta(tenant_id)
    if meta is None:
        raise NotFound(f"Tenant {tenant_id} not found.")
    manifest = _manifest(tenant_id)
    collections = set(deps.gateway().list_collections())
    return TenantDetail(
        **_summary_fields(tenant_id, meta, collections, manifest),
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


async def get_tenant(tenant_id: str) -> TenantDetail:
    validate_tenant_id(tenant_id)
    return await asyncio.to_thread(detail_sync, tenant_id)


# --- writes -----------------------------------------------------------------


def _check_documents(documents: list[DocumentIn]) -> None:
    names = [d.filename for d in documents]
    for name in names:
        validate_filename(name)
    if len(set(names)) != len(names):
        raise InvalidInput("Document names must be unique within a tenant.")


def _store_documents(tenant_id: str, documents: list[DocumentIn]) -> dict[str, dict]:
    stored = {}
    for doc in documents:
        data = doc.text.encode("utf-8")
        key = deps.doc_key(tenant_id, doc.filename)
        deps.store().put_bytes(key, data, TEXT_TYPES[doc.filename.rsplit(".", 1)[1]])
        stored[doc.filename] = {
            "filename": doc.filename, "key": key, "size_bytes": len(data), "chunks": 0, "payload_bytes": 0,
        }
    return stored


def _index(tenant_id: str, entries: dict[str, dict], texts: list[tuple[str, str]]) -> None:
    stats = index_documents(
        deps.gateway(), deps.embedder(), tenant_id, deps.collection_name(tenant_id), texts
    )
    for filename, (chunks, payload) in stats.items():
        entries[filename].update(chunks=chunks, payload_bytes=payload)


def _create_sync(request: TenantCreate) -> TenantDetail:
    tenant_id = request.tenant_id
    if read_meta(tenant_id) is not None:
        raise Conflict(f"Tenant {tenant_id} already exists.")
    entries = _store_documents(tenant_id, request.documents)
    meta = {
        "tenant_id": tenant_id,
        "display_name": request.display_name,
        "created_at": datetime.now(UTC).isoformat(),
        "documents": list(entries.values()),
        "snapshot_stale": False,
    }
    # Metadata first: if indexing fails the tenant still exists, as "empty".
    write_meta(meta)
    _index(tenant_id, entries, [(d.filename, d.text) for d in request.documents])
    write_meta(meta)
    state.touch(tenant_id)
    return detail_sync(tenant_id)


async def create_tenant(request: TenantCreate) -> TenantDetail:
    validate_tenant_id(request.tenant_id)
    _check_documents(request.documents)
    async with state.lock_for(request.tenant_id):
        return await asyncio.to_thread(_create_sync, request)


def _update_sync(tenant_id: str, request: TenantUpdate) -> TenantDetail:
    meta = read_meta(tenant_id)
    if meta is None:
        raise NotFound(f"Tenant {tenant_id} not found.")
    entries = {d["filename"]: d for d in meta.get("documents", [])}
    missing = [n for n in request.remove_documents if n not in entries]
    if missing:
        raise InvalidInput(f"Not documents of this tenant: {', '.join(missing)}")
    if len(entries) - len(set(request.remove_documents)) + len(
        {d.filename for d in request.add_documents} - set(entries)
    ) < 1:
        raise InvalidInput("A tenant needs at least one document.")
    collection = deps.collection_name(tenant_id)
    gateway, store = deps.gateway(), deps.store()
    has_manifest = _manifest(tenant_id) is not None
    changes = bool(request.add_documents or request.remove_documents)
    hot = collection in gateway.list_collections()
    if changes and not hot and has_manifest:
        restore_locked(tenant_id)
        hot = True
    for name in request.remove_documents:
        if hot:
            gateway.delete_doc_points(collection, name)
        store.delete_keys([entries.pop(name)["key"]])
    texts = []
    if changes and not hot:  # empty tenant: index what it already has
        texts = [(n, (store.get_bytes(e["key"]) or b"").decode("utf-8")) for n, e in entries.items()]
    for doc in request.add_documents:
        if hot and doc.filename in entries:
            gateway.delete_doc_points(collection, doc.filename)
    entries.update(_store_documents(tenant_id, request.add_documents))
    texts += [(d.filename, d.text) for d in request.add_documents]
    if texts:
        _index(tenant_id, entries, texts)
    if request.display_name:
        meta["display_name"] = request.display_name
    meta["documents"] = list(entries.values())
    meta["snapshot_stale"] = bool(meta.get("snapshot_stale")) or (changes and has_manifest)
    write_meta(meta)
    state.touch(tenant_id)
    return detail_sync(tenant_id)


async def update_tenant(tenant_id: str, request: TenantUpdate) -> TenantDetail:
    validate_tenant_id(tenant_id)
    _check_documents(request.add_documents)
    async with state.lock_for(tenant_id):
        return await asyncio.to_thread(_update_sync, tenant_id, request)


def _delete_sync(tenant_id: str) -> DeleteTenantResult:
    if read_meta(tenant_id) is None:
        raise NotFound(f"Tenant {tenant_id} not found.")
    collection = deps.collection_name(tenant_id)
    gateway, store = deps.gateway(), deps.store()
    dropped = collection in gateway.list_collections() and gateway.delete_collection(collection)
    deleted = snapshot_store.delete_prefix(store, deps.snapshot_prefix(tenant_id))
    # Corpus last: the tenant stays listed until everything else is gone.
    deleted += snapshot_store.delete_prefix(store, deps.corpus_prefix(tenant_id))
    state.forget(tenant_id)
    return DeleteTenantResult(deleted_keys=deleted, collection_dropped=bool(dropped))


async def delete_tenant(tenant_id: str, confirm: str) -> DeleteTenantResult:
    validate_tenant_id(tenant_id)
    if confirm != tenant_id:
        raise InvalidInput("Type the tenant id exactly to confirm deletion.")
    async with state.lock_for(tenant_id):
        return await asyncio.to_thread(_delete_sync, tenant_id)
