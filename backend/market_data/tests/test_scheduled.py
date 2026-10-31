"""Batch acceptance tests using real PostgreSQL and injected source HTTP responses."""
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
import psycopg
from psycopg import sql

from market_data.calendar import EASTERN, latest_published_session, sessions
from market_data.executions import ExecutionRepository
from market_data.pipeline import DailyPricePipeline
from market_data.provider import MassiveDailyProvider
from market_data.repository import PriceRepository
from market_data.scheduled import ScheduledETL, main
from market_data.storage import LocalRawStore


class ScheduledTests(unittest.TestCase):
    def setUp(self):
        self.dsn = os.environ['MARKET_TEST_DATABASE_URL']
        self.connection = psycopg.connect(self.dsn, autocommit=True)
        self.schema = 'test_' + uuid4().hex
        self.connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
        self.connection.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(self.schema)))
        self.addCleanup(self.connection.close)
        self.addCleanup(lambda: self.connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema))))
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.prices = PriceRepository(self.connection)
        self.prices.migrate()
        self.executions = ExecutionRepository(self.prices)
        self.now = datetime(2026, 10, 24, 8, tzinfo=timezone.utc)
        self.day = date(2026, 10, 23)
        self.calls = 0

    def worker(self, *, bad=False, provider=True):
        def response(request):
            self.calls += 1
            parts = request.url.path.split('/')
            symbol, start, end = parts[4], date.fromisoformat(parts[-2]), date.fromisoformat(parts[-1])
            bars = [{'o':100, 'h':110, 'l':90, 'c':105, 'v':1000,
                     't':int(datetime.combine(day, datetime.min.time(), EASTERN).timestamp()*1000)}
                    for day in sessions(start, end)]
            if bad:
                bars.append({**bars[0], 'c':-1})
            return httpx.Response(200, json={'ticker':symbol, 'status':'OK', 'adjusted':True,
                                           'resultsCount':len(bars), 'results':bars})
        client = httpx.Client(transport=httpx.MockTransport(response))
        self.addCleanup(client.close)
        pipeline = DailyPricePipeline(MassiveDailyProvider('test-only', client) if provider else None,
            LocalRawStore(Path(self.directory.name)), self.prices, clock=lambda:self.now)
        return ScheduledETL(pipeline, self.prices, clock=lambda:self.now)

    def test_daily_uses_published_session_and_repeat_skips_fetch(self):
        first = self.worker().run('daily', symbols=['AAPL'])
        self.assertEqual(first['to_date'], '2026-10-23')
        self.assertEqual(first['status'], 'succeeded')
        self.assertEqual(first['accepted_count'], 1)
        self.assertIsNotNone(first['duration_seconds'])
        self.assertEqual(len(first['runs']), 1)
        second = self.worker().run('daily', symbols=['AAPL'])
        self.assertEqual(second['status'], 'succeeded')
        self.assertEqual(second['accepted_count'], 0)
        self.assertEqual(self.calls, 1)
        self.assertEqual(self.connection.execute('SELECT count(*) FROM daily_prices').fetchone()[0], 1)

    def test_quality_failure_with_complete_dates_is_partial_and_alerted(self):
        result = self.worker(bad=True).run('daily', symbols=['AAPL'])
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['error_code'], 'quality_rejected')
        self.assertEqual(result['accepted_count'], 1)
        self.assertEqual(result['rejected_count'], 1)
        self.assertEqual(self.executions.alerts()[0]['execution_id'], result['id'])

    def test_key_missing_preserves_original_run_and_recovery(self):
        result = self.worker(provider=False).run('daily', symbols=['AAPL'])
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['error_code'], 'provider_key_required')
        run_id = result['runs'][0]['id']
        recovered = self.worker().run('daily', symbols=['AAPL'])
        self.assertEqual(recovered['status'], 'succeeded')
        self.assertEqual(recovered['runs'][0]['id'], run_id)
        original = self.executions.get(result['id'])
        self.assertEqual(original, result)
        self.assertEqual(original['accepted_count'], 0)
        self.assertEqual(recovered['accepted_count'], 1)

    def test_batch_lock_blocks_other_connection_then_allows_retry(self):
        with psycopg.connect(self.dsn, autocommit=True, options=f'-c search_path={self.schema}') as other:
            with PriceRepository(other).symbol_lock('__scheduled_batch__') as acquired:
                self.assertTrue(acquired)
                result = self.worker().run('daily', symbols=['AAPL'])
                self.assertEqual(result['status'], 'blocked')
                self.assertEqual(result['error_code'], 'batch_busy')
                self.assertEqual(self.calls, 0)
            self.assertEqual(self.worker().run('daily', symbols=['AAPL'])['status'], 'succeeded')

    def test_legacy_symbol_lock_still_blocks_scheduled_worker(self):
        with psycopg.connect(self.dsn, autocommit=True, options=f'-c search_path={self.schema}') as other:
            with PriceRepository(other).symbol_lock('AAPL'):
                result = self.worker().run('daily', symbols=['AAPL'])
                self.assertEqual(result['status'], 'partial')
                self.assertEqual(result['error_code'], 'symbol_busy')
                self.assertEqual(self.calls, 0)

    def test_missed_middle_session_alert_then_manual_backfill_recovers(self):
        self.worker().run('daily', symbols=['AAPL'])
        before = self.executions.monitor(self.now, ['AAPL'])
        self.assertEqual(before['health']['prices'][0]['status'], 'fresh')
        self.assertFalse(before['health']['healthy'])
        self.assertTrue(before['emitted_alerts'])
        self.assertEqual(self.executions.monitor(self.now, ['AAPL'])['emitted_alerts'], [])
        result = self.worker().run('backfill', self.day-timedelta(days=6), self.day, ['AAPL'])
        self.assertEqual(result['status'], 'succeeded')
        self.assertTrue(self.executions.monitor(self.now, ['AAPL'])['health']['healthy'])
        self.assertTrue(self.executions.alerts())  # Historical events remain, health is current.

    def test_overdue_execution_is_detected_without_etl_running(self):
        execution_id = self.executions.start('daily', self.day, self.day, ['AAPL'], self.now-timedelta(hours=1))
        result = self.executions.monitor(self.now, ['AAPL'])
        self.assertIn(execution_id, result['health']['overdue_execution_ids'])
        self.assertTrue(any(e['code']=='execution_overdue' for e in result['emitted_alerts']))
        self.worker().run('daily', symbols=['AAPL'])
        self.assertEqual(self.executions.get(execution_id)['error_code'], 'worker_interrupted')
        self.assertEqual(self.executions.monitor(self.now, ['AAPL'])['health']['overdue_execution_ids'], [])

    def test_cli_returns_nonzero_for_quality_failure(self):
        worker = self.worker(bad=True)
        test_dsn = self.dsn + '?options=-csearch_path%3D' + self.schema
        with patch.dict(os.environ, {'MARKET_DATABASE_URL':test_dsn}), patch('builtins.print'):
            code = main(['backfill', '--from',str(self.day),'--to',str(self.day),
                         '--symbols','AAPL','--raw-dir',self.directory.name],
                        provider_factory=lambda client: worker.pipeline.provider)
        self.assertEqual(code, 1)

    def test_publication_calendar_handles_holiday_and_dst(self):
        self.assertEqual(latest_published_session(datetime(2026,11,30,5,15,tzinfo=timezone.utc)), date(2026,11,27))
        self.assertEqual(latest_published_session(datetime(2026,7,4,4,15,tzinfo=timezone.utc)), date(2026,7,2))


if __name__ == '__main__':
    unittest.main()
