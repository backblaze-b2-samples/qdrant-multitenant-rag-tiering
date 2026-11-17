"""Chunk documents, embed them, and upsert them into a tenant's collection."""

import json
import re
import uuid
from collections.abc import Callable

from app.types.ports import ChunkPoint, EmbedderPort, QdrantGatewayPort

CHUNK_WORDS = 120
OVERLAP_WORDS = 20
EMBED_BATCH = 16  # chunks per embed call: progress granularity, still batched
_POINT_NAMESPACE = uuid.UUID("1b2c3d4e-5f60-4a7b-8c9d-0e1f2a3b4c5d")


def chunk_text(text: str, max_words: int = CHUNK_WORDS, overlap: int = OVERLAP_WORDS) -> list[str]:
    """Split on whitespace into windows of `max_words` with `overlap` carried over."""
    words = re.split(r"\s+", text.strip())
    words = [w for w in words if w]
    if not words:
        return []
    step = max(1, max_words - overlap)
    chunks = []
    for start in range(0, len(words), step):
        chunks.append(" ".join(words[start : start + max_words]))
        if start + max_words >= len(words):
            break
    return chunks


def point_id(tenant_id: str, filename: str, chunk: int) -> str:
    """Deterministic, so re-ingesting a document overwrites its own points."""
    return str(uuid.uuid5(_POINT_NAMESPACE, f"{tenant_id}/{filename}#{chunk}"))


def payload_bytes(doc: str, chunk: int, text: str) -> int:
    return len(json.dumps({"doc": doc, "chunk": chunk, "text": text}).encode())


def index_documents(
    gateway: QdrantGatewayPort,
    embedder: EmbedderPort,
    tenant_id: str,
    collection: str,
    documents: list[tuple[str, str]],
    on_progress: Callable[[str, int, int], None] | None = None,
) -> dict[str, tuple[int, int]]:
    """Embed and upsert documents. Returns {filename: (chunks, payload_bytes)}.

    Creates the collection, sized from the embedding model, if it is missing.
    `on_progress(stage, done, total)` reports "embedding" chunk counts (in
    batches of EMBED_BATCH, so a long document still advances) then "upserting".
    """
    report = on_progress or (lambda *_: None)
    chunked = [(filename, chunk_text(text)) for filename, text in documents]
    total = sum(len(chunks) for _, chunks in chunked)
    report("embedding", 0, total)
    if collection not in gateway.list_collections():
        gateway.create_collection(collection, embedder.vector_size())
    stats: dict[str, tuple[int, int]] = {}
    points: list[ChunkPoint] = []
    done = 0
    for filename, chunks in chunked:
        vectors: list[list[float]] = []
        for start in range(0, len(chunks), EMBED_BATCH):
            vectors += embedder.embed(chunks[start : start + EMBED_BATCH])
            done += len(chunks[start : start + EMBED_BATCH])
            report("embedding", done, total)
        size = 0
        for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
            points.append(
                ChunkPoint(
                    id=point_id(tenant_id, filename, index),
                    vector=vector,
                    doc=filename,
                    chunk=index,
                    text=chunk,
                )
            )
            size += payload_bytes(filename, index, chunk)
        stats[filename] = (len(chunks), size)
    report("upserting", 0, 1)
    if points:
        gateway.upsert(collection, points)
    return stats
