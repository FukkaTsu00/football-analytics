"""Runtime configuration, read from environment variables.

Every value has a local-development default so the code runs without a .env file,
but nothing secret is hard-coded in the pipeline logic itself.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    # "minio" (S3-compatible object store, used in Docker) or "local" (a folder, used in dev and tests)
    storage_backend: str
    local_storage_dir: Path

    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_secure: bool
    bucket: str

    # Directory of the Scrapy project (contains scrapy.cfg)
    scraper_dir: Path

    @classmethod
    def from_env(cls) -> Settings:
        project_root = Path(__file__).resolve().parents[2]
        return cls(
            storage_backend=_env("STORAGE_BACKEND", "local"),
            local_storage_dir=Path(_env("LOCAL_STORAGE_DIR", str(project_root / "data" / "lake"))),
            minio_endpoint=_env("MINIO_ENDPOINT", "localhost:9000"),
            minio_access_key=_env("MINIO_ACCESS_KEY", "minioadmin"),
            minio_secret_key=_env("MINIO_SECRET_KEY", "minioadmin"),
            minio_secure=_env("MINIO_SECURE", "false").lower() == "true",
            bucket=_env("MINIO_BUCKET", "football-data"),
            scraper_dir=Path(_env("SCRAPER_DIR", str(project_root / "scraper"))),
        )