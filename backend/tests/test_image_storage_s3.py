"""Unit tests for S3ImageStorage with an in-memory fake S3 client.

Avoids depending on boto3 at test time - the fake just needs to expose
``put_object``, ``get_object``, and ``delete_object`` shaped like the real
client. Production runtime gets the real boto3 client via lazy import.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.image_storage import (
    ImageNotFoundError,
    ImageStorageError,
    S3ImageStorage,
    get_image_storage,
)


class _FakeS3Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _ClientError(Exception):
    """Mimic boto3 botocore.exceptions.ClientError shape (``response`` attr)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class _FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], dict[str, Any]] = {}

    def put_object(
        self, *, Bucket: str, Key: str, Body: bytes, ContentType: str
    ) -> dict[str, Any]:
        self.objects[(Bucket, Key)] = {"Body": Body, "ContentType": ContentType}
        return {}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        try:
            stored = self.objects[(Bucket, Key)]
        except KeyError as exc:
            raise _ClientError("NoSuchKey") from exc
        return {"Body": _FakeS3Body(stored["Body"]), "ContentType": stored["ContentType"]}

    def delete_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        self.objects.pop((Bucket, Key), None)
        return {}


def test_save_writes_to_bucket_and_returns_storage_key() -> None:
    fake = _FakeS3Client()
    storage = S3ImageStorage(bucket="ams-test", client=fake)

    key = storage.save(
        repair_request_id="rr-1",
        image_id="img-1",
        suffix=".png",
        content=b"\x89PNG-bytes",
    )

    assert key == "rr-1/img-1.png"
    assert fake.objects[("ams-test", "rr-1/img-1.png")]["Body"] == b"\x89PNG-bytes"
    assert fake.objects[("ams-test", "rr-1/img-1.png")]["ContentType"] == "image/png"


def test_save_applies_key_prefix() -> None:
    fake = _FakeS3Client()
    storage = S3ImageStorage(bucket="ams-test", key_prefix="repair-requests", client=fake)

    key = storage.save(
        repair_request_id="rr-1", image_id="img-1", suffix=".jpg", content=b"jpg"
    )

    # Storage key (DB row) stays unprefixed - portable across environments.
    assert key == "rr-1/img-1.jpg"
    # Actual S3 object key is prefixed.
    assert ("ams-test", "repair-requests/rr-1/img-1.jpg") in fake.objects


def test_open_returns_bytes_and_content_type() -> None:
    fake = _FakeS3Client()
    storage = S3ImageStorage(bucket="ams-test", client=fake)
    storage.save(
        repair_request_id="rr-1", image_id="img-1", suffix=".png", content=b"PNG"
    )

    content, content_type = storage.open("rr-1/img-1.png")

    assert content == b"PNG"
    assert content_type == "image/png"


def test_open_missing_object_raises_image_not_found() -> None:
    storage = S3ImageStorage(bucket="ams-test", client=_FakeS3Client())

    with pytest.raises(ImageNotFoundError):
        storage.open("rr-1/missing.png")


def test_cleanup_removes_objects_and_swallows_errors() -> None:
    fake = _FakeS3Client()
    storage = S3ImageStorage(bucket="ams-test", client=fake)
    storage.save(
        repair_request_id="rr-1", image_id="img-1", suffix=".png", content=b"a"
    )

    # Mix of existing + missing keys - cleanup must not raise on either.
    storage.cleanup(["rr-1/img-1.png", "rr-1/never-existed.png"])

    assert ("ams-test", "rr-1/img-1.png") not in fake.objects


def test_constructor_rejects_empty_bucket() -> None:
    with pytest.raises(ImageStorageError):
        S3ImageStorage(bucket="", client=_FakeS3Client())


def test_get_image_storage_with_unknown_backend_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import config

    config.get_settings.cache_clear()
    monkeypatch.setenv("REPAIR_IMAGE_BACKEND", "azure-blob")
    try:
        with pytest.raises(ImageStorageError):
            get_image_storage()
    finally:
        monkeypatch.delenv("REPAIR_IMAGE_BACKEND", raising=False)
        config.get_settings.cache_clear()
