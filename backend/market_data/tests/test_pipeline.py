import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from datetime import date, datetime, timedelta, timezone

import httpx
import psycopg
from psycopg import sql

from market_data.pipeline import DailyPricePipeline
from market_data.provider import MassiveDailyProvider
from market_data.repository import PriceRepository
from market_data.storage import LocalRawStore


class PipelineTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch
        sleeping = patch("market_data.pipeline.time.sleep", return_value=None)
        sleeping.start()
        self.addCleanup(sleeping.stop)
        self.connection = psycopg.connect(os.environ["MARKET_TEST_DATABASE_URL"], autocommit=True)
        self.schema = "test_" + uuid.uuid4().hex
        self.connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.connection.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema)))
        self.addCleanup(self.connection.close)
        self.addCleanup(lambda: self.connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema))))
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repository = PriceRepository(self.connection)
        self.repository.migrate()
        self.raw = LocalRawStore(Path(self.directory.name))
        self.now = datetime(2026, 10, 24, 8, tzinfo=timezone.utc)
        self.payload = {
            "ticker": "AAPL", "adjusted": True, "status": "OK", "resultsCount": 1,
            "results": [{"o": 100, "h": 110, "l": 95, "c": 105, "v": 1200,
                         "t": 1792728000000}],  # 2026-10-23 midnight America/New_York
        }

    def pipeline(self, payload=None):
        body = json.dumps(payload if payload is not None else self.payload).encode()
        def respond(request):
            self.assertEqual(request.headers["Authorization"], "Bearer test-key")
            self.assertNotIn("apiKey", str(request.url))
            return httpx.Response(200, content=body)
        client = httpx.Client(transport=httpx.MockTransport(respond))
        self.addCleanup(client.close)
        return DailyPricePipeline(MassiveDailyProvider("test-key", client), self.raw, self.repository,
                                  clock=lambda: self.now), body

    def test_source_response_becomes_traceable_verified_daily_price(self):
        pipeline, original = self.pipeline()
        run = pipeline.run("AAPL", date(2026, 10, 23), date(2026, 10, 23))
        self.assertEqual(run["status"], "succeeded")
        self.assertEqual(run["accepted_count"], 1)
        self.assertEqual(self.raw.read(run["raw_key"]), original)
        price = self.repository.latest("AAPL", as_of=self.now)
        self.assertEqual(price["status"], "fresh")
        self.assertEqual(price["price"]["close"], "105")
        self.assertEqual(price["price"]["trade_date"], "2026-10-23")
        self.assertEqual(price["price"]["source"], "massive")
        self.assertEqual(price["price"]["run_id"], run["id"])
        self.assertEqual(self.repository.get_run(run["id"])["raw_sha256"], run["raw_sha256"])

    def test_invalid_bars_are_retained_as_raw_but_never_become_prices(self):
        for changes in [
            {"c": -1}, {"h": 90}, {"l": 106}, {"o": "NaN"}, {"h": "Infinity"},
            {"v": -1}, {"v": "Infinity"}, {"v": True}, {"c": "105"}, {"t": 0},
        ]:
            with self.subTest(changes=changes):
                payload = {**self.payload, "results": [{**self.payload["results"][0], **changes}]}
                pipeline, original = self.pipeline(payload)
                run = pipeline.run("AAPL", date(2026, 10, 23), date(2026, 10, 23))
                self.assertEqual(run["status"], "failed")
                self.assertEqual(run["accepted_count"], 0)
                self.assertTrue(run["error_code"])
                self.assertEqual(self.raw.read(run["raw_key"]), original)
                self.assertEqual(self.repository.latest("AAPL", as_of=self.now)["status"], "unavailable")

    def test_empty_result_is_unavailable_not_a_successful_price(self):
        pipeline, _ = self.pipeline({**self.payload, "results": [], "resultsCount": 0})
        run = pipeline.run("AAPL", date(2026, 10, 23), date(2026, 10, 23))
        self.assertEqual(run["status"], "unavailable")
        self.assertEqual(run["error_code"], "no_bars")
        self.assertIsNone(self.repository.latest("AAPL", as_of=self.now)["price"])

    def test_quality_rejection_has_separate_immutable_quarantine_manifest(self):
        payload = {**self.payload, 'results': [{**self.payload['results'][0], 'c': -1}]}
        pipeline, body = self.pipeline(payload)
        run = pipeline.run('AAPL', date(2026,10,23), date(2026,10,23))
        paths = list(Path(self.directory.name).glob('quarantine/massive/AAPL/*/*.json'))
        self.assertEqual(len(paths), 1)
        manifest = json.loads(paths[0].read_text())
        self.assertEqual(manifest['run_id'], run['id'])
        self.assertEqual(manifest['raw_sha256'], run['raw_sha256'])
        self.assertEqual(self.raw.read(manifest['raw_key']), body)
        self.assertEqual(manifest['rejected'][0]['row_index'], 0)

    def test_quarantine_storage_failure_never_publishes_partial_success(self):
        from unittest.mock import patch
        payload = {**self.payload, 'results': [self.payload['results'][0], {**self.payload['results'][0], 'c': -1}]}
        pipeline, _ = self.pipeline(payload)
        original = self.raw.save
        def failing_save(key, body):
            if key.startswith('quarantine/'):
                raise OSError('test disk failure')
            return original(key, body)
        with patch.object(self.raw, 'save', side_effect=failing_save):
            run = pipeline.run('AAPL', date(2026,10,23), date(2026,10,23))
        self.assertEqual(run['status'], 'failed')
        self.assertEqual(run['error_code'], 'quarantine_storage_failed')
        self.assertEqual(run['accepted_count'], 0)
        self.assertIsNone(self.repository.latest('AAPL', as_of=self.now)['price'])

    def test_provider_failures_leave_sanitized_run_records(self):
        for status in [401, 403, 429, 500]:
            with self.subTest(status=status):
                body = b'{"status":"ERROR","message":"upstream failure"}'
                with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status, content=body))) as client:
                    pipeline = DailyPricePipeline(MassiveDailyProvider("test-key", client), self.raw,
                                                  self.repository, clock=lambda: self.now)
                    run = pipeline.run("AAPL", date(2026, 10, 23), date(2026, 10, 23))
                self.assertEqual(run["status"], "failed")
                self.assertEqual(run["error_code"], f"provider_http_{status}")
                self.assertEqual(self.raw.read(run["raw_key"]), body)
                self.assertNotIn("test-key", json.dumps(run))
                self.assertEqual(len(self.repository.attempts(run["id"])), 3 if status in (429, 500) else 1)
                self.assertIsNone(run["completed_through"])

    def test_timeout_is_recorded_without_inventing_a_price(self):
        def timeout(request):
            raise httpx.ReadTimeout("private request details", request=request)
        with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
            pipeline = DailyPricePipeline(MassiveDailyProvider("test-key", client), self.raw,
                                          self.repository, clock=lambda: self.now)
            run = pipeline.run("AAPL", date(2026, 10, 23), date(2026, 10, 23))
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["error_code"], "provider_timeout")
        self.assertIsNone(run["raw_key"])
        self.assertEqual(len(self.repository.attempts(run["id"])), 3)
        self.assertEqual(self.repository.latest("AAPL", as_of=self.now)["status"], "unavailable")

    def test_weekends_holidays_and_dst_use_the_latest_publishable_session(self):
        for timestamp, expected in [
            ("2026-10-25T12:00:00+00:00", "2026-10-23"),
            ("2026-10-26T21:00:00+00:00", "2026-10-23"),
            ("2026-10-27T04:00:00+00:00", "2026-10-26"),
            ("2026-03-10T03:59:00+00:00", "2026-03-06"),
            ("2026-03-10T04:00:00+00:00", "2026-03-09"),
            ("2026-11-03T04:59:00+00:00", "2026-10-30"),
            ("2026-11-03T05:00:00+00:00", "2026-11-02"),
            ("2026-11-27T05:00:00+00:00", "2026-11-25"),
        ]:
            with self.subTest(timestamp=timestamp):
                result = self.repository.latest("AAPL", as_of=datetime.fromisoformat(timestamp))
                self.assertEqual(result["expected_trade_date"], expected)
        pipeline, _ = self.pipeline()
        pipeline.run("AAPL", date(2026, 10, 23), date(2026, 10, 23))
        stale = self.repository.latest("AAPL", as_of=datetime(2026, 10, 27, 4, tzinfo=timezone.utc))
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(stale["price"]["close"], "105")

    def test_rerun_keeps_the_same_observation_identity_and_new_run_evidence(self):
        pipeline, _ = self.pipeline()
        first = pipeline.run("AAPL", date(2026, 10, 23), date(2026, 10, 23))
        first_price = self.repository.latest("AAPL", as_of=self.now)["price"]
        second = pipeline.run("AAPL", date(2026, 10, 23), date(2026, 10, 23))
        second_price = self.repository.latest("AAPL", as_of=self.now)["price"]
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(first_price["id"], second_price["id"])
        self.assertEqual(first["raw_sha256"], second["raw_sha256"])

    def test_invalid_envelopes_never_publish_prices(self):
        for changes in [
            {"ticker": "MSFT"}, {"adjusted": False}, {"status": "ERROR"},
            {"resultsCount": 2}, {"results": None}, {"next_url": "https://api.massive.com/more"},
            {"results": [{"c": 105}]},
        ]:
            with self.subTest(changes=changes):
                pipeline, _ = self.pipeline({**self.payload, **changes})
                run = pipeline.run("AAPL", date(2026, 10, 23), date(2026, 10, 23))
                self.assertEqual(run["status"], "failed")
                self.assertEqual(self.repository.latest("AAPL", as_of=self.now)["status"], "unavailable")

    def test_unsafe_symbol_and_unbounded_date_range_are_rejected_before_fetch(self):
        pipeline, _ = self.pipeline()
        for symbol, start, end in [
            ("../AAPL", date(2026, 10, 23), date(2026, 10, 23)),
            ("UNSUPPORTED", date(2026, 10, 23), date(2026, 10, 23)),
            ("AAPL", date(2026, 10, 24), date(2026, 10, 23)),
            ("AAPL", date(2025, 1, 1), date(2026, 10, 23)),
            ("AAPL", date(2026, 10, 24), date(2026, 10, 24)),
        ]:
            with self.subTest(symbol=symbol, start=start, end=end):
                with self.assertRaises(ValueError):
                    pipeline.run(symbol, start, end)

    def test_raw_storage_failure_does_not_publish_untraceable_prices(self):
        from unittest.mock import patch
        pipeline, _ = self.pipeline()
        with patch.object(self.raw, "save", side_effect=OSError("test disk unavailable")):
            run = pipeline.run("AAPL", date(2026, 10, 23), date(2026, 10, 23))
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["error_code"], "raw_storage_failed")
        self.assertEqual(self.repository.latest("AAPL", as_of=self.now)["status"], "unavailable")

    def test_smoke_evidence_requires_complete_requested_coverage(self):
        from market_data.evidence import smoke_evidence
        pipeline, _ = self.pipeline()
        day = date(2026, 10, 23)
        run = pipeline.run("AAPL", day, day)
        evidence = smoke_evidence(self.repository, run, day, day, self.now)
        self.assertEqual(evidence["status"], "passed")
        self.assertEqual(evidence["expected_session_count"], 1)
        self.assertNotIn("test-key", json.dumps(evidence))
        self.assertNotIn("raw_location", evidence)
        missing = smoke_evidence(self.repository, run, date(2026, 10, 22), day, self.now)
        self.assertEqual(missing["status"], "failed")

    def test_real_provider_fractional_volume_preserves_decimal_precision(self):
        # Massive's 2026 fractional-share feed supplies decimal numeric volume.
        payload = {**self.payload, "results": [{**self.payload["results"][0], "v": 51859042.576473}]}
        pipeline, _ = self.pipeline(payload)
        run = pipeline.run("AAPL", date(2026, 10, 23), date(2026, 10, 23))
        self.assertEqual(run["status"], "succeeded")
        self.assertEqual(self.repository.latest("AAPL", as_of=self.now)["price"]["volume"], "51859042.576473")

    def test_database_failure_rolls_back_the_batch_and_records_failure(self):
        self.connection.execute("ALTER TABLE daily_prices ADD CONSTRAINT fail_fixture CHECK (close <> 106)")
        row = self.payload["results"][0]
        payload = {**self.payload, "resultsCount": 2, "results": [
            {**row, "t": 1792641600000},  # 2026-10-22 midnight ET
            {**row, "c": 106},
        ]}
        pipeline, original = self.pipeline(payload)
        run = pipeline.run("AAPL", date(2026, 10, 22), date(2026, 10, 23))
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["error_code"], "database_load_failed")
        self.assertEqual(self.repository.latest("AAPL", as_of=self.now)["status"], "unavailable")
        self.assertEqual(self.raw.read(run["raw_key"]), original)

    def test_partial_batch_quarantines_bad_row_without_hiding_valid_price_or_gap(self):
        row = self.payload["results"][0]
        pipeline, original = self.pipeline({**self.payload, "resultsCount": 2, "results": [
            {**row, "t": 1792641600000, "c": -1}, row,
        ]})
        run = pipeline.run("AAPL", date(2026, 10, 22), date(2026, 10, 23))
        self.assertEqual(run["status"], "partial")
        self.assertEqual((run["accepted_count"], run["rejected_count"]), (1, 1))
        self.assertIsNone(run["completed_through"])
        self.assertEqual(self.repository.latest("AAPL", as_of=self.now)["price"]["close"], "105")
        issues = self.repository.quarantine(run["id"])
        self.assertEqual(issues[0]["row_index"], 0)
        self.assertEqual(issues[0]["reason"], "invalid_price")
        self.assertEqual(issues[0]["raw_sha256"], run["raw_sha256"])
        self.assertEqual(self.raw.read(issues[0]["raw_key"]), original)

    def test_transient_provider_failures_retry_with_bound_and_attempt_evidence(self):
        replies = [httpx.Response(429, content=b'{"status":"ERROR"}', headers={"Retry-After": "20"}),
                   httpx.ReadTimeout("private"), httpx.Response(200, json=self.payload)]
        delays = []
        def respond(request):
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            pipeline = DailyPricePipeline(MassiveDailyProvider("test-key", client), self.raw,
                                          self.repository, clock=lambda: self.now, sleep=delays.append)
            run = pipeline.run("AAPL", date(2026, 10, 23), date(2026, 10, 23))
        self.assertEqual(run["status"], "succeeded")
        self.assertEqual(delays, [20, 2])
        attempts = self.repository.attempts(run["id"])
        self.assertEqual([a["error_code"] for a in attempts], ["provider_http_429", "provider_timeout", None])
        self.assertEqual(self.raw.read(attempts[0]["raw_key"]), b'{"status":"ERROR"}')
        self.assertEqual(self.raw.read(attempts[2]["raw_key"]), json.dumps(self.payload, separators=(",", ":")).encode())

    def test_provider_revision_back_to_original_keeps_versions_and_latest_sighting(self):
        day = date(2026, 10, 23)
        original, _ = self.pipeline()
        first = original.run("AAPL", day, day)
        first_price = self.repository.latest("AAPL", as_of=self.now)["price"]
        self.now += timedelta(seconds=1)
        corrected, _ = self.pipeline({**self.payload, "results": [{**self.payload["results"][0], "c": 106}]})
        second = corrected.run("AAPL", day, day)
        second_price = self.repository.latest("AAPL", as_of=self.now)["price"]
        self.assertEqual(second_price["close"], "106")
        self.now += timedelta(seconds=1)
        third = original.run("AAPL", day, day)
        latest = self.repository.latest("AAPL", as_of=self.now)["price"]
        self.assertEqual(latest["close"], "105")
        self.assertEqual(latest["id"], first_price["id"])
        self.assertEqual(latest["run_id"], third["id"])
        history = self.repository.observations("AAPL", day)
        self.assertEqual(len(history), 2)
        self.assertEqual(len(self.repository.observations_for_run(first["id"])), 1)
        self.assertEqual(self.repository.observations_for_run(second["id"])[0]["id"], second_price["id"])
        self.assertEqual(self.repository.observations_for_run(third["id"])[0]["id"], first_price["id"])

    def test_concurrent_same_symbol_run_cannot_fetch_or_publish_ahead_of_owner(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        entered, release = Event(), Event()
        day = date(2026, 10, 23)
        def slow_response(request):
            entered.set()
            if not release.wait(10):
                raise AssertionError("Test did not release source response")
            return httpx.Response(200, json=self.payload)
        def concurrent_run():
            with psycopg.connect(os.environ["MARKET_TEST_DATABASE_URL"], autocommit=True) as conn:
                conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema)))
                with httpx.Client(transport=httpx.MockTransport(slow_response)) as client:
                    return DailyPricePipeline(MassiveDailyProvider("test-key", client), self.raw,
                                              PriceRepository(conn), clock=lambda: self.now).run("AAPL", day, day)
        with ThreadPoolExecutor(max_workers=1) as workers:
            first = workers.submit(concurrent_run)
            try:
                self.assertTrue(entered.wait(5))
                self.assertEqual(self.repository.latest("AAPL", as_of=self.now)["status"], "unavailable")
                pipeline, _ = self.pipeline()
                busy = pipeline.run("AAPL", day, day)
                self.assertEqual(busy["status"], "failed")
                self.assertEqual(busy["error_code"], "symbol_busy")
                self.assertIsNone(busy["completed_through"])
                self.assertEqual(self.repository.attempts(busy["id"]), [])
                active = self.repository.runs(status="running")[0]
                with self.assertRaisesRegex(ValueError, "still active"):
                    pipeline.resume(active["id"])
            finally:
                release.set()
            self.assertEqual(first.result(timeout=10)["status"], "succeeded")

    def test_resume_retained_raw_after_interruption_is_idempotent_and_keeps_observation_time(self):
        import hashlib
        day = date(2026, 10, 23)
        body = json.dumps(self.payload).encode()
        run_id = self.repository.start_run("AAPL", day, day, self.now)
        self.repository.begin_attempt(run_id, 1, self.now)
        digest = hashlib.sha256(body).hexdigest()
        key = f"raw/massive/AAPL/{run_id}/1/{digest}.json"
        location = self.raw.save(key, body)
        self.repository.record_attempt(run_id, 1, self.now, status=200, key=key, digest=digest, location=location)
        self.assertEqual(self.repository.get_run(run_id)["status"], "running")
        self.assertEqual(self.repository.latest("AAPL", as_of=self.now)["status"], "unavailable")
        observed_at = self.now.isoformat()
        self.now += timedelta(hours=1)
        def forbidden(request):
            raise AssertionError("Recovery must use saved raw evidence")
        with httpx.Client(transport=httpx.MockTransport(forbidden)) as client:
            pipeline = DailyPricePipeline(MassiveDailyProvider("test-key", client), self.raw,
                                          self.repository, clock=lambda: self.now)
            recovered = pipeline.resume(run_id)
            self.assertEqual(recovered["status"], "succeeded")
            self.assertEqual(pipeline.resume(run_id), recovered)
        price = self.repository.latest("AAPL", as_of=self.now)["price"]
        self.assertEqual(datetime.fromisoformat(price["fetched_at"]), datetime.fromisoformat(observed_at))
        self.assertEqual(len(self.repository.observations("AAPL", day)), 1)

    def test_resume_after_rate_limit_preserves_retry_after_and_attempt_budget(self):
        delays = []
        replies = [httpx.Response(429, json={"status": "ERROR"}, headers={"Retry-After": "20"}),
                   httpx.Response(200, json=self.payload)]
        class InterruptedSleep:
            def __call__(self, seconds):
                raise InterruptedError("Simulate worker crash before backoff")
        with httpx.Client(transport=httpx.MockTransport(lambda request: replies.pop(0))) as client:
            pipeline = DailyPricePipeline(MassiveDailyProvider("test-key", client), self.raw,
                                          self.repository, clock=lambda: self.now, sleep=InterruptedSleep())
            with self.assertRaises(InterruptedError):
                pipeline.run("AAPL", date(2026, 10, 23), date(2026, 10, 23))
            # Operator-facing list is needed to find interrupted runs.
            run = self.repository.runs(status="running")[0]
            pipeline.sleep = delays.append
            recovered = pipeline.resume(run["id"])
        self.assertEqual(delays, [20])
        self.assertEqual(recovered["status"], "succeeded")
        self.assertEqual(len(self.repository.attempts(run["id"])), 2)

    def test_operator_cli_reports_failures_without_reading_a_provider_key(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        from psycopg.conninfo import make_conninfo
        from market_data.__main__ import main
        pipeline, _ = self.pipeline({**self.payload, "results": [{"c": 105}]})
        failed = pipeline.run("AAPL", date(2026, 10, 23), date(2026, 10, 23))
        environment = {"MARKET_DATABASE_URL": make_conninfo(os.environ["MARKET_TEST_DATABASE_URL"],
                                                           options=f"-csearch_path={self.schema}")}
        with patch.dict(os.environ, environment, clear=True), redirect_stdout(StringIO()) as output:
            self.assertEqual(main(["inspect", failed["id"]]), 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["run"]["status"], "failed")
        self.assertEqual(report["quarantine"][0]["reason"], "missing_bar_fields")
        self.assertEqual(len(report["attempts"]), 1)

    def test_fractional_volume_revision_beyond_decimal_context_is_not_deduplicated(self):
        day = date(2026, 10, 23)
        for volume in ("1200.12345678901234567890123456781", "1200.12345678901234567890123456782"):
            body = json.dumps(self.payload).replace('"v": 1200', '"v": ' + volume).encode()
            with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body))) as client:
                pipeline = DailyPricePipeline(MassiveDailyProvider("test-key", client), self.raw,
                                              self.repository, clock=lambda: self.now)
                self.assertEqual(pipeline.run("AAPL", day, day)["status"], "succeeded")
            self.assertEqual(self.repository.latest("AAPL", as_of=self.now)["price"]["volume"], volume)
        self.assertEqual(len(self.repository.observations("AAPL", day)), 2)

    def test_duplicate_dates_are_all_quarantined_and_silent_gaps_are_partial(self):
        row = self.payload["results"][0]
        pipeline, _ = self.pipeline({**self.payload, "resultsCount": 2, "results": [row, {**row, "c": 106}]})
        duplicate = pipeline.run("AAPL", date(2026, 10, 23), date(2026, 10, 23))
        self.assertEqual(duplicate["status"], "failed")
        self.assertEqual(duplicate["accepted_count"], 0)
        self.assertEqual([q["reason"] for q in self.repository.quarantine(duplicate["id"])],
                         ["duplicate_trade_date", "duplicate_trade_date"])
        pipeline, _ = self.pipeline()
        gap = pipeline.run("AAPL", date(2026, 10, 22), date(2026, 10, 23))
        self.assertEqual(gap["status"], "partial")
        self.assertEqual(gap["missing_count"], 1)
        self.assertEqual(gap["rejected_count"], 0)
        self.assertIsNone(gap["completed_through"])

    def test_retry_after_above_bound_stops_instead_of_retrying_too_early(self):
        delays = []
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
                429, json={"status": "ERROR"}, headers={"Retry-After": "120"}))) as client:
            pipeline = DailyPricePipeline(MassiveDailyProvider("test-key", client), self.raw,
                                          self.repository, clock=lambda: self.now, sleep=delays.append)
            result = pipeline.run("AAPL", date(2026, 10, 23), date(2026, 10, 23))
        self.assertEqual(result["error_code"], "provider_http_429")
        self.assertEqual(len(self.repository.attempts(result["id"])), 1)
        self.assertEqual(delays, [])

    def test_corrupt_retained_raw_cannot_be_published_on_resume(self):
        import hashlib
        day = date(2026, 10, 23)
        run_id = self.repository.start_run("AAPL", day, day, self.now)
        self.repository.begin_attempt(run_id, 1, self.now)
        body = json.dumps(self.payload).encode()
        key = f"raw/massive/AAPL/{run_id}/original.json"
        location = self.raw.save(key, body)
        self.repository.record_attempt(run_id, 1, self.now, status=200, key=key,
                                       digest=hashlib.sha256(body).hexdigest(), location=location)
        (self.raw.root / key).write_bytes(b'{"tampered":true}')
        pipeline, _ = self.pipeline()
        result = pipeline.resume(run_id)
        self.assertEqual(result["error_code"], "raw_digest_mismatch")
        self.assertIsNone(result["completed_through"])
        self.assertEqual(self.repository.observations_for_run(run_id), [])

    def test_repeated_migration_preserves_existing_versions_and_sightings(self):
        pipeline, _ = self.pipeline()
        day = date(2026, 10, 23)
        first = pipeline.run("AAPL", day, day)
        second = pipeline.run("AAPL", day, day)
        price = self.repository.latest("AAPL", as_of=self.now)["price"]
        self.repository.migrate()
        self.repository.migrate()
        self.assertEqual(self.repository.latest("AAPL", as_of=self.now)["price"], price)
        self.assertEqual(len(self.repository.observations("AAPL", day)), 1)
        self.assertEqual(len(self.repository.observations_for_run(first["id"])), 1)
        self.assertEqual(len(self.repository.observations_for_run(second["id"])), 1)

    def test_task_two_database_upgrade_preserves_existing_verified_price(self):
        # Original schema from merged task 2 (7691716), not the current schema.
        schema = "legacy_" + uuid.uuid4().hex
        self.connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        self.addCleanup(lambda: self.connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))))
        self.connection.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        self.connection.execute((Path(__file__).parent / "fixtures/task-02-schema.sql").read_text())
        run_id, price_id = uuid.uuid4(), uuid.uuid4()
        self.connection.execute("""INSERT INTO market_runs
            (id, source, symbol, from_date, to_date, adjusted, started_at, finished_at, status, accepted_count, raw_sha256)
            VALUES (%s, 'massive', 'AAPL', '2026-10-23', '2026-10-23', true, %s, %s, 'succeeded', 1, 'original-digest')""",
            (run_id, self.now, self.now))
        self.connection.execute("""INSERT INTO daily_prices
            (id, source, symbol, trade_date, adjusted, open, high, low, close, volume, fetched_at, version, run_id)
            VALUES (%s, 'massive', 'AAPL', '2026-10-23', true, 100, 110, 95, 105, 1200.25, %s, 'original-version', %s)""",
            (price_id, self.now, run_id))
        self.repository.migrate()
        self.repository.migrate()
        result = self.repository.latest("AAPL", as_of=self.now)
        self.assertEqual(result["status"], "fresh")
        self.assertEqual(result["price"]["id"], str(price_id))
        self.assertEqual(result["price"]["raw_sha256"], "original-digest")
        self.assertEqual(result["price"]["volume"], "1200.25")

    def test_failed_database_load_can_be_retried_after_fix_without_advancing_early(self):
        day = date(2026, 10, 23)
        self.connection.execute("ALTER TABLE daily_prices ADD CONSTRAINT fail_load CHECK (close <> 105)")
        pipeline, _ = self.pipeline()
        failed = pipeline.run("AAPL", day, day)
        self.assertEqual(failed["error_code"], "database_load_failed")
        self.assertIsNone(failed["completed_through"])
        self.assertEqual(self.repository.observations_for_run(failed["id"]), [])
        self.connection.execute("ALTER TABLE daily_prices DROP CONSTRAINT fail_load")
        retried = pipeline.retry(failed["id"])
        self.assertEqual(retried["status"], "succeeded")
        self.assertEqual(retried["retry_of"], failed["id"])
        self.assertEqual(retried["completed_through"], "2026-10-23")
        self.assertEqual(self.repository.get_run(failed["id"]), failed)
        self.assertEqual(len(self.repository.observations("AAPL", day)), 1)
