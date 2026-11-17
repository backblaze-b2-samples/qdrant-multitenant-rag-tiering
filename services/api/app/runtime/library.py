"""Library route: the app's own objects under RAG_PREFIX."""

from typing import Literal

from fastapi import APIRouter

from app.runtime.errors import http_errors
from app.service.library import list_library
from app.types.library import LibraryEntry

router = APIRouter()


@router.get("/library", response_model=list[LibraryEntry])
def library_endpoint(
    tenant_id: str | None = None,
    kind: Literal["corpus", "snapshots", "reports"] | None = None,
):
    with http_errors():
        return list_library(tenant_id, kind)
