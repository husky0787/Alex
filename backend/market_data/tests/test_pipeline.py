import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from datetime import date, datetime, timezone

import httpx
import psycopg
from psycopg import sql

from market_data.pipeline import DailyPricePipeline
from market_data.provider import MassiveDailyProvider
from market_data.repository import PriceRepository
from market_data.storage import LocalRawStore


class PipelineTests(unittest.TestCase):
    def setUp(self):
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
