"""Tenant ids and document filenames become B2 keys and collection names."""

import pytest

from app.service.errors import InvalidInput
from app.service.tenants import validate_filename, validate_tenant_id

VALID_IDS = ["ab", "acme-legal", "a1", "x" * 40, "tenant-2026"]
INVALID_IDS = ["", "a", "A1", "-ab", "ab-", "a_b", "a.b", "x" * 41, "../ab", "ab/cd"]


@pytest.mark.parametrize("tenant_id", VALID_IDS)
def test_valid_ids(tenant_id):
    validate_tenant_id(tenant_id)


@pytest.mark.parametrize("tenant_id", INVALID_IDS)
def test_invalid_ids(tenant_id):
    with pytest.raises(InvalidInput):
        validate_tenant_id(tenant_id)


@pytest.mark.parametrize("name", ["notes.md", "Q3 report.txt", "a-b_c.md"])
def test_valid_filenames(name):
    validate_filename(name)


@pytest.mark.parametrize(
    "name", ["", "_tenant.json", "../x.md", "dir/x.md", "x.pdf", "x", ".md", "a\\b.txt"]
)
def test_invalid_filenames(name):
    with pytest.raises(InvalidInput):
        validate_filename(name)


@pytest.mark.asyncio
async def test_create_with_bad_id_is_rejected_before_any_write(client, rag):
    response = await client.post(
        "/tenants",
        json={
            "tenant_id": "Bad_ID",
            "display_name": "x",
            "documents": [{"filename": "a.md", "text": "hi"}],
        },
    )
    assert response.status_code in (400, 422)
    assert rag.store.objects == {}


@pytest.mark.asyncio
async def test_bad_id_in_path_returns_400(client):
    assert (await client.get("/tenants/Bad_ID")).status_code == 400
