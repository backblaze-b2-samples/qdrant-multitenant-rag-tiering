import hashlib
import logging
import mimetypes
import re
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from urllib.parse import quote, urlencode

from app.config import settings
from app.repo import (
    delete_file,
    get_download_count,
    get_file_metadata,
    get_object_bytes,
    get_upload_stats,
    increment_download_count,
    list_files,
    open_object_stream,
    prewarm_listing,
)
from app.types import FileMetadata, FileMetadataDetail, UploadStats
from app.types.formatting import humanize_bytes
from app.types.stats import DailyUploadCount

logger = logging.getLogger(__name__)

_DANGEROUS_KEY_RE = re.compile(r"(\.\./|/\.\.|\\|%2e%2e|%00|\x00)")


class FileKeyError(Exception):
    """Raised when a file key is invalid."""

    def __init__(self, detail: str = "Invalid file key"):
        self.detail = detail
        super().__init__(detail)


class FileNotFoundServiceError(Exception):
    """Raised when a file is not found.

    Named distinctly from the built-in ``FileNotFoundError`` so it never
    shadows it at module scope — code here (and in callers) can rely on the
    built-in meaning what it says.
    """

    def __init__(self, detail: str = "File not found"):
        self.detail = detail
        super().__init__(detail)


class FileTooLargeServiceError(Exception):
    """Raised when an object is too large to recompute detailed metadata for.

    Detailed extraction downloads and buffers the whole object in memory, so
    objects above the upload size ceiling are refused rather than risking the
    API process's memory.
    """

    def __init__(self, detail: str = "File too large for detailed metadata"):
        self.detail = detail
        super().__init__(detail)


def validate_key(key: str) -> None:
    """Reject empty keys, path-traversal patterns, and — when configured — keys
    outside the allowed prefix.

    `settings.allowed_key_prefix` is empty by default, so any key shape is
    accepted (the by-key routes deliberately support arbitrary folders and
    reserved-word segments). Set it to confine key ops to a prefix like
    "uploads/" when the bucket also holds non-app data.
    """
    if not key:
        raise FileKeyError()
    if _DANGEROUS_KEY_RE.search(key.lower()):
        raise FileKeyError()
    prefix = settings.allowed_key_prefix
    if prefix and not key.startswith(prefix):
        raise FileKeyError()


def warm_listing_cache() -> None:
    """Warm the shared bucket-listing cache in the background.

    Called once at startup (see `main.lifespan`). Both `/files` and
    `/files/stats` need a full listing, so warming it here moves the one
    unavoidable slow scan off whichever page the first user happens to open.
    Never raises: a warm-up failure just means the first request pays as before.
    """
    logger.info("Warming bucket listing cache")
    prewarm_listing()


def get_files(prefix: str = "", limit: int = 100) -> list[FileMetadata]:
    # SECURITY: this lists the whole bucket (or `prefix`) with no per-user
    # filter — see docs/SECURITY.md. A multi-tenant clone must scope this to
    # the caller's own prefixes, or users see each other's files.
    if limit < 1 or limit > 1000:
        raise ValueError("Limit must be between 1 and 1000")
    # list_files paginates the whole prefix (not just the first 1000 keys).
    # Sort newest-first here so the endpoint's "recent uploads" contract holds
    # regardless of repo ordering, then slice to the requested limit.
    files = list_files(prefix=prefix)
    files.sort(key=lambda f: f.uploaded_at, reverse=True)
    return files[:limit]


def get_stats() -> UploadStats:
    data = get_upload_stats()
    data["total_downloads"] = get_download_count()
    return UploadStats(**data)


def get_file(key: str) -> FileMetadata:
    validate_key(key)
    metadata = get_file_metadata(key)
    if not metadata:
        raise FileNotFoundServiceError()
    return metadata


def get_file_detail(key: str) -> FileMetadataDetail:
    """Recompute checksums for a stored object by re-reading it.

    Buffers the whole object, so it heads first and refuses objects above
    `max_file_size`. Raises FileKeyError, FileNotFoundServiceError or
    FileTooLargeServiceError.
    """
    validate_key(key)
    metadata = get_file_metadata(key)
    if not metadata:
        raise FileNotFoundServiceError()
    if metadata.size_bytes > settings.max_file_size:
        raise FileTooLargeServiceError(
            "File too large for detailed metadata. "
            f"Max size: {humanize_bytes(settings.max_file_size)}"
        )
    data = get_object_bytes(key)
    filename = metadata.filename
    return FileMetadataDetail(
        filename=filename,
        size_bytes=len(data),
        size_human=humanize_bytes(len(data)),
        mime_type=metadata.content_type
        or mimetypes.guess_type(filename)[0]
        or "application/octet-stream",
        extension=filename.rsplit(".", 1)[1].lower() if "." in filename else "",
        md5=hashlib.md5(data, usedforsecurity=False).hexdigest(),
        sha256=hashlib.sha256(data).hexdigest(),
        uploaded_at=metadata.uploaded_at,
    )


CONTENT_PATH = "/files-by-key/content"
DISPOSITIONS = ("attachment", "inline")


def _content_url(key: str, disposition: str) -> str:
    """API-relative content-proxy URL. The browser never sees a B2 URL."""
    validate_key(key)
    if not get_file_metadata(key):
        raise FileNotFoundServiceError()
    return f"{CONTENT_PATH}?{urlencode({'key': key, 'disposition': disposition})}"


def get_preview_url(key: str) -> str:
    """Inline content URL. Opening a preview does not count as a download."""
    return _content_url(key, "inline")


def get_download_url(key: str) -> str:
    """Attachment content URL, recorded as a download."""
    url = _content_url(key, "attachment")
    increment_download_count()
    return url


def open_content(key: str, disposition: str) -> tuple[Iterator[bytes], str, dict[str, str]]:
    """Stream an object through the API: (chunks, content type, headers).

    The bytes travel B2 -> this API's S3 client (custom user agent) -> browser,
    instead of the browser fetching a presigned URL directly from B2.
    """
    if disposition not in DISPOSITIONS:
        raise FileKeyError(f"disposition must be one of {DISPOSITIONS}")
    validate_key(key)
    metadata = get_file_metadata(key)
    if not metadata:
        raise FileNotFoundServiceError()
    chunks, content_type = open_object_stream(key)
    encoded = quote(metadata.filename, safe="")
    headers = {
        "Content-Disposition": (
            f"{disposition}; filename=\"{encoded}\"; filename*=UTF-8''{encoded}"
        ),
        "Content-Length": str(metadata.size_bytes),
        "Cache-Control": "private, max-age=60",
    }
    return chunks, content_type, headers


def remove_file(key: str) -> None:
    """Validate key and delete the file. Raises RuntimeError on B2 failure."""
    validate_key(key)
    delete_file(key)


def get_upload_activity(days: int = 7) -> list[DailyUploadCount]:
    """Return daily upload counts for the last N days."""
    files = list_files(prefix="")
    today = datetime.now(UTC).date()
    cutoff = today - timedelta(days=days - 1)

    counts: dict[str, int] = defaultdict(int)
    for f in files:
        d = f.uploaded_at.date()
        if d >= cutoff:
            counts[d.isoformat()] += 1

    # Fill in missing days with zero
    return [
        DailyUploadCount(
            date=(cutoff + timedelta(days=i)).isoformat(),
            uploads=counts.get((cutoff + timedelta(days=i)).isoformat(), 0),
        )
        for i in range(days)
    ]
