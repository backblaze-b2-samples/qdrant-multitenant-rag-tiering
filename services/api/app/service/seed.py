"""Seed demo tenants from the synthetic corpus (no download, no key, no license)."""

from app.service import tenants
from app.service.errors import Conflict
from app.service.seed_corpus import SEED_TENANTS
from app.types.tenants import DocumentIn, SeedRequest, SeedResult, TenantCreate


async def seed_tenants(request: SeedRequest) -> SeedResult:
    """Create the first `tenant_count` demo tenants, skipping ones that exist."""
    created: list[str] = []
    skipped: list[str] = []
    for spec in SEED_TENANTS[: request.tenant_count]:
        create = TenantCreate(
            tenant_id=spec["tenant_id"],
            display_name=spec["display_name"],
            documents=[
                DocumentIn(filename=name, text=text) for name, text in spec["documents"].items()
            ],
        )
        try:
            await tenants.create_tenant(create)
        except Conflict:
            skipped.append(spec["tenant_id"])
            continue
        created.append(spec["tenant_id"])
    return SeedResult(created=created, skipped=skipped)
