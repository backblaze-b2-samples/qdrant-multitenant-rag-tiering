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
from app.service.tenant_reads import (
    derive_state,
    detail_sync,
    get_progress,
    list_tenant_ids,
    list_tenants_sync,
    parked_ids,
    payload_total,
    read_manifest,
    read_meta,
)
from app.service.validation import validate_filename, validate_tenant_id
from app.types.tenants import (
    DeleteTenantResult,
    DocumentIn,
    TenantCreate,
    TenantDetail,
    TenantUpdate,
)

# The read side lives in `tenant_reads`; re-exported so callers keep one module.
__all__ = [
    "derive_state", "detail_sync", "get_progress", "list_tenant_ids", "list_tenants_sync", "parked_ids",
    "payload_total", "read_meta", "validate_filename", "validate_tenant_id",
]

TEXT_TYPES = {"md": "text/markdown; charset=utf-8", "txt": "text/plain; charset=utf-8"}


# --- metadata ---------------------------------------------------------------


def write_meta(meta: dict) -> None:
    meta["updated_at"] = datetime.now(UTC).isoformat()
    deps.store().put_bytes(
        deps.tenant_meta_key(meta["tenant_id"]),
        json.dumps(meta, indent=2).encode(),
        "application/json",
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
    for done, doc in enumerate(documents):
        state.set_progress(tenant_id, done, len(documents))
        data = doc.text.encode("utf-8")
        key = deps.doc_key(tenant_id, doc.filename)
        deps.store().put_bytes(key, data, TEXT_TYPES[doc.filename.rsplit(".", 1)[1]])
        stored[doc.filename] = {
            "filename": doc.filename, "key": key, "size_bytes": len(data), "chunks": 0, "payload_bytes": 0,
        }
    return stored


def _report(tenant_id: str, stage: str, done: int, total: int) -> None:
    if state.transitional(tenant_id) != stage:
        state.set_transitional(tenant_id, stage)
    state.set_progress(tenant_id, done, total)


def _index(tenant_id: str, entries: dict[str, dict], texts: list[tuple[str, str]]) -> None:
    stats = index_documents(
        deps.gateway(), deps.embedder(), tenant_id, deps.collection_name(tenant_id), texts,
        on_progress=lambda stage, done, total: _report(tenant_id, stage, done, total),
    )
    for filename, (chunks, payload) in stats.items():
        entries[filename].update(chunks=chunks, payload_bytes=payload)


def _create_sync(request: TenantCreate) -> TenantDetail:
    tenant_id = request.tenant_id
    if read_meta(tenant_id) is not None:
        raise Conflict(f"Tenant {tenant_id} already exists.")
    # Stages (writing, embedding, upserting) are polled by the create dialog.
    state.set_transitional(tenant_id, "writing")
    try:
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
    finally:
        state.set_transitional(tenant_id, None)
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
    has_manifest = read_manifest(tenant_id) is not None
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
        try:
            _index(tenant_id, entries, texts)
        finally:
            state.set_transitional(tenant_id, None)
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
