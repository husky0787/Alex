"""Read the live-ingested DB through real API auth with an offline test issuer.

Run only from run_integration.py's isolated live-smoke database.
"""
import json
import os
from pathlib import Path
import sys


def main():
    if not os.environ.get("MARKET_TEST_DATABASE_URL") or os.environ.get("MARKET_DATABASE_URL") != os.environ["MARKET_TEST_DATABASE_URL"]:
        raise SystemExit("Use the isolated live-smoke runner")
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api"))
    from test_error_contract import APIErrorContractTests

    evidence_path = Path(".local/market-data/smoke.json")
    evidence = json.loads(evidence_path.read_text())
    APIErrorContractTests.setUpClass()
    case = APIErrorContractTests()
    try:
        case.setUp()
        case.assertEqual(case.client.get("/api/market-data/AAPL").status_code, 403)
        response = case.client.get("/api/market-data/AAPL", headers=case.headers())
        case.assertEqual(response.status_code, 200, "Authenticated market API must succeed")
        result = response.json()
        case.assertEqual(result["status"], "fresh")
        case.assertEqual(result["price"]["trade_date"], evidence["to_date"])
        case.assertEqual(result["price"]["run_id"], evidence["run_id"])
        case.assertEqual(result["price"]["raw_sha256"], evidence["raw_sha256"])
        Path(".local/market-data/api-response.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        evidence["authenticated_api_check"] = "passed; test issuer, real API and PostgreSQL"
        evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print("Live-ingested data -> authenticated API: passed")
        case.tearDown()
    finally:
        case.doCleanups()
        APIErrorContractTests.doClassCleanups()


if __name__ == "__main__":
    main()
