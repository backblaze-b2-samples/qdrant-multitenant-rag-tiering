"""Library: the app's own objects, classified by tenant and kind."""

import pytest

from app.service import deps
from app.service.tiering import park_tenant
from tests.helpers import GARDEN_DOCS, create_tenant


@pytest.mark.asyncio
async def test_library_groups_by_tenant_and_kind(client, rag):
    await create_tenant(client, "acme-legal")
    await create_tenant(client, "green-garden", docs=GARDEN_DOCS)
    await park_tenant("acme-legal")
    rag.store.put_bytes(deps.report_key("run-1"), b"{}", "application/json")
    rag.store.put_bytes("unrelated/outside.txt", b"x", "text/plain")

    everything = (await client.get("/library")).json()
    kinds = {(e["tenant_id"], e["kind"]) for e in everything}
    assert ("acme-legal", "corpus") in kinds
    assert ("acme-legal", "snapshots") in kinds
    assert ("green-garden", "corpus") in kinds
    assert (None, "reports") in kinds
    assert not [e for e in everything if e["key"].startswith("unrelated/")]

    snapshots = (await client.get("/library", params={"tenant_id": "acme-legal", "kind": "snapshots"})).json()
    assert snapshots and all(e["kind"] == "snapshots" and e["tenant_id"] == "acme-legal" for e in snapshots)
    assert any(e["key"].endswith("/latest.json") for e in snapshots)


@pytest.mark.asyncio
async def test_library_rejects_unknown_kind_and_bad_tenant(client):
    assert (await client.get("/library", params={"kind": "models"})).status_code == 422
    assert (await client.get("/library", params={"tenant_id": "Bad_ID"})).status_code == 400
