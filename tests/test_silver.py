import pytest

from football_analytics.bronze import write_bronze
from football_analytics.silver import build_silver, quality_key, run_silver, silver_key
from football_analytics.storage import get_json


def test_duplicates_keep_the_latest_scrape(make_raw):
    old = make_raw(title="Old title", scraped_at="2026-10-11T10:00:00+00:00")
    new = make_raw(title="New title", scraped_at="2026-10-11T11:00:00+00:00")
    for order in ([old, new], [new, old]):  # the result must not depend on the order
        articles, report = build_silver(order)
        assert [a["title"] for a in articles] == ["New title"]
        assert report["duplicates"] == 1


def test_articles_without_title_or_content_are_dropped(make_raw):
    articles, report = build_silver([make_raw(content=""), make_raw(url="https://e.com/b", title="   ")])
    assert articles == []
    assert report["dropped_empty"] == 2


def test_article_without_url_is_dropped(make_raw):
    _, report = build_silver([make_raw(url="")])
    assert report["dropped_no_url"] == 1


def test_bad_date_is_kept_but_counted(make_raw):
    articles, report = build_silver([make_raw(published_at="not a date")])
    assert len(articles) == 1
    assert articles[0]["published_at"] is None
    assert report["missing_published_at"] == 1


def test_run_silver_merges_all_runs_of_the_day_only(storage, make_raw):
    write_bronze(storage, [make_raw("https://e.com/1")], "2026-10-11", "r1", "bbc")
    write_bronze(storage, [make_raw("https://e.com/1"), make_raw("https://e.com/2")], "2026-10-11", "r2", "bbc")
    write_bronze(storage, [make_raw("https://e.com/3")], "2026-10-12", "r3", "bbc")  # another day: ignored

    report = run_silver(storage, "2026-10-11")

    assert report["bronze_files"] == 2
    assert report["output"] == 2
    assert report["duplicates"] == 1
    assert len(get_json(storage, silver_key("2026-10-11"))) == 2
    assert get_json(storage, quality_key("2026-10-11"))["output"] == 2


def test_run_silver_without_bronze_fails_loudly(storage):
    with pytest.raises(FileNotFoundError):
        run_silver(storage, "2026-01-01")


def test_bronze_file_must_be_a_list(storage):
    storage.put_bytes("bronze/date=2026-10-11/run=r1/bbc.json", b'{"not": "a list"}')
    with pytest.raises(ValueError):
        run_silver(storage, "2026-10-11")