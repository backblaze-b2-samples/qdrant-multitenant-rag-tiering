"""Map service errors to HTTP responses in one place."""

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException

from app.service.errors import ServiceError


@contextmanager
def http_errors() -> Iterator[None]:
    """Turn a `ServiceError` into an `HTTPException` with its own status code."""
    try:
        yield
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from None
