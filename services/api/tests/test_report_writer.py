"""Latency report: statistics, result comparison and the report.json writer."""

import json

import pytest

from app.service import deps
from app.service.reports import latency_stats, results_match
from app.types.tenants import QueryHit
from tests.helpers import GARDEN_DOCS, create_tenant


def test_latency_stats_nearest_rank():
    stats = latency_stats([5.0, 1.0, 3.0, 2.0, 4.0, 10.0, 6.0, 7.0, 8.0, 9.0])
    assert stats.n == 10
    assert stats.p50_ms == 5.0
    assert stats.p95_ms == 10.0
    assert stats.mean_ms == 5.5


def test_latency_stats_empty():
    stats = latency_stats([])
    assert stats.n == 0 and stats.p50_ms == 0.0


def _hit(doc, chunk, score):
    return QueryHit(doc=doc, chunk=chunk, score=score, text="")


def test_results_match_tolerance():
    a = [[_hit("a.md", 0, 0.91), _hit("b.md", 1, 0.5)]]
    assert results_match(a, [[_hit("a.md", 0, 0.91005), _hit("b.md", 1, 0.5)]])
    assert not results_match(a, [[_hit("a.md", 0, 0.9102), _hit("b.md", 1, 0.5)]])
    assert not results_match(a, [[_hit("b.md", 1, 0.5), _hit("a.md", 0, 0.91)]])


@pytest.mark.asyncio
async def test_benchmark_writes_report_json(client, rag):
    await create_tenant(client, "acme-legal")
    await create_tenant(client, "green-garden", docs=GARDEN_DOCS)

    response = await client.post(
        "/reports", json={"tenant_ids": ["acme-legal", "green-garden"], "queries_per_phase": 5}
    )

    assert response.status_code == 200, response.text
    report = response.json()
    key = deps.report_key(report["run_id"])
    stored = json.loads(rag.store.objects[key])
    assert stored["run_id"] == report["run_id"]
    assert len(stored["tenants"]) == 2
    first = stored["tenants"][0]
    assert first["warm"]["n"] == 5 and first["post_restore"]["n"] == 5
    assert first["results_match"] is True
    assert first["snapshot_bytes"] > 0
    assert first["restore"]["total_ms"] >= 0
    assert first["memory_freed"]["vector_bytes_estimate"] > 0
    assert first["memory_freed"]["node_rss_delta_bytes"] is not None
    # The benchmark leaves every tenant hot again.
    assert "tenant_acme-legal" in rag.gateway.collections

    listing = (await client.get("/reports")).json()
    assert listing[0]["run_id"] == report["run_id"]
    assert listing[0]["tenant_count"] == 2
    again = (await client.get(f"/reports/{report['run_id']}")).json()
    assert again == report


@pytest.mark.asyncio
async def test_unknown_report_is_404(client):
    assert (await client.get("/reports/nope-123")).status_code == 404


@pytest.mark.asyncio
async def test_benchmark_rejects_unknown_tenant(client):
    response = await client.post("/reports", json={"tenant_ids": ["ghost-tenant"]})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_benchmark_progress_tracks_phase_and_tenant(client, rag, monkeypatch):
    """A running benchmark is visible (phase, tenant, n of N), even after a reload."""
    from app.service import reports

    await create_tenant(client, "acme-legal")
    assert (await client.get("/reports/progress")).json()["running"] is False

    seen = []
    original_park = reports.park_tenant

    async def park_and_record(tenant_id, *args, **kwargs):
        seen.append((await client.get("/reports/progress")).json())
        return await original_park(tenant_id, *args, **kwargs)

    monkeypatch.setattr(reports, "park_tenant", park_and_record)

    response = await client.post(
        "/reports", json={"tenant_ids": ["acme-legal"], "queries_per_phase": 5}
    )

    assert response.status_code == 200, response.text
    assert seen[0]["running"] is True
    assert seen[0]["phase"] == "park"
    assert seen[0]["tenant_id"] == "acme-legal"
    assert seen[0]["tenants_done"] == 0 and seen[0]["tenants_total"] == 1
    # A reloaded page shows the run's own tenant set, not its default selection.
    assert seen[0]["tenant_ids"] == ["acme-legal"]
    done = (await client.get("/reports/progress")).json()
    assert done["running"] is False
    # A tab that only watched the progress can open the report it produced.
    assert done["last_run_id"] == response.json()["run_id"]
    assert seen[0]["last_run_id"] is None


@pytest.mark.asyncio
async def test_benchmark_progress_clears_after_failure(client, rag):
    response = await client.post("/reports", json={"tenant_ids": ["ghost-tenant"]})
    assert response.status_code == 404
    assert (await client.get("/reports/progress")).json()["running"] is False


@pytest.mark.asyncio
async def test_report_list_reads_reports_concurrently(client, rag, monkeypatch):
    """GET /reports read every report.json one after another, so the list
    refetched after a run landed seconds after the "finished" toast."""
    import time

    from app.service.reports import write_report
    from app.types.reports import LatencyReport

    for n in range(4):
        write_report(LatencyReport(
            run_id=f"20261117-12000{n}-abcdef", created_at=f"2026-11-17T12:00:0{n}Z",
            qdrant_version=None, embedding_model="m", tenants=[],
        ))
    original = rag.store.get_bytes

    def slow_get(key):
        time.sleep(0.2)  # one B2 round trip
        return original(key)

    monkeypatch.setattr(rag.store, "get_bytes", slow_get)

    started = time.perf_counter()
    listing = (await client.get("/reports")).json()
    elapsed = time.perf_counter() - started

    assert listing[0]["run_id"] == "20261117-120003-abcdef"
    assert elapsed < 0.5, elapsed  # sequential would be >= 0.8 s
