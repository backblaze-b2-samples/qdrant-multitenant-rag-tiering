"""The three adapter ports the services talk to, and the plain values they carry.

Real implementations live in `app/repo/` (boto3 against B2, qdrant-client plus
raw HTTP against Qdrant, fastembed). Tests install in-memory fakes behind the
same methods, so the park/restore state machine runs unchanged against either.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO, Protocol


@dataclass(frozen=True)
class ObjectEntry:
    key: str
    size_bytes: int
    last_modified: datetime


@dataclass(frozen=True)
class UploadResult:
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class CollectionStats:
    points: int
    vector_size: int
    distance: str


@dataclass(frozen=True)
class NodeSnapshot:
    """A snapshot file Qdrant wrote to its own local storage."""

    name: str
    size_bytes: int
    checksum: str | None


@dataclass(frozen=True)
class ChunkPoint:
    id: str
    vector: list[float]
    doc: str
    chunk: int
    text: str


@dataclass(frozen=True)
class ScoredPoint:
    doc: str
    chunk: int
    score: float
    text: str


class ObjectStorePort(Protocol):
    def put_bytes(self, key: str, data: bytes, content_type: str) -> None: ...
    def get_bytes(self, key: str) -> bytes | None: ...
    def head_size(self, key: str) -> int | None: ...
    def list_objects(self, prefix: str) -> list[ObjectEntry]: ...
    def delete_keys(self, keys: list[str]) -> list[str]: ...
    def iter_object(self, key: str, chunk_size: int) -> Iterator[bytes]: ...
    def create_multipart(self, key: str, content_type: str) -> str: ...
    def upload_part(self, key: str, upload_id: str, part_number: int, data: bytes) -> str: ...
    def complete_multipart(
        self, key: str, upload_id: str, parts: list[tuple[int, str]]
    ) -> None: ...
    def abort_multipart(self, key: str, upload_id: str) -> None: ...


class QdrantGatewayPort(Protocol):
    def version(self) -> str | None: ...
    def list_collections(self) -> list[str]: ...
    def create_collection(self, name: str, vector_size: int) -> None: ...
    def upsert(self, name: str, points: list[ChunkPoint]) -> None: ...
    def delete_doc_points(self, name: str, doc: str) -> None: ...
    def search(self, name: str, vector: list[float], limit: int) -> list[ScoredPoint]: ...
    def collection_stats(self, name: str) -> CollectionStats | None: ...
    def delete_collection(self, name: str) -> bool: ...
    def create_snapshot(self, name: str) -> NodeSnapshot: ...
    def iter_snapshot(self, name: str, snapshot_name: str, chunk_size: int) -> Iterator[bytes]: ...
    def delete_snapshot(self, name: str, snapshot_name: str) -> None: ...
    def upload_snapshot(
        self, name: str, fileobj: BinaryIO, filename: str, checksum: str | None
    ) -> None: ...
    def memory_bytes(self) -> int | None: ...


class EmbedderPort(Protocol):
    model_name: str

    def vector_size(self) -> int: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...
