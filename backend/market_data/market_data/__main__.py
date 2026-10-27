"""Explicit operator commands; importing this package never connects to a service."""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
from uuid import UUID

import boto3
from dotenv import load_dotenv
import httpx
import psycopg

from .calendar import EASTERN, latest_published_session
from .backfill import HistoryBackfill
from .pipeline import DailyPricePipeline
from .provider import MassiveDailyProvider
from .repository import PriceRepository
from .storage import LocalRawStore, S3RawStore


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verified daily market data; no paid plan is selected automatically.")
    parser.add_argument("--env-file", type=Path, help="Explicit local .env file; existing environment variables win")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="Create additive market-data tables in MARKET_DATABASE_URL")
    show = sub.add_parser("latest", help="Read a verified price, never legacy current_price")
    show.add_argument("--symbol", default="AAPL")
    history = sub.add_parser("history", help="Read up to 90 calendar days with explicit missing/non-trading dates")
    history.add_argument("--symbol", default="AAPL")
    history.add_argument("--from", dest="start", type=date.fromisoformat)
    history.add_argument("--to", dest="end", type=date.fromisoformat)
    backfill = sub.add_parser("backfill", help="Fill missing published sessions; repeat to continue after interruption")
    backfill.add_argument("--symbols", nargs="+", help="Supported subset; defaults to all 20 symbols")
    backfill.add_argument("--from", dest="start", type=date.fromisoformat)
    backfill.add_argument("--to", dest="end", type=date.fromisoformat)
    backfill.add_argument("--raw-dir", type=Path, default=Path(".local/market-data"))
    backfill.add_argument("--raw-bucket", help="Existing private data bucket")
    backfill.add_argument("--evidence", type=Path, help="Optional credential-free coverage summary")
    listing = sub.add_parser("runs", help="List up to 100 recent runs for operator diagnosis")
    listing.add_argument("--status", choices=["running", "succeeded", "partial", "failed", "unavailable"])
    inspect = sub.add_parser("inspect", help="Show run, attempts, quarantine and published observations")
    inspect.add_argument("run_id", type=UUID)
    for name in ("resume", "retry"):
        recovery = sub.add_parser(name, help="Resume an interrupted run" if name == "resume" else "Create a linked retry of a failed/partial run")
        recovery.add_argument("run_id", type=UUID)
        recovery.add_argument("--raw-dir", type=Path, default=Path(".local/market-data"))
        recovery.add_argument("--raw-bucket", help="Same private bucket as the original run")
    run = sub.add_parser("ingest", help="Ingest one symbol and an inclusive date range")
    run.add_argument("--symbol", default="AAPL")
    run.add_argument("--from", dest="start", type=date.fromisoformat, required=True)
    run.add_argument("--to", dest="end", type=date.fromisoformat, required=True)
    run.add_argument("--raw-dir", type=Path, default=Path(".local/market-data"))
    run.add_argument("--raw-bucket", help="Existing private S3 data bucket; leave unset for local files")
    smoke = sub.add_parser("smoke", help="Verify AAPL's latest and 90-calendar-day coverage with one live provider request")
    smoke.add_argument("--raw-dir", type=Path, default=Path(".local/market-data"))
    smoke.add_argument("--evidence", type=Path, default=Path(".local/market-data/smoke.json"))
    args = parser.parse_args(argv)
    if args.env_file:
        load_dotenv(args.env_file, override=False)
    dsn = os.getenv("MARKET_DATABASE_URL")
    if not dsn:
        parser.error("Set MARKET_DATABASE_URL to the intended PostgreSQL database")
    now = datetime.now(timezone.utc)
    try:
        with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as connection:
            repository = PriceRepository(connection)
            if args.command == "migrate":
                repository.migrate()
                print(json.dumps({"status": "migrated"}))
                return 0
            if args.command == "latest":
                from .universe import require_symbol
                print(json.dumps(repository.latest(require_symbol(args.symbol), as_of=now)))
                return 0
            if args.command == "history":
                print(json.dumps(repository.history(args.symbol, args.start, args.end, as_of=now)))
                return 0
            if args.command == "runs":
                print(json.dumps(repository.runs(status=args.status)))
                return 0
            if args.command == "inspect":
                print(json.dumps(repository.report(str(args.run_id))))
                return 0
            key = os.getenv("MASSIVE_API_KEY") or os.getenv("POLYGON_API_KEY")
            if not key and args.command not in ("resume", "backfill"):
                parser.error("Set POLYGON_API_KEY or MASSIVE_API_KEY locally; never paste it into chat or commit it")
            store = (S3RawStore(args.raw_bucket, boto3.client("s3"))
                     if getattr(args, "raw_bucket", None) else LocalRawStore(args.raw_dir))
            with httpx.Client() as client:
                pipeline = DailyPricePipeline(MassiveDailyProvider(key, client, min_interval=13) if key else None,
                                              store, repository, clock=lambda: datetime.now(timezone.utc))
                if args.command == "backfill":
                    from .universe import SYMBOLS
                    def progress(row):
                        print(f"{row['symbol']}: {row['coverage']} ({row['available_count']}/{row['expected_count']})",
                              file=sys.stderr, flush=True)
                    result = HistoryBackfill(pipeline, repository, clock=lambda: now).run(
                        args.start, args.end, symbols=args.symbols or SYMBOLS, on_progress=progress)
                    if args.evidence:
                        args.evidence.parent.mkdir(parents=True, exist_ok=True)
                        args.evidence.write_text(json.dumps(result, indent=2), encoding="utf-8")
                    print(json.dumps(result))
                    return 0 if result["status"] == "succeeded" else 1
                if args.command in ("resume", "retry"):
                    result = getattr(pipeline, args.command)(str(args.run_id))
                else:
                    symbol = "AAPL" if args.command == "smoke" else args.symbol
                    start = now.astimezone(EASTERN).date() - timedelta(days=89) if args.command == "smoke" else args.start
                    end = latest_published_session(now) if args.command == "smoke" else args.end
                    result = pipeline.run(symbol, start, end)
            if args.command == "smoke":
                from .evidence import smoke_evidence
                evidence = smoke_evidence(repository, result, start, end, now)
                args.evidence.parent.mkdir(parents=True, exist_ok=True)
                args.evidence.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
                print(json.dumps(evidence))
                return 0 if evidence["status"] == "passed" else 1
            print(json.dumps(result))
            return 0 if result["status"] == "succeeded" else 1
    except (psycopg.Error, OSError, ValueError):
        # Do not print DSNs, API keys, request headers, or upstream response text.
        print("Market-data operation failed; check local configuration and run records.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
