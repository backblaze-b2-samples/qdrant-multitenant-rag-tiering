"""Backend wiring and the one place B2 keys and collection names are built.

The three adapters are constructed lazily on first use (importing the app never
opens a connection or loads a model). Tests replace them with in-memory fakes
through `set_backends`.

Key layout, all under `settings.key_prefix` (default `rag/`):

    corpus/<tenant>/_tenant.json        tenant metadata
    corpus/<tenant>/<filename>          source documents
    snapshots/<tenant>/<id>.snapshot    Qdrant collection snapshots
    snapshots/<tenant>/latest.json      manifest, written last
    reports/<run-id>/report.json        latency benchmark results
"""

from threading import Lock

from app.config import settings
from app.types.ports import EmbedderPort, ObjectStorePort, QdrantGatewayPort

_lock = Lock()
_backends: dict[str, object] = {}

TENANT_META = "_tenant.json"
MANIFEST = "latest.json"


def store() -> ObjectStorePort:
    with _lock:
        if "store" not in _backends:
            from app.repo.b2_object import B2ObjectStore

            _backends["store"] = B2ObjectStore()
        return _backends["store"]  # type: ignore[return-value]


def gateway() -> QdrantGatewayPort:
    with _lock:
        if "gateway" not in _backends:
            from app.repo.qdrant_gateway import QdrantGateway

            _backends["gateway"] = QdrantGateway(settings.qdrant_url)
        return _backends["gateway"]  # type: ignore[return-value]


def embedder() -> EmbedderPort:
    with _lock:
        if "embedder" not in _backends:
            from app.repo.embedder import get_embedder

            _backends["embedder"] = get_embedder(settings.embedding_model)
        return _backends["embedder"]  # type: ignore[return-value]


def set_backends(
    store: ObjectStorePort | None = None,
    gateway: QdrantGatewayPort | None = None,
    embedder: EmbedderPort | None = None,
) -> None:
    """Install explicit adapters (tests, or a script driving a second node)."""
    with _lock:
        for name, value in (("store", store), ("gateway", gateway), ("embedder", embedder)):
            if value is not None:
                _backends[name] = value


def reset_backends() -> None:
    with _lock:
        _backends.clear()


def qdrant_status() -> tuple[bool, str | None]:
    """(reachable, version) for /health. Never raises."""
    try:
        version = gateway().version()
    except Exception:
        return False, None
    return version is not None, version


# --- keys ----------------------------------------------------------------


def prefix() -> str:
    return settings.key_prefix


def corpus_root() -> str:
    return f"{prefix()}corpus/"


def snapshots_root() -> str:
    return f"{prefix()}snapshots/"


def reports_root() -> str:
    return f"{prefix()}reports/"


def corpus_prefix(tenant_id: str) -> str:
    return f"{corpus_root()}{tenant_id}/"


def tenant_meta_key(tenant_id: str) -> str:
    return corpus_prefix(tenant_id) + TENANT_META


def doc_key(tenant_id: str, filename: str) -> str:
    return corpus_prefix(tenant_id) + filename


def snapshot_prefix(tenant_id: str) -> str:
    return f"{snapshots_root()}{tenant_id}/"


def snapshot_key(tenant_id: str, snapshot_id: str) -> str:
    return f"{snapshot_prefix(tenant_id)}{snapshot_id}.snapshot"


def manifest_key(tenant_id: str) -> str:
    return snapshot_prefix(tenant_id) + MANIFEST


def report_key(run_id: str) -> str:
    return f"{reports_root()}{run_id}/report.json"


def collection_name(tenant_id: str) -> str:
    return f"tenant_{tenant_id}"
