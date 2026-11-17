"""Create progress: document n of N while writing, chunk n of N while embedding.

A create of a few real READMEs takes 15+ s; the dialog polls
GET /tenants/<id>/progress (in memory, no B2 read, answers even before the
tenant's metadata exists) so its line advances during each long step.
"""

import pytest

from app.service import tenant_reads

LONG = " ".join(f"word{i}" for i in range(2_000))  # ~20 chunks of 120 words
DOCS = [
    {"filename": "a.md", "text": LONG},
    {"filename": "b.md", "text": LONG},
    {"filename": "c.txt", "text": "short"},
]


@pytest.mark.asyncio
async def test_progress_counts_documents_then_chunks(client, rag, monkeypatch):
    seen = []
    put, embed = rag.store.put_bytes, rag.embedder.embed

    def record():
        p = tenant_reads.get_progress("big-tenant")
        seen.append((p.state, p.done, p.total))

    def put_and_record(key, data, content_type):
        record()
        put(key, data, content_type)

    def embed_and_record(texts):
        record()
        return embed(texts)

    monkeypatch.setattr(rag.store, "put_bytes", put_and_record)
    monkeypatch.setattr(rag.embedder, "embed", embed_and_record)

    response = await client.post(
        "/tenants", json={"tenant_id": "big-tenant", "display_name": "Big", "documents": DOCS}
    )

    assert response.status_code == 201, response.text
    writing = [s for s in seen if s[0] == "writing"]
    assert writing[:3] == [("writing", 0, 3), ("writing", 1, 3), ("writing", 2, 3)]
    embedding = [s for s in seen if s[0] == "embedding"]
    total = embedding[0][2]
    assert total > 30  # every chunk of every document, counted up front
    assert len(embedding) > 2  # batched, so the count advances within a document
    assert [s[1] for s in embedding] == sorted(s[1] for s in embedding)
    assert all(s[2] == total for s in embedding)


@pytest.mark.asyncio
async def test_progress_endpoint_is_idle_outside_an_operation(client, rag):
    body = (await client.get("/tenants/nobody-here/progress")).json()
    assert body == {"tenant_id": "nobody-here", "state": None, "done": None, "total": None}


@pytest.mark.asyncio
async def test_progress_endpoint_rejects_a_bad_id(client):
    assert (await client.get("/tenants/BAD_ID!/progress")).status_code in (400, 422)
