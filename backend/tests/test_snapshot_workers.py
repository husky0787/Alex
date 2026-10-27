"""Run once per agent; real handlers/adapters, substituted AWS and paid model boundaries."""
import importlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

AGENT = os.environ.get("SNAPSHOT_AGENT", "planner")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / AGENT))


class SnapshotWorkerTests(unittest.TestCase):
    def setUp(self):
        environment = {
            "AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing",
            "AWS_SESSION_TOKEN": "testing", "AWS_EC2_METADATA_DISABLED": "true",
            "AWS_CONFIG_FILE": os.devnull, "AWS_SHARED_CREDENTIALS_FILE": os.devnull,
            "AWS_DEFAULT_REGION": "us-east-1", "DEFAULT_AWS_REGION": "us-east-1",
            "AURORA_CLUSTER_ARN": "arn:aws:rds:us-east-1:123456789012:cluster:test",
            "AURORA_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:123456789012:secret:test",
            "LANGFUSE_SECRET_KEY": "", "LANGFUSE_PUBLIC_KEY": "", "OPENAI_API_KEY": "",
            "OTEL_SDK_DISABLED": "true", "MOCK_LAMBDAS": "false",
        }
        for guard in (patch.dict(os.environ, environment), patch("dotenv.load_dotenv", return_value=False),
                      patch("httpx.HTTPTransport.handle_request", side_effect=AssertionError("HTTP forbidden"))):
            guard.start(); self.addCleanup(guard.stop)
        import agents
        agents.set_tracing_disabled(True)
        self.handler = importlib.import_module("lambda_handler")
        from src.snapshots import snapshot_digest
        self.snapshot = {"schema_version": 1, "user_id": "user_alice",
            "captured_at": "2026-10-27T12:00:00+00:00", "expected_trade_date": "2026-10-26", "status": "stale",
            "user_preferences": {"years_until_retirement": 20, "target_retirement_income": 50000, "current_age": 40},
            "prices": [{"symbol": "AAPL", "close": "105", "trade_date": "2026-10-23", "status": "stale",
                        "source": "massive", "observation_id": "price-version", "version": "digest", "run_id": "run"}],
            "accounts": [{"id": "account", "name": "Savings", "type": "investment", "cash_balance": "50",
                          "positions": [{"symbol": "AAPL", "quantity": "2", "instrument": {
                              "name": "Apple", "allocation_asset_class": {"equity": 100}}}]}]}
        self.snapshot["sha256"] = snapshot_digest(self.snapshot)
        self.job_id = "123e4567-e89b-12d3-a456-426614174002"
        self.job = {"id": self.job_id, "clerk_user_id": "user_alice", "request_payload": {"price_snapshot": self.snapshot}}
        self.writes, self.prompts = [], []

        def aws_call(client, operation, params):
            if operation != "ExecuteStatement":
                raise AssertionError(f"Unexpected AWS operation {operation}")
            sql = params["sql"].strip()
            values = {p["name"]: next(iter(p["value"].values())) for p in params["parameters"]}
            self.assertEqual(values.get("id"), self.job_id)
            if sql.startswith("SELECT * FROM jobs"):
                return {"columnMetadata": [{"name": key} for key in self.job],
                        "records": [[{"stringValue": json.dumps(value) if isinstance(value, dict) else value}
                                     for value in self.job.values()]]}
            if sql.startswith("UPDATE jobs"):
                self.writes.append(values)
                return {"numberOfRecordsUpdated": 1}
            raise AssertionError(f"Agent must only read its job snapshot, got {sql}")
        transport = patch("botocore.client.BaseClient._make_api_call", new=aws_call)
        transport.start(); self.addCleanup(transport.stop)

        async def model(*args, **kwargs):
            self.prompts.append(kwargs["input"])
            output = json.dumps({"charts": [{"key": "allocation", "type": "pie", "data": [{"name": "AAPL", "value": 210}]}]}) \
                if AGENT == "charter" else "Analysis based on frozen holdings."
            return SimpleNamespace(final_output=output)
        paid_model = patch("agents.Runner.run", side_effect=model)
        paid_model.start(); self.addCleanup(paid_model.stop)

    def test_agent_uses_persisted_snapshot_ignores_event_prices_and_discloses_stale_dates(self):
        response = self.handler.lambda_handler({"job_id": self.job_id,
            "portfolio_data": {"accounts": [], "current_price": "99999"}, "user_data": {"user_id": "user_bob"}}, None)
        self.assertEqual(response["statusCode"], 200, response)
        self.assertTrue(self.prompts)
        prompt = self.prompts[0]
        self.assertIn("2026-10-23", prompt)
        self.assertIn("STALE", prompt)
        self.assertIn("105", prompt)
        self.assertNotIn("99999", prompt)
        self.assertTrue(self.writes)
        if AGENT == "reporter":
            report = json.loads(next(row["report_payload"] for row in self.writes if "report_payload" in row))
            self.assertIn("STALE", report["content"])
            self.assertIn("2026-10-23", report["content"])
            self.assertEqual(report["price_snapshot_sha256"], self.snapshot["sha256"])

    def test_missing_changed_or_wrong_owner_snapshot_rejects_before_model(self):
        original = json.loads(json.dumps(self.snapshot))
        for case in ("legacy", "null_payload", "changed", "wrong_owner"):
            with self.subTest(case=case):
                self.prompts.clear()
                self.job["request_payload"] = {"price_snapshot": json.loads(json.dumps(original))}
                if case == "legacy":
                    self.job["request_payload"] = {}
                elif case == "null_payload":
                    self.job["request_payload"] = None
                elif case == "changed":
                    self.job["request_payload"]["price_snapshot"]["prices"][0]["close"] = "99999"
                else:
                    from src.snapshots import snapshot_digest
                    snapshot = self.job["request_payload"]["price_snapshot"]
                    snapshot["user_id"] = "user_bob"
                    snapshot["sha256"] = snapshot_digest(snapshot)
                response = self.handler.lambda_handler({"job_id": self.job_id,
                    "portfolio_data": {"accounts": [], "current_price": "99999"}}, None)
                self.assertNotEqual(response["statusCode"], 200)
                self.assertIn("verified_price_snapshot_", response["body"])
                self.assertEqual(self.prompts, [])

    def test_fresh_snapshot_has_no_stale_warning_and_does_not_rewrite_inputs(self):
        from src.snapshots import snapshot_digest
        self.snapshot["status"] = "fresh"
        self.snapshot["prices"][0]["status"] = "fresh"
        self.snapshot["expected_trade_date"] = "2026-10-23"
        self.snapshot["sha256"] = snapshot_digest(self.snapshot)
        original = json.dumps(self.snapshot, sort_keys=True)
        response = self.handler.lambda_handler({"job_id": self.job_id}, None)
        self.assertEqual(response["statusCode"], 200, response)
        self.assertIn("105", self.prompts[0])
        self.assertNotIn("STALE", self.prompts[0])
        self.assertEqual(json.dumps(self.snapshot, sort_keys=True), original)
        self.assertTrue(all("request_payload" not in write for write in self.writes))


if __name__ == "__main__":
    unittest.main()
