"""The hot tier: one Qdrant node, one collection per tenant.

`qdrant-client` handles collections, points and search. Snapshot transfer and
the node's metrics use raw HTTP (httpx) because they are byte streams the
client library buffers or does not expose:

- `iter_snapshot` streams `GET /collections/<c>/snapshots/<name>` so a snapshot
  goes to B2 without ever being held whole in memory.
- `upload_snapshot` posts a snapshot file to
  `POST /collections/<c>/snapshots/upload?priority=snapshot`, which works on any
  node, including one whose storage has never seen the tenant. Qdrant's
  "recover from URL" is deliberately not used: it would make Qdrant fetch from
  B2 itself, outside this app's S3 client and its custom user agent.
- `memory_bytes` reads `memory_resident_bytes` from `/metrics` (verified
  present on the pinned qdrant/qdrant:v1.20.2 image).
"""

import logging
from collections.abc import Iterator
from typing import BinaryIO

import httpx
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse

from app.types.ports import ChunkPoint, CollectionStats, NodeSnapshot, ScoredPoint

logger = logging.getLogger(__name__)

RESIDENT_METRIC = "memory_resident_bytes"


class QdrantGateway:
    """`QdrantGatewayPort` over a real node. Raises RuntimeError on HTTP errors."""

    def __init__(self, url: str, timeout_seconds: float = 120.0) -> None:
        self.url = url.rstrip("/")
        self.client = QdrantClient(url=self.url, timeout=int(timeout_seconds))
        self.http = httpx.Client(
            base_url=self.url, timeout=httpx.Timeout(timeout_seconds, connect=5.0)
        )

    # --- node -------------------------------------------------------------

    def version(self) -> str | None:
        try:
            response = self.http.get("/", timeout=3.0)
            response.raise_for_status()
            return response.json().get("version")
        except (httpx.HTTPError, ValueError):
            return None

    def memory_bytes(self) -> int | None:
        try:
            response = self.http.get("/metrics", timeout=5.0)
            response.raise_for_status()
        except httpx.HTTPError:
            return None
        for line in response.text.splitlines():
            if line.startswith(RESIDENT_METRIC + " "):
                return int(float(line.split()[1]))
        return None

    # --- collections and points ------------------------------------------

    def list_collections(self) -> list[str]:
        return sorted(c.name for c in self.client.get_collections().collections)

    def create_collection(self, name: str, vector_size: int) -> None:
        self.client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
        )

    def upsert(self, name: str, points: list[ChunkPoint]) -> None:
        for start in range(0, len(points), 256):
            batch = points[start : start + 256]
            self.client.upsert(
                collection_name=name,
                wait=True,
                points=[
                    models.PointStruct(
                        id=p.id,
                        vector=p.vector,
                        payload={"doc": p.doc, "chunk": p.chunk, "text": p.text},
                    )
                    for p in batch
                ],
            )

    def delete_doc_points(self, name: str, doc: str) -> None:
        self.client.delete(
            collection_name=name,
            wait=True,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[models.FieldCondition(key="doc", match=models.MatchValue(value=doc))]
                )
            ),
        )

    def search(self, name: str, vector: list[float], limit: int) -> list[ScoredPoint]:
        result = self.client.query_points(
            collection_name=name, query=vector, limit=limit, with_payload=True
        )
        return [
            ScoredPoint(
                doc=str(p.payload.get("doc", "")),
                chunk=int(p.payload.get("chunk", 0)),
                score=float(p.score),
                text=str(p.payload.get("text", "")),
            )
            for p in result.points
        ]

    def collection_stats(self, name: str) -> CollectionStats | None:
        if not self.client.collection_exists(name):
            return None
        try:
            info = self.client.get_collection(name)
            count = self.client.count(collection_name=name, exact=True).count
        except UnexpectedResponse as e:
            # Dropped between the check and the read (a park's last step).
            if e.status_code == 404:
                return None
            raise
        vectors = info.config.params.vectors
        distance = vectors.distance
        return CollectionStats(
            points=int(count),
            vector_size=int(vectors.size),
            distance=getattr(distance, "value", str(distance)),
        )

    def delete_collection(self, name: str) -> bool:
        return bool(self.client.delete_collection(collection_name=name))

    # --- snapshots --------------------------------------------------------

    def create_snapshot(self, name: str) -> NodeSnapshot:
        snapshot = self.client.create_snapshot(collection_name=name, wait=True)
        if snapshot is None:
            raise RuntimeError(f"Qdrant returned no snapshot for {name}")
        return NodeSnapshot(
            name=snapshot.name, size_bytes=int(snapshot.size), checksum=snapshot.checksum
        )

    def iter_snapshot(self, name: str, snapshot_name: str, chunk_size: int) -> Iterator[bytes]:
        path = f"/collections/{name}/snapshots/{snapshot_name}"
        with self.http.stream("GET", path) as response:
            if response.status_code != 200:
                raise RuntimeError(f"Qdrant snapshot download failed: HTTP {response.status_code}")
            yield from response.iter_bytes(chunk_size)

    def delete_snapshot(self, name: str, snapshot_name: str) -> None:
        self.client.delete_snapshot(collection_name=name, snapshot_name=snapshot_name, wait=True)

    def upload_snapshot(
        self, name: str, fileobj: BinaryIO, filename: str, checksum: str | None
    ) -> None:
        params = {"priority": "snapshot", "wait": "true"}
        if checksum:
            params["checksum"] = checksum
        response = self.http.post(
            f"/collections/{name}/snapshots/upload",
            params=params,
            files={"snapshot": (filename, fileobj, "application/octet-stream")},
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Qdrant snapshot upload failed: HTTP {response.status_code} {response.text[:300]}"
            )
