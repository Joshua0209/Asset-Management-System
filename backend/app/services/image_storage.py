from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Protocol

from fastapi import Depends, HTTPException, status

from app.core.config import get_settings

logger = logging.getLogger(__name__)


_SUFFIX_TO_CONTENT_TYPE: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


class ImageStorageError(RuntimeError):
    """Raised when the storage backend cannot fulfill a request."""


class ImageNotFoundError(ImageStorageError):
    """Raised when a stored image is missing from the backend."""


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
            raise ImageStorageError(f"Unsupported stored image suffix {target.suffix!r}")
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
            raise ImageStorageError(f"Storage key escapes base directory: {storage_key!r}")
        return candidate


def get_image_storage() -> ImageStorage:
    return LocalImageStorage(Path(get_settings().repair_upload_dir))


ImageStorageDep = Annotated[ImageStorage, Depends(get_image_storage)]


def image_storage_error_to_http(exc: ImageStorageError) -> HTTPException:
    if isinstance(exc, ImageNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found.")
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Unable to retrieve image. Please try again later.",
    )
