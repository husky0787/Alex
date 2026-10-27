"""Search attributed research using the shared vector adapter."""
import json
import logging
from research_chain import search, InvalidResearch


def lambda_handler(event, context):
    try:
        body = event.get("body", {})
        if isinstance(body, str):
            body = json.loads(body)
        if not isinstance(body, dict):
            raise InvalidResearch("research_query_required")
        results = search(body.get("query"), body.get("k", 3))
        return {"statusCode": 200, "body": json.dumps({"results": results})}
    except (InvalidResearch, json.JSONDecodeError) as exc:
        return {"statusCode": 400, "body": json.dumps({"error": str(exc)})}
    except Exception:
        logging.exception("Research retrieval failed")
        return {"statusCode": 503, "body": json.dumps({"error": "research_retrieval_unavailable"})}
