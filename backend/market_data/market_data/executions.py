"""Durable batch outcomes and alert events, separate from per-symbol price runs."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .calendar import latest_published_session
from .repository import serialize
from .universe import SYMBOLS


class ExecutionRepository:
    def __init__(self, prices):
        self.prices = prices
        self.connection = prices.connection

    def start(self, mode, start, end, symbols, now):
        execution_id = str(uuid4())
        self.connection.execute(
            """INSERT INTO market_executions
               (id, mode, from_date, to_date, symbols, started_at, status)
               VALUES (%s, %s, %s, %s, %s, %s, 'running')""",
            (execution_id, mode, start, end, list(symbols), now),
        )
        return execution_id

    def checkpoint(self, execution_id, results):
        self.connection.execute("UPDATE market_executions SET results=%s WHERE id=%s",
                                (Jsonb(results), execution_id))

    def interrupted(self, execution_id):
        # Caller holds the scheduled batch lock: no previous batch can still be
        # doing work. Exclude just-created contenders until their lock check runs.
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("""SELECT id FROM market_executions WHERE status='running'
                              AND sequence < (SELECT sequence FROM market_executions WHERE id=%s)
                              AND started_at < (SELECT started_at FROM market_executions WHERE id=%s)
                                               - interval '45 minutes'""", (execution_id, execution_id))
            return [str(row['id']) for row in cursor.fetchall()]

    def finish(self, execution_id, status, now, error=None):
        self.connection.execute(
            "UPDATE market_executions SET status=%s, finished_at=%s, error_code=%s WHERE id=%s",
            (status, now, error, execution_id),
        )
        return self.get(execution_id)

    def get(self, execution_id):
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT * FROM market_executions WHERE id=%s", (execution_id,))
            return self.summary(cursor.fetchone())

    def summary(self, row):
        result = serialize(row)
        result['duration_seconds'] = ((row['finished_at'] - row['started_at']).total_seconds()
                                      if row['finished_at'] else None)
        run_ids = list(dict.fromkeys(run_id for item in result['results'] for run_id in item['run_ids']))
        # Include original IDs and safe diagnostics, never raw locations or response bodies.
        runs = [self.prices.get_run(run_id) for run_id in run_ids]
        result['runs'] = [{key: run[key] for key in (
            'id', 'symbol', 'status', 'started_at', 'finished_at', 'accepted_count',
            'rejected_count', 'missing_count', 'error_code')} for run in runs]
        result['accepted_count'] = sum(run['accepted_count'] for run in runs)
        result['rejected_count'] = sum(run['rejected_count'] for run in runs)
        return result

    def recent(self, limit=20):
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT * FROM market_executions ORDER BY sequence DESC LIMIT %s", (limit,))
            return [self.summary(row) for row in cursor.fetchall()]

    def alert(self, key, code, details, now, execution_id=None):
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """INSERT INTO market_alerts (id, dedup_key, created_at, code, execution_id, details)
                   VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (dedup_key) DO NOTHING RETURNING *""",
                (uuid4(), key, now, code, execution_id, Jsonb(details)),
            )
            return serialize(cursor.fetchone())

    def alerts(self):
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT * FROM market_alerts ORDER BY created_at DESC, id DESC LIMIT 100")
            return [serialize(row) for row in cursor.fetchall()]

    def health(self, now, symbols=SYMBOLS):
        expected = latest_published_session(now)
        # Check a rolling week, including interior holes even when the latest bar is fresh.
        start = expected - timedelta(days=6)
        prices = []
        for symbol in symbols:
            latest = self.prices.latest(symbol, as_of=now)
            history = self.prices.history(symbol, start, expected, as_of=now)
            prices.append({'symbol': symbol, 'status': latest['status'],
                           'latest_trade_date': latest['price']['trade_date'] if latest['price'] else None,
                           'missing_dates': history['missing_dates']})
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT id FROM market_executions WHERE status='running' AND started_at < %s",
                           (now - timedelta(minutes=45),))
            overdue = [str(row['id']) for row in cursor.fetchall()]
        return {'as_of': now.isoformat(), 'expected_trade_date': expected.isoformat(),
                'from_date': start.isoformat(), 'healthy': not overdue and not any(p['missing_dates'] for p in prices),
                'prices': prices, 'overdue_execution_ids': overdue}

    def monitor(self, now=None, symbols=SYMBOLS):
        now = now or datetime.now(timezone.utc)
        health = self.health(now, symbols)
        emitted = []
        for price in health['prices']:
            for missing in price['missing_dates']:
                event = self.alert(f"missing:{price['symbol']}:{missing}", 'missing_session',
                                   {'symbol': price['symbol'], 'trade_date': missing}, now)
                if event:
                    emitted.append(event)
        for execution_id in health['overdue_execution_ids']:
            event = self.alert(f'overdue:{execution_id}', 'execution_overdue', {}, now, execution_id)
            if event:
                emitted.append(event)
        return {'health': health, 'emitted_alerts': emitted}
