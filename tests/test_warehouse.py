from sqlalchemy import func, select

from football_analytics.gold import enrich
from football_analytics.silver import build_silver
from football_analytics.warehouse import article_entities, article_topics, articles, load_date, pipeline_runs


def count(engine, table, *conditions) -> int:
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(table).where(*conditions)).scalar_one()


def gold_rows(raws: list[dict]) -> list[dict]:
    silver, _ = build_silver(raws)
    return [enrich(a) for a in silver]


def test_loading_the_same_date_twice_creates_no_duplicates(engine, make_raw):
    rows = gold_rows([make_raw("https://e.com/1"), make_raw("https://e.com/2")])
    load_date(engine, rows, "2026-10-11")
    load_date(engine, rows, "2026-10-11")
    assert count(engine, articles) == 2
    assert count(engine, pipeline_runs) == 1
    assert count(engine, article_entities) == 2  # "Arsenal" in each article
    assert count(engine, article_topics, article_topics.c.topic == "transfer") == 2


def test_rescraped_article_moves_to_the_latest_date(engine, make_raw):
    load_date(engine, gold_rows([make_raw("https://e.com/1")]), "2026-10-10")
    load_date(engine, gold_rows([make_raw("https://e.com/1")]), "2026-10-11")
    assert count(engine, articles) == 1
    assert count(engine, articles, articles.c.ingest_date == "2026-10-11") == 1


def test_article_removed_from_a_date_is_deleted(engine, make_raw):
    load_date(engine, gold_rows([make_raw("https://e.com/1"), make_raw("https://e.com/2")]), "2026-10-11")
    load_date(engine, gold_rows([make_raw("https://e.com/1")]), "2026-10-11")
    assert count(engine, articles) == 1
    assert count(engine, article_entities) == 1


def test_publication_time_is_stored(engine, make_raw):
    load_date(engine, gold_rows([make_raw()]), "2026-10-11")
    with engine.connect() as conn:
        published = conn.execute(select(articles.c.published_at)).scalar_one()
    assert (published.year, published.month, published.day, published.hour) == (2026, 10, 11, 10)
