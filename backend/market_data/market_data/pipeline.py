"""One entry point for daily pulls and bounded historical date ranges."""
from datetime import date, datetime, timedelta, timezone
import hashlib
from email.utils import parsedate_to_datetime
import math
import time
import httpx
import psycopg
from botocore.exceptions import BotoCoreError, ClientError
from .validation import InvalidMarketData, normalize_bars
from .calendar import latest_published_session, sessions
from .universe import require_symbol


class RunBlocked(ValueError):
    """An actionable precondition blocks a run without changing its evidence."""

    def __init__(self, run_id, code, message):
        super().__init__(message)
        self.run_id = run_id
        self.code = code


class DailyPricePipeline:
    def __init__(self, provider, raw_store, repository, *, clock=None, sleep=None):
        self.provider = provider
        self.raw_store = raw_store
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sleep = sleep or time.sleep

    def run(self, symbol, start, end):
        return self._run(symbol, start, end)

    def retry(self, run_id):
        run = self.repository.get_run(run_id)
        if run is None or run["status"] not in ("failed", "partial", "unavailable"):
            raise ValueError("Retry requires a failed, partial or unavailable run; resume interrupted runs")
        return self._run(run["symbol"], date.fromisoformat(run["from_date"]),
                         date.fromisoformat(run["to_date"]), retry_of=run_id)

    def _run(self, symbol, start, end, *, retry_of=None):
        now = self.clock()
        symbol = require_symbol(symbol)
        if type(start) is not date or type(end) is not date or not 0 <= (end - start).days < 90:
            raise ValueError("Supply an inclusive date range of 1 to 90 calendar days")
        if end > latest_published_session(now):
            raise ValueError("The requested end date is not yet available on the Basic plan")
        run_id = self.repository.start_run(symbol, start, end, now, retry_of=retry_of)
        with self.repository.symbol_lock(symbol) as acquired:
            if not acquired:
                return self.repository.finish(run_id, "failed", self.clock(), error_code="symbol_busy")
            return self._fetch(run_id, symbol, start, end)

    def resume(self, run_id):
        run = self.repository.get_run(run_id)
        if run is None:
            raise ValueError("Unknown market run")
        if run["status"] != "running":
            return run
        with self.repository.symbol_lock(run["symbol"]) as acquired:
            if not acquired:
                raise RunBlocked(run_id, "recovery_pending", "Market run is still active; retry recovery after it stops")
            run = self.repository.get_run(run_id)
            if run["status"] != "running":
                return run
            attempts = self.repository.attempts(run_id)
            last = attempts[-1] if attempts else None
            start, end = date.fromisoformat(run["from_date"]), date.fromisoformat(run["to_date"])
            if last and last["http_status"] == 200 and last["raw_key"]:
                try:
                    body = self.raw_store.read(last["raw_key"])
                except (OSError, BotoCoreError, ClientError):
                    return self.repository.finish(run_id, "failed", self.clock(), error_code="raw_recovery_failed")
                if hashlib.sha256(body).hexdigest() != last["raw_sha256"]:
                    return self.repository.finish(run_id, "failed", self.clock(), error_code="raw_digest_mismatch")
                return self._publish(run_id, body, run["symbol"], start, end,
                                     datetime.fromisoformat(last["finished_at"]))
            if last and last["finished_at"]:
                if not last["retry_at"]:
                    return self.repository.finish(run_id, "failed", self.clock(), error_code=last["error_code"])
                delay = max(0, (datetime.fromisoformat(last["retry_at"]) - self.clock()).total_seconds())
                if delay > 60:
                    raise RunBlocked(run_id, "recovery_pending", "Retry time is still in the future; resume later")
                if delay:
                    self.sleep(delay)
            return self._fetch(run_id, run["symbol"], start, end)

    def _fetch(self, run_id, symbol, start, end):
        for number in range(len(self.repository.attempts(run_id)) + 1, 4):
            if self.provider is None:
                raise RunBlocked(run_id, "provider_key_required", "A provider API key is needed to resume fetching")
            self.repository.begin_attempt(run_id, number, self.clock())
            response = None
            try:
                response = self.provider.fetch(symbol, start, end)
                error = None if response.status_code == 200 else f"provider_http_{response.status_code}"
            except httpx.TimeoutException:
                error = "provider_timeout"
            except httpx.RequestError:
                error = "provider_connection_error"
            key = digest = location = None
            if response is not None:
                digest = hashlib.sha256(response.content).hexdigest()
                key = f"raw/massive/{symbol}/{run_id}/{number}/{digest}.json"
                try:
                    location = self.raw_store.save(key, response.content)
                except (OSError, BotoCoreError, ClientError):
                    self.repository.record_attempt(run_id, number, self.clock(), error_code="raw_storage_failed")
                    return self.repository.finish(run_id, "failed", self.clock(), error_code="raw_storage_failed")
            transient = response is None or response.status_code in (408, 429, 500, 502, 503, 504)
            delay = self._retry_delay(response, number)
            retry_at = self.clock() + timedelta(seconds=delay) if error and transient and number < 3 and delay <= 60 else None
            self.repository.record_attempt(run_id, number, self.clock(),
                                           status=response.status_code if response is not None else None,
                                           error_code=error, key=key, digest=digest, location=location, retry_at=retry_at)
            if error is None:
                return self._publish(run_id, response.content, symbol, start, end, self.clock())
            if retry_at is None:
                return self.repository.finish(run_id, "failed", self.clock(), error_code=error)
            self.sleep(delay)
        return self.repository.finish(run_id, "failed", self.clock(), error_code="retry_budget_exhausted")

    def _retry_delay(self, response, number):
        delay = float(2 ** (number - 1))
        header = response.headers.get("Retry-After") if response is not None else None
        if header:
            try:
                requested = float(header)
            except ValueError:
                try:
                    requested = (parsedate_to_datetime(header) - self.clock()).total_seconds()
                except (ValueError, TypeError, OverflowError):
                    requested = delay
            if math.isfinite(requested):
                delay = max(delay, requested)
        return delay

    def _publish(self, run_id, body, symbol, start, end, now):
        try:
            bars, rejected = normalize_bars(body, symbol, start, end, now)
        except InvalidMarketData as error:
            return self.repository.finish(run_id, "failed", self.clock(), error_code=str(error),
                                          rejected=[{"row_index": None, "reason": str(error)}])
        if not bars and not rejected:
            return self.repository.finish(run_id, "unavailable", self.clock(), error_code="no_bars")
        dates = {bar["trade_date"] for bar in bars}
        expected = sessions(start, end)
        completed_through = None
        for day in expected:
            if day not in dates:
                break
            completed_through = day
        missing_count = len(set(expected) - dates)
        status = "failed" if not bars else "partial" if rejected or missing_count else "succeeded"
        try:
            return self.repository.finish(run_id, status, self.clock(), bars=bars, rejected=rejected,
                                          completed_through=completed_through, missing_count=missing_count,
                                          error_code="quality_rejected" if rejected else "missing_sessions" if missing_count else None)
        except psycopg.Error:
            # The load transaction has rolled back. If PostgreSQL itself is
            # unreachable this update also fails, leaving a recoverable run.
            return self.repository.finish(run_id, "failed", self.clock(), error_code="database_load_failed")
