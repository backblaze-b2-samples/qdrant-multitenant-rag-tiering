"""Latency benchmark report models (`rag/reports/<run-id>/report.json`)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.types.base import ResponseModel
from app.types.tenants import RestoreTiming


class LatencyStats(ResponseModel):
    n: int
    p50_ms: float
    p95_ms: float
    mean_ms: float


class MemoryFreed(ResponseModel):
    vector_bytes_estimate: int
    node_rss_delta_bytes: int | None = Field(
        description="Observed Qdrant resident-memory drop; null when the metric is absent."
    )


class TenantLatency(ResponseModel):
    tenant_id: str
    point_count: int
    warm: LatencyStats
    snapshot_bytes: int
    snapshot_upload_ms: float
    restore: RestoreTiming
    first_query_after_restore_ms: float
    post_restore: LatencyStats
    memory_freed: MemoryFreed
    results_match: bool = Field(
        description="Post-restore hits equal warm hits (same ids, scores within 1e-4)."
    )


class LatencyReport(ResponseModel):
    run_id: str
    created_at: datetime
    qdrant_version: str | None
    embedding_model: str
    tenants: list[TenantLatency]


class BenchmarkRequest(BaseModel):
    tenant_ids: list[str] = Field(min_length=1, max_length=6)
    queries_per_phase: Literal[5, 10, 20] = 10


class ReportSummary(ResponseModel):
    run_id: str
    created_at: datetime
    tenant_count: int
