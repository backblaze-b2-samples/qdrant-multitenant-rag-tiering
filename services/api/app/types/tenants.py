"""Tenant, document and query models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.types.base import ResponseModel
from app.types.tiering import SnapshotManifest

TenantState = Literal[
    "hot", "parked", "empty",
    "writing", "embedding", "upserting",  # create stages
    "snapshotting", "uploading", "verifying", "dropping",  # park stages
    "restoring",
]

TENANT_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{0,38}[a-z0-9]$"


class DocumentIn(BaseModel):
    """One text or Markdown document, sent as text (the browser reads the file)."""

    filename: str = Field(min_length=1, max_length=100, examples=["contracts.md"])
    text: str = Field(min_length=1, max_length=200_000)


class TenantCreate(BaseModel):
    tenant_id: str = Field(
        pattern=TENANT_ID_PATTERN,
        description="Lowercase letters, digits and hyphens, 2 to 40 characters.",
        examples=["acme-legal"],
    )
    display_name: str = Field(min_length=1, max_length=80, examples=["Acme Legal"])
    documents: list[DocumentIn] = Field(min_length=1, max_length=50)


class TenantUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    add_documents: list[DocumentIn] = Field(default_factory=list, max_length=50)
    remove_documents: list[str] = Field(default_factory=list, max_length=50)


class DocumentInfo(ResponseModel):
    filename: str
    key: str = Field(description="B2 object key of the source document.")
    size_bytes: int
    chunks: int


class TenantSummary(ResponseModel):
    """One row of the tenants table. State is derived, never stored."""

    tenant_id: str
    display_name: str
    state: TenantState
    point_count: int
    document_count: int
    vector_bytes_estimate: int = Field(
        description="points * vector_size * 4 plus payload bytes: the hot-tier footprint."
    )
    last_query_at: datetime | None = Field(
        description="In-memory; resets when the API restarts."
    )
    snapshot_size_bytes: int | None
    snapshot_created_at: datetime | None


class TenantDetail(TenantSummary):
    created_at: datetime
    documents: list[DocumentInfo]
    manifest: SnapshotManifest | None
    snapshot_stale: bool = Field(
        description="True when documents changed after the latest snapshot was taken."
    )


class SeedRequest(BaseModel):
    tenant_count: int = Field(default=4, ge=2, le=6)


class SeedResult(ResponseModel):
    created: list[str]
    skipped: list[str]


class DeleteTenantResult(ResponseModel):
    deleted_keys: list[str]
    collection_dropped: bool


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2_000)
    top_k: int = Field(default=5, ge=1, le=20)


class QueryHit(ResponseModel):
    doc: str
    chunk: int
    score: float
    text: str


class RestoreTiming(ResponseModel):
    download_ms: float
    load_ms: float
    total_ms: float


class QueryResponse(ResponseModel):
    hits: list[QueryHit]
    latency_ms: float = Field(description="Embedding plus vector search, excluding any restore.")
    restored: bool
    restore: RestoreTiming | None


class RestoreResult(ResponseModel):
    tenant_id: str
    state: TenantState
    timing: RestoreTiming
    point_count: int


class TenantProgress(ResponseModel):
    """What is running on a tenant right now (in memory; no B2 read)."""

    tenant_id: str
    state: TenantState | None = Field(description="The stage in flight; null when idle.")
    done: int | None = Field(description="Units done in this stage (documents or chunks).")
    total: int | None
