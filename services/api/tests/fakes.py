"""In-memory stand-ins for the three repo adapters (B2 objects, Qdrant, embedder).

They implement the same ports as the real modules in `app/repo/`, so the service
code under test (park state machine, restore, manifest-last ordering, verify,
prune) runs unchanged. Only the storage primitives are faked: multipart
streaming, manifest writes and verification are the real repo/service code.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import BinaryIO

from app.types.ports import (
    ChunkPoint,
    CollectionStats,
    NodeSnapshot,
    ObjectEntry,
    ScoredPoint,
)


class FakeStore:
    """Object store with an ordered event log of completed writes."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.modified: dict[str, datetime] = {}
        self.events: list[tuple[str, str]] = []
        self._uploads: dict[str, dict[int, bytes]] = {}
        self.fail_upload_part = False
        self.corrupt_after_complete: str | None = None  # "size" | "checksum"
        self._clock = 0

    def _stamp(self, key: str) -> None:
        self._clock += 1
        self.modified[key] = datetime.fromtimestamp(1_700_000_000 + self._clock, UTC)

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = data
        self._stamp(key)
        self.events.append(("put", key))

    def get_bytes(self, key: str) -> bytes | None:
        return self.objects.get(key)

    def head_size(self, key: str) -> int | None:
        data = self.objects.get(key)
        return None if data is None else len(data)

    def list_objects(self, prefix: str) -> list[ObjectEntry]:
        return [
            ObjectEntry(key=k, size_bytes=len(v), last_modified=self.modified[k])
            for k, v in sorted(self.objects.items())
            if k.startswith(prefix)
        ]

    def delete_keys(self, keys: list[str]) -> list[str]:
        deleted = []
        for key in keys:
            if self.objects.pop(key, None) is not None:
                self.modified.pop(key, None)
                deleted.append(key)
                self.events.append(("delete", key))
        return deleted

    def iter_object(self, key: str, chunk_size: int) -> Iterator[bytes]:
        data = self.objects[key]
        for i in range(0, len(data), chunk_size):
            yield data[i : i + chunk_size]

    def create_multipart(self, key: str, content_type: str) -> str:
        upload_id = f"up-{len(self._uploads) + 1}"
        self._uploads[upload_id] = {}
        return upload_id

    def upload_part(self, key: str, upload_id: str, part_number: int, data: bytes) -> str:
        if self.fail_upload_part:
            raise RuntimeError("simulated B2 upload_part failure")
        self._uploads[upload_id][part_number] = data
        return f"etag-{part_number}"

    def complete_multipart(
        self, key: str, upload_id: str, parts: list[tuple[int, str]]
    ) -> None:
        stored = self._uploads.pop(upload_id)
        data = b"".join(stored[n] for n, _ in parts)
        if self.corrupt_after_complete == "size":
            data = data + b"x"
        elif self.corrupt_after_complete == "checksum":
            data = bytes([data[0] ^ 0xFF]) + data[1:]
        self.objects[key] = data
        self._stamp(key)
        self.events.append(("complete", key))

    def abort_multipart(self, key: str, upload_id: str) -> None:
        self._uploads.pop(upload_id, None)
        self.events.append(("abort", key))


class FakeGateway:
    """A Qdrant node whose snapshots are JSON dumps of the collection's points."""

    def __init__(self, delay_snapshot: float = 0.0) -> None:
        self.collections: dict[str, dict[str, ChunkPoint]] = {}
        self.sizes: dict[str, int] = {}
        self.node_snapshots: dict[tuple[str, str], bytes] = {}
        self.events: list[tuple[str, str]] = []
        self.delay_snapshot = delay_snapshot
        self.memory = 500_000_000

    def version(self) -> str | None:
        return "1.20.2"

    def list_collections(self) -> list[str]:
        return sorted(self.collections)

    def create_collection(self, name: str, vector_size: int) -> None:
        self.collections[name] = {}
        self.sizes[name] = vector_size
        self.events.append(("create", name))

    def upsert(self, name: str, points: list[ChunkPoint]) -> None:
        for point in points:
            self.collections[name][point.id] = point

    def delete_doc_points(self, name: str, doc: str) -> None:
        points = self.collections[name]
        for pid in [pid for pid, p in points.items() if p.doc == doc]:
            del points[pid]

    def search(self, name: str, vector: list[float], limit: int) -> list[ScoredPoint]:
        self.events.append(("search", name))
        scored = [
            ScoredPoint(doc=p.doc, chunk=p.chunk, score=_cosine(vector, p.vector), text=p.text)
            for p in self.collections[name].values()
        ]
        scored.sort(key=lambda s: (-s.score, s.doc, s.chunk))
        return scored[:limit]

    def collection_stats(self, name: str) -> CollectionStats | None:
        if name not in self.collections:
            return None
        return CollectionStats(
            points=len(self.collections[name]), vector_size=self.sizes[name], distance="Cosine"
        )

    def delete_collection(self, name: str) -> bool:
        self.events.append(("delete_collection", name))
        self.memory -= 1000 * len(self.collections.get(name, {}))
        return self.collections.pop(name, None) is not None

    def create_snapshot(self, name: str) -> NodeSnapshot:
        if self.delay_snapshot:
            time.sleep(self.delay_snapshot)
        payload = json.dumps(
            {
                "size": self.sizes[name],
                "points": [p.__dict__ for p in self.collections[name].values()],
            },
            sort_keys=True,
        ).encode()
        snap = f"{name}-{len(self.node_snapshots) + 1}.snapshot"
        self.node_snapshots[(name, snap)] = payload
        return NodeSnapshot(
            name=snap, size_bytes=len(payload), checksum=hashlib.sha256(payload).hexdigest()
        )

    def iter_snapshot(self, name: str, snapshot_name: str, chunk_size: int) -> Iterator[bytes]:
        data = self.node_snapshots[(name, snapshot_name)]
        for i in range(0, len(data), chunk_size):
            yield data[i : i + chunk_size]

    def delete_snapshot(self, name: str, snapshot_name: str) -> None:
        self.node_snapshots.pop((name, snapshot_name), None)

    def upload_snapshot(
        self, name: str, fileobj: BinaryIO, filename: str, checksum: str | None
    ) -> None:
        data = fileobj.read()
        if checksum and hashlib.sha256(data).hexdigest() != checksum:
            raise RuntimeError("checksum rejected by node")
        body = json.loads(data)
        self.collections[name] = {p["id"]: ChunkPoint(**p) for p in body["points"]}
        self.sizes[name] = body["size"]
        self.events.append(("restore", name))

    def memory_bytes(self) -> int | None:
        return self.memory


class FakeEmbedder:
    """Hashed bag-of-words vectors: deterministic, and similar texts score high."""

    model_name = "fake/bow-32"

    def __init__(self, dim: int = 32) -> None:
        self.dim = dim

    def vector_size(self) -> int:
        return self.dim

    def _vec(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))
