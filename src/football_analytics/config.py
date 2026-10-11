"""Runtime configuration, read from environment variables.

Values come from (first match wins):
  1. real environment variables (set by Docker / Airflow / CI)
  2. the project's .env file (your local secrets, never committed)
  3. the defaults below (safe local values, no secrets)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")  # does nothing if the file doesn't exist; never overrides real env vars


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

    # Database URL: Postgres (from .env), or a SQLite file if WAREHOUSE_URL isn't set (tests)
    warehouse_url: str

    # Directory of the Scrapy project (contains scrapy.cfg)
    scraper_dir: Path

    @classmethod
    def from_env(cls) -> Settings:
        default_db = (PROJECT_ROOT / "data" / "warehouse.sqlite").as_posix()
        return cls(
            storage_backend=_env("STORAGE_BACKEND", "local"),
            local_storage_dir=Path(_env("LOCAL_STORAGE_DIR", str(PROJECT_ROOT / "data" / "lake"))),
            minio_endpoint=_env("MINIO_ENDPOINT", "localhost:9000"),
            minio_access_key=_env("MINIO_ACCESS_KEY", "minioadmin"),
            minio_secret_key=_env("MINIO_SECRET_KEY", "minioadmin"),
            minio_secure=_env("MINIO_SECURE", "false").lower() == "true",
            bucket=_env("MINIO_BUCKET", "football-data"),
            warehouse_url=_env("WAREHOUSE_URL", f"sqlite:///{default_db}"),
            scraper_dir=Path(_env("SCRAPER_DIR", str(PROJECT_ROOT / "scraper"))),
        )