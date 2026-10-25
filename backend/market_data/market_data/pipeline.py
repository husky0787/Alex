"""One entry point for daily pulls and bounded historical date ranges."""
from datetime import date, datetime, timezone
import hashlib
import httpx
import psycopg
from botocore.exceptions import BotoCoreError, ClientError
from .validation import InvalidMarketData, normalize_bars
from .calendar import latest_published_session
from .universe import require_symbol


class DailyPricePipeline:
    def __init__(self, provider, raw_store, repository, *, clock=None):
        self.provider = provider
        self.raw_store = raw_store
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def run(self, symbol, start, end):
        now = self.clock()
        symbol = require_symbol(symbol)
        if type(start) is not date or type(end) is not date or not 0 <= (end - start).days < 90:
            raise ValueError("Supply an inclusive date range of 1 to 90 calendar days")
        if end > latest_published_session(now):
            raise ValueError("The requested end date is not yet available on the Basic plan")
        run_id = self.repository.start_run(symbol, start, end, now)
        try:
            response = self.provider.fetch(symbol, start, end)
        except httpx.TimeoutException:
            return self.repository.finish(run_id, "failed", self.clock(), error_code="provider_timeout")
        except httpx.RequestError:
            return self.repository.finish(run_id, "failed", self.clock(), error_code="provider_connection_error")
        digest = hashlib.sha256(response.content).hexdigest()
        key = f"raw/massive/{symbol}/{run_id}/{digest}.json"
        try:
            location = self.raw_store.save(key, response.content)
        except (OSError, BotoCoreError, ClientError):
            return self.repository.finish(run_id, "failed", self.clock(), error_code="raw_storage_failed")
        self.repository.record_raw(run_id, key, digest, location)
        if response.status_code != 200:
            return self.repository.finish(run_id, "failed", self.clock(), error_code=f"provider_http_{response.status_code}")
        try:
            bars = normalize_bars(response.content, symbol, start, end, now)
        except InvalidMarketData as error:
            return self.repository.finish(run_id, "failed", self.clock(), error_code=str(error))
        if not bars:
            return self.repository.finish(run_id, "unavailable", self.clock(), error_code="no_bars")
        try:
            return self.repository.finish(run_id, "succeeded", self.clock(), bars=bars)
        except psycopg.Error:
            # The load transaction has rolled back. If PostgreSQL itself is
            # unreachable this update also fails, leaving a recoverable run.
            return self.repository.finish(run_id, "failed", self.clock(), error_code="database_load_failed")
