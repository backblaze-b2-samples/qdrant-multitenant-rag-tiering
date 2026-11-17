"""Shared request builders for the tenant / tiering tests."""

from __future__ import annotations

LEGAL_DOCS = [
    {
        "filename": "contracts.md",
        "text": (
            "Every supplier contract needs a signed indemnity clause. "
            "Termination for convenience requires ninety days written notice."
        ),
    },
    {
        "filename": "privacy.txt",
        "text": (
            "Personal data is retained for thirty days after account closure. "
            "Data subject access requests are answered within one month."
        ),
    },
]

GARDEN_DOCS = [
    {
        "filename": "tomatoes.md",
        "text": "Water tomatoes deeply twice a week and stake the vines early.",
    },
    {
        "filename": "compost.txt",
        "text": "Turn the compost pile weekly and keep it as damp as a sponge.",
    },
]


async def create_tenant(client, tenant_id="acme-legal", docs=None, name=None):
    response = await client.post(
        "/tenants",
        json={
            "tenant_id": tenant_id,
            "display_name": name or tenant_id.replace("-", " ").title(),
            "documents": docs if docs is not None else LEGAL_DOCS,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()
