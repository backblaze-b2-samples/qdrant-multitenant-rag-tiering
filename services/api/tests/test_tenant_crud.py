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


@pytest.mark.asyncio
async def test_tenant_list_reads_tenants_concurrently(client, rag, monkeypatch):
    """GET /tenants did one B2 round trip after another per tenant (5 s for 8
    tenants), so a refetch after seed or a sweep landed seconds late. Per-tenant
    reads must overlap: total time ~ one tenant's reads, not the sum."""
    import time

    for tenant_id in ("t-one", "t-two", "t-three", "t-four"):
        await create_tenant(client, tenant_id)
    for tenant_id in ("t-one", "t-two"):
        await park_tenant(tenant_id)

    original = rag.store.get_bytes

    def slow_get(key):
        time.sleep(0.2)  # one B2 round trip
        return original(key)

    monkeypatch.setattr(rag.store, "get_bytes", slow_get)

    started = time.perf_counter()
    response = await client.get("/tenants")
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    assert [t["tenant_id"] for t in response.json()] == ["t-four", "t-one", "t-three", "t-two"]
    # 6 sequential GETs (4 metas + 2 manifests) would take >= 1.2 s.
    assert elapsed < 0.8, elapsed


@pytest.mark.asyncio
async def test_create_reports_each_stage_in_order(client, rag, monkeypatch):
    """Like a park, a create sets its stage so the dialog can show progress."""
    from app.service import state

    seen: list[str | None] = []
    original = state.set_transitional

    def record(tenant_id, value):
        seen.append(value)
        original(tenant_id, value)

    monkeypatch.setattr(state, "set_transitional", record)

    detail = await create_tenant(client, "acme-legal")

    assert seen == ["writing", "embedding", "upserting", None]
    assert detail["state"] == "hot"


@pytest.mark.asyncio
async def test_failed_create_does_not_leave_a_stage_behind(client, rag, monkeypatch):
    from app.service import state

    def boom(*_args, **_kwargs):
        raise RuntimeError("embedder down")

    monkeypatch.setattr(rag.embedder, "embed", boom)
    response = await client.post(
        "/tenants",
        json={"tenant_id": "acme-legal", "display_name": "Acme", "documents": LEGAL_DOCS},
    )

    assert response.status_code >= 500
    assert state.transitional("acme-legal") is None


@pytest.mark.asyncio
async def test_edit_that_reindexes_ends_hot_not_mid_stage(client, rag):
    await create_tenant(client, "acme-legal")

    response = await client.patch(
        "/tenants/acme-legal",
        json={"add_documents": [{"filename": "extra.md", "text": "Extra clause text here."}]},
    )

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "hot"


@pytest.mark.asyncio
async def test_list_does_not_call_a_just_created_tenant_empty(client, rag, monkeypatch):
    """GET /tenants used to snapshot the collection names first and read each
    tenant later; a create that finished in between read as "Empty, 0 points".
    State and points must come from the same, per-tenant read."""
    await create_tenant(client, "acme-legal")
    # The collection snapshot predates the create finishing.
    monkeypatch.setattr(rag.gateway, "list_collections", lambda: [])

    row = (await client.get("/tenants")).json()[0]

    assert row["state"] == "hot"
    assert row["point_count"] > 0


@pytest.mark.asyncio
async def test_list_sees_a_park_that_finished_mid_listing(client, rag, monkeypatch):
    """Same race for a first park: the manifest listing predates it."""
    from app.service import tenant_reads

    await create_tenant(client, "acme-legal")
    await park_tenant("acme-legal")
    monkeypatch.setattr(tenant_reads, "parked_ids", lambda: set())

    row = (await client.get("/tenants")).json()[0]

    assert row["state"] == "parked"
    assert row["point_count"] > 0
