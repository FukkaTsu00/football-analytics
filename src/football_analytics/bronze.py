"""Bronze layer: raw scraped articles, stored exactly as the spiders produced them.

Layout: bronze/date=YYYY-MM-DD/run=<run_id>/<source>.json
Each run writes its own immutable folder, so a new run never corrupts or erases an older one.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path

from .config import Settings
from .storage import Storage, put_json

log = logging.getLogger(__name__)

# Our short source name -> the Scrapy spider's `name`
SPIDERS = {
    "bbc": "bbc_football",
    "goal": "goal_football",
}


def bronze_key(ingest_date: str, run_id: str, source: str) -> str:
    return f"bronze/date={ingest_date}/run={run_id}/{source}.json"


def run_spider(source: str, settings: Settings, timeout_s: int = 900) -> list[dict]:
    """Run one Scrapy spider in its own process and return the scraped items."""
    if source not in SPIDERS:
        raise ValueError(f"Unknown source {source!r}; expected one of {sorted(SPIDERS)}")

    with tempfile.TemporaryDirectory() as tmp:
        out_file = Path(tmp) / f"{source}.json"
        cmd = [sys.executable, "-m", "scrapy", "crawl", SPIDERS[source], "-O", str(out_file)]
        result = subprocess.run(cmd, cwd=settings.scraper_dir, capture_output=True, text=True, timeout=timeout_s)

        # Scrapy logs to stderr: keep the end of it so failures explain themselves
        tail = "\n".join(result.stderr.splitlines()[-40:])
        if result.returncode != 0:
            raise RuntimeError(f"Spider {source} failed (exit {result.returncode}):\n{tail}")
        log.info("Spider %s finished. Log tail:\n%s", source, tail)

        if not out_file.exists():
            return []
        items = json.loads(out_file.read_text(encoding="utf-8") or "[]")

    if not isinstance(items, list):
        raise ValueError(f"Spider {source} produced {type(items).__name__}, expected a list")
    return items


def write_bronze(storage: Storage, items: list[dict], ingest_date: str, run_id: str, source: str) -> str:
    """Store one run's raw items for one source."""
    key = bronze_key(ingest_date, run_id, source)
    put_json(storage, key, items)
    log.info("Bronze: %d %s items -> %s", len(items), source, key)
    return key


def ingest_source(
    source: str, ingest_date: str, run_id: str, storage: Storage, settings: Settings, min_items: int = 1
) -> str:
    """Scrape one source and land the raw result in bronze."""
    items = run_spider(source, settings)
    if len(items) < min_items:
        # 0 articles almost always means the site changed its HTML (or blocked us): fail loudly
        raise RuntimeError(f"Spider {source} returned {len(items)} items (< {min_items}); selectors may be broken")
    return write_bronze(storage, items, ingest_date, run_id, source)