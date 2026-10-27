"""Ingest attributed research using the shared vector adapter."""
import json
import logging
from research_chain import ingest, InvalidResearch


def lambda_handler(event, context):
    try:
        body = event.get("body", {})
        if isinstance(body, str):
            body = json.loads(body)
        result = ingest(body)
        return {"statusCode": 200, "body": json.dumps(result)}
    except (InvalidResearch, json.JSONDecodeError) as exc:
        return {"statusCode": 400, "body": json.dumps({"error": str(exc)})}
    except Exception:
        logging.exception("Research ingestion failed")
        return {"statusCode": 503, "body": json.dumps({"error": "research_ingestion_unavailable"})}
