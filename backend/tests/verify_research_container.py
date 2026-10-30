"""Offline image smoke: real FastAPI health and Chromium/MCP source capture.

Mount this file into the Researcher image and run with uv; no AWS/model calls.
"""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

import agents
import httpx
from mcp_servers import create_playwright_mcp_server
from server import app


class FixturePage(BaseHTTPRequestHandler):
    def do_GET(self):
        content = b"<html><title>Alex smoke</title><body>Known research fixture 4137</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, *args):
        pass


async def main():
    agents.set_tracing_disabled(True)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200 and response.json()["status"] == "healthy", response.text
    web = ThreadingHTTPServer(("127.0.0.1", 0), FixturePage)
    thread = threading.Thread(target=web.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{web.server_port}/"
    sources = {}
    try:
        async with create_playwright_mcp_server(sources=sources) as browser:
            result = await browser.call_tool("browser_navigate", {"url": url})
            text = "\n".join(getattr(part, "text", "") for part in result.content)
            assert not result.isError, text
            assert url in sources, f"Browser source not captured: {text}"
            assert sources[url].endswith("+00:00"), sources
            # Navigation may return a file link; the snapshot tool returns page text.
            snapshot = await browser.call_tool("browser_snapshot", {})
            snapshot_text = "\n".join(getattr(part, "text", "") for part in snapshot.content)
            assert not snapshot.isError, snapshot_text
            assert "Known research fixture 4137" in snapshot_text, snapshot_text
    finally:
        web.shutdown()
        web.server_close()
        thread.join(timeout=5)
    print(json.dumps({"health": "passed", "chromium_mcp": "passed", "source_capture": "passed", "aws_calls": 0}))


if __name__ == "__main__":
    asyncio.run(main())
