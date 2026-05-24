"""Unit tests for ``app/services/image_storage.py``.

Targets the bits that ``test_images.py`` cannot reach through the HTTP
surface: path-traversal rejection (CWE-22), unsupported-suffix integrity
errors, cleanup error swallowing, the exception-to-HTTP mapping helper,
and the production S3 backend (which never runs locally so all its
branches need direct coverage with an injected fake client).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.services.image_storage import (
    ImageNotFoundError,
    ImageStorageError,
    ImageStorageIntegrityError,
    LocalImageStorage,
    S3ImageStorage,
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


class _FakeBotocoreClientError(Exception):
    """Duck-typed stand-in for botocore.exceptions.ClientError.

    ``S3ImageStorage._s3_error_code`` reads ``exc.response["Error"]["Code"]``
    without importing boto3, so any exception with that shape exercises the
    NoSuchKey discrimination branch.
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class _FakeS3Client:
    """Records put/get/delete calls and lets each be overridden per-test."""

    def __init__(
        self,
        *,
        get_response: dict[str, Any] | None = None,
        put_side_effect: BaseException | None = None,
        get_side_effect: BaseException | None = None,
        delete_side_effect: BaseException | None = None,
    ) -> None:
        self.put_calls: list[dict[str, Any]] = []
        self.get_calls: list[dict[str, Any]] = []
        self.delete_calls: list[dict[str, Any]] = []
        self._get_response = get_response
        self._put_side_effect = put_side_effect
        self._get_side_effect = get_side_effect
        self._delete_side_effect = delete_side_effect

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        self.put_calls.append(kwargs)
        if self._put_side_effect is not None:
            raise self._put_side_effect
        return {}

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        self.get_calls.append(kwargs)
        if self._get_side_effect is not None:
            raise self._get_side_effect
        assert self._get_response is not None
        return self._get_response

    def delete_object(self, **kwargs: Any) -> dict[str, Any]:
        self.delete_calls.append(kwargs)
        if self._delete_side_effect is not None:
            raise self._delete_side_effect
        return {}


class _BodyStub:
    """Minimal boto3-shaped Body — only ``read()`` is part of the contract."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload


class TestS3ImageStorageInit:
    def test_rejects_empty_bucket(self) -> None:
        with pytest.raises(ImageStorageError, match="bucket name is required"):
            S3ImageStorage(bucket="", client=_FakeS3Client())

    def test_strips_slashes_from_key_prefix(self) -> None:
        # Prefix is joined as ``f"{prefix}/{key}"`` so a leading/trailing slash
        # would produce ``//`` in S3 keys, which are valid but break parity with
        # the local backend's POSIX-style keys.
        storage = S3ImageStorage(
            bucket="b", key_prefix="/env/prod/", client=_FakeS3Client()
        )
        assert storage._object_key("rr-1/img-1.png") == "env/prod/rr-1/img-1.png"

    def test_no_prefix_returns_raw_key(self) -> None:
        storage = S3ImageStorage(bucket="b", client=_FakeS3Client())
        assert storage._object_key("rr-1/img-1.png") == "rr-1/img-1.png"


class TestS3ImageStorageSave:
    def test_uploads_with_correct_bucket_key_and_content_type(self) -> None:
        client = _FakeS3Client()
        storage = S3ImageStorage(bucket="ams-prod", key_prefix="env/prod", client=client)

        returned_key = storage.save(
            repair_request_id="rr-1",
            image_id="img-1",
            suffix=".png",
            content=b"png-bytes",
        )

        # Returned storage_key is the prefix-FREE relative key — that's what the
        # DB stores so a future bucket/prefix change doesn't require a migration.
        assert returned_key == "rr-1/img-1.png"
        assert client.put_calls == [
            {
                "Bucket": "ams-prod",
                "Key": "env/prod/rr-1/img-1.png",
                "Body": b"png-bytes",
                "ContentType": "image/png",
            }
        ]

    def test_unknown_suffix_falls_back_to_octet_stream(self) -> None:
        # Mirrors S3ImageStorage.save's ``_SUFFIX_TO_CONTENT_TYPE.get(..., default)``.
        # If this drifts the wrong way (e.g. raises) we'd silently lose the
        # ability to store the bytes at all.
        client = _FakeS3Client()
        storage = S3ImageStorage(bucket="b", client=client)
        storage.save(repair_request_id="rr-1", image_id="img-1", suffix=".bin", content=b"x")
        assert client.put_calls[0]["ContentType"] == "application/octet-stream"

    def test_wraps_boto3_exception_as_image_storage_error(self) -> None:
        # Any boto3 failure (ClientError, ConnectionError, EndpointConnectionError)
        # must surface as the typed ImageStorageError so the endpoint's
        # 503-mapping handler catches it.
        client = _FakeS3Client(put_side_effect=RuntimeError("network down"))
        storage = S3ImageStorage(bucket="b", client=client)

        with pytest.raises(ImageStorageError, match="Failed to upload"):
            storage.save(
                repair_request_id="rr-1",
                image_id="img-1",
                suffix=".png",
                content=b"x",
            )


class TestS3ImageStorageOpen:
    def test_returns_bytes_and_content_type_on_happy_path(self) -> None:
        client = _FakeS3Client(get_response={"Body": _BodyStub(b"png-bytes")})
        storage = S3ImageStorage(bucket="b", key_prefix="env/prod", client=client)

        content, content_type = storage.open("rr-1/img-1.png")

        assert content == b"png-bytes"
        assert content_type == "image/png"
        assert client.get_calls == [{"Bucket": "b", "Key": "env/prod/rr-1/img-1.png"}]

    def test_no_such_key_maps_to_image_not_found_error(self) -> None:
        # Duck-typed branch of S3ImageStorage.open — botocore.ClientError has
        # ``exc.response["Error"]["Code"] == "NoSuchKey"``, and that specific
        # path must surface the more-specific subclass so the endpoint returns
        # 404 (not 503). A regression that drops ``_s3_error_code`` would map
        # this to the generic 503 branch and silently degrade.
        client = _FakeS3Client(get_side_effect=_FakeBotocoreClientError("NoSuchKey"))
        storage = S3ImageStorage(bucket="b", client=client)

        with pytest.raises(ImageNotFoundError):
            storage.open("rr-1/img-1.png")

    def test_other_client_error_maps_to_generic_storage_error(self) -> None:
        client = _FakeS3Client(get_side_effect=_FakeBotocoreClientError("AccessDenied"))
        storage = S3ImageStorage(bucket="b", client=client)

        with pytest.raises(ImageStorageError) as excinfo:
            storage.open("rr-1/img-1.png")

        # Must NOT be the NotFound subclass — that would map to 404 and hide
        # an IAM/permissions outage.
        assert not isinstance(excinfo.value, ImageNotFoundError)

    def test_non_client_exception_maps_to_generic_storage_error(self) -> None:
        # Anything without the .response dict (e.g. ConnectionError) must still
        # be caught — S3ImageStorage.open's bare ``except Exception`` should
        # surface a typed error rather than bubble the raw exception.
        client = _FakeS3Client(get_side_effect=RuntimeError("connection reset"))
        storage = S3ImageStorage(bucket="b", client=client)

        with pytest.raises(ImageStorageError):
            storage.open("rr-1/img-1.png")

    def test_unsupported_suffix_raises_integrity_error(self) -> None:
        # Same contract as LocalImageStorage: an unsupported suffix on a stored
        # row is a data-integrity failure, not a transient one.
        client = _FakeS3Client(get_response={"Body": _BodyStub(b"gif-bytes")})
        storage = S3ImageStorage(bucket="b", client=client)

        with pytest.raises(ImageStorageIntegrityError, match="Unsupported stored image suffix"):
            storage.open("rr-1/img-1.gif")


class TestS3ImageStorageCleanup:
    def test_deletes_each_key_with_prefix_applied(self) -> None:
        client = _FakeS3Client()
        storage = S3ImageStorage(bucket="b", key_prefix="env/prod", client=client)

        storage.cleanup(["rr-1/img-1.png", "rr-1/img-2.png"])

        assert client.delete_calls == [
            {"Bucket": "b", "Key": "env/prod/rr-1/img-1.png"},
            {"Bucket": "b", "Key": "env/prod/rr-1/img-2.png"},
        ]

    def test_swallows_boto3_exception_and_logs_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Same contract as LocalImageStorage.cleanup — runs from a finally
        # block where raising would mask the in-flight exception.
        client = _FakeS3Client(delete_side_effect=RuntimeError("network down"))
        storage = S3ImageStorage(bucket="b", client=client)

        caplog.set_level(logging.WARNING, logger="app.services.image_storage")
        storage.cleanup(["rr-1/img-1.png"])

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any(
            "Failed to remove orphaned S3 upload" in r.message
            and "rr-1/img-1.png" in r.message
            for r in warnings
        )

    def test_empty_list_is_noop(self) -> None:
        client = _FakeS3Client()
        storage = S3ImageStorage(bucket="b", client=client)
        storage.cleanup([])
        assert client.delete_calls == []
