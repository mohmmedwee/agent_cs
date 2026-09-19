"""Byte storage for uploaded files — local disk or S3/MinIO.

Postgres keeps metadata and ownership; this layer only holds opaque blobs keyed
by `storage_key`. Local mode is the default for single-node / dev; S3 mode is
what multi-pod k8s needs so every replica sees the same bytes.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

__all__ = ["BlobStore", "LocalBlobStore", "S3BlobStore", "build_blob_store"]

logger = logging.getLogger(__name__)


class BlobStore(Protocol):
    def put(
        self, key: str, data: bytes, *, content_type: str | None = None
    ) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class LocalBlobStore:
    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._directory.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self._directory / key

    def put(
        self, key: str, data: bytes, *, content_type: str | None = None
    ) -> None:
        del content_type  # unused on disk
        self._path(key).write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3BlobStore:
    """S3-compatible object storage (AWS S3, MinIO, Garage, …)."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        endpoint_url: str | None,
        access_key: str,
        secret_key: str,
    ) -> None:
        import boto3
        from botocore.client import Config

        self._bucket = bucket
        kwargs: dict = {
            "service_name": "s3",
            "region_name": region,
            "config": Config(signature_version="s3v4"),
        }
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        if access_key:
            kwargs["aws_access_key_id"] = access_key
        if secret_key:
            kwargs["aws_secret_access_key"] = secret_key
        self._client = boto3.client(**kwargs)
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except Exception:
            logger.info("creating object-storage bucket %s", self._bucket)
            self._client.create_bucket(Bucket=self._bucket)

    def put(
        self, key: str, data: bytes, *, content_type: str | None = None
    ) -> None:
        extra: dict = {}
        if content_type:
            extra["ContentType"] = content_type
        self._client.put_object(
            Bucket=self._bucket, Key=key, Body=data, **extra
        )

    def get(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)


def build_blob_store(settings, upload_dir: Path) -> BlobStore:
    """Pick local or S3 from settings. S3 needs a bucket name at minimum."""
    backend = (getattr(settings, "file_storage", "local") or "local").lower()
    if backend == "s3":
        bucket = getattr(settings, "s3_bucket", "") or ""
        if not bucket:
            raise ValueError("file_storage=s3 requires s3_bucket")
        logger.info(
            "file storage: s3 bucket=%s endpoint=%s",
            bucket,
            getattr(settings, "s3_endpoint_url", None) or "aws-default",
        )
        return S3BlobStore(
            bucket=bucket,
            region=getattr(settings, "s3_region", "us-east-1") or "us-east-1",
            endpoint_url=getattr(settings, "s3_endpoint_url", None) or None,
            access_key=getattr(settings, "s3_access_key", "") or "",
            secret_key=getattr(settings, "s3_secret_key", "") or "",
        )
    logger.info("file storage: local dir=%s", upload_dir)
    return LocalBlobStore(upload_dir)
