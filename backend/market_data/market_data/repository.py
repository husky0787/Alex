"""PostgreSQL history and run records; no fallback to instruments.current_price."""
from datetime import date, datetime
from contextlib import contextmanager
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

    @contextmanager
    def symbol_lock(self, symbol):
        # A session lock fences source acquisition as well as publication. A
        # disconnected/crashed worker releases it automatically in PostgreSQL.
        key = self.connection.execute(
            "SELECT hashtextextended(current_schema() || ':market:massive:' || %s, 0)", (symbol,),
        ).fetchone()[0]
        acquired = self.connection.execute("SELECT pg_try_advisory_lock(%s)", (key,)).fetchone()[0]
        try:
            yield acquired
        finally:
            if acquired and not self.connection.closed:
                self.connection.execute("SELECT pg_advisory_unlock(%s)", (key,))

    def start_run(self, symbol, start, end, now, *, retry_of=None):
        run_id = uuid4()
        with self.connection.transaction():
            self.connection.execute(
                """INSERT INTO market_runs
                   (id, source, symbol, from_date, to_date, adjusted, started_at, status, retry_of)
                   VALUES (%s, 'massive', %s, %s, %s, true, %s, 'running', %s)""",
                (run_id, symbol, start, end, now, retry_of),
            )
        return str(run_id)

    def record_raw(self, run_id, key, digest, location):
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE market_runs SET raw_key=%s, raw_sha256=%s, raw_location=%s WHERE id=%s",
                (key, digest, location, run_id),
            )

    def begin_attempt(self, run_id, number, now):
        with self.connection.transaction():
            self.connection.execute(
                "INSERT INTO market_attempts (run_id, number, started_at) VALUES (%s, %s, %s)",
                (run_id, number, now),
            )

    def record_attempt(self, run_id, number, now, *, status=None, error_code=None,
                       key=None, digest=None, location=None, retry_at=None):
        with self.connection.transaction():
            self.connection.execute(
                """UPDATE market_attempts SET finished_at=%s, http_status=%s, error_code=%s,
                   raw_key=%s, raw_sha256=%s, raw_location=%s, retry_at=%s WHERE run_id=%s AND number=%s""",
                (now, status, error_code, key, digest, location, retry_at, run_id, number),
            )
            if key:
                self.record_raw(run_id, key, digest, location)

    def attempts(self, run_id):
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT * FROM market_attempts WHERE run_id=%s ORDER BY number", (run_id,))
            return [serialize(row) for row in cursor.fetchall()]

    def finish(self, run_id, status, now, *, bars=(), error_code=None, rejected=(),
               completed_through=None, missing_count=0):
        with self.connection.transaction():
            current = self.connection.execute("SELECT status FROM market_runs WHERE id=%s FOR UPDATE", (run_id,)).fetchone()
            if current is None:
                raise ValueError("Unknown market run")
            if current[0] != "running":
                return self.get_run(run_id)
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
                    """INSERT INTO market_observations (run_id, price_id, observed_at)
                       SELECT %s, id, %s FROM daily_prices WHERE source='massive' AND symbol=%s
                         AND trade_date=%s AND adjusted=true AND version=%s
                       ON CONFLICT DO NOTHING""",
                    (run_id, bar["fetched_at"], bar["symbol"], bar["trade_date"], bar["version"]),
                )
            for issue in rejected:
                self.connection.execute(
                    """INSERT INTO market_quarantine (id, run_id, row_index, reason, raw_key, raw_sha256)
                       SELECT %s, id, %s, %s, raw_key, raw_sha256 FROM market_runs WHERE id=%s""",
                    (uuid4(), issue["row_index"], issue["reason"], run_id),
                )
            self.connection.execute(
                """UPDATE market_runs SET status=%s, finished_at=%s, accepted_count=%s, error_code=%s,
                   rejected_count=%s, completed_through=%s, missing_count=%s WHERE id=%s""",
                (status, now, len(bars), error_code, len(rejected), completed_through, missing_count, run_id),
            )
        return self.get_run(run_id)

    def get_run(self, run_id):
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT * FROM market_runs WHERE id=%s", (run_id,))
            return serialize(cursor.fetchone())

    def runs(self, *, status=None, limit=100):
        if not 1 <= limit <= 100:
            raise ValueError("Run list limit must be between 1 and 100")
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """SELECT * FROM market_runs WHERE (%s::text IS NULL OR status=%s)
                   ORDER BY sequence DESC LIMIT %s""", (status, status, limit),
            )
            return [serialize(row) for row in cursor.fetchall()]

    def report(self, run_id):
        run = self.get_run(run_id)
        if run is None:
            raise ValueError("Unknown market run")
        return {"run": run, "attempts": self.attempts(run_id), "quarantine": self.quarantine(run_id),
                "observations": self.observations_for_run(run_id)}

    def quarantine(self, run_id):
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT * FROM market_quarantine WHERE run_id=%s ORDER BY row_index", (run_id,))
            return [serialize(row) for row in cursor.fetchall()]

    def observations(self, symbol, trade_date):
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT * FROM daily_prices WHERE symbol=%s AND trade_date=%s ORDER BY fetched_at, id",
                           (symbol, trade_date))
            return [serialize(row) for row in cursor.fetchall()]

    def observations_for_run(self, run_id):
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """SELECT p.*, o.observed_at FROM daily_prices p
                   JOIN market_observations o ON o.price_id=p.id WHERE o.run_id=%s ORDER BY p.trade_date""",
                (run_id,),
            )
            return [serialize(row) for row in cursor.fetchall()]

    def latest(self, symbol, *, as_of):
        expected = latest_published_session(as_of)
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """SELECT p.*, o.run_id, o.observed_at AS fetched_at, r.raw_sha256 FROM daily_prices p
                   JOIN market_observations o ON o.price_id=p.id
                   JOIN market_runs r ON r.id = o.run_id
                   WHERE p.symbol=%s AND p.source='massive' AND p.adjusted=true
                     AND p.trade_date <= %s AND r.status IN ('succeeded', 'partial')
                   ORDER BY p.trade_date DESC, o.observed_at DESC, r.sequence DESC LIMIT 1""",
                (symbol, expected),
            )
            row = cursor.fetchone()
        return {
            "symbol": symbol,
            "status": "unavailable" if row is None else "fresh" if row["trade_date"] == expected else "stale",
            "expected_trade_date": expected.isoformat(),
            "price": serialize(row),
        }
