"""Local and private Tencent COS storage for homework image objects."""

from __future__ import annotations

import mimetypes
import os
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from config import settings


COS_LOCATOR_PREFIX = "cos://"


class LocalStorageProvider:
    def store_bytes(
        self, content: bytes, *, task_id: str, image_index: int,
        filename: str | None, content_type: str | None,
    ) -> str:
        suffix = Path(filename or "").suffix.lower()
        if not suffix:
            suffix = mimetypes.guess_extension(content_type or "") or ".bin"
        path = Path(settings.UPLOAD_DIR) / f"{task_id}_{image_index}_{uuid.uuid4().hex}{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return str(path)

    def get_signed_download_url(self, locator: str) -> str | None:
        return None

    @contextmanager
    def materialize(self, locator: str) -> Iterator[str]:
        if locator.startswith(COS_LOCATOR_PREFIX):
            with get_cos_provider().materialize(locator) as local_path:
                yield local_path
            return
        yield locator


class COSStorageProvider:
    def __init__(self) -> None:
        if not settings.COS_BUCKET or not settings.COS_REGION:
            raise RuntimeError("COS bucket and region are required when STORAGE_PROVIDER=cos")
        if not settings.COS_SECRET_ID or not settings.COS_SECRET_KEY:
            raise RuntimeError("COS credentials are required when STORAGE_PROVIDER=cos")
        try:
            from qcloud_cos import CosConfig, CosS3Client
        except ImportError as exc:
            raise RuntimeError("Tencent COS SDK is not installed") from exc

        config_args = {
            "Region": settings.COS_REGION,
            "SecretId": settings.COS_SECRET_ID,
            "SecretKey": settings.COS_SECRET_KEY,
            "Scheme": "https",
        }
        if settings.COS_SESSION_TOKEN:
            config_args["Token"] = settings.COS_SESSION_TOKEN
        self.client = CosS3Client(CosConfig(**config_args))
        self.bucket = settings.COS_BUCKET

    @staticmethod
    def _key(locator: str) -> str:
        if not locator.startswith(COS_LOCATOR_PREFIX):
            raise ValueError("not a COS object locator")
        key = locator[len(COS_LOCATOR_PREFIX):].lstrip("/")
        if not key or key.startswith("/") or ".." in Path(key).parts:
            raise ValueError("invalid COS object locator")
        return key

    def store_bytes(
        self, content: bytes, *, task_id: str, image_index: int,
        filename: str | None, content_type: str | None,
    ) -> str:
        suffix = Path(filename or "").suffix.lower()
        if not suffix:
            suffix = mimetypes.guess_extension(content_type or "") or ".bin"
        prefix = settings.COS_OBJECT_PREFIX.strip("/")
        key = f"{prefix}/{task_id}/{image_index}_{uuid.uuid4().hex}{suffix}"
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType=content_type or mimetypes.guess_type(filename or "")[0] or "application/octet-stream",
        )
        return COS_LOCATOR_PREFIX + key

    def get_signed_download_url(self, locator: str) -> str:
        return self.client.get_presigned_download_url(
            Bucket=self.bucket,
            Key=self._key(locator),
            Expired=max(60, min(int(settings.COS_SIGNED_URL_TTL_SECONDS), 900)),
        )

    def download_to(self, locator: str, destination: str) -> None:
        response = self.client.get_object(Bucket=self.bucket, Key=self._key(locator))
        body = response["Body"]
        try:
            body.get_stream_to_file(destination)
        finally:
            close = getattr(body, "close", None)
            if close:
                close()

    @contextmanager
    def materialize(self, locator: str) -> Iterator[str]:
        suffix = Path(self._key(locator)).suffix or ".bin"
        handle, local_path = tempfile.mkstemp(prefix="homework-cos-", suffix=suffix)
        os.close(handle)
        try:
            self.download_to(locator, local_path)
            yield local_path
        finally:
            try:
                os.remove(local_path)
            except FileNotFoundError:
                pass


_cos_provider: COSStorageProvider | None = None


def get_cos_provider() -> COSStorageProvider:
    global _cos_provider
    if _cos_provider is None:
        _cos_provider = COSStorageProvider()
    return _cos_provider


def get_storage_provider() -> LocalStorageProvider | COSStorageProvider:
    provider = settings.STORAGE_PROVIDER.strip().lower()
    if provider == "local":
        return LocalStorageProvider()
    if provider == "cos":
        return get_cos_provider()
    raise RuntimeError("STORAGE_PROVIDER must be local or cos")


@contextmanager
def materialize_image(locator: str) -> Iterator[str]:
    if locator.startswith(COS_LOCATOR_PREFIX):
        with get_cos_provider().materialize(locator) as path:
            yield path
    else:
        yield locator
