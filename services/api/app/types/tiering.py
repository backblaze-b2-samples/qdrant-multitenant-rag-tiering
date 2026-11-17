"""Snapshot manifest, parking, policy and prune models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.types.base import ResponseModel


class SnapshotManifest(ResponseModel):
    """`rag/snapshots/<tenant>/latest.json`, written LAST in a park.

    Restore trusts nothing else: the object key, its size and sha256, and the
    vector configuration the points were embedded with.
    """

    tenant_id: str
    snapshot_key: str
    snapshot_id: str
    size_bytes: int
    point_count: int
    sha256: str
    vector_size: int
    distance: str
    embedding_model: str
    qdrant_version: str | None
    created_at: datetime
    payload_bytes: int = Field(
        default=0, description="Payload bytes recorded at ingest, for the memory estimate."
    )


class ParkResult(ResponseModel):
    tenant_id: str
    state: Literal["hot", "parked", "empty"]
    manifest: SnapshotManifest | None
    verified: bool
    reason: str | None
    vector_bytes_freed: int = Field(
        default=0, description="Estimated hot-tier bytes released (0 if not parked)."
    )
    node_rss_delta_bytes: int | None = Field(
        default=None,
        description="Observed change in Qdrant resident memory; the allocator may lag.",
    )
    snapshot_upload_ms: float = 0.0


class SnapshotEntry(ResponseModel):
    key: str
    size_bytes: int
    created_at: datetime
    is_latest: bool


class TieringPolicy(ResponseModel):
    idle_seconds: int
    sweep_interval_seconds: int
    prune_enabled: bool


class TieringRunRequest(BaseModel):
    idle_seconds: int | None = Field(default=None, ge=0)
    dry_run: bool = True


class SkippedTenant(ResponseModel):
    tenant_id: str
    reason: str


class TieringRunResult(ResponseModel):
    candidates: list[str]
    parked: list[str]
    skipped: list[SkippedTenant]
    dry_run: bool


class TieringStats(ResponseModel):
    hot: int
    parked: int
    empty: int
    vector_bytes_hot: int
    vector_bytes_freed: int
    snapshot_bytes_b2: int
    corpus_bytes_b2: int


class PruneRequest(BaseModel):
    keep_last: int = Field(default=1, ge=1, le=5)
    apply: bool = False


class PruneResult(ResponseModel):
    enabled: bool
    applied: bool
    candidates: list[str]
    deleted: list[str]
