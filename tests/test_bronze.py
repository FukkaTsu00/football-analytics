from dataclasses import replace
from pathlib import Path

import pytest

from football_analytics.bronze import SPIDERS, bronze_key, ingest_source, run_spider
from football_analytics.config import Settings
from football_analytics.storage import get_json

FAKE_SPIDER = '''
import scrapy


class FakeSpider(scrapy.Spider):
    name = "{name}"
    start_urls = ["data:,offline"]  # a page stored in the URL itself: no network needed

    def parse(self, response):
        for i in range({n}):
            yield {{"title": f"Article {{i}}", "content": "text", "url": f"https://e.com/{{i}}"}}
'''


def fake_scrapy_project(folder: Path, n_items: int) -> Settings:
    """Create a minimal Scrapy project whose 'bbc' spider yields n_items fake articles."""
    pkg = folder / "fake_scraper"
    (pkg / "spiders").mkdir(parents=True)
    (folder / "scrapy.cfg").write_text("[settings]\ndefault = fake_scraper.settings\n")
    (pkg / "__init__.py").write_text("")
    (pkg / "settings.py").write_text('SPIDER_MODULES = ["fake_scraper.spiders"]\n')
    (pkg / "spiders" / "__init__.py").write_text("")
    (pkg / "spiders" / "fake.py").write_text(FAKE_SPIDER.format(name=SPIDERS["bbc"], n=n_items))
    return replace(Settings.from_env(), scraper_dir=folder)


def test_bronze_key_layout():
    assert bronze_key("2026-10-11", "20261011T130000", "bbc") == "bronze/date=2026-10-11/run=20261011T130000/bbc.json"


def test_unknown_source_is_rejected():
    with pytest.raises(ValueError):
        run_spider("lequipe", Settings.from_env())


def test_spider_runs_in_a_subprocess_and_returns_items(tmp_path):
    settings = fake_scrapy_project(tmp_path, n_items=3)
    items = run_spider("bbc", settings)
    assert [i["title"] for i in items] == ["Article 0", "Article 1", "Article 2"]


def test_ingest_writes_one_bronze_file(tmp_path, storage):
    settings = fake_scrapy_project(tmp_path, n_items=2)
    key = ingest_source("bbc", "2026-10-11", "r1", storage, settings)
    assert len(get_json(storage, key)) == 2


def test_empty_scrape_fails_loudly(tmp_path, storage):
    settings = fake_scrapy_project(tmp_path, n_items=0)
    with pytest.raises(RuntimeError, match="selectors may be broken"):
        ingest_source("bbc", "2026-10-11", "r1", storage, settings)


def test_crashing_spider_reports_its_log(tmp_path):
    settings = replace(Settings.from_env(), scraper_dir=tmp_path)  # no Scrapy project here: scrapy fails
    with pytest.raises(RuntimeError, match="Spider bbc failed"):
        run_spider("bbc", settings)