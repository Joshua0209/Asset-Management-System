"""Unit tests for ``app/services/image_storage.py``.

Targets the bits that ``test_images.py`` cannot reach through the HTTP
surface: path-traversal rejection (CWE-22), unsupported-suffix integrity
errors, cleanup error swallowing, and the exception-to-HTTP mapping helper.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.services.image_storage import (
    ImageNotFoundError,
    ImageStorageError,
    ImageStorageIntegrityError,
    LocalImageStorage,
    image_storage_error_to_http,
)


class TestLocalImageStoragePathTraversal:
    """CWE-22 guard inside ``_resolve``. Storage keys are minted by the service
    so a traversal in production means a tampered DB row or a bug — either way
    we refuse rather than serve an arbitrary file from the host."""

    def test_open_rejects_relative_traversal_outside_base(
        self, tmp_path: Path
    ) -> None:
        storage = LocalImageStorage(tmp_path)

        with pytest.raises(ImageStorageIntegrityError, match="escapes base directory"):
            storage.open("../../../etc/passwd")

    def test_open_rejects_absolute_path_storage_key(self, tmp_path: Path) -> None:
        storage = LocalImageStorage(tmp_path)

        # ``Path("/etc/passwd").resolve()`` won't be a child of tmp_path.
        with pytest.raises(ImageStorageIntegrityError, match="escapes base directory"):
            storage.open("/etc/passwd")


class TestLocalImageStorageOpenErrors:
    """The ``open`` failure paths above ``ImageNotFoundError`` — both the
    OSError-on-read branch (line 102-103) and the unsupported-suffix branch
    (line 106) must surface typed errors, not bubble raw OS exceptions."""

    def test_read_oserror_raises_image_storage_error(self, tmp_path: Path) -> None:
        storage = LocalImageStorage(tmp_path)
        storage_key = "rr-1/img-1.png"
        target = tmp_path / storage_key
        target.parent.mkdir(parents=True)
        target.write_bytes(b"payload")

        # Anything other than ``FileNotFoundError`` must surface as the
        # generic ``ImageStorageError`` (it's transient — retry may help).
        with patch.object(Path, "read_bytes", side_effect=OSError("EIO")):
            with pytest.raises(ImageStorageError) as excinfo:
                storage.open(storage_key)

        # Must NOT be the more specific NotFound subclass — that would map to
        # 404 in ``image_storage_error_to_http`` and hide a real outage.
        assert not isinstance(excinfo.value, ImageNotFoundError)
        assert not isinstance(excinfo.value, ImageStorageIntegrityError)

    def test_unsupported_suffix_raises_integrity_error(self, tmp_path: Path) -> None:
        storage = LocalImageStorage(tmp_path)
        # Suffix not in ``_SUFFIX_TO_CONTENT_TYPE`` — the DB shouldn't have
        # produced this, so it's a data-integrity error, not a transient one.
        storage_key = "rr-1/img-1.gif"
        target = tmp_path / storage_key
        target.parent.mkdir(parents=True)
        target.write_bytes(b"gif-bytes")

        with pytest.raises(ImageStorageIntegrityError, match="Unsupported stored image suffix"):
            storage.open(storage_key)


class TestLocalImageStorageCleanup:
    """``cleanup`` runs from a ``finally`` block in the submit endpoint; it
    must never raise, otherwise it would mask the in-flight exception."""

    def test_cleanup_swallows_oserror_and_does_not_raise(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        storage = LocalImageStorage(tmp_path)
        storage_key = "rr-1/img-1.png"
        target = tmp_path / storage_key
        target.parent.mkdir(parents=True)
        target.write_bytes(b"payload")

        with patch.object(Path, "unlink", side_effect=OSError("EACCES")):
            # Must not raise — that's the contract.
            storage.cleanup([storage_key])

        # And it must log the failure so the orphan can be reconciled later.
        assert any("Failed to remove orphaned upload" in r.message for r in caplog.records)

    def test_cleanup_silently_skips_already_missing_file(self, tmp_path: Path) -> None:
        storage = LocalImageStorage(tmp_path)
        # File never existed; ``missing_ok=True`` should make this a no-op.
        storage.cleanup(["rr-1/never-existed.png"])


class TestImageStorageErrorToHttp:
    """The error → HTTP mapping is the contract image endpoints rely on to
    choose between 404 / 500 / 503. Each branch needs a direct test because
    the integration coverage only fires the 404 path naturally."""

    def test_image_not_found_maps_to_404(self) -> None:
        result = image_storage_error_to_http(ImageNotFoundError("missing"))
        assert isinstance(result, HTTPException)
        assert result.status_code == 404

    def test_image_storage_integrity_error_maps_to_500(self) -> None:
        # Data-integrity errors are permanent — operator must intervene.
        result = image_storage_error_to_http(
            ImageStorageIntegrityError("bad storage key")
        )
        assert isinstance(result, HTTPException)
        assert result.status_code == 500

    def test_generic_image_storage_error_maps_to_503(self) -> None:
        # Transient backend failure — caller may retry.
        result = image_storage_error_to_http(ImageStorageError("backend timeout"))
        assert isinstance(result, HTTPException)
        assert result.status_code == 503
