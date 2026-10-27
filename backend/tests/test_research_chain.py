"""Research ingestion/search boundaries with only AWS transports substituted."""
import importlib
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BACKEND / "ingest"), str(BACKEND / "research")]


class ResearchChainTests(unittest.TestCase):
    def setUp(self):
        env = {"AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing",
               "AWS_SESSION_TOKEN": "testing", "AWS_EC2_METADATA_DISABLED": "true",
               "AWS_CONFIG_FILE": os.devnull, "AWS_SHARED_CREDENTIALS_FILE": os.devnull,
               "AWS_DEFAULT_REGION": "us-east-1", "VECTOR_BUCKET": "test-research",
               "SAGEMAKER_ENDPOINT": "test-embedding", "INDEX_NAME": "financial-research"}
        guard = patch.dict(os.environ, env)
        guard.start(); self.addCleanup(guard.stop)
        self.vectors = {}
        self.embedding = [[0.25] * 384]

        def aws(client, operation, params):
            if operation == "InvokeEndpoint":
                return {"Body": io.BytesIO(json.dumps(self.embedding).encode())}
            if operation == "PutVectors":
                for vector in params["vectors"]:
                    self.vectors[vector["key"]] = vector
                return {}
            if operation == "QueryVectors":
                self.assertEqual(len(params["queryVector"]["float32"]), 384)
                return {"vectors": [dict(v, distance=0.1) for v in self.vectors.values()]}
            raise AssertionError(f"Unexpected AWS operation: {operation}")
        transport = patch("botocore.client.BaseClient._make_api_call", new=aws)
        transport.start(); self.addCleanup(transport.stop)
        self.ingest = importlib.import_module("ingest_s3vectors")
        self.search = importlib.import_module("search_s3vectors")
        self.document = {"text": "Apple announced a new product. Source content, not a price quote.",
                         "metadata": {"topic": "AAPL", "research_id": "research-known-001",
                                      "sources": [{"url": "https://www.apple.com/newsroom/",
                                                   "fetched_at": "2026-10-27T12:00:00+00:00"}]}}

    def test_known_research_is_retrievable_with_stable_identity_and_provenance(self):
        first = self.ingest.lambda_handler({"body": json.dumps(self.document)}, None)
        second = self.ingest.lambda_handler({"body": json.dumps(self.document)}, None)
        self.assertEqual(first["statusCode"], 200, first)
        self.assertEqual(json.loads(first["body"])["document_id"], "research-known-001")
        self.assertEqual(json.loads(second["body"])["document_id"], "research-known-001")
        response = self.search.lambda_handler({"body": json.dumps({"query": "Apple news"})}, None)
        self.assertEqual(response["statusCode"], 200, response)
        results = json.loads(response["body"])["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "research-known-001")
        self.assertEqual(results[0]["metadata"]["sources"], self.document["metadata"]["sources"])
        self.assertEqual(results[0]["text"], self.document["text"])

    def test_unattributed_research_is_rejected_and_legacy_vectors_are_not_cited(self):
        self.document["metadata"].pop("sources")
        response = self.ingest.lambda_handler({"body": self.document}, None)
        self.assertEqual(response["statusCode"], 400)
        self.vectors["legacy"] = {"key": "legacy", "metadata": {"text": "Unattributed news"}}
        response = self.search.lambda_handler({"body": {"query": "Apple"}}, None)
        self.assertEqual(json.loads(response["body"])["results"], [])

    def test_supported_embedding_shapes_and_bad_embedding_failure(self):
        for value in ([0.25] * 384, [[0.25] * 384], [[[0.25] * 384]]):
            self.embedding = value
            response = self.ingest.lambda_handler({"body": self.document}, None)
            self.assertEqual(response["statusCode"], 200, response)
        for value in ([0.25], [[[0.25] * 384], [[0.25] * 384]], [True] * 384):
            self.embedding = value
            response = self.ingest.lambda_handler({"body": self.document}, None)
            self.assertEqual(response["statusCode"], 503, response)

    def test_feature_extraction_token_vectors_can_be_ingested_and_queried(self):
        self.embedding = [[[0.25] * 384, [0.75] * 384]]
        response = self.ingest.lambda_handler({"body": self.document}, None)
        self.assertEqual(response["statusCode"], 200, response)
        response = self.search.lambda_handler({"body": {"query": "Apple news"}}, None)
        self.assertEqual(response["statusCode"], 200, response)
        self.assertEqual(json.loads(response["body"])["results"][0]["id"], "research-known-001")


if __name__ == "__main__":
    unittest.main()
