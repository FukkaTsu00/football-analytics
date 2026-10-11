"""Silver layer: cleaned, typed and de-duplicated articles for one ingestion date.

Reads every bronze run of the date, so the hourly runs of a day are merged and an
article scraped several times appears once (the most recent scrape wins).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from .storage import Storage, get_json, put_json
from .text import article_id, clean_text, parse_published_at

log = logging.getLogger(__name__)


def silver_key(ingest_date: str) -> str:
    return f"silver/date={ingest_date}/articles.json"


def quality_key(ingest_date: str) -> str:
    return f"silver/date={ingest_date}/_quality.json"


def transform_article(raw: dict) -> dict:
    """Clean one raw article and give it a stable id."""
    url = (raw.get("url") or "").strip()
    content = clean_text(raw.get("content"))
    return {
        "article_id": article_id(url) if url else None,
        "url": url,
        "source": raw.get("source", ""),
        "title": clean_text(raw.get("title")),
        "author": (raw.get("author") or "Unknown").strip(),
        "published_at": parse_published_at(raw.get("published_at")),
        "content": content,
        "content_length": len(content),
        "content_type": raw.get("content_type", "full"),
        "scraped_at": raw.get("scraped_at"),
    }


def build_silver(raw_articles: list[dict]) -> tuple[list[dict], dict]:
    """Clean and de-duplicate articles. Returns (articles, quality report)."""
    report = {
        "input": len(raw_articles),
        "dropped_no_url": 0,
        "dropped_empty": 0,
        "missing_published_at": 0,
        "duplicates": 0,
    }
    by_id: dict[str, dict] = {}

    for raw in raw_articles:
        art = transform_article(raw)
        if not art["article_id"]:
            report["dropped_no_url"] += 1
            continue
        if not art["title"] or not art["content"]:
            report["dropped_empty"] += 1
            continue
        if art["published_at"] is None:
            # kept (still useful) but counted, so a broken date selector gets noticed
            report["missing_published_at"] += 1

        existing = by_id.get(art["article_id"])
        if existing is not None:
            report["duplicates"] += 1
            if (existing["scraped_at"] or "") >= (art["scraped_at"] or ""):
                continue  # the copy we already have is newer: keep it
        by_id[art["article_id"]] = art

    # sorted output = same input always gives the same file (easy to compare and test)
    articles = sorted(by_id.values(), key=lambda a: (a["source"], a["article_id"]))
    report["output"] = len(articles)
    report["per_source"] = {}
    for a in articles:
        report["per_source"][a["source"]] = report["per_source"].get(a["source"], 0) + 1
    return articles, report


def run_silver(storage: Storage, ingest_date: str) -> dict:
    """Read every bronze run of the date, build silver, write articles + quality report."""
    keys = [k for k in storage.list_keys(f"bronze/date={ingest_date}/") if k.endswith(".json")]
    if not keys:
        raise FileNotFoundError(f"No bronze data for {ingest_date}")

    raw_articles: list[dict] = []
    for key in keys:
        data = get_json(storage, key)
        if not isinstance(data, list):
            raise ValueError(f"{key} is not a JSON list")
        raw_articles.extend(data)

    articles, report = build_silver(raw_articles)
    report["ingest_date"] = ingest_date
    report["bronze_files"] = len(keys)
    report["built_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    put_json(storage, silver_key(ingest_date), articles)
    put_json(storage, quality_key(ingest_date), report)
    log.info("Silver %s: %d raw -> %d articles (%d duplicates)",
             ingest_date, report["input"], report["output"], report["duplicates"])
    return report