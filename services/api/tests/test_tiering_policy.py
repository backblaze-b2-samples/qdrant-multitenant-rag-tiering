"""Idle selection and the policy sweep."""

import pytest

from app.service import deps, state
from app.service.tiering import park_tenant, select_candidates
from tests.helpers import GARDEN_DOCS, create_tenant

NOW = 10_000.0


def test_select_candidates_threshold_edges():
    states = {"a": "hot", "b": "hot", "c": "hot"}
    activity = {"a": NOW - 60, "b": NOW - 59.9, "c": NOW - 3600}

    assert select_candidates(states, activity, idle_seconds=60, now=NOW) == ["a", "c"]


def test_select_candidates_skips_empty_and_parked():
    states = {"hot-one": "hot", "parked-one": "parked", "empty-one": "empty"}
    activity = dict.fromkeys(states, 0.0)

    assert select_candidates(states, activity, idle_seconds=1, now=NOW) == ["hot-one"]


def test_select_candidates_skips_transitional_states():
    states = {"x": "snapshotting", "y": "restoring", "z": "hot"}
    activity = dict.fromkeys(states, 0.0)

    assert select_candidates(states, activity, idle_seconds=1, now=NOW) == ["z"]


def test_idle_clock_defaults_to_startup():
    state.reset(started_at=NOW - 30)
    assert state.last_activity("never-touched") == NOW - 30


@pytest.mark.asyncio
async def test_dry_run_parks_nothing(client, rag):
    await create_tenant(client, "acme-legal")
    state.touch("acme-legal", when=0.0)

    response = await client.post("/tiering/run", json={"idle_seconds": 30})

    body = response.json()
    assert response.status_code == 200
    assert body["dry_run"] is True
    assert body["candidates"] == ["acme-legal"]
    assert body["parked"] == []
    assert "tenant_acme-legal" in rag.gateway.collections
    assert deps.manifest_key("acme-legal") not in rag.store.objects


@pytest.mark.asyncio
async def test_run_parks_only_idle_tenants(client, rag):
    await create_tenant(client, "acme-legal")
    await create_tenant(client, "green-garden", docs=GARDEN_DOCS)
    state.touch("acme-legal", when=0.0)  # idle for a very long time
    await client.post("/tenants/green-garden/query", json={"query": "tomatoes"})

    response = await client.post(
        "/tiering/run", json={"idle_seconds": 300, "dry_run": False}
    )

    body = response.json()
    assert body["candidates"] == ["acme-legal"]
    assert body["parked"] == ["acme-legal"]
    assert body["skipped"] == []
    assert "tenant_acme-legal" not in rag.gateway.collections
    assert "tenant_green-garden" in rag.gateway.collections


@pytest.mark.asyncio
async def test_run_reports_failed_park_under_skipped(client, rag):
    await create_tenant(client, "acme-legal")
    state.touch("acme-legal", when=0.0)
    rag.store.fail_upload_part = True

    body = (
        await client.post("/tiering/run", json={"idle_seconds": 1, "dry_run": False})
    ).json()

    assert body["parked"] == []
    assert body["skipped"][0]["tenant_id"] == "acme-legal"
    assert "upload" in body["skipped"][0]["reason"].lower()


@pytest.mark.asyncio
async def test_stats_split_hot_and_parked(client, rag):
    await create_tenant(client, "acme-legal")
    await create_tenant(client, "green-garden", docs=GARDEN_DOCS)
    await park_tenant("acme-legal")

    stats = (await client.get("/tiering/stats")).json()

    assert stats["hot"] == 1 and stats["parked"] == 1 and stats["empty"] == 0
    assert stats["vector_bytes_hot"] > 0
    assert stats["vector_bytes_freed"] > 0
    assert stats["snapshot_bytes_b2"] > 0
    assert stats["corpus_bytes_b2"] > 0


@pytest.mark.asyncio
async def test_policy_reports_configuration(client):
    body = (await client.get("/tiering/policy")).json()
    assert set(body) == {"idle_seconds", "sweep_interval_seconds", "prune_enabled"}
