"""Researcher ingestion tool; source observations and receipts belong to one run."""
import os
import logging
from dataclasses import dataclass, field
from uuid import uuid4
import httpx
from agents import function_tool, RunContextWrapper
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from research_chain import validate_document


@dataclass
class ResearchContext:
    sources: dict = field(default_factory=dict)
    receipts: list = field(default_factory=list)


def retryable(exc):
    return isinstance(exc, httpx.TransportError) or (
        isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (429, 500, 502, 503, 504))


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=4),
       retry=retry_if_exception(retryable), reraise=True)
def ingest_with_retries(document):
    with httpx.Client() as client:
        response = client.post(os.environ["ALEX_API_ENDPOINT"], json=document,
                               headers={"x-api-key": os.environ["ALEX_API_KEY"]}, timeout=30.0)
        response.raise_for_status()
        return response.json()


@function_tool
async def ingest_financial_document(wrapper: RunContextWrapper[ResearchContext],
                                    topic: str, analysis: str, source_urls: list[str]) -> dict:
    """Store research based on successfully visited browser pages.

    Args:
        topic: Subject of the research.
        analysis: Concise research summary based on the visited pages.
        source_urls: Exact final Page URLs of the browser pages used as sources.
    """
    if not os.getenv("ALEX_API_ENDPOINT") or not os.getenv("ALEX_API_KEY"):
        return {"success": False, "error": "research_ingestion_not_configured"}
    if not source_urls or any(url not in wrapper.context.sources for url in source_urls):
        return {"success": False, "error": "research_sources_not_observed"}
    research_id = str(uuid4())
    try:
        document = validate_document({"text": analysis, "metadata": {
            "research_id": research_id, "topic": topic,
            "sources": [{"url": url, "fetched_at": wrapper.context.sources[url]} for url in dict.fromkeys(source_urls)]}})
        # The same identity/payload is retained through all HTTP retries.
        result = ingest_with_retries(document)
        if result.get("document_id") != research_id:
            raise ValueError("research_ingestion_receipt_invalid")
        receipt = {"research_id": research_id, "sources": document["metadata"]["sources"]}
        wrapper.context.receipts.append(receipt)
        return {"success": True, "document_id": research_id}
    except Exception:
        logging.exception("Research ingestion failed")
        return {"success": False, "error": "research_ingestion_failed", "research_id": research_id}
