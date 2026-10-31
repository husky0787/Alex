"""Offline HTTP contract tests: real Clerk JWT checks and real database adapters.

Only external JWKS HTTP, AWS responses and local .env loading are substituted.
Run from backend/api: uv run --locked --package api -m unittest test_error_contract -v
"""

import importlib
import io
import json
import os
import time
import unittest
from unittest.mock import patch

import jwt
from botocore.stub import ANY, Stubber
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient


class APIErrorContractTests(unittest.TestCase):
    account_id = "123e4567-e89b-12d3-a456-426614174000"
    position_id = "123e4567-e89b-12d3-a456-426614174001"
    job_id = "123e4567-e89b-12d3-a456-426614174002"

    @classmethod
    def setUpClass(cls):
        env = {
            "AWS_ACCESS_KEY_ID": "testing",
            "AWS_SECRET_ACCESS_KEY": "testing",
            "AWS_SESSION_TOKEN": "testing",
            "AWS_EC2_METADATA_DISABLED": "true",
            "AWS_CONFIG_FILE": os.devnull,
            "AWS_SHARED_CREDENTIALS_FILE": os.devnull,
            "DEFAULT_AWS_REGION": "us-east-1",
            "AURORA_CLUSTER_ARN": "arn:aws:rds:us-east-1:123456789012:cluster:test",
            "AURORA_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:123456789012:secret:test",
            "AURORA_DATABASE": "alex",
            "CLERK_JWKS_URL": "https://clerk.example.test/.well-known/jwks.json",
            "SQS_QUEUE_URL": "https://sqs.us-east-1.amazonaws.com/123456789012/test",
        }
        cls.environment = patch.dict(os.environ, env)
        cls.environment.start()
        cls.addClassCleanup(cls.environment.stop)
        # Never load a developer's .env or allow a real AWS request in this suite.
        cls.network = patch("botocore.httpsession.URLLib3Session.send", side_effect=AssertionError("AWS network forbidden"))
        cls.network.start()
        cls.addClassCleanup(cls.network.stop)
        with patch("dotenv.load_dotenv", return_value=False):
            cls.api = importlib.import_module("main")
        cls.signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.untrusted_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(cls.signing_key.public_key()))
        public_jwk.update(kid="test-key", use="sig", alg="RS256")
        cls.jwks = json.dumps({"keys": [public_jwk]}).encode()

    def setUp(self):
        self.jwks_http = patch("urllib.request.urlopen", side_effect=lambda *a, **kw: io.BytesIO(self.jwks))
        self.jwks_http.start()
        self.addCleanup(self.jwks_http.stop)
        self.rds = Stubber(self.api.db.client.client)
        self.rds.activate()
        self.addCleanup(self.rds.deactivate)
        self.sqs = Stubber(self.api.sqs_client)
        self.sqs.activate()
        self.addCleanup(self.sqs.deactivate)
        self.client = TestClient(self.api.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)

    def tearDown(self):
        self.rds.assert_no_pending_responses()
        self.sqs.assert_no_pending_responses()

    def headers(self, user="user_alice", *, expires_in=300, key=None):
        token = jwt.encode(
            {"sub": user, "exp": int(time.time()) + expires_in},
            key or self.signing_key, algorithm="RS256", headers={"kid": "test-key"},
        )
        return {"Authorization": f"Bearer {token}"}

    def rows(self, rows, *, sql=ANY, parameters=ANY):
        """Queue an RDS Data API response, exercising the real row decoder."""
        columns = list(rows[0]) if rows else []
        response = {
            "columnMetadata": [{"name": name} for name in columns],
            "records": [[{"stringValue": str(row[name])} for name in columns] for row in rows],
        }
        self.rds.add_response("execute_statement", response, {
            "resourceArn": self.api.db.client.cluster_arn,
            "secretArn": self.api.db.client.secret_arn,
            "database": "alex", "includeResultMetadata": True,
            "sql": sql, "parameters": parameters,
        })

    def assert_json_error(self, response, status):
        self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(response.headers["content-type"], "application/json")
        self.assertIn("detail", response.json())
        self.assertNotIn("<!DOCTYPE", response.text)

    def test_missing_profile_stays_404_on_all_profile_required_mutations(self):
        for method, url, body in [
            ("PUT", "/api/user", {"display_name": "Alice"}),
            ("POST", "/api/accounts", {"account_name": "Savings"}),
            ("POST", "/api/analyze", {}),
            ("DELETE", "/api/reset-accounts", None),
            ("POST", "/api/populate-test-data", None),
        ]:
            with self.subTest(method=method, url=url):
                self.rows([], parameters=[{"name": "clerk_id", "value": {"stringValue": "user_alice"}}])
                response = self.client.request(method, url, json=body, headers=self.headers())
                self.assert_json_error(response, 404)

    def test_missing_invalid_expired_and_forged_tokens_are_rejected(self):
        for headers in [
            {}, {"Authorization": "Basic invalid"}, {"Authorization": "Bearer not-a-jwt"},
            self.headers(expires_in=-60), self.headers(key=self.untrusted_key),
        ]:
            with self.subTest(headers_kind=headers.get("Authorization", "missing")[:16]):
                self.assert_json_error(self.client.get("/api/accounts", headers=headers), 403)

    def test_signed_in_user_can_load_own_profile_and_accounts(self):
        profile = {"clerk_user_id": "user_alice", "display_name": "Alice"}
        self.rows([profile], parameters=[{"name": "clerk_id", "value": {"stringValue": "user_alice"}}])
        response = self.client.get("/api/user", headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"user": profile, "created": False})

        account = {"id": self.account_id, "clerk_user_id": "user_alice", "account_name": "Savings"}
        # Assert the SQL ownership predicate too: a stub must not hide an unfiltered list query.
        self.rows([account], sql=(
            "\n            SELECT * FROM accounts \n"
            "            WHERE clerk_user_id = :user_id \n"
            "            ORDER BY created_at DESC\n        "
        ), parameters=[{"name": "user_id", "value": {"stringValue": "user_alice"}}])
        response = self.client.get("/api/accounts?clerk_user_id=user_bob", headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [account])

    def test_other_users_account_reads_and_writes_are_rejected(self):
        for method, url, body in [
            ("GET", f"/api/accounts/{self.account_id}/positions", None),
            ("PUT", f"/api/accounts/{self.account_id}", {"account_name": "Stolen"}),
            ("DELETE", f"/api/accounts/{self.account_id}", None),
            ("POST", "/api/positions", {"account_id": self.account_id, "symbol": "AAPL", "quantity": 1}),
        ]:
            with self.subTest(method=method, url=url):
                self.rows([{"id": self.account_id, "clerk_user_id": "user_bob"}],
                          parameters=[{"name": "id", "value": {"stringValue": self.account_id}}])
                response = self.client.request(method, url, json=body, headers=self.headers())
                self.assert_json_error(response, 403)
                self.assertNotIn("user_bob", response.text)

    def test_other_users_position_writes_are_rejected(self):
        for method in ["PUT", "DELETE"]:
            with self.subTest(method=method):
                self.rows([{"id": self.position_id, "account_id": self.account_id}])
                self.rows([{"id": self.account_id, "clerk_user_id": "user_bob"}])
                response = self.client.request(method, f"/api/positions/{self.position_id}",
                                               json={"quantity": 2}, headers=self.headers())
                self.assert_json_error(response, 403)

    def test_own_account_positions_load_successfully(self):
        self.rows([{"id": self.account_id, "clerk_user_id": "user_alice"}])
        position = {"id": self.position_id, "account_id": self.account_id, "symbol": "AAPL", "quantity": "2"}
        self.rows([position], parameters=[{"name": "account_id", "value": {"stringValue": self.account_id}}])
        instrument = {"symbol": "AAPL", "name": "Apple"}
        self.rows([instrument], parameters=[{"name": "symbol", "value": {"stringValue": "AAPL"}}])
        response = self.client.get(f"/api/accounts/{self.account_id}/positions", headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"positions": [{**position, "instrument": instrument}]})

    def test_job_results_are_only_visible_to_the_owner(self):
        job = {"id": self.job_id, "clerk_user_id": "user_alice", "status": "completed"}
        for user, expected in [("user_alice", 200), ("user_bob", 403)]:
            with self.subTest(user=user):
                self.rows([job], parameters=[{"name": "id", "value": {"stringValue": self.job_id}}])
                response = self.client.get(f"/api/jobs/{self.job_id}", headers=self.headers(user))
                if expected == 200:
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json(), job)
                else:
                    self.assert_json_error(response, expected)
                    self.assertNotIn("completed", response.text)

    def test_missing_resources_and_routes_return_json_404(self):
        for url in [f"/api/accounts/{self.account_id}/positions", f"/api/jobs/{self.job_id}"]:
            with self.subTest(url=url):
                self.rows([])
                self.assert_json_error(self.client.get(url, headers=self.headers()), 404)
        for url in ["/api", "/api/does-not-exist"]:
            with self.subTest(url=url):
                self.assert_json_error(self.client.get(url, headers=self.headers()), 404)

    def test_invalid_input_returns_json_422_without_database_access(self):
        response = self.client.post("/api/accounts", json={"account_name": ""}, headers=self.headers())
        self.assert_json_error(response, 422)

    def test_analysis_rejects_unverified_legacy_prices_before_creating_or_queueing_job(self):
        self.rows([{"clerk_user_id": "user_alice"}])
        response = self.client.post("/api/analyze", json={}, headers=self.headers())
        self.assert_json_error(response, 503)
        self.assertEqual(response.json()["code"], "verified_price_snapshot_required")

    def test_real_database_failure_still_returns_json_500_without_internal_details(self):
        self.rds.add_client_error("execute_statement", service_error_code="DatabaseUnavailableException",
                                  service_message="private database details", http_status_code=500)
        response = self.client.put("/api/user", json={"display_name": "Alice"}, headers=self.headers())
        self.assert_json_error(response, 500)
        self.assertNotIn("private database details", response.text)

    def test_readiness_checks_database_but_liveness_survives_failure(self):
        with Stubber(self.api.readiness_client) as readiness:
            expected = {'resourceArn': self.api.db.client.cluster_arn,
                        'secretArn': self.api.db.client.secret_arn, 'database':'alex', 'sql':'SELECT 1'}
            readiness.add_response('execute_statement', {'records': [[{'longValue':1}]]}, expected)
            self.assertEqual(self.client.get('/ready').status_code, 200)
            readiness.add_client_error('execute_statement', service_error_code='DatabaseUnavailableException',
                                       service_message='private details', expected_params=expected)
            with self.assertLogs('main', level='WARNING') as logs:
                self.assert_json_error(self.client.get('/ready'), 503)
            self.assertIn('DatabaseUnavailableException', logs.output[0])
            self.assertNotIn('private details', logs.output[0])
            self.assertEqual(self.client.get('/health').status_code, 200)
            readiness.assert_no_pending_responses()


if __name__ == "__main__":
    unittest.main()
