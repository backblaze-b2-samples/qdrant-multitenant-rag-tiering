"""Prune superseded snapshots. Opt-in twice; the manifest's target is untouchable."""

from collections import defaultdict

from app.config import settings
from app.repo import snapshot_store
from app.service import deps
from app.service.errors import Conflict
from app.types.ports import ObjectEntry
from app.types.tiering import PruneRequest, PruneResult


def prune_snapshots(request: PruneRequest) -> PruneResult:
    """List (and with `apply`, delete) all but the newest `keep_last` snapshots.

    Raises Conflict (409) when SNAPSHOT_PRUNE_ENABLED is false. The object that
    `latest.json` points at is never a candidate, whatever its age.
    """
    if not settings.snapshot_prune_enabled:
        raise Conflict(
            "Snapshot pruning is disabled. Set SNAPSHOT_PRUNE_ENABLED=true and "
            "restart the API to allow it."
        )
    store = deps.store()
    root = deps.snapshots_root()
    by_tenant: dict[str, list[ObjectEntry]] = defaultdict(list)
    with_manifest: set[str] = set()
    for entry in store.list_objects(root):
        tenant_id = entry.key[len(root) :].split("/")[0]
        if entry.key.endswith(".snapshot"):
            by_tenant[tenant_id].append(entry)
        elif entry.key.endswith("/" + deps.MANIFEST):
            with_manifest.add(tenant_id)

    candidates: list[str] = []
    for tenant_id, entries in sorted(by_tenant.items()):
        protected = None
        if tenant_id in with_manifest:
            manifest = snapshot_store.get_manifest(store, deps.manifest_key(tenant_id))
            protected = manifest.snapshot_key if manifest else None
        newest_first = sorted(entries, key=lambda e: (e.last_modified, e.key), reverse=True)
        candidates += [
            e.key for e in newest_first[request.keep_last :] if e.key != protected
        ]

    deleted = store.delete_keys(candidates) if request.apply and candidates else []
    return PruneResult(
        enabled=True, applied=request.apply, candidates=candidates, deleted=deleted
    )
