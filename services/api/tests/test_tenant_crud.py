"""Tenant create / read / edit / delete through the HTTP API."""

import pytest

from app.service import deps
from app.service.tiering import park_tenant
from tests.helpers import GARDEN_DOCS, LEGAL_DOCS, create_tenant

T = "acme-legal"


@pytest.mark.asyncio
async def test_create_stores_corpus_in_b2_and_indexes_it(client, rag):
    body = await create_tenant(client, T)

    assert body["state"] == "hot"
    assert body["point_count"] >= 2
    assert {d["filename"] for d in body["documents"]} == {"contracts.md", "privacy.txt"}
    assert f"{deps.corpus_prefix(T)}contracts.md" in rag.store.objects
    assert f"{deps.corpus_prefix(T)}_tenant.json" in rag.store.objects
    assert len(rag.gateway.collections["tenant_acme-legal"]) == body["point_count"]


@pytest.mark.asyncio
async def test_create_duplicate_returns_409(client):
    await create_tenant(client, T)
    response = await client.post(
        "/tenants", json={"tenant_id": T, "display_name": "x", "documents": LEGAL_DOCS}
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_list_derives_state(client):
    await create_tenant(client, T)
    await create_tenant(client, "green-garden", docs=GARDEN_DOCS)
    await park_tenant(T)

    listing = {t["tenant_id"]: t for t in (await client.get("/tenants")).json()}

    assert listing[T]["state"] == "parked"
    assert listing[T]["snapshot_size_bytes"] > 0
    assert listing["green-garden"]["state"] == "hot"


@pytest.mark.asyncio
async def test_edit_renames_adds_and_removes_documents(client, rag):
    await create_tenant(client, T)

    response = await client.patch(
        f"/tenants/{T}",
        json={
            "display_name": "Acme Legal EU",
            "add_documents": [{"filename": "gdpr.md", "text": "Fines reach four percent."}],
            "remove_documents": ["privacy.txt"],
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["display_name"] == "Acme Legal EU"
    assert {d["filename"] for d in body["documents"]} == {"contracts.md", "gdpr.md"}
    assert f"{deps.corpus_prefix(T)}privacy.txt" not in rag.store.objects
    docs = {p.doc for p in rag.gateway.collections["tenant_acme-legal"].values()}
    assert docs == {"contracts.md", "gdpr.md"}


@pytest.mark.asyncio
async def test_edit_parked_tenant_restores_and_marks_snapshot_stale(client, rag):
    await create_tenant(client, T)
    await park_tenant(T)

    body = (
        await client.patch(f"/tenants/{T}", json={"remove_documents": ["privacy.txt"]})
    ).json()

    assert body["state"] == "hot"
    assert body["snapshot_stale"] is True


@pytest.mark.asyncio
async def test_delete_requires_typed_confirmation(client, rag):
    await create_tenant(client, T)

    response = await client.delete(f"/tenants/{T}", params={"confirm": "wrong"})

    assert response.status_code == 400
    assert f"{deps.corpus_prefix(T)}_tenant.json" in rag.store.objects
    assert "tenant_acme-legal" in rag.gateway.collections


@pytest.mark.asyncio
async def test_delete_removes_only_that_tenants_objects(client, rag):
    await create_tenant(client, T)
    await create_tenant(client, "green-garden", docs=GARDEN_DOCS)
    await park_tenant(T)
    report_key = deps.report_key("run-1")
    rag.store.put_bytes(report_key, b"{}", "application/json")

    response = await client.delete(f"/tenants/{T}", params={"confirm": T})

    body = response.json()
    assert response.status_code == 200
    assert all(k.startswith((deps.corpus_prefix(T), deps.snapshot_prefix(T))) for k in body["deleted_keys"])
    assert not [k for k in rag.store.objects if f"/{T}/" in k]
    assert report_key in rag.store.objects
    assert f"{deps.corpus_prefix('green-garden')}_tenant.json" in rag.store.objects
    assert (await client.get(f"/tenants/{T}")).status_code == 404


@pytest.mark.asyncio
async def test_query_returns_timed_hits(client):
    await create_tenant(client, T)

    body = (
        await client.post(f"/tenants/{T}/query", json={"query": "data retention", "top_k": 1})
    ).json()

    assert body["latency_ms"] >= 0
    assert body["hits"][0]["doc"] == "privacy.txt"
    assert body["restored"] is False


@pytest.mark.asyncio
async def test_seed_creates_distinct_tenants_and_skips_existing(client):
    first = (await client.post("/tenants/seed", json={"tenant_count": 2})).json()
    second = (await client.post("/tenants/seed", json={"tenant_count": 2})).json()

    assert len(first["created"]) == 2 and first["skipped"] == []
    assert second["created"] == [] and sorted(second["skipped"]) == sorted(first["created"])
