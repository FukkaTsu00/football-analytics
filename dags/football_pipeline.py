"""Hourly football news pipeline: scrape -> bronze -> silver -> gold -> Postgres.

Each task calls a function from our package, so any error and its traceback
appear directly in the Airflow task log.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from football_analytics.bronze import SPIDERS, ingest_source
from football_analytics.config import Settings
from football_analytics.gold import run_gold
from football_analytics.silver import run_silver
from football_analytics.storage import get_storage
from football_analytics.warehouse import get_engine, run_load


# Airflow passes context values (ds, ts_nodash, ...) as keyword arguments; **_ ignores the rest.
def scrape(source: str, ds: str, ts_nodash: str, **_) -> str:
    settings = Settings.from_env()
    return ingest_source(source, ds, ts_nodash, get_storage(settings), settings)


def silver(ds: str, **_) -> dict:
    return run_silver(get_storage(), ds)


def gold(ds: str, **_) -> dict:
    return run_gold(get_storage(), ds)


def load(ds: str, **_) -> int:
    settings = Settings.from_env()
    engine = get_engine(settings.warehouse_url)
    try:
        return run_load(get_storage(settings), engine, ds)
    finally:
        engine.dispose()


with DAG(
    dag_id="football_pipeline",
    description="Scrape football news, build bronze/silver/gold, load Postgres",
    schedule="@hourly",
    start_date=datetime(2026, 10, 1),
    catchup=False,       # don't run all the missed hours since start_date
    max_active_runs=1,   # silver/gold rebuild the whole day: never two runs at once
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
        "execution_timeout": timedelta(minutes=20),
    },
    tags=["football", "medallion"],
) as dag:
    scrape_tasks = [
        PythonOperator(task_id=f"scrape_{source}", python_callable=scrape, op_kwargs={"source": source})
        for source in sorted(SPIDERS)
    ]
    # all_done: build silver even if one site failed, so the other source's data isn't lost
    build_silver = PythonOperator(task_id="build_silver", python_callable=silver, trigger_rule="all_done")
    build_gold = PythonOperator(task_id="build_gold", python_callable=gold)
    load_warehouse = PythonOperator(task_id="load_warehouse", python_callable=load)

    scrape_tasks >> build_silver >> build_gold >> load_warehouse
