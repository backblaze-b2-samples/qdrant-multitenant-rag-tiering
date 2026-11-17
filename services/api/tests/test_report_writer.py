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
