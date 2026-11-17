"""Opening the app at 127.0.0.1 instead of localhost must not be CORS-blocked."""

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", ["http://localhost:3000", "http://127.0.0.1:3000"])
async def test_default_cors_allows_both_loopback_names(client, origin):
    response = await client.get("/health", headers={"Origin": origin})
    assert response.headers.get("access-control-allow-origin") == origin
