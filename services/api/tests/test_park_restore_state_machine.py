"""The park state machine: verify-before-drop, manifest-last, restore on query."""

import asyncio

import pytest

from app.service import deps
from app.service.restore import query_tenant, restore_tenant
from app.service.tiering import park_tenant
from app.types.tenants import QueryRequest
from tests.helpers import create_tenant

T = "acme-legal"
COLL = "tenant_acme-legal"


def _snapshot_objects(store):
    return [k for k in store.objects if k.endswith(".snapshot")]


@pytest.mark.asyncio
async def test_park_succeeds_only_after_verification(client, rag):
    await create_tenant(client, T)

    result = await park_tenant(T)

    assert result.verified is True
    assert result.state == "parked"
    assert result.manifest is not None
    assert COLL not in rag.gateway.collections
    assert rag.gateway.node_snapshots == {}  # node-local snapshot file removed
    stored = rag.store.objects[result.manifest.snapshot_key]
    assert len(stored) == result.manifest.size_bytes
    # The collection is only dropped after the manifest exists in B2.
    manifest_put = rag.store.events.index(("put", deps.manifest_key(T)))
    assert manifest_put >= 0
    detail = (await client.get(f"/tenants/{T}")).json()
    assert detail["state"] == "parked"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fault", "reason_word"),
    [("upload", "upload"), ("size", "size"), ("checksum", "checksum")],
)
async def test_failed_park_leaves_tenant_hot_without_new_manifest(
    client, rag, fault, reason_word
):
    await create_tenant(client, T)
    if fault == "upload":
        rag.store.fail_upload_part = True
    else:
        rag.store.corrupt_after_complete = fault

    result = await park_tenant(T)

    assert result.verified is False
    assert result.state == "hot"
    assert reason_word in (result.reason or "").lower()
    assert COLL in rag.gateway.collections
    assert deps.manifest_key(T) not in rag.store.objects
    assert _snapshot_objects(rag.store) == []  # unverified object not kept
    detail = (await client.get(f"/tenants/{T}")).json()
    assert detail["state"] == "hot"


@pytest.mark.asyncio
async def test_failed_park_keeps_previous_good_manifest(client, rag):
    await create_tenant(client, T)
    first = await park_tenant(T)
    await restore_tenant(T)
    previous = rag.store.objects[deps.manifest_key(T)]

    rag.store.corrupt_after_complete = "checksum"
    second = await park_tenant(T)

    assert second.verified is False
    assert rag.store.objects[deps.manifest_key(T)] == previous
    assert first.manifest.snapshot_key in rag.store.objects


@pytest.mark.asyncio
async def test_restore_loads_snapshot_and_checks_point_count(client, rag):
    created = await create_tenant(client, T)
    await park_tenant(T)

    result = await restore_tenant(T)

    assert result.state == "hot"
    assert result.point_count == created["point_count"]
    assert result.timing.total_ms >= result.timing.load_ms >= 0
    assert ("restore", COLL) in rag.gateway.events


@pytest.mark.asyncio
async def test_restore_rejects_point_count_mismatch(client, rag):
    await create_tenant(client, T)
    parked = await park_tenant(T)
    tampered = parked.manifest.model_copy(update={"point_count": 999})
    rag.store.objects[deps.manifest_key(T)] = tampered.model_dump_json().encode()

    response = await client.post(f"/tenants/{T}/restore")

    assert response.status_code == 502
    assert "point count" in response.json()["detail"].lower()
    assert COLL not in rag.gateway.collections


@pytest.mark.asyncio
async def test_restore_rejects_other_embedding_model(client, rag):
    await create_tenant(client, T)
    await park_tenant(T)
    rag.embedder.model_name = "fake/other-model"

    response = await client.post(f"/tenants/{T}/restore")

    assert response.status_code == 409
    assert "embedding model" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_query_on_parked_tenant_restores_first(client, rag):
    await create_tenant(client, T)
    warm = await query_tenant(T, QueryRequest(query="indemnity clause", top_k=3))
    await park_tenant(T)

    after = await query_tenant(T, QueryRequest(query="indemnity clause", top_k=3))

    assert warm.restored is False and warm.restore is None
    assert after.restored is True and after.restore is not None
    assert [(h.doc, h.chunk) for h in after.hits] == [(h.doc, h.chunk) for h in warm.hits]
    assert after.hits[0].doc == "contracts.md"


@pytest.mark.asyncio
async def test_concurrent_query_during_park_waits_on_the_lock(client, rag):
    await create_tenant(client, T)
    rag.gateway.delay_snapshot = 0.3

    park_task = asyncio.create_task(park_tenant(T))
    await asyncio.sleep(0.05)  # park now holds the tenant lock
    query = await query_tenant(T, QueryRequest(query="notice period", top_k=2))
    parked = await park_task

    assert parked.verified is True
    assert query.restored is True
    events = rag.gateway.events
    assert events.index(("delete_collection", COLL)) < events.index(("restore", COLL))
    last_search = max(i for i, event in enumerate(events) if event == ("search", COLL))
    assert events.index(("restore", COLL)) < last_search
