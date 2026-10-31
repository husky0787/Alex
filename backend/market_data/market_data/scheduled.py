"""Shared CronJob/manual Job entry; persisted outcomes plus structured JSON logs."""
import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path

import boto3
import httpx
import psycopg

from .backfill import HistoryBackfill
from .calendar import history_window, latest_published_session
from .executions import ExecutionRepository
from .pipeline import DailyPricePipeline, RunBlocked
from .provider import MassiveDailyProvider
from .repository import PriceRepository
from .storage import LocalRawStore, S3RawStore
from .universe import SYMBOLS, require_symbol


class ScheduledETL:
    def __init__(self, pipeline, prices, *, clock=None):
        self.pipeline = pipeline
        self.prices = prices
        self.executions = ExecutionRepository(prices)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def run(self, mode, start=None, end=None, symbols=SYMBOLS):
        now = self.clock()
        if mode == 'daily':
            start = end = latest_published_session(now)
        elif mode != 'backfill':
            raise ValueError('Expected daily or backfill mode')
        start, end = history_window(now, start, end)
        if end > latest_published_session(now):
            raise ValueError('End date is not published yet')
        symbols = tuple(dict.fromkeys(require_symbol(symbol) for symbol in symbols))
        if not symbols:
            raise ValueError('Select at least one supported symbol')
        execution_id = self.executions.start(mode, start, end, symbols, now)
        results = []
        # Serializes scheduled/manual batches, including rate pacing. The pipeline's
        # existing per-symbol lock still protects against legacy ingest/backfill commands.
        with self.prices.symbol_lock('__scheduled_batch__') as acquired:
            if not acquired:
                return self._finish(execution_id, 'blocked', 'batch_busy')
            for interrupted in self.executions.interrupted(execution_id):
                self._finish(interrupted, 'failed', 'worker_interrupted')
            for symbol in symbols:
                try:
                    result = HistoryBackfill(self.pipeline, self.prices, clock=lambda: now).run(
                        start, end, symbols=[symbol])
                    results.extend(result['symbols'])
                except RunBlocked as exc:
                    results.append({'symbol': symbol, 'run_id': exc.run_id, 'run_ids': [exc.run_id],
                                    'error_code': exc.code, 'complete': False})
                    self.executions.checkpoint(execution_id, results)
                    return self._finish(execution_id, 'failed', exc.code)
                except Exception as exc:
                    # Persist a safe exception class and retain the original exception
                    # for the caller; never turn an unknown failure into pending/success.
                    try:
                        self._finish(execution_id, 'failed', type(exc).__name__)
                    except psycopg.Error:
                        raise exc from None
                    raise
                self.executions.checkpoint(execution_id, results)
            failed = [row for row in results if not row['complete'] or row['error_code']
                      or row['run_status'] not in (None, 'succeeded')]
            return self._finish(execution_id, 'partial' if failed else 'succeeded',
                                failed[0]['error_code'] or 'missing_sessions' if failed else None)

    def _finish(self, execution_id, status, error=None):
        now = self.clock()
        with self.prices.connection.transaction():
            result = self.executions.finish(execution_id, status, now, error)
            if status != 'succeeded':
                self.executions.alert(f'execution:{execution_id}', 'execution_' + status,
                                      {'error_code': error}, now, execution_id)
        return result


def main(argv=None, *, provider_factory=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['daily', 'backfill', 'monitor'])
    parser.add_argument('--from', dest='start', type=date.fromisoformat)
    parser.add_argument('--to', dest='end', type=date.fromisoformat)
    parser.add_argument('--symbols', nargs='+', default=list(SYMBOLS))
    parser.add_argument('--raw-dir', type=Path, default=Path('/data'))
    parser.add_argument('--raw-bucket')
    args = parser.parse_args(argv)
    if args.mode == 'daily' and (args.start or args.end):
        parser.error('Daily selects its date from the publication calendar; use backfill for a range')
    if args.mode == 'backfill' and (not args.start or not args.end):
        parser.error('Backfill requires --from and --to')
    try:
        dsn = os.environ['MARKET_DATABASE_URL']
        with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as connection:
            prices = PriceRepository(connection)
            if args.mode == 'monitor':
                result = ExecutionRepository(prices).monitor(symbols=[require_symbol(s) for s in args.symbols])
                print(json.dumps(result), flush=True)
                return 0 if result['health']['healthy'] else 1
            store = S3RawStore(args.raw_bucket, boto3.client('s3')) if args.raw_bucket else LocalRawStore(args.raw_dir)
            with httpx.Client() as client:
                key = os.getenv('MASSIVE_API_KEY') or os.getenv('POLYGON_API_KEY')
                provider = (provider_factory(client) if provider_factory else
                            MassiveDailyProvider(key, client, min_interval=13) if key else None)
                result = ScheduledETL(DailyPricePipeline(provider, store, prices), prices).run(
                    args.mode, args.start, args.end, args.symbols)
            print(json.dumps(result), flush=True)
            return 0 if result['status'] == 'succeeded' else 1
    except Exception as exc:
        # Failed Jobs retain this JSON event even when PostgreSQL itself is unreachable.
        print(json.dumps({'event': 'etl_process_failed', 'error_code': type(exc).__name__,
                          'mode': args.mode}), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
