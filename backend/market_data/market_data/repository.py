"""PostgreSQL history and run records; no fallback to instruments.current_price."""
from datetime import date, datetime
from decimal import Decimal
from importlib.resources import files
from uuid import UUID, uuid4

from psycopg.rows import dict_row

from .calendar import latest_published_session


def serialize(row):
    if row is None:
        return None
    return {key: str(value) if isinstance(value, (Decimal, UUID)) else
            value.isoformat() if isinstance(value, (date, datetime)) else value
            for key, value in row.items()}


class PriceRepository:
    def __init__(self, connection):
        self.connection = connection

    def migrate(self):
        with self.connection.transaction():
            self.connection.execute(files("market_data").joinpath("schema.sql").read_text())

    def start_run(self, symbol, start, end, now):
        run_id = uuid4()
        with self.connection.transaction():
            self.connection.execute(
                """INSERT INTO market_runs
                   (id, source, symbol, from_date, to_date, adjusted, started_at, status)
                   VALUES (%s, 'massive', %s, %s, %s, true, %s, 'running')""",
                (run_id, symbol, start, end, now),
            )
        return str(run_id)

    def record_raw(self, run_id, key, digest, location):
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE market_runs SET raw_key=%s, raw_sha256=%s, raw_location=%s WHERE id=%s",
                (key, digest, location, run_id),
            )

    def finish(self, run_id, status, now, *, bars=(), error_code=None):
        with self.connection.transaction():
            for bar in bars:
                self.connection.execute(
                    """INSERT INTO daily_prices
                       (id, source, symbol, trade_date, adjusted, open, high, low, close,
                        volume, fetched_at, version, run_id)
                       VALUES (%s, 'massive', %s, %s, true, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (source, symbol, trade_date, adjusted, version) DO NOTHING""",
                    (uuid4(), bar["symbol"], bar["trade_date"], bar["open"], bar["high"],
                     bar["low"], bar["close"], bar["volume"], bar["fetched_at"], bar["version"], run_id),
                )
            self.connection.execute(
                "UPDATE market_runs SET status=%s, finished_at=%s, accepted_count=%s, error_code=%s WHERE id=%s",
                (status, now, len(bars), error_code, run_id),
            )
        return self.get_run(run_id)

    def get_run(self, run_id):
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT * FROM market_runs WHERE id=%s", (run_id,))
            return serialize(cursor.fetchone())

    def latest(self, symbol, *, as_of):
        expected = latest_published_session(as_of)
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """SELECT p.*, r.raw_sha256 FROM daily_prices p
                   JOIN market_runs r ON r.id = p.run_id
                   WHERE p.symbol=%s AND p.source='massive' AND p.adjusted=true
                     AND p.trade_date <= %s AND r.status='succeeded'
                   ORDER BY p.trade_date DESC, p.fetched_at DESC, p.id DESC LIMIT 1""",
                (symbol, expected),
            )
            row = cursor.fetchone()
        return {
            "symbol": symbol,
            "status": "unavailable" if row is None else "fresh" if row["trade_date"] == expected else "stale",
            "expected_trade_date": expected.isoformat(),
            "price": serialize(row),
        }
