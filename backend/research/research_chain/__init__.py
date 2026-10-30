"""Research provenance and the shared SageMaker/S3 Vectors adapter."""
import json
import math
import logging
import os
import re
from datetime import datetime, UTC
from urllib.parse import urlsplit

import boto3


class InvalidResearch(ValueError):
    """Research cannot be attributed to a captured source."""


def validate_document(document):
    if not isinstance(document, dict) or not isinstance(document.get("metadata"), dict):
        raise InvalidResearch("research_metadata_required")
    text, metadata = document.get("text"), document["metadata"]
    if not isinstance(text, str) or not text.strip() or len(text.encode()) > 24000:
        raise InvalidResearch("research_text_required_or_too_large")
    research_id = metadata.get("research_id")
    if not isinstance(research_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", research_id):
        raise InvalidResearch("research_id_required")
    topic = metadata.get("topic")
    if not isinstance(topic, str) or not topic.strip() or len(topic.encode()) > 512:
        raise InvalidResearch("research_topic_required")
    sources = metadata.get("sources")
    if not isinstance(sources, list) or not 1 <= len(sources) <= 5:
        raise InvalidResearch("research_sources_required")
    clean_sources = []
    for source in sources:
        if not isinstance(source, dict):
            raise InvalidResearch("research_source_invalid")
        url, captured = source.get("url"), source.get("fetched_at")
        try:
            parsed = urlsplit(url) if isinstance(url, str) else None
            date = datetime.fromisoformat(captured) if isinstance(captured, str) else None
            valid = (parsed and parsed.scheme in ("http", "https") and parsed.hostname
                     and not parsed.username and not parsed.password and len(url) <= 2048
                     and not any(ord(c) < 33 for c in url)
                     and date and date.tzinfo is not None and date <= datetime.now(UTC))
        except ValueError:
            valid = False
        if not valid:
            raise InvalidResearch("research_source_url_or_fetched_at_invalid")
        clean_sources.append({"url": url, "fetched_at": date.astimezone(UTC).isoformat()})
    return {"text": text, "metadata": {"research_id": research_id, "topic": topic, "sources": clean_sources}}


def embedding(text):
    region = os.getenv("RESEARCH_AWS_REGION", os.getenv("DEFAULT_AWS_REGION", "us-east-1"))
    response = boto3.client("sagemaker-runtime", region_name=region).invoke_endpoint(
        EndpointName=os.getenv("SAGEMAKER_ENDPOINT", "alex-embedding-endpoint"),
        ContentType="application/json", Body=json.dumps({"inputs": text}))
    value = json.loads(response["Body"].read())
    # A single unpadded input can return a sentence vector or token vectors.
    while isinstance(value, list) and len(value) == 1 and isinstance(value[0], list):
        value = value[0]
    rows = value if isinstance(value, list) and value and isinstance(value[0], list) else [value]
    if any(not isinstance(row, list) or len(row) != 384
           or any(type(v) not in (float, int) or not math.isfinite(v) for v in row) for row in rows):
        raise ValueError("research_embedding_invalid")
    # Mean pooling for the feature-extraction pipeline; cosine supplies normalization.
    pooled = [sum(column) / len(rows) for column in zip(*rows)]
    if not any(pooled) or any(not math.isfinite(v) for v in pooled):
        raise ValueError("research_embedding_invalid")
    return pooled


def vector_location():
    region = os.getenv("RESEARCH_AWS_REGION", os.getenv("DEFAULT_AWS_REGION", "us-east-1"))
    bucket = os.getenv("VECTOR_BUCKET")
    if not bucket:
        account = boto3.client("sts", region_name=region).get_caller_identity()["Account"]
        bucket = f"alex-vectors-{account}"
    return boto3.client("s3vectors", region_name=region), {
        "vectorBucketName": bucket, "indexName": os.getenv("INDEX_NAME", "financial-research")}


def ingest(document):
    document = validate_document(document)
    metadata = document["metadata"]
    vector = embedding(document["text"])
    client, location = vector_location()
    client.put_vectors(**location, vectors=[{
        "key": metadata["research_id"], "data": {"float32": vector},
        "metadata": {"research_id": metadata["research_id"], "topic": metadata["topic"],
                     "text": document["text"], "sources_json": json.dumps(metadata["sources"])}}])
    return {"document_id": metadata["research_id"], "message": "Document indexed successfully"}


def search(query, k=3):
    if not isinstance(query, str) or not query.strip() or len(query) > 4000:
        raise InvalidResearch("research_query_required_or_too_large")
    if type(k) is not int or not 1 <= k <= 10:
        raise InvalidResearch("research_k_must_be_1_to_10")
    vector = embedding(query)
    client, location = vector_location()
    response = client.query_vectors(**location, queryVector={"float32": vector},
                                    topK=k, returnMetadata=True, returnDistance=True)
    results = []
    for item in response.get("vectors", []):
        metadata = item.get("metadata", {})
        try:
            document = validate_document({"text": metadata.get("text"), "metadata": {
                "research_id": metadata.get("research_id"), "topic": metadata.get("topic"),
                "sources": json.loads(metadata.get("sources_json", "null"))}})
            if item["key"] != document["metadata"]["research_id"]:
                raise InvalidResearch("research_identity_mismatch")
        except (InvalidResearch, ValueError, TypeError, KeyError):
            # Legacy/unattributed vectors must not become cited research.
            continue
        results.append({"id": item["key"], "score": item.get("distance"), **document})
    return results


def retrieve_evidence(symbols):
    """Resolve research once before writing a report; never substitute invented text."""
    checked_at = datetime.now(UTC).isoformat()
    try:
        results = search("market analysis " + " ".join(symbols), k=3)
        return {"status": "available" if results else "unavailable",
                "reason": None if results else "no_attributed_results",
                "retrieved_at": checked_at, "results": results}
    except Exception as exc:
        logging.exception("Research retrieval unavailable")
        return {"status": "unavailable", "reason": "retrieval_failed",
                "error_type": type(exc).__name__, "retrieved_at": checked_at, "results": []}


def evidence_markdown(evidence):
    if evidence["status"] != "available":
        return ("## Research unavailable\n\nNo retrieved research supports this report. "
                "Only the verified holdings and dated price basis are shown. "
                f"Reason: {evidence['reason']}.")
    lines = ["## Retrieved research sources", "", "These retrieved summaries are source material, not verified market prices."]
    for result in evidence["results"]:
        lines.append(f"\nResearch ID: `{result['id']}`")
        for source in result["metadata"]["sources"]:
            lines.append(f"- <{source['url']}> — fetched at {source['fetched_at']}")
    return "\n".join(lines)
