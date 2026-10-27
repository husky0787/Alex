"""History and backfill behaviors over the real PostgreSQL pipeline boundary."""
from datetime import date, datetime, timedelta, timezone
import unittest

import test_pipeline


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_pipeline.PipelineTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.repository = self.fixture.repository

    def test_history_is_sorted_and_distinguishes_gaps_from_nontrading_and_unpublished_days(self):
        pipeline, _ = self.fixture.pipeline()
        pipeline.run("AAPL", date(2026, 10, 23), date(2026, 10, 23))
        history = self.repository.history("AAPL", date(2026, 10, 22), date(2026, 10, 26),
                                          as_of=datetime(2026, 10, 26, 21, tzinfo=timezone.utc))
        self.assertEqual([day["date"] for day in history["days"]],
                         ["2026-10-22", "2026-10-23", "2026-10-24", "2026-10-25", "2026-10-26"])
        self.assertEqual([day["status"] for day in history["days"]],
                         ["missing", "available", "weekend", "weekend", "not_published"])
        self.assertIsNone(history["days"][0]["price"])
        self.assertEqual(history["days"][1]["price"]["close"], "105")
        self.assertEqual(history["expected_count"], 2)
        self.assertEqual(history["available_count"], 1)
        self.assertEqual(history["missing_dates"], ["2026-10-22"])
        self.assertEqual(history["coverage"], "partial")
        self.assertEqual(history["source"], "massive")

    def test_all_twenty_symbols_backfill_and_restart_from_persisted_gaps(self):
        import httpx
        from market_data.backfill import HistoryBackfill
        from market_data.pipeline import DailyPricePipeline
        from market_data.provider import MassiveDailyProvider
        from market_data.universe import SYMBOLS
        requests = []
        stop_at = "MSFT"
        def response(request):
            symbol = request.url.path.split('/')[4]
            requests.append(symbol)
            if symbol == stop_at:
                raise InterruptedError("Simulate process interruption")
            return httpx.Response(200, json={**self.fixture.payload, "ticker": symbol})
        with httpx.Client(transport=httpx.MockTransport(response)) as client:
            pipeline = DailyPricePipeline(MassiveDailyProvider("test-key", client), self.fixture.raw,
                                          self.repository, clock=lambda: self.fixture.now)
            backfill = HistoryBackfill(pipeline, self.repository, clock=lambda: self.fixture.now)
            day = date(2026, 10, 23)
            with self.assertRaises(InterruptedError):
                backfill.run(day, day)
            first_aapl = self.repository.history("AAPL", day, day, as_of=self.fixture.now)["days"][0]["price"]
            stop_at = None
            result = backfill.run(day, day)
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual([r["symbol"] for r in result["symbols"]], list(SYMBOLS))
            self.assertEqual(len(result["symbols"]), 20)
            self.assertEqual(requests.count("AAPL"), 1)
            self.assertEqual(requests.count("MSFT"), 2)
            before = len(requests)
            again = backfill.run(day, day)
            self.assertEqual(again["status"], "succeeded")
            self.assertEqual(len(requests), before)
            self.assertTrue(all(row["action"] == "skipped" for row in again["symbols"]))
            self.assertEqual(self.repository.history("AAPL", day, day, as_of=self.fixture.now)["days"][0]["price"]["id"], first_aapl["id"])
            self.assertEqual(self.repository.runs(status="running"), [])

    def test_source_pacing_covers_retries_and_the_next_symbol(self):
        import httpx
        from market_data.backfill import HistoryBackfill
        from market_data.pipeline import DailyPricePipeline
        from market_data.provider import MassiveDailyProvider
        elapsed, request_times = [0.0], []
        def sleep(seconds):
            elapsed[0] += seconds
        def respond(request):
            request_times.append(elapsed[0])
            if len(request_times) == 1:
                return httpx.Response(429, json={"status": "ERROR"})
            symbol = request.url.path.split('/')[4]
            return httpx.Response(200, json={**self.fixture.payload, "ticker": symbol})
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            source = MassiveDailyProvider("test-key", client, min_interval=13,
                                          monotonic=lambda: elapsed[0], sleep=sleep)
            pipeline = DailyPricePipeline(source, self.fixture.raw, self.repository,
                                          clock=lambda: self.fixture.now, sleep=sleep)
            result = HistoryBackfill(pipeline, self.repository, clock=lambda: self.fixture.now).run(
                date(2026, 10, 23), date(2026, 10, 23), symbols=("AAPL", "MSFT"))
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(request_times, [0, 13, 26])

    def test_cli_history_and_backfill_reuse_persisted_coverage_without_provider_calls(self):
        from contextlib import redirect_stdout
        from io import StringIO
        import json, os
        from unittest.mock import patch
        from psycopg.conninfo import make_conninfo
        from market_data.__main__ import main
        pipeline, _ = self.fixture.pipeline()
        pipeline.run("AAPL", date(2026, 10, 23), date(2026, 10, 23))
        environment = {"MARKET_DATABASE_URL": make_conninfo(os.environ["MARKET_TEST_DATABASE_URL"],
                                                           options=f"-csearch_path={self.fixture.schema}")}
        commands = [
            ["history", "--symbol", "AAPL", "--from", "2026-10-23", "--to", "2026-10-23"],
            ["backfill", "--symbols", "AAPL", "--from", "2026-10-23", "--to", "2026-10-23"],
        ]
        for argv in commands:
            with self.subTest(command=argv[0]), patch.dict(os.environ, environment, clear=True), \
                 patch("market_data.__main__.datetime") as now, redirect_stdout(StringIO()) as output:
                now.now.return_value = self.fixture.now
                self.assertEqual(main(argv), 0)
                result = json.loads(output.getvalue())
                if argv[0] == "history":
                    self.assertEqual(result["coverage"], "complete")
                else:
                    self.assertEqual(result["symbols"][0]["action"], "skipped")

    def test_backfill_fills_an_earlier_gap_even_when_latest_price_is_fresh(self):
        import httpx
        from market_data.backfill import HistoryBackfill
        from market_data.pipeline import DailyPricePipeline
        from market_data.provider import MassiveDailyProvider
        pipeline, _ = self.fixture.pipeline()
        pipeline.run("AAPL", date(2026, 10, 23), date(2026, 10, 23))
        self.assertEqual(self.repository.latest("AAPL", as_of=self.fixture.now)["status"], "fresh")
        requests = []
        def respond(request):
            requests.append(request.url.path)
            return httpx.Response(200, json={**self.fixture.payload, "results": [
                {**self.fixture.payload["results"][0], "t": 1792641600000},
            ]})
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            pipeline = DailyPricePipeline(MassiveDailyProvider("test-key", client), self.fixture.raw,
                                          self.repository, clock=lambda: self.fixture.now)
            result = HistoryBackfill(pipeline, self.repository, clock=lambda: self.fixture.now).run(
                date(2026, 10, 22), date(2026, 10, 23), symbols=("AAPL",))
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(requests, ["/v2/aggs/ticker/AAPL/range/1/day/2026-10-22/2026-10-22"])
        self.assertEqual(result["symbols"][0]["available_count"], 2)

    def test_history_respects_holidays_dst_and_exact_ninety_day_window(self):
        for instant, target, status in [
            ("2026-03-10T03:59:00+00:00", "2026-03-09", "not_published"),
            ("2026-03-10T04:00:00+00:00", "2026-03-09", "missing"),
            ("2026-11-03T04:59:00+00:00", "2026-11-02", "not_published"),
            ("2026-11-03T05:00:00+00:00", "2026-11-02", "missing"),
            ("2026-11-27T05:00:00+00:00", "2026-11-26", "holiday"),
        ]:
            with self.subTest(instant=instant):
                now, day = datetime.fromisoformat(instant), date.fromisoformat(target)
                history = self.repository.history("AAPL", day, day, as_of=now)
                self.assertEqual(history["days"][0]["status"], status)
        history = self.repository.history("AAPL", as_of=self.fixture.now)
        self.assertEqual(history["from_date"], "2026-07-27")
        self.assertEqual(history["to_date"], "2026-10-24")
        self.assertEqual(len(history["days"]), 90)

    def test_history_selects_latest_sighting_including_revision_back_to_original(self):
        day = date(2026, 10, 23)
        original, _ = self.fixture.pipeline()
        original.run("AAPL", day, day)
        first = self.repository.history("AAPL", day, day, as_of=self.fixture.now)["days"][0]["price"]
        self.fixture.now += timedelta(seconds=1)
        revision, _ = self.fixture.pipeline({**self.fixture.payload, "results": [
            {**self.fixture.payload["results"][0], "c": 106},
        ]})
        revision.run("AAPL", day, day)
        self.assertEqual(self.repository.history("AAPL", day, day, as_of=self.fixture.now)["days"][0]["price"]["close"], "106")
        self.fixture.now += timedelta(seconds=1)
        restored = original.run("AAPL", day, day)
        history = self.repository.history("AAPL", day, day, as_of=self.fixture.now)
        self.assertEqual(history["available_count"], 1)
        self.assertEqual(history["days"][0]["price"]["id"], first["id"])
        self.assertEqual(history["days"][0]["price"]["run_id"], restored["id"])

    def test_resuming_a_smaller_interrupted_range_still_fills_remaining_requested_dates(self):
        import hashlib, json
        import httpx
        from market_data.backfill import HistoryBackfill
        from market_data.pipeline import DailyPricePipeline
        from market_data.provider import MassiveDailyProvider
        day = date(2026, 10, 22)
        body = json.dumps({**self.fixture.payload, "results": [
            {**self.fixture.payload["results"][0], "t": 1792641600000}]}).encode()
        run_id = self.repository.start_run("AAPL", day, day, self.fixture.now)
        self.repository.begin_attempt(run_id, 1, self.fixture.now)
        key = f"raw/{run_id}/saved.json"
        location = self.fixture.raw.save(key, body)
        self.repository.record_attempt(run_id, 1, self.fixture.now, status=200, key=key,
                                       digest=hashlib.sha256(body).hexdigest(), location=location)
        requests = []
        def respond(request):
            requests.append(request.url.path)
            return httpx.Response(200, json=self.fixture.payload)
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            pipeline = DailyPricePipeline(MassiveDailyProvider("test-key", client), self.fixture.raw,
                                          self.repository, clock=lambda: self.fixture.now)
            result = HistoryBackfill(pipeline, self.repository, clock=lambda: self.fixture.now).run(
                day, date(2026, 10, 23), symbols=("AAPL",))
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(self.repository.get_run(run_id)["status"], "succeeded")
        self.assertEqual(requests, ["/v2/aggs/ticker/AAPL/range/1/day/2026-10-23/2026-10-23"])

    def test_partial_backfill_keeps_other_symbols_and_recovers_only_the_failed_one(self):
        import httpx
        from market_data.backfill import HistoryBackfill
        from market_data.pipeline import DailyPricePipeline
        from market_data.provider import MassiveDailyProvider
        fail, requests = [True], []
        def respond(request):
            symbol = request.url.path.split('/')[4]
            requests.append(symbol)
            if symbol == "MSFT" and fail[0]:
                return httpx.Response(500, json={"status": "ERROR"})
            return httpx.Response(200, json={**self.fixture.payload, "ticker": symbol})
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            pipeline = DailyPricePipeline(MassiveDailyProvider("test-key", client), self.fixture.raw,
                                          self.repository, clock=lambda: self.fixture.now)
            batch = HistoryBackfill(pipeline, self.repository, clock=lambda: self.fixture.now)
            day = date(2026, 10, 23)
            first = batch.run(day, day, symbols=("AAPL", "MSFT", "GOOGL"))
            self.assertEqual(first["status"], "partial")
            self.assertEqual([row["available_count"] for row in first["symbols"]], [1, 0, 1])
            self.assertEqual(first["symbols"][1]["error_code"], "provider_http_500")
            self.assertEqual(requests, ["AAPL", "MSFT", "MSFT", "MSFT", "GOOGL"])
            fail[0] = False
            second = batch.run(day, day, symbols=("AAPL", "MSFT", "GOOGL"))
            self.assertEqual(second["status"], "succeeded")
            self.assertEqual([row["action"] for row in second["symbols"]], ["skipped", "fetched", "skipped"])
            self.assertEqual(requests[-1], "MSFT")
            self.assertEqual(len(self.repository.observations("AAPL", day)), 1)
