"""Authenticated analysis through real market PostgreSQL and AWS transport stubs."""
from datetime import date
import importlib
import json
import unittest
from unittest.mock import patch

from botocore.stub import ANY, Stubber
import test_api


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.market = test_api.MarketAPITests()
        self.market.setUp()
        self.addCleanup(self.market.doCleanups)
        self.api = importlib.import_module("main")
        self.rds = Stubber(self.api.db.client.client)
        self.sqs = Stubber(self.api.sqs_client)
        self.rds.activate(); self.sqs.activate()
        self.addCleanup(self.rds.deactivate); self.addCleanup(self.sqs.deactivate)
        queue = patch.object(self.api, "SQS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123456789012/test")
        queue.start(); self.addCleanup(queue.stop)
        self.job_id = "123e4567-e89b-12d3-a456-426614174002"
        self.account_id = "123e4567-e89b-12d3-a456-426614174000"
        self.created = []
        def capture(params, **kwargs):
            if params["sql"].strip().startswith("INSERT INTO jobs"):
                values = {p["name"]: p["value"] for p in params["parameters"]}
                self.created.append(json.loads(values["request_payload"]["stringValue"]))
        events = self.api.db.client.client.meta.events
        events.register("before-parameter-build.rds-data.ExecuteStatement", capture)
        self.addCleanup(lambda: events.unregister("before-parameter-build.rds-data.ExecuteStatement", capture))

    def tearDown(self):
        self.rds.assert_no_pending_responses()
        self.sqs.assert_no_pending_responses()

    def rows(self, rows, parameters=ANY):
        columns = list(rows[0]) if rows else []
        def field(value):
            return {"stringValue": json.dumps(value) if isinstance(value, (dict, list)) else str(value)}
        self.rds.add_response("execute_statement", {
            "columnMetadata": [{"name": name} for name in columns],
            "records": [[field(row[name]) for name in columns] for row in rows],
        }, {"resourceArn": self.api.db.client.cluster_arn, "secretArn": self.api.db.client.secret_arn,
            "database": "alex", "includeResultMetadata": True, "sql": ANY, "parameters": parameters})

    def owned_portfolio(self, symbols=("AAPL",)):
        self.rows([{"clerk_user_id": "user_alice", "years_until_retirement": "20", "target_retirement_income": "50000"}])
        self.rows([{"id": self.account_id, "clerk_user_id": "user_alice", "account_name": "Savings", "cash_balance": "50"}],
                  [{"name": "user_id", "value": {"stringValue": "user_alice"}}])
        self.rows([{"symbol": symbol, "quantity": "2", "account_id": self.account_id} for symbol in symbols],
                  [{"name": "account_id", "value": {"stringValue": self.account_id}}])
        for symbol in symbols:
            self.rows([{"symbol": symbol, "name": symbol, "current_price": "99999",
                        "allocation_asset_class": {"equity": 100}}])

    def queue_success(self):
        self.rows([{"id": self.job_id}])
        self.sqs.add_response("send_message", {"MessageId": "test-message"},
                              {"QueueUrl": self.api.SQS_QUEUE_URL, "MessageBody": self.job_id})

    def analyze(self, **body):
        return self.market.client.post("/api/analyze", json=body,
                                       headers={"Authorization": f"Bearer {self.market.token}"})

    def test_owned_job_freezes_verified_price_and_never_uses_seed_price(self):
        pipeline, _ = self.market.database.pipeline()
        pipeline.run("AAPL", date(2026, 10, 23), date(2026, 10, 23))
        self.owned_portfolio()
        self.queue_success()
        response = self.analyze(options={"clerk_user_id": "user_bob", "snapshot": {"price": "1"}})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["job_id"], self.job_id)
        snapshot = self.created[0]["price_snapshot"]
        self.assertEqual(snapshot["user_id"], "user_alice")
        self.assertEqual(snapshot["status"], "fresh")
        self.assertEqual(snapshot["prices"][0]["close"], "105")
        self.assertEqual(snapshot["prices"][0]["trade_date"], "2026-10-23")
        self.assertTrue(snapshot["prices"][0]["observation_id"])
        self.assertEqual(snapshot["accounts"][0]["positions"][0]["quantity"], "2")
        self.assertNotIn("99999", json.dumps(snapshot))

    def test_stale_prices_are_frozen_and_later_source_corrections_do_not_change_old_job(self):
        payload = {**self.market.database.payload, "results": [
            {**self.market.database.payload["results"][0], "t": 1792641600000}]}
        pipeline, _ = self.market.database.pipeline(payload)
        pipeline.run("AAPL", date(2026, 10, 22), date(2026, 10, 22))
        self.owned_portfolio(); self.queue_success()
        self.assertEqual(self.analyze().status_code, 200)
        original = json.loads(json.dumps(self.created[0]))
        snapshot = original["price_snapshot"]
        self.assertEqual(snapshot["status"], "stale")
        self.assertEqual(snapshot["expected_trade_date"], "2026-10-23")
        self.assertEqual(snapshot["prices"][0]["trade_date"], "2026-10-22")
        revised = {**payload, "results": [{**payload["results"][0], "c": 108}]}
        pipeline, _ = self.market.database.pipeline(revised)
        pipeline.run("AAPL", date(2026, 10, 22), date(2026, 10, 22))
        self.assertEqual(self.market.database.repository.latest("AAPL", as_of=self.market.database.now)["price"]["close"], "108")
        self.rows([{"id": self.job_id, "clerk_user_id": "user_alice", "request_payload": original}])
        response = self.market.client.get(f"/api/jobs/{self.job_id}",
                                         headers={"Authorization": f"Bearer {self.market.token}"})
        from src.snapshots import read_snapshot, portfolio_from_snapshot
        stored = read_snapshot(response.json())
        self.assertEqual(stored, snapshot)
        self.assertEqual(portfolio_from_snapshot(stored)["accounts"][0]["positions"][0]["instrument"]["current_price"], "105")

    def test_missing_and_unsupported_holdings_are_listed_without_creating_a_job(self):
        self.owned_portfolio(symbols=("MSFT", "UNSUPPORTED"))
        response = self.analyze()
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json()["affected_symbols"], [
            {"symbol": "MSFT", "reason": "unavailable"}, {"symbol": "UNSUPPORTED", "reason": "unsupported"}])
        self.assertEqual(self.created, [])
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_snapshot_job_is_not_visible_to_another_user(self):
        import time
        import jwt
        self.rows([{"id": self.job_id, "clerk_user_id": "user_alice",
                    "request_payload": {"price_snapshot": {"private": "alice-holdings"}}}])
        token = jwt.encode({"sub": "user_bob", "exp": int(time.time()) + 300}, self.market.key,
                           algorithm="RS256", headers={"kid": self.market.database.schema})
        response = self.market.client.get(f"/api/jobs/{self.job_id}", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("alice-holdings", response.text)

    def test_queue_failure_does_not_report_success(self):
        pipeline, _ = self.market.database.pipeline()
        pipeline.run("AAPL", date(2026, 10, 23), date(2026, 10, 23))
        self.owned_portfolio()
        self.rows([{"id": self.job_id}])
        self.sqs.add_client_error("send_message", service_error_code="ServiceUnavailable",
                                  service_message="private transport error", http_status_code=503)
        self.rows([], parameters=[{"name": "status", "value": {"stringValue": "failed"}},
                                  {"name": "completed_at", "value": ANY},
                                  {"name": "error_message", "value": {"stringValue": "analysis_queue_unavailable"}},
                                  {"name": "id", "value": {"stringValue": self.job_id}}])
        response = self.analyze()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private transport", response.text)
