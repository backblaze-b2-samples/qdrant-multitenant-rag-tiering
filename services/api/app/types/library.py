"""Library view: the app's own objects under RAG_PREFIX, grouped by kind."""

from datetime import datetime
from typing import Literal

from app.types.base import ResponseModel

LibraryKind = Literal["corpus", "snapshots", "reports"]


class LibraryEntry(ResponseModel):
    key: str
    tenant_id: str | None
    kind: LibraryKind
    size_bytes: int
    last_modified: datetime
