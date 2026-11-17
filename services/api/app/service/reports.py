"""Latency benchmark: warm, park, restore-on-query, post-restore, per tenant.

For each tenant the same probe queries run warm, then the tenant is parked
through the real state machine, the first query restores it from B2, and the
probes run again. Hit ids and scores are compared (tolerance 1e-4) and the
whole run is written to `rag/reports/<run-id>/report.json`.
"""

import asyncio
import json
import math
import re
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from app.service import deps, tenants
from app.service.errors import Conflict, NotFound, StorageFailure
from app.service.restore import query_tenant
from app.service.tenant_reads import LIST_READ_WORKERS
from app.service.tiering import park_tenant
from app.service.validation import validate_run_id, validate_tenant_id
from app.types.reports import (
    BenchmarkProgress,
    BenchmarkRequest,
    LatencyReport,
    LatencyStats,
    MemoryFreed,
    ReportSummary,
    TenantLatency,
)
from app.types.tenants import QueryHit, QueryRequest

SCORE_TOLERANCE = 1e-4
TOP_K = 5

# The benchmark in flight, so a reloaded Reports page can show it. In-memory:
# it is lost on restart, like the run it describes.
_progress = BenchmarkProgress(running=False)


def get_progress() -> BenchmarkProgress:
    return _progress


def _set_progress(**changes) -> None:
    global _progress
    _progress = _progress.model_copy(update=changes)


def latency_stats(samples: list[float]) -> LatencyStats:
    """Nearest-rank percentiles, so every reported figure is a real sample."""
    if not samples:
        return LatencyStats(n=0, p50_ms=0.0, p95_ms=0.0, mean_ms=0.0)
    ordered = sorted(samples)

    def rank(q: float) -> float:
        return ordered[max(0, math.ceil(q * len(ordered)) - 1)]

    return LatencyStats(
        n=len(ordered),
        p50_ms=round(rank(0.50), 3),
        p95_ms=round(rank(0.95), 3),
        mean_ms=round(sum(ordered) / len(ordered), 3),
    )


def results_match(
    before: list[list[QueryHit]], after: list[list[QueryHit]], tolerance: float = SCORE_TOLERANCE
) -> bool:
    if len(before) != len(after):
        return False
    for hits_a, hits_b in zip(before, after, strict=True):
        if [(h.doc, h.chunk) for h in hits_a] != [(h.doc, h.chunk) for h in hits_b]:
            return False
        if any(abs(a.score - b.score) > tolerance for a, b in zip(hits_a, hits_b, strict=True)):
            return False
    return True


def probe_queries(tenant_id: str, count: int) -> list[str]:
    """Fixed probes from the tenant's own corpus: its sentences, in document order."""
    meta = tenants.read_meta(tenant_id)
    if meta is None:
        raise NotFound(f"Tenant {tenant_id} not found.")
    sentences: list[str] = []
    for doc in meta.get("documents", []):
        raw = deps.store().get_bytes(doc["key"]) or b""
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", raw.decode("utf-8", "replace")):
            cleaned = sentence.strip(" #*-\t")
            if len(cleaned.split()) >= 3 and cleaned not in sentences:
                sentences.append(cleaned)
    if not sentences:
        sentences = [meta.get("display_name", tenant_id)]
    return [sentences[i % len(sentences)] for i in range(count)]


async def _run_phase(tenant_id: str, probes: list[str]) -> tuple[list[list[QueryHit]], list[float]]:
    hits, latencies = [], []
    for probe in probes:
        response = await query_tenant(tenant_id, QueryRequest(query=probe, top_k=TOP_K))
        hits.append(response.hits)
        latencies.append(response.latency_ms)
    return hits, latencies


async def _bench_tenant(tenant_id: str, count: int) -> TenantLatency:
    _set_progress(phase="warm", tenant_id=tenant_id)  # probe reads count as warm-up
    probes = await asyncio.to_thread(probe_queries, tenant_id, count)
    # Warm-up: makes the tenant hot (restoring it if it was parked) and pays the
    # first-call cost of the embedder, so the warm phase measures steady state.
    await query_tenant(tenant_id, QueryRequest(query=probes[0], top_k=TOP_K))
    warm_hits, warm_ms = await _run_phase(tenant_id, probes)

    _set_progress(phase="park")
    parked = await park_tenant(tenant_id)
    if not parked.verified or parked.manifest is None:
        raise Conflict(f"Could not park {tenant_id}: {parked.reason}")

    _set_progress(phase="restore")
    started = time.perf_counter()
    first = await query_tenant(tenant_id, QueryRequest(query=probes[0], top_k=TOP_K))
    first_ms = round((time.perf_counter() - started) * 1000, 3)
    if first.restore is None:
        raise StorageFailure(f"{tenant_id} answered without restoring after park")

    _set_progress(phase="post_restore")
    post_hits, post_ms = await _run_phase(tenant_id, probes)
    return TenantLatency(
        tenant_id=tenant_id,
        point_count=parked.manifest.point_count,
        warm=latency_stats(warm_ms),
        snapshot_bytes=parked.manifest.size_bytes,
        snapshot_upload_ms=parked.snapshot_upload_ms,
        restore=first.restore,
        first_query_after_restore_ms=first_ms,
        post_restore=latency_stats(post_ms),
        memory_freed=MemoryFreed(
            vector_bytes_estimate=parked.vector_bytes_freed,
            node_rss_delta_bytes=parked.node_rss_delta_bytes,
        ),
        results_match=results_match(warm_hits, post_hits),
    )


def _new_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)


def write_report(report: LatencyReport) -> None:
    deps.store().put_bytes(
        deps.report_key(report.run_id),
        report.model_dump_json(indent=2).encode(),
        "application/json",
    )


async def run_benchmark(request: BenchmarkRequest) -> LatencyReport:
    tenant_ids = list(dict.fromkeys(request.tenant_ids))
    for tenant_id in tenant_ids:
        validate_tenant_id(tenant_id)
        if await asyncio.to_thread(tenants.read_meta, tenant_id) is None:
            raise NotFound(f"Tenant {tenant_id} not found.")
    _set_progress(
        running=True, phase=None, tenant_id=None, tenants_done=0, tenant_ids=tenant_ids,
        tenants_total=len(tenant_ids), started_at=datetime.now(UTC), last_run_id=None,
    )
    try:
        results: list[TenantLatency] = []
        for tenant_id in tenant_ids:
            results.append(await _bench_tenant(tenant_id, request.queries_per_phase))
            _set_progress(tenants_done=len(results))
        report = LatencyReport(
            run_id=_new_run_id(),
            created_at=datetime.now(UTC),
            qdrant_version=await asyncio.to_thread(deps.gateway().version),
            embedding_model=deps.embedder().model_name,
            tenants=results,
        )
        await asyncio.to_thread(write_report, report)
        _set_progress(last_run_id=report.run_id)
    finally:
        _set_progress(running=False, phase=None, tenant_id=None)
    return report


def _summary(key: str) -> ReportSummary | None:
    raw = deps.store().get_bytes(key)
    if raw is None:
        return None
    body = json.loads(raw)
    return ReportSummary(
        run_id=body["run_id"],
        created_at=body["created_at"],
        tenant_count=len(body.get("tenants", [])),
    )


def list_reports() -> list[ReportSummary]:
    """Every report, newest first; the report.json reads overlap (one B2 GET each)."""
    keys = [
        e.key for e in deps.store().list_objects(deps.reports_root())
        if e.key.endswith("/report.json")
    ]
    with ThreadPoolExecutor(max_workers=LIST_READ_WORKERS) as pool:
        summaries = [s for s in pool.map(_summary, keys) if s is not None]
    return sorted(summaries, key=lambda s: s.created_at, reverse=True)


def get_report(run_id: str) -> LatencyReport:
    validate_run_id(run_id)
    raw = deps.store().get_bytes(deps.report_key(run_id))
    if raw is None:
        raise NotFound(f"Report {run_id} not found.")
    return LatencyReport.model_validate_json(raw)
