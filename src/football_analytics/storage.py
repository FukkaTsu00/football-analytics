"""Storage abstraction for the data lake.

The pipeline only talks to the `Storage` interface, so the same code runs against
MinIO in Docker and against a local folder in development and tests.
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol

from .config import Settings


class Storage(Protocol):
    """Anything with these 4 methods can be used as storage."""

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/json") -> None: ...
    def get_bytes(self, key: str) -> bytes: ...
    def list_keys(self, prefix: str) -> list[str]: ...
    def exists(self, key: str) -> bool: ...


def put_json(storage: Storage, key: str, obj: Any) -> None:
    storage.put_bytes(key, json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8"))


def get_json(storage: Storage, key: str) -> Any:
    return json.loads(storage.get_bytes(key).decode("utf-8"))


class LocalStorage:
    """Stores objects as files under a root folder: key 'bronze/x.json' -> <root>/bronze/x.json."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / key

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/json") -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def list_keys(self, prefix: str) -> list[str]:
        if not self.root.exists():
            return []
        keys = [p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file()]
        return sorted(k for k in keys if k.startswith(prefix))

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()


class MinioStorage:
    """Stores objects in a MinIO (S3-compatible) bucket."""

    def __init__(self, settings: Settings) -> None:
        from minio import Minio  # imported here so dev/tests work without MinIO installed or running
        from minio.error import S3Error

        self.bucket = settings.bucket
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        if not self.client.bucket_exists(self.bucket):
            try:
                self.client.make_bucket(self.bucket)
            except S3Error as exc:
                # Two Airflow tasks can try to create the bucket at the same moment: "already exists" is fine
                if exc.code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                    raise

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/json") -> None:
        self.client.put_object(self.bucket, key, BytesIO(data), length=len(data), content_type=content_type)

    def get_bytes(self, key: str) -> bytes:
        response = self.client.get_object(self.bucket, key)
        try:
            return response.read()
        finally:
            response.close()  # always give the HTTP connection back, even if reading failed
            response.release_conn()

    def list_keys(self, prefix: str) -> list[str]:
        objects = self.client.list_objects(self.bucket, prefix=prefix, recursive=True)
        return sorted(o.object_name for o in objects)

    def exists(self, key: str) -> bool:
        from minio.error import S3Error

        try:
            self.client.stat_object(self.bucket, key)
            return True
        except S3Error:
            return False


def get_storage(settings: Settings | None = None) -> Storage:
    """Factory: build the storage backend chosen by STORAGE_BACKEND."""
    settings = settings or Settings.from_env()
    if settings.storage_backend == "local":
        return LocalStorage(settings.local_storage_dir)
    if settings.storage_backend == "minio":
        return MinioStorage(settings)
    raise ValueError(f"Unknown STORAGE_BACKEND: {settings.storage_backend!r}")