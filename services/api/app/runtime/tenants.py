"""Tenant routes. Handlers only translate HTTP <-> service calls."""

from fastapi import APIRouter, Query

from app.runtime import metrics
from app.runtime.errors import http_errors
from app.service import restore, seed, tenants, tiering
from app.types.tenants import (
    DeleteTenantResult,
    QueryRequest,
    QueryResponse,
    RestoreResult,
    SeedRequest,
    SeedResult,
    TenantCreate,
    TenantDetail,
    TenantProgress,
    TenantSummary,
    TenantUpdate,
)
from app.types.tiering import ParkResult, SnapshotEntry

router = APIRouter()

# SECURITY: unauthenticated, single-operator demo stance (docs/SECURITY.md).
# "Tenant" here is a data-isolation unit for the vector store, not a login: put
# auth in front of every route before exposing this API to tenants themselves.


@router.get("/tenants", response_model=list[TenantSummary])
def list_tenants_endpoint():
    with http_errors():
        return tenants.list_tenants_sync()


@router.post("/tenants", response_model=TenantDetail, status_code=201)
async def create_tenant_endpoint(body: TenantCreate):
    with http_errors():
        return await tenants.create_tenant(body)


@router.post("/tenants/seed", response_model=SeedResult)
async def seed_tenants_endpoint(body: SeedRequest):
    with http_errors():
        return await seed.seed_tenants(body)


@router.get("/tenants/{tenant_id}", response_model=TenantDetail)
async def get_tenant_endpoint(tenant_id: str):
    with http_errors():
        return await tenants.get_tenant(tenant_id)


@router.patch("/tenants/{tenant_id}", response_model=TenantDetail)
async def update_tenant_endpoint(tenant_id: str, body: TenantUpdate):
    """Edit name and documents. A parked tenant is restored first."""
    with http_errors():
        return await tenants.update_tenant(tenant_id, body)


@router.delete("/tenants/{tenant_id}", response_model=DeleteTenantResult)
async def delete_tenant_endpoint(
    tenant_id: str,
    confirm: str = Query(description="Must equal tenant_id."),
):
    """Drop the collection and delete ONLY this tenant's corpus and snapshots."""
    with http_errors():
        return await tenants.delete_tenant(tenant_id, confirm)


@router.post("/tenants/{tenant_id}/query", response_model=QueryResponse)
async def query_tenant_endpoint(tenant_id: str, body: QueryRequest):
    """Search a tenant; a parked tenant is restored from B2 first."""
    with http_errors():
        response = await restore.query_tenant(tenant_id, body)
    if response.restored:
        metrics.record_restore()
    return response


@router.post("/tenants/{tenant_id}/park", response_model=ParkResult)
async def park_tenant_endpoint(tenant_id: str):
    with http_errors():
        result = await tiering.park_tenant(tenant_id)
    if result.verified:
        metrics.record_park()
    return result


@router.post("/tenants/{tenant_id}/restore", response_model=RestoreResult)
async def restore_tenant_endpoint(tenant_id: str):
    with http_errors():
        result = await restore.restore_tenant(tenant_id)
    if result.timing.total_ms > 0:
        metrics.record_restore()
    return result


@router.get("/tenants/{tenant_id}/progress", response_model=TenantProgress)
def tenant_progress_endpoint(tenant_id: str):
    """The stage in flight and its count (in memory): polled while a create runs."""
    with http_errors():
        return tenants.get_progress(tenant_id)


@router.get("/tenants/{tenant_id}/snapshots", response_model=list[SnapshotEntry])
def list_snapshots_endpoint(tenant_id: str):
    with http_errors():
        return tiering.list_snapshots(tenant_id)
