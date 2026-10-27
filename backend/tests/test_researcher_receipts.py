"""Researcher HTTP -> observed browser sources -> ingestion -> retrieval contracts."""
import asyncio
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BACKEND / "researcher"), str(BACKEND / "research"), str(BACKEND / "ingest")]


class ResearcherReceiptTests(unittest.TestCase):
    def exercise(self, mode):
        env = {"AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing",
               "AWS_SESSION_TOKEN": "testing", "AWS_EC2_METADATA_DISABLED": "true",
               "AWS_CONFIG_FILE": os.devnull, "AWS_SHARED_CREDENTIALS_FILE": os.devnull,
               "AWS_DEFAULT_REGION": "us-east-1", "VECTOR_BUCKET": "test-research",
               "SAGEMAKER_ENDPOINT": "test-embedding", "OPENAI_API_KEY": "",
               "ALEX_API_ENDPOINT": "https://ingest.invalid/ingest", "ALEX_API_KEY": "test-key"}
        self.stored = {}
        self.submissions = []
        with patch.dict(os.environ, env), patch("dotenv.load_dotenv", return_value=False):
            import agents
            agents.set_tracing_disabled(True)
            from agents.mcp import MCPServerStdio
            from mcp.types import CallToolResult, TextContent
            import server
            import ingest_s3vectors
            import search_s3vectors
            import httpx

            async def enter(instance):
                return instance

            async def exit_server(*args):
                return None

            async def browser(instance, tool_name, arguments):
                return CallToolResult(content=[TextContent(type="text", text="### Page\n- Page URL: https://www.apple.com/newsroom/\n- Page Title: Apple Newsroom\n### Snapshot\nApple published a product update.")], isError=False)

            def aws(client, operation, params):
                if operation == "InvokeEndpoint":
                    return {"Body": io.BytesIO(json.dumps([[0.25] * 384]).encode())}
                if operation == "PutVectors":
                    self.stored.update({v["key"]: v for v in params["vectors"]})
                    return {}
                if operation == "QueryVectors":
                    return {"vectors": [dict(v, distance=0.1) for v in self.stored.values()]}
                raise AssertionError(operation)

            def http(transport, request):
                self.submissions.append(json.loads(request.content))
                if mode == "bad_receipt":
                    return httpx.Response(200, json={"message": "ok"}, request=request)
                if mode == "rejected":
                    return httpx.Response(403, json={"error": "denied"}, request=request)
                result = ingest_s3vectors.lambda_handler({"body": request.content.decode()}, None)
                return httpx.Response(result["statusCode"], json=json.loads(result["body"]), request=request)

            async def model(agent, **kwargs):
                if mode != "skipped":
                    if mode != "unvisited":
                        await agent.mcp_servers[0].call_tool("browser_navigate", {"url": "https://www.apple.com/newsroom/"})
                    arguments = {"topic": "AAPL", "analysis": "Apple published a product update.",
                                 "source_urls": ["https://www.apple.com/newsroom/"]}
                    await agent.tools[0].on_invoke_tool(agents.RunContextWrapper(context=kwargs["context"]), json.dumps(arguments))
                return SimpleNamespace(final_output="Research successfully stored!")

            async def request():
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
                    return await client.post("/research", json={"topic": "AAPL"})

            with patch.object(MCPServerStdio, "__aenter__", enter), patch.object(MCPServerStdio, "__aexit__", exit_server), \
                    patch.object(MCPServerStdio, "call_tool", browser), patch("agents.Runner.run", side_effect=model), \
                    patch("httpx.HTTPTransport.handle_request", new=http), patch("botocore.client.BaseClient._make_api_call", new=aws):
                response = asyncio.run(request())
                retrieved = search_s3vectors.lambda_handler({"body": {"query": "Apple update"}}, None)
            return response, json.loads(retrieved["body"])["results"]

    def test_model_cannot_claim_success_without_stored_research(self):
        for mode in ("skipped", "bad_receipt", "rejected", "unvisited"):
            with self.subTest(mode=mode):
                response, results = self.exercise(mode)
                self.assertEqual(response.status_code, 503, response.text)
                self.assertIn("research_not_stored", response.text)
                self.assertEqual(results, [])

    def test_visited_source_and_server_capture_time_survive_ingestion_and_retrieval(self):
        response, results = self.exercise("success")
        self.assertEqual(response.status_code, 200, response.text)
        receipt = response.json()["research"][0]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], receipt["research_id"])
        self.assertEqual(results[0]["metadata"]["sources"], receipt["sources"])
        self.assertEqual(receipt["sources"][0]["url"], "https://www.apple.com/newsroom/")
        self.assertTrue(receipt["sources"][0]["fetched_at"].endswith("+00:00"))


if __name__ == "__main__":
    unittest.main()
