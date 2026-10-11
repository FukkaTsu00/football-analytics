"""End-to-end: real articles through bronze -> silver -> gold -> warehouse, the CLI, and the DAG."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select

from football_analytics.bronze import write_bronze
from football_analytics.cli import main
from football_analytics.gold import run_gold
from football_analytics.silver import run_silver
from football_analytics.storage import LocalStorage
from football_analytics.warehouse import articles, run_load

DATE = "2026-10-11"


def test_full_pipeline_on_real_articles(storage, engine, real_articles):
    # Two hourly runs that scraped the same pages (the old project's JSON broke here)
    for run_id in ("20261011T120000", "20261011T130000"):
        for source, items in real_articles.items():
            write_bronze(storage, items, DATE, run_id, source)
    total_raw = 2 * sum(len(items) for items in real_articles.values())

    report = run_silver(storage, DATE)
    assert report["input"] == total_raw
    assert report["bronze_files"] == 4
    # every raw article is either dropped, a duplicate, or kept once
    dropped = report["dropped_no_url"] + report["dropped_empty"]
    assert dropped + report["duplicates"] + report["output"] == total_raw
    assert report["duplicates"] >= report["output"] > 0  # the 2nd run re-scraped everything
    assert set(report["per_source"]) == {"BBC Sport", "Goal.com"}
    assert report["missing_published_at"] == 0

    summary = run_gold(storage, DATE)
    assert summary["total_articles"] == report["output"]

    assert run_load(storage, engine, DATE) == report["output"]
    assert run_load(storage, engine, DATE) == report["output"]  # idempotent
    with engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(articles)).scalar_one() == report["output"]


def test_cli_runs_the_whole_pipeline(tmp_path, monkeypatch, capsys, make_raw):
    db_url = f"sqlite:///{(tmp_path / 'warehouse.sqlite').as_posix()}"
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_STORAGE_DIR", str(tmp_path / "lake"))
    monkeypatch.setenv("WAREHOUSE_URL", db_url)

    raws = [make_raw("https://e.com/1"), make_raw("https://e.com/2")]
    write_bronze(LocalStorage(tmp_path / "lake"), raws, DATE, "r1", "bbc")

    main(["all", "--skip-scrape", "--date", DATE])
    main(["gold", "--date", DATE])
    assert '"total_articles": 2' in capsys.readouterr().out

    engine = create_engine(db_url)
    with engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(articles)).scalar_one() == 2
    engine.dispose()


def test_dag_loads_with_the_right_tasks():
    pytest.importorskip("airflow", reason="Airflow isn't installed locally; this test runs in CI")
    from airflow.models import DagBag

    bag = DagBag(dag_folder=str(Path(__file__).resolve().parents[1] / "dags"), include_examples=False)
    assert bag.import_errors == {}
    dag = bag.get_dag("football_pipeline")
    assert {t.task_id for t in dag.tasks} == {
        "scrape_bbc", "scrape_goal", "build_silver", "build_gold", "load_warehouse",
    }
    assert dag.get_task("build_silver").upstream_task_ids == {"scrape_bbc", "scrape_goal"}
    assert dag.get_task("load_warehouse").upstream_task_ids == {"build_gold"}
