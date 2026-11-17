"""Snapshot manifest, multipart streaming and verification (repo/snapshot_store)."""

import hashlib
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.repo import snapshot_store
from app.service import deps
from app.service.tiering import park_tenant
from app.types.tiering import SnapshotManifest
from tests.fakes import FakeStore
from tests.helpers import create_tenant


def _manifest(**overrides) -> SnapshotManifest:
    fields = {
        "tenant_id": "acme-legal",
        "snapshot_key": "rag/snapshots/acme-legal/s1.snapshot",
        "snapshot_id": "s1",
        "size_bytes": 10,
        "point_count": 4,
        "sha256": "ab" * 32,
        "vector_size": 384,
        "distance": "Cosine",
        "embedding_model": "BAAI/bge-small-en-v1.5",
        "qdrant_version": "1.20.2",
        "created_at": datetime(2026, 11, 17, tzinfo=UTC),
        "payload_bytes": 120,
    }
    fields.update(overrides)
    return SnapshotManifest(**fields)


def test_manifest_round_trip():
    store = FakeStore()
    manifest = _manifest()

    snapshot_store.put_manifest(store, "rag/snapshots/acme-legal/latest.json", manifest)

    assert snapshot_store.get_manifest(store, "rag/snapshots/acme-legal/latest.json") == manifest
    assert snapshot_store.get_manifest(store, "rag/snapshots/other/latest.json") is None


@pytest.mark.parametrize(
    "field", ["snapshot_key", "size_bytes", "sha256", "point_count", "embedding_model"]
)
def test_manifest_requires_core_fields(field):
    data = _manifest().model_dump()
    del data[field]
    with pytest.raises(ValidationError):
        SnapshotManifest(**data)


def test_upload_stream_splits_parts_and_hashes(monkeypatch):
    monkeypatch.setattr(snapshot_store, "MIN_PART_SIZE", 4)
    store = FakeStore()
    data = b"0123456789"

    result = snapshot_store.upload_stream(
        store, "k.snapshot", iter([data[:3], data[3:7], data[7:]]), part_size=4
    )

    assert result.size_bytes == 10
    assert result.sha256 == hashlib.sha256(data).hexdigest()
    assert store.objects["k.snapshot"] == data


def test_upload_stream_aborts_on_failure():
    store = FakeStore()
    store.fail_upload_part = True

    with pytest.raises(RuntimeError):
        snapshot_store.upload_stream(store, "k.snapshot", iter([b"abc"]), part_size=4)

    assert ("abort", "k.snapshot") in store.events
    assert "k.snapshot" not in store.objects


def test_part_size_is_never_below_the_s3_minimum():
    assert snapshot_store.effective_part_size(1024) == snapshot_store.MIN_PART_SIZE
    assert snapshot_store.effective_part_size(16 * 1024 * 1024) == 16 * 1024 * 1024


def test_verify_detects_size_and_checksum_mismatch():
    store = FakeStore()
    data = b"snapshot-bytes"
    store.put_bytes("k", data, "application/octet-stream")
    good = hashlib.sha256(data).hexdigest()

    assert snapshot_store.verify_snapshot(store, "k", len(data), good) is None
    assert "size" in snapshot_store.verify_snapshot(store, "k", len(data) + 1, good)
    assert "checksum" in snapshot_store.verify_snapshot(store, "k", len(data), "0" * 64)
    assert "missing" in snapshot_store.verify_snapshot(store, "nope", 1, good)


@pytest.mark.asyncio
async def test_manifest_is_written_after_the_snapshot_object(client, rag):
    await create_tenant(client, "acme-legal")

    result = await park_tenant("acme-legal")

    events = rag.store.events
    snapshot_done = events.index(("complete", result.manifest.snapshot_key))
    manifest_put = events.index(("put", deps.manifest_key("acme-legal")))
    assert snapshot_done < manifest_put
    stored = SnapshotManifest.model_validate_json(
        rag.store.objects[deps.manifest_key("acme-legal")]
    )
    assert stored.sha256 == hashlib.sha256(
        rag.store.objects[result.manifest.snapshot_key]
    ).hexdigest()
    assert stored.embedding_model == rag.embedder.model_name
    assert stored.vector_size == rag.embedder.dim
