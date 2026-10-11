"""Shared test fixtures: pytest finds this file automatically."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from football_analytics.storage import LocalStorage
from football_analytics.warehouse import get_engine, init_schema

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def storage(tmp_path):
    """An empty data lake in a temporary folder (pytest deletes it after the test)."""
    return LocalStorage(tmp_path / "lake")


@pytest.fixture
def engine(tmp_path):
    """An empty SQLite warehouse in a temporary file: no Postgres needed."""
    eng = get_engine(f"sqlite:///{(tmp_path / 'warehouse.sqlite').as_posix()}")
    init_schema(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def real_articles():
    """Real scraped articles (a small sample made by scripts/make_fixtures.py)."""
    return {
        source: json.loads((FIXTURES / f"{source}.json").read_text(encoding="utf-8"))
        for source in ("bbc", "goal")
    }


@pytest.fixture
def make_raw():
    """Build a fake raw (bronze) article; any field can be overridden."""

    def _make(url: str = "https://www.bbc.com/sport/football/articles/test1", **overrides) -> dict:
        raw = {
            "title": "Arsenal sign a new striker",
            "author": "Reporter",
            "published_at": "2026-10-11T10:00:00.000Z",
            "content": "Arsenal have completed the signing of a striker on a five-year deal.",
            "url": url,
            "source": "BBC Sport",
            "scraped_at": "2026-10-11T12:00:00+00:00",
        }
        raw.update(overrides)
        return raw

    return _make