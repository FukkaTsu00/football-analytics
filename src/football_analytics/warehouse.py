"""Warehouse: load the gold layer into a SQL database (Postgres in Docker, SQLite in tests).

Tables:
  articles          one row per article
  article_topics    article x topic        (e.g. abc123 | transfer)
  article_entities  article x club/player  (e.g. abc123 | club | Arsenal)
  pipeline_runs     one row per loaded date, with silver's quality report

Loading is idempotent: loading the same date twice gives the same tables, never duplicates.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text, create_engine, delete, insert, select
from sqlalchemy.engine import Engine

from .gold import gold_articles_key
from .silver import quality_key
from .storage import Storage, get_json

log = logging.getLogger(__name__)

metadata = MetaData()

articles = Table(
    "articles", metadata,
    Column("article_id", String(16), primary_key=True),
    Column("ingest_date", String(10), nullable=False, index=True),
    Column("source", String(64), nullable=False, index=True),
    Column("url", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("author", String(255)),
    Column("published_at", DateTime(timezone=True), index=True),
    Column("scraped_at", DateTime(timezone=True)),
    Column("content", Text),
    Column("content_length", Integer),
    Column("content_type", String(32)),
)

article_topics = Table(
    "article_topics", metadata,
    Column("article_id", String(16), primary_key=True),
    Column("topic", String(64), primary_key=True),
    Column("method", String(64), primary_key=True),
)

article_entities = Table(
    "article_entities", metadata,
    Column("article_id", String(16), primary_key=True),
    Column("entity_type", String(16), primary_key=True),  # "club" or "player"
    Column("entity", String(128), primary_key=True),
    Column("method", String(64), nullable=False),
)

pipeline_runs = Table(
    "pipeline_runs", metadata,
    Column("ingest_date", String(10), primary_key=True),
    Column("loaded_at", DateTime(timezone=True), nullable=False),
    Column("articles_loaded", Integer, nullable=False),
    Column("quality_report", Text),
)


def get_engine(url: str) -> Engine:
    return create_engine(url)


def init_schema(engine: Engine) -> None:
    """Create the tables if they don't exist yet (does nothing if they do)."""
    metadata.create_all(engine)


def _to_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def load_date(engine: Engine, enriched: list[dict], ingest_date: str, quality: dict | None = None) -> int:
    """Replace one date's data in the warehouse with the given gold articles."""
    new_ids = {a["article_id"] for a in enriched}

    # One transaction: if anything fails, nothing is half-written
    with engine.begin() as conn:
        # 1. Delete what this date loaded before, plus older copies of the articles we're about to insert
        old_ids = set(conn.execute(select(articles.c.article_id).where(articles.c.ingest_date == ingest_date)).scalars())
        to_delete = list(old_ids | new_ids)
        for start in range(0, len(to_delete), 500):  # in chunks: databases limit the size of IN (...)
            chunk = to_delete[start:start + 500]
            for table in (article_topics, article_entities, articles):
                conn.execute(delete(table).where(table.c.article_id.in_(chunk)))

        # 2. Insert the fresh rows
        if enriched:
            conn.execute(insert(articles), [
                {
                    "article_id": a["article_id"],
                    "ingest_date": ingest_date,
                    "source": a["source"],
                    "url": a["url"],
                    "title": a["title"],
                    "author": a.get("author"),
                    "published_at": _to_datetime(a.get("published_at")),
                    "scraped_at": _to_datetime(a.get("scraped_at")),
                    "content": a.get("content"),
                    "content_length": a.get("content_length"),
                    "content_type": a.get("content_type"),
                }
                for a in enriched
            ])

            topic_rows = [
                {"article_id": a["article_id"], "topic": t, "method": a["enrichment_method"]}
                for a in enriched for t in a["topics"]
            ]
            entity_rows = [
                {"article_id": a["article_id"], "entity_type": kind, "entity": name, "method": a["enrichment_method"]}
                for a in enriched
                for kind, names in (("club", a["clubs"]), ("player", a["players"]))
                for name in names
            ]
            if topic_rows:
                conn.execute(insert(article_topics), topic_rows)
            if entity_rows:
                conn.execute(insert(article_entities), entity_rows)

        # 3. Record the load
        conn.execute(delete(pipeline_runs).where(pipeline_runs.c.ingest_date == ingest_date))
        conn.execute(insert(pipeline_runs), [{
            "ingest_date": ingest_date,
            "loaded_at": datetime.now(timezone.utc),
            "articles_loaded": len(enriched),
            "quality_report": json.dumps(quality or {}),
        }])

    log.info("Warehouse: loaded %d articles for %s", len(enriched), ingest_date)
    return len(enriched)


def run_load(storage: Storage, engine: Engine, ingest_date: str) -> int:
    """Read gold (and silver's quality report) for a date and load them into the warehouse."""
    init_schema(engine)
    enriched = get_json(storage, gold_articles_key(ingest_date))
    key = quality_key(ingest_date)
    quality = get_json(storage, key) if storage.exists(key) else None
    return load_date(engine, enriched, ingest_date, quality)