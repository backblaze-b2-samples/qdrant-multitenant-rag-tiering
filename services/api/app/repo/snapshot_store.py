"""Snapshot transport between a Qdrant node and B2.

Storage-agnostic on purpose: every function takes an `ObjectStorePort` (the
boto3-backed `B2ObjectStore` in production, an in-memory fake in tests), so the
multipart streaming, the manifest writes and the verification below run the
same code in both.

- `upload_stream` streams an iterator of bytes into a multipart upload while
  hashing it, and aborts the upload on any failure, so a half-written snapshot
  never becomes a visible object.
- `verify_snapshot` re-checks a stored object against a manifest: `head_object`
  size first (cheap), then a streamed re-read and sha256.
- `download_to_spool` streams an object into a spooled temp file for restore,
  hashing as it goes, so memory stays bounded for large collections.
"""

import contextlib
import hashlib
import tempfile
from collections.abc import Iterable

from app.types.ports import ObjectStorePort, UploadResult
from app.types.tiering import SnapshotManifest

# S3 rejects any multipart part below 5 MiB except the last one.
MIN_PART_SIZE = 5 * 1024 * 1024
READ_CHUNK = 1024 * 1024
SPOOL_MAX_IN_MEMORY = 32 * 1024 * 1024
SNAPSHOT_CONTENT_TYPE = "application/octet-stream"


def effective_part_size(requested: int) -> int:
    """The configured part size, raised to the S3 minimum when below it."""
    return max(int(requested), MIN_PART_SIZE)


def upload_stream(
    store: ObjectStorePort,
    key: str,
    chunks: Iterable[bytes],
    part_size: int,
    content_type: str = SNAPSHOT_CONTENT_TYPE,
) -> UploadResult:
    """Multipart-upload `chunks` to `key`, hashing sha256 while streaming.

    Holds at most one part in memory. On any failure the multipart upload is
    aborted (so no partial object appears) and the original error re-raised.
    """
    size = effective_part_size(part_size)
    upload_id = store.create_multipart(key, content_type)
    digest = hashlib.sha256()
    total = 0
    buffer = bytearray()
    parts: list[tuple[int, str]] = []
    try:
        for chunk in chunks:
            digest.update(chunk)
            total += len(chunk)
            buffer.extend(chunk)
            while len(buffer) >= size:
                number = len(parts) + 1
                parts.append((number, store.upload_part(key, upload_id, number, bytes(buffer[:size]))))
                del buffer[:size]
        if buffer or not parts:
            number = len(parts) + 1
            parts.append((number, store.upload_part(key, upload_id, number, bytes(buffer))))
        store.complete_multipart(key, upload_id, parts)
    except Exception:
        # An abort failure must not mask the error that caused it.
        with contextlib.suppress(Exception):
            store.abort_multipart(key, upload_id)
        raise
    return UploadResult(size_bytes=total, sha256=digest.hexdigest())


def put_manifest(store: ObjectStorePort, key: str, manifest: SnapshotManifest) -> None:
    store.put_bytes(key, manifest.model_dump_json(indent=2).encode(), "application/json")


def get_manifest(store: ObjectStorePort, key: str) -> SnapshotManifest | None:
    raw = store.get_bytes(key)
    return None if raw is None else SnapshotManifest.model_validate_json(raw)


def stream_sha256(store: ObjectStorePort, key: str) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    for chunk in store.iter_object(key, READ_CHUNK):
        digest.update(chunk)
        total += len(chunk)
    return digest.hexdigest(), total


def verify_snapshot(
    store: ObjectStorePort, key: str, size_bytes: int, sha256: str
) -> str | None:
    """Return None when the stored object matches, else a human-readable reason."""
    stored_size = store.head_size(key)
    if stored_size is None:
        return f"verify failed: snapshot object {key} is missing from B2"
    if stored_size != size_bytes:
        return (
            f"verify failed: size mismatch, B2 holds {stored_size} bytes "
            f"but the manifest says {size_bytes}"
        )
    actual, _ = stream_sha256(store, key)
    if actual != sha256:
        return "verify failed: checksum mismatch between the B2 object and the manifest"
    return None


def download_to_spool(
    store: ObjectStorePort, key: str
) -> tuple[tempfile.SpooledTemporaryFile, str, int]:
    """Stream `key` into a spooled temp file. Returns (file at offset 0, sha256, size)."""
    spool = tempfile.SpooledTemporaryFile(max_size=SPOOL_MAX_IN_MEMORY)  # noqa: SIM115 (returned open)
    digest = hashlib.sha256()
    total = 0
    try:
        for chunk in store.iter_object(key, READ_CHUNK):
            digest.update(chunk)
            spool.write(chunk)
            total += len(chunk)
    except Exception:
        spool.close()
        raise
    spool.seek(0)
    return spool, digest.hexdigest(), total


def delete_prefix(store: ObjectStorePort, prefix: str) -> list[str]:
    """Delete every object under `prefix` (which must be non-empty and end in '/')."""
    if not prefix or not prefix.endswith("/"):
        raise ValueError(f"refusing to delete an unscoped prefix: {prefix!r}")
    keys = [entry.key for entry in store.list_objects(prefix)]
    return store.delete_keys(keys) if keys else []
