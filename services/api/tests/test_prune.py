"""Snapshot pruning: opt-in twice, never deletes the manifest's target."""

import pytest

from app.config import settings
from app.service import deps
from app.service.restore import restore_tenant
from app.service.tiering import park_tenant
from app.types.tiering import SnapshotManifest
from tests.helpers import create_tenant

T = "acme-legal"


async def _three_snapshots(client):
    await create_tenant(client, T)
    keys = []
    for _ in range(3):
        keys.append((await park_tenant(T)).manifest.snapshot_key)
        await restore_tenant(T)
    return keys


@pytest.mark.asyncio
async def test_prune_disabled_returns_409_and_deletes_nothing(client, rag, monkeypatch):
    monkeypatch.setattr(settings, "snapshot_prune_enabled", False)
    keys = await _three_snapshots(client)

    response = await client.post("/snapshots/prune", json={"keep_last": 1, "apply": True})

    assert response.status_code == 409
    assert all(k in rag.store.objects for k in keys)


@pytest.mark.asyncio
async def test_prune_without_apply_is_a_dry_run(client, rag, monkeypatch):
    monkeypatch.setattr(settings, "snapshot_prune_enabled", True)
    keys = await _three_snapshots(client)

    body = (await client.post("/snapshots/prune", json={"keep_last": 1})).json()

    assert body["applied"] is False
    assert sorted(body["candidates"]) == sorted(keys[:2])
    assert body["deleted"] == []
    assert all(k in rag.store.objects for k in keys)


@pytest.mark.asyncio
async def test_prune_never_deletes_the_latest_target(client, rag, monkeypatch):
    monkeypatch.setattr(settings, "snapshot_prune_enabled", True)
    keys = await _three_snapshots(client)
    # Point latest.json at the OLDEST snapshot: it must survive keep_last=1.
    oldest = await _manifest_for(rag, keys[0])
    rag.store.objects[deps.manifest_key(T)] = oldest

    body = (
        await client.post("/snapshots/prune", json={"keep_last": 1, "apply": True})
    ).json()

    assert body["applied"] is True
    assert keys[0] in rag.store.objects
    assert keys[0] not in body["deleted"]
    assert keys[2] in rag.store.objects  # newest kept by keep_last
    assert body["deleted"] == [keys[1]]


async def _manifest_for(rag, key):
    current = SnapshotManifest.model_validate_json(rag.store.objects[deps.manifest_key(T)])
    return current.model_copy(update={"snapshot_key": key}).model_dump_json().encode()
