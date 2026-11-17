"""The Library view: every object this app wrote, grouped by tenant and kind."""

from app.service import deps
from app.service.errors import InvalidInput
from app.service.validation import validate_tenant_id
from app.types.library import LibraryEntry

KINDS = ("corpus", "snapshots", "reports")


def list_library(tenant_id: str | None = None, kind: str | None = None) -> list[LibraryEntry]:
    if tenant_id:
        validate_tenant_id(tenant_id)
    if kind is not None and kind not in KINDS:
        raise InvalidInput(f"kind must be one of {', '.join(KINDS)}")
    root = deps.prefix()
    entries: list[LibraryEntry] = []
    for obj in deps.store().list_objects(root):
        parts = obj.key[len(root) :].split("/")
        if len(parts) < 3 or parts[0] not in KINDS:
            continue
        entry_kind = parts[0]
        owner = None if entry_kind == "reports" else parts[1]
        if kind and entry_kind != kind:
            continue
        if tenant_id and owner != tenant_id:
            continue
        entries.append(
            LibraryEntry(
                key=obj.key,
                tenant_id=owner,
                kind=entry_kind,
                size_bytes=obj.size_bytes,
                last_modified=obj.last_modified,
            )
        )
    return sorted(entries, key=lambda e: (e.tenant_id or "~", e.kind, e.key))
