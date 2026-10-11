"""Command-line entry point: run any pipeline stage without Airflow.

    python -m football_analytics scrape all
    python -m football_analytics silver
    python -m football_analytics gold
    python -m football_analytics load
    python -m football_analytics all            (scrape + silver + gold + load)
    python -m football_analytics all --skip-scrape
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone

from .bronze import SPIDERS, ingest_source
from .config import Settings
from .gold import run_gold
from .silver import run_silver
from .storage import Storage, get_storage
from .warehouse import get_engine, run_load


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


def _load(storage: Storage, settings: Settings, ingest_date: str) -> None:
    engine = get_engine(settings.warehouse_url)
    try:
        run_load(storage, engine, ingest_date)
    finally:
        engine.dispose()  # close the database connections


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="football_analytics")
    sub = parser.add_subparsers(dest="command", required=True)

    scrape = sub.add_parser("scrape", help="scrape one source (or all) into bronze")
    scrape.add_argument("source", choices=sorted(SPIDERS) + ["all"])
    scrape.add_argument("--run-id", default=_run_id(), help="run folder name (default: current UTC time)")

    sub.add_parser("silver", help="bronze -> silver for one date")
    sub.add_parser("gold", help="silver -> gold for one date")
    sub.add_parser("load", help="gold -> warehouse for one date")

    everything = sub.add_parser("all", help="scrape + silver + gold + load")
    everything.add_argument("--skip-scrape", action="store_true", help="reuse today's bronze data")
    everything.add_argument("--run-id", default=_run_id())

    # every command works on one ingestion date
    for command in sub.choices.values():
        command.add_argument("--date", default=_today(), help="ingestion date partition (YYYY-MM-DD)")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()
    storage = get_storage(settings)

    if args.command == "scrape":
        sources = sorted(SPIDERS) if args.source == "all" else [args.source]
        for source in sources:
            ingest_source(source, args.date, args.run_id, storage, settings)
    elif args.command == "silver":
        print(json.dumps(run_silver(storage, args.date), indent=2))
    elif args.command == "gold":
        print(json.dumps(run_gold(storage, args.date), indent=2, ensure_ascii=False))
    elif args.command == "load":
        _load(storage, settings, args.date)
    elif args.command == "all":
        if not args.skip_scrape:
            for source in sorted(SPIDERS):
                ingest_source(source, args.date, args.run_id, storage, settings)
        run_silver(storage, args.date)
        run_gold(storage, args.date)
        _load(storage, settings, args.date)
