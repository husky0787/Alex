"""Real HTTP auth and PostgreSQL reads; only JWKS HTTP and time are substituted."""
import importlib
import io
import json
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from psycopg.conninfo import make_conninfo

import test_pipeline


class MarketAPITests(unittest.TestCase):
    def setUp(self):
        # Reuse the PostgreSQL fixture, not its tests or production collaborators.
        self.database = test_pipeline.PipelineTests()
        self.database.setUp()
        self.addCleanup(self.database.doCleanups)
        env = {
            "AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing",
            "AWS_SESSION_TOKEN": "testing", "AWS_EC2_METADATA_DISABLED": "true",
            "AWS_CONFIG_FILE": os.devnull, "AWS_SHARED_CREDENTIALS_FILE": os.devnull,
            "AURORA_CLUSTER_ARN": "arn:aws:rds:us-east-1:123456789012:cluster:test",
            "AURORA_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:123456789012:secret:test",
            "CLERK_JWKS_URL": "https://clerk.example.test/.well-known/jwks.json",
            "MARKET_DATABASE_URL": make_conninfo(os.environ["MARKET_TEST_DATABASE_URL"],
                                                 options=f"-csearch_path={self.database.schema}"),
        }
        self.environment = patch.dict(os.environ, env)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        blocked = patch("botocore.httpsession.URLLib3Session.send", side_effect=AssertionError("AWS network forbidden"))
        blocked.start()
        self.addCleanup(blocked.stop)
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api"))
        self.addCleanup(lambda: sys.path.pop(0))
        with patch("dotenv.load_dotenv", return_value=False):
            api = importlib.import_module("main")
        clock = patch("main.datetime")
        clock.start().now.return_value = self.database.now
        self.addCleanup(clock.stop)
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        kid = self.database.schema
        public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        public.update(kid=kid, use="sig", alg="RS256")
        jwks = patch("urllib.request.urlopen", side_effect=lambda *a, **kw: io.BytesIO(json.dumps({"keys": [public]}).encode()))
        jwks.start()
        self.addCleanup(jwks.stop)
        self.token = jwt.encode({"sub": "user_alice", "exp": int(time.time()) + 300},
                                self.key, algorithm="RS256", headers={"kid": kid})
        self.client = TestClient(api.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)

    def test_verified_market_api_requires_authentication(self):
        response = self.client.get("/api/market-data/AAPL")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.headers["content-type"], "application/json")

    def test_authenticated_price_and_unavailable_contract(self):
        headers = {"Authorization": f"Bearer {self.token}"}
        response = self.client.get("/api/market-data/AAPL", headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "unavailable")
        self.assertIsNone(response.json()["price"])
        pipeline, _ = self.database.pipeline()
        from datetime import date
        pipeline.run("AAPL", date(2026, 10, 23), date(2026, 10, 23))
        response = self.client.get("/api/market-data/AAPL", headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["price"]["source"], "massive")
        self.assertEqual(response.json()["price"]["trade_date"], "2026-10-23")
        self.assertNotIn("raw_location", response.text)
        self.assertEqual(self.client.get("/api/market-data/NOTSUPPORTED", headers=headers).status_code, 404)
