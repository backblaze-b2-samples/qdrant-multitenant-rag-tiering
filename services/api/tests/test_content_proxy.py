"""Preview and download are proxied by the backend: no presigned URL leaves it."""

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest

from app.service import files as files_service
from app.types import FileMetadata

KEY = "rag/corpus/acme-legal/notes #1.md"
BODY = b"# Notes\nretention is thirty days\n"


def _metadata(key: str) -> FileMetadata:
    return FileMetadata(
        key=key,
        filename=key.rsplit("/", 1)[-1],
        folder="rag/corpus/acme-legal/",
        size_bytes=len(BODY),
        size_human=f"{len(BODY)} B",
        content_type="text/markdown",
        uploaded_at=datetime.now(UTC),
        url=None,
    )


@pytest.fixture
def stored(monkeypatch):
    monkeypatch.setattr(files_service, "get_file_metadata", _metadata)
    monkeypatch.setattr(
        files_service, "open_object_stream", lambda key: (iter([BODY[:5], BODY[5:]]), "text/markdown")
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("disposition", ["inline", "attachment"])
async def test_content_route_streams_object(client, stored, disposition):
    response = await client.get(
        "/files-by-key/content", params={"key": KEY, "disposition": disposition}
    )

    assert response.status_code == 200
    assert response.content == BODY
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"].startswith(f"{disposition};")
    assert "notes%20%231.md" in response.headers["content-disposition"]


@pytest.mark.asyncio
async def test_preview_and_download_point_at_the_content_route(client, stored):
    preview = (await client.get("/files-by-key/preview", params={"key": KEY})).json()["url"]
    download = (await client.get("/files-by-key/download", params={"key": KEY})).json()["url"]

    for url, disposition in ((preview, "inline"), (download, "attachment")):
        parsed = urlparse(url)
        assert parsed.scheme == "" and parsed.netloc == ""
        assert parsed.path == "/files-by-key/content"
        assert parse_qs(parsed.query) == {"key": [KEY], "disposition": [disposition]}
        assert "X-Amz-Signature" not in url
    assert files_service.get_download_count() == 1


@pytest.mark.asyncio
async def test_content_route_rejects_bad_keys_and_dispositions(client, stored):
    bad_key = await client.get("/files-by-key/content", params={"key": "../etc/passwd"})
    bad_disp = await client.get(
        "/files-by-key/content", params={"key": KEY, "disposition": "sideways"}
    )
    assert bad_key.status_code == 400
    assert bad_disp.status_code == 422


@pytest.mark.asyncio
async def test_content_route_missing_object_is_404(client, monkeypatch):
    monkeypatch.setattr(files_service, "get_file_metadata", lambda key: None)
    response = await client.get("/files-by-key/content", params={"key": "rag/missing.md"})
    assert response.status_code == 404
