from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Any, Protocol

from fastapi import Depends, HTTPException, status

from app.core.config import get_settings

logger = logging.getLogger(__name__)


_SUFFIX_TO_CONTENT_TYPE: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


def _s3_error_code(exc: BaseException) -> str | None:
    """Best-effort extraction of botocore ClientError's error code."""
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return None
    error = response.get("Error")
    if not isinstance(error, dict):
        return None
    code = error.get("Code")
    return code if isinstance(code, str) else None


class ImageStorageError(RuntimeError):
    """Raised when the storage backend cannot fulfill a request."""


class ImageNotFoundError(ImageStorageError):
    """Raised when a stored image is missing from the backend."""


class ImageStorageIntegrityError(ImageStorageError):
    """Raised when a stored image's storage key or stored bytes are invalid.

    Distinct from a transient backend failure: the DB row itself is bad
    (e.g. path-traversal storage key, unsupported file extension), so a
    retry will not help.
    """


class ImageStorage(Protocol):
    """Backend-agnostic image persistence.

    Implementations must be safe to use as a FastAPI dependency (cheap to
    construct or memoised). The contract is intentionally narrow so a future
    S3-backed implementation can drop in without touching call sites.
    """

    def save(
        self,
        *,
        repair_request_id: str,
        image_id: str,
        suffix: str,
        content: bytes,
    ) -> str:
        """Persist ``content`` and return an opaque storage key.

        The returned key is what callers should record in the database; it must
        be accepted by :meth:`open` and :meth:`cleanup` later.
        """

    def open(self, storage_key: str) -> tuple[bytes, str]:
        """Read the bytes for ``storage_key`` and return ``(content, content_type)``."""

    def cleanup(self, storage_keys: list[str]) -> None:
        """Best-effort delete used to roll back orphaned uploads.

        Implementations must not raise; cleanup is called from a ``finally``
        block where masking the original exception would lose information.
        """


class LocalImageStorage:
    """Filesystem-backed :class:`ImageStorage` rooted at ``base_dir``.

    Storage keys are POSIX-style relative paths (``"<rr-id>/<img-id>.png"``) so
    they remain stable when the deployment root changes and translate cleanly
    to S3 object keys during a future migration.
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

    def save(
        self,
        *,
        repair_request_id: str,
        image_id: str,
        suffix: str,
        content: bytes,
    ) -> str:
        key = f"{repair_request_id}/{image_id}{suffix}"
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return key

    def open(self, storage_key: str) -> tuple[bytes, str]:
        target = self._resolve(storage_key)
        try:
            content = target.read_bytes()
        except FileNotFoundError as exc:
            raise ImageNotFoundError(storage_key) from exc
        except OSError as exc:
            raise ImageStorageError(f"Unable to read {storage_key!r}") from exc
        content_type = _SUFFIX_TO_CONTENT_TYPE.get(target.suffix.lower())
        if content_type is None:
            raise ImageStorageIntegrityError(
                f"Unsupported stored image suffix {target.suffix!r}"
            )
        return content, content_type

    def cleanup(self, storage_keys: list[str]) -> None:
        for key in storage_keys:
            try:
                self._resolve(key).unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Failed to remove orphaned upload %s: %s", key, exc)

    def _resolve(self, storage_key: str) -> Path:
        # Reject keys that try to escape the base directory. Keys are minted by
        # this service, so a traversal here means a bug or a tampered DB row.
        candidate = (self._base_dir / storage_key).resolve()
        base = self._base_dir.resolve()
        if base != candidate and base not in candidate.parents:
            raise ImageStorageIntegrityError(
                f"Storage key escapes base directory: {storage_key!r}"
            )
        return candidate


class S3ImageStorage:
    """S3-backed :class:`ImageStorage` for production deployments.

    Storage keys remain POSIX-style relative paths (``"<rr-id>/<img-id>.png"``)
    so the same DB rows work whether the bucket is read locally or in AWS.
    The optional ``key_prefix`` namespaces objects under ``<prefix>/<key>``
    so a single bucket can host multiple environments.
    """

    def __init__(self, *, bucket: str, key_prefix: str = "", client: Any = None) -> None:
        if not bucket:
            raise ImageStorageError("S3 bucket name is required for S3ImageStorage.")
        self._bucket = bucket
        self._key_prefix = key_prefix.strip("/")
        # Lazy-import so dev/test runs without boto3 installed succeed when
        # the local backend is selected. Tests inject a fake client via the
        # `client` parameter to avoid the import + AWS credential discovery.
        if client is None:
            import boto3

            client = boto3.client("s3")
        self._client = client

    def save(
        self,
        *,
        repair_request_id: str,
        image_id: str,
        suffix: str,
        content: bytes,
    ) -> str:
        key = f"{repair_request_id}/{image_id}{suffix}"
        content_type = _SUFFIX_TO_CONTENT_TYPE.get(suffix.lower(), "application/octet-stream")
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=self._object_key(key),
                Body=content,
                ContentType=content_type,
            )
        except Exception as exc:  # boto3 ClientError, ConnectionError, etc.
            raise ImageStorageError(f"Failed to upload {key!r} to S3.") from exc
        return key

    def open(self, storage_key: str) -> tuple[bytes, str]:
        try:
            response = self._client.get_object(
                Bucket=self._bucket,
                Key=self._object_key(storage_key),
            )
        except Exception as exc:
            # boto3 raises ClientError with "NoSuchKey" code for missing
            # objects. We cannot import the boto3 type here without making
            # boto3 a hard dependency, so we duck-type on the .response
            # attribute that botocore.exceptions.ClientError exposes.
            if _s3_error_code(exc) == "NoSuchKey":
                raise ImageNotFoundError(storage_key) from exc
            raise ImageStorageError(f"Unable to read {storage_key!r} from S3.") from exc

        suffix = Path(storage_key).suffix.lower()
        content_type = _SUFFIX_TO_CONTENT_TYPE.get(suffix)
        if content_type is None:
            raise ImageStorageIntegrityError(
                f"Unsupported stored image suffix {suffix!r}"
            )
        return response["Body"].read(), content_type

    def cleanup(self, storage_keys: list[str]) -> None:
        for key in storage_keys:
            try:
                self._client.delete_object(Bucket=self._bucket, Key=self._object_key(key))
            except Exception as exc:
                logger.warning("Failed to remove orphaned S3 upload %s: %s", key, exc)

    def _object_key(self, storage_key: str) -> str:
        if self._key_prefix:
            return f"{self._key_prefix}/{storage_key}"
        return storage_key


def get_image_storage() -> ImageStorage:
    settings = get_settings()
    backend = settings.repair_image_backend.lower()
    if backend == "s3":
        return S3ImageStorage(
            bucket=settings.repair_s3_bucket,
            key_prefix=settings.repair_s3_prefix,
        )
    if backend != "local":
        # Fail loud on misconfiguration rather than silently fall back -
        # silent fallback is the kind of bug that wastes hours during a
        # production deploy.
        raise ImageStorageError(
            f"Unknown REPAIR_IMAGE_BACKEND {settings.repair_image_backend!r}; "
            "expected 'local' or 's3'."
        )
    return LocalImageStorage(Path(settings.repair_upload_dir))


ImageStorageDep = Annotated[ImageStorage, Depends(get_image_storage)]


def image_storage_error_to_http(exc: ImageStorageError) -> HTTPException:
    if isinstance(exc, ImageNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found.")
    if isinstance(exc, ImageStorageIntegrityError):
        # Permanent data error — retrying won't help; surface 500 so it gets
        # operator attention instead of pretending it's a transient backend.
        logger.error("Image storage integrity error: %s", exc)
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Image storage integrity error.",
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Unable to retrieve image. Please try again later.",
    )
