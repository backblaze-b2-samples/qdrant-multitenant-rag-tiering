"""Object-level B2 primitives: body reads, streams, writes, multipart, deletes.

Kept apart from `b2_client.py` (client factory, bucket listing, file metadata)
to stay under the 300-line ceiling. Every call reuses the one cached S3 client
from `b2_client`, so every request carries the app's custom user agent.

`B2ObjectStore` implements `app.types.ports.ObjectStorePort`; the snapshot
orchestration in `snapshot_store.py` and every service use it through that
port, which is what lets the offline tests swap in an in-memory store.
"""

from collections.abc import Iterator

from botocore.exceptions import BotoCoreError, ClientError

from app.config import settings
from app.repo.b2_client import get_s3_client
from app.repo.list_cache import invalidate as _invalidate_list_cache
from app.types.ports import ObjectEntry

_MISSING = ("404", "NoSuchKey", "NotFound")


def _is_missing(error: ClientError) -> bool:
    return error.response.get("Error", {}).get("Code", "") in _MISSING


def get_object_bytes(key: str) -> bytes:
    """Download an object's full body into memory.

    Buffers the whole object, so callers MUST size-guard before calling (see
    `service.files.get_file_detail`). Raises RuntimeError on any S3 failure,
    including a mid-stream BotoCoreError, which is not a ClientError.
    """
    client = get_s3_client()
    try:
        response = client.get_object(Bucket=settings.b2_bucket_name, Key=key)
        return response["Body"].read()
    except (ClientError, BotoCoreError) as e:
        raise RuntimeError(f"B2 get_object failed for '{key}': {e}") from e


def open_object_stream(key: str, chunk_size: int = 64 * 1024) -> tuple[Iterator[bytes], str]:
    """Return (body chunks, content type) for streaming an object to a client."""
    client = get_s3_client()
    try:
        response = client.get_object(Bucket=settings.b2_bucket_name, Key=key)
    except (ClientError, BotoCoreError) as e:
        raise RuntimeError(f"B2 get_object failed for '{key}': {e}") from e
    content_type = response.get("ContentType") or "application/octet-stream"
    return response["Body"].iter_chunks(chunk_size), content_type


class B2ObjectStore:
    """The `ObjectStorePort` over the shared boto3 client. Raises RuntimeError."""

    @property
    def _bucket(self) -> str:
        return settings.b2_bucket_name

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        try:
            get_s3_client().put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
            )
        except (ClientError, BotoCoreError) as e:
            raise RuntimeError(f"B2 put_object failed for '{key}': {e}") from e
        _invalidate_list_cache()

    def get_bytes(self, key: str) -> bytes | None:
        try:
            response = get_s3_client().get_object(Bucket=self._bucket, Key=key)
            return response["Body"].read()
        except ClientError as e:
            if _is_missing(e):
                return None
            raise RuntimeError(f"B2 get_object failed for '{key}': {e}") from e
        except BotoCoreError as e:
            raise RuntimeError(f"B2 get_object failed for '{key}': {e}") from e

    def head_size(self, key: str) -> int | None:
        try:
            response = get_s3_client().head_object(Bucket=self._bucket, Key=key)
        except ClientError as e:
            if _is_missing(e):
                return None
            raise RuntimeError(f"B2 head_object failed for '{key}': {e}") from e
        return int(response["ContentLength"])

    def list_objects(self, prefix: str) -> list[ObjectEntry]:
        client = get_s3_client()
        kwargs: dict = {"Bucket": self._bucket, "Prefix": prefix, "MaxKeys": 1000}
        entries: list[ObjectEntry] = []
        try:
            while True:
                response = client.list_objects_v2(**kwargs)
                entries.extend(
                    ObjectEntry(
                        key=obj["Key"], size_bytes=obj["Size"], last_modified=obj["LastModified"]
                    )
                    for obj in response.get("Contents", [])
                )
                if not response.get("IsTruncated"):
                    return entries
                kwargs["ContinuationToken"] = response["NextContinuationToken"]
        except (ClientError, BotoCoreError) as e:
            raise RuntimeError(f"B2 list failed for prefix '{prefix}': {e}") from e

    def delete_keys(self, keys: list[str]) -> list[str]:
        """Delete exactly these keys (batched by 1000). Returns the deleted keys."""
        client = get_s3_client()
        deleted: list[str] = []
        for start in range(0, len(keys), 1000):
            batch = keys[start : start + 1000]
            try:
                response = client.delete_objects(
                    Bucket=self._bucket,
                    Delete={"Objects": [{"Key": k} for k in batch], "Quiet": False},
                )
            except (ClientError, BotoCoreError) as e:
                raise RuntimeError(f"B2 delete_objects failed: {e}") from e
            deleted.extend(d["Key"] for d in response.get("Deleted", []))
            if response.get("Errors"):
                first = response["Errors"][0]
                raise RuntimeError(f"B2 refused to delete '{first['Key']}': {first['Message']}")
        _invalidate_list_cache()
        return deleted

    def iter_object(self, key: str, chunk_size: int) -> Iterator[bytes]:
        try:
            response = get_s3_client().get_object(Bucket=self._bucket, Key=key)
            yield from response["Body"].iter_chunks(chunk_size)
        except (ClientError, BotoCoreError) as e:
            raise RuntimeError(f"B2 get_object failed for '{key}': {e}") from e

    def create_multipart(self, key: str, content_type: str) -> str:
        try:
            response = get_s3_client().create_multipart_upload(
                Bucket=self._bucket, Key=key, ContentType=content_type
            )
        except (ClientError, BotoCoreError) as e:
            raise RuntimeError(f"B2 create_multipart_upload failed for '{key}': {e}") from e
        return response["UploadId"]

    def upload_part(self, key: str, upload_id: str, part_number: int, data: bytes) -> str:
        try:
            response = get_s3_client().upload_part(
                Bucket=self._bucket,
                Key=key,
                UploadId=upload_id,
                PartNumber=part_number,
                Body=data,
            )
        except (ClientError, BotoCoreError) as e:
            raise RuntimeError(f"B2 upload_part {part_number} failed for '{key}': {e}") from e
        return response["ETag"]

    def complete_multipart(
        self, key: str, upload_id: str, parts: list[tuple[int, str]]
    ) -> None:
        try:
            get_s3_client().complete_multipart_upload(
                Bucket=self._bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={"Parts": [{"PartNumber": n, "ETag": e} for n, e in parts]},
            )
        except (ClientError, BotoCoreError) as e:
            raise RuntimeError(f"B2 complete_multipart_upload failed for '{key}': {e}") from e
        _invalidate_list_cache()

    def abort_multipart(self, key: str, upload_id: str) -> None:
        try:
            get_s3_client().abort_multipart_upload(
                Bucket=self._bucket, Key=key, UploadId=upload_id
            )
        except (ClientError, BotoCoreError) as e:
            raise RuntimeError(f"B2 abort_multipart_upload failed for '{key}': {e}") from e
