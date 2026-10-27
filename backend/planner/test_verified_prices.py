"""Exercise the real planner entry point with AWS transport responses only."""
import importlib
import json
import os
import unittest
from unittest.mock import patch

from botocore.stub import ANY, Stubber


class VerifiedPriceGuardTests(unittest.TestCase):
    def test_direct_or_queued_analysis_fails_before_models_or_legacy_prices(self):
        environment = {
            "AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing",
            "AWS_SESSION_TOKEN": "testing", "AWS_EC2_METADATA_DISABLED": "true",
            "AWS_CONFIG_FILE": os.devnull, "AWS_SHARED_CREDENTIALS_FILE": os.devnull,
            "AWS_DEFAULT_REGION": "us-east-1", "DEFAULT_AWS_REGION": "us-east-1",
            "AURORA_CLUSTER_ARN": "arn:aws:rds:us-east-1:123456789012:cluster:test",
            "AURORA_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:123456789012:secret:test",
            "AURORA_DATABASE": "alex", "LANGFUSE_SECRET_KEY": "", "OPENAI_API_KEY": "",
            "OTEL_SDK_DISABLED": "true",
        }
        with patch.dict(os.environ, environment), patch("dotenv.load_dotenv", return_value=False), \
                patch("botocore.httpsession.URLLib3Session.send", side_effect=AssertionError("AWS forbidden")), \
                patch("httpx.HTTPTransport.handle_request", side_effect=AssertionError("HTTP forbidden")):
            handler = importlib.import_module("lambda_handler")
            job_id = "123e4567-e89b-12d3-a456-426614174002"
            for event in ({"job_id": job_id}, {"Records": [{"body": job_id}]}):
                with self.subTest(event=event), Stubber(handler.db.client.client) as rds:
                    for status in ("running", "failed"):
                        parameters = [{"name": "status", "value": {"stringValue": status}},
                                      {"name": "started_at" if status == "running" else "completed_at", "value": ANY}]
                        if status == "failed":
                            parameters.append({"name": "error_message", "value": {
                                "stringValue": "verified_price_snapshot_required: This job has no verified price snapshot."}})
                        parameters.append({"name": "id", "value": {"stringValue": job_id}})
                        rds.add_response("execute_statement", {"numberOfRecordsUpdated": 1}, {
                            "resourceArn": environment["AURORA_CLUSTER_ARN"],
                            "secretArn": environment["AURORA_SECRET_ARN"], "database": "alex",
                            "includeResultMetadata": True, "sql": ANY, "parameters": parameters,
                        })
                        if status == "running":
                            rds.add_response("execute_statement", {
                                "columnMetadata": [{"name": "id"}, {"name": "clerk_user_id"}, {"name": "request_payload"}],
                                "records": [[{"stringValue": job_id}, {"stringValue": "user_alice"}, {"stringValue": "{}"}]],
                            }, {"resourceArn": environment["AURORA_CLUSTER_ARN"],
                                "secretArn": environment["AURORA_SECRET_ARN"], "database": "alex",
                                "includeResultMetadata": True, "sql": ANY,
                                "parameters": [{"name": "id", "value": {"stringValue": job_id}}]})
                    response = handler.lambda_handler(event, None)
                    self.assertEqual(response["statusCode"], 500)
                    self.assertIn("verified_price_snapshot_required", json.loads(response["body"])["error"])
                    rds.assert_no_pending_responses()


if __name__ == "__main__":
    unittest.main()
