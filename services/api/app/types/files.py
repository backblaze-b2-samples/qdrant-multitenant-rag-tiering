from datetime import datetime

from pydantic import Field

from app.types.base import ResponseModel


class FileMetadata(ResponseModel):
    """One stored object as the file list and the by-key metadata route see it."""

    key: str
    filename: str
    folder: str
    size_bytes: int
    size_human: str
    content_type: str
    uploaded_at: datetime
    url: str | None = Field(
        default=None,
        description=(
            "Public object URL, set only when B2_PUBLIC_URL_BASE is configured "
            "and the bucket is public. Null otherwise: the UI asks the API "
            "for a proxied content URL instead."
        ),
    )


class FileMetadataDetail(ResponseModel):
    """Checksums recomputed on demand by re-reading the stored object."""

    filename: str
    size_bytes: int
    size_human: str
    mime_type: str
    extension: str
    md5: str
    sha256: str
    uploaded_at: datetime


class FileUrlResponse(ResponseModel):
    """Where the browser fetches one object's bytes, through this API.

    No presigned B2 URL is ever handed to the browser: every byte goes through
    the backend's S3 client, which carries the app's custom user agent.
    """

    url: str = Field(
        description=(
            "API-relative URL of the content proxy (`/files-by-key/content`). "
            "Download URLs ask for an attachment disposition; preview URLs ask "
            "for inline so a PDF or text file renders in place."
        )
    )


class DeleteFileResponse(ResponseModel):
    """Acknowledgement that one object was removed from the bucket."""

    deleted: bool
    key: str
