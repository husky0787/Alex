"""Read all live-ingested histories through real auth and prove a second backfill does no work."""
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sys

import httpx
import psycopg
from market_data.backfill import HistoryBackfill
from market_data.pipeline import DailyPricePipeline
from market_data.repository import PriceRepository
from market_data.storage import LocalRawStore
from market_data.universe import SYMBOLS


def main():
    dsn = os.environ.get("MARKET_TEST_DATABASE_URL")
    if not dsn or dsn != os.environ.get("MARKET_DATABASE_URL"):
        raise SystemExit("Use the isolated live-backfill runner")
    root = Path(".local/market-data/task-04")
    evidence = json.loads((root / "backfill.json").read_text())
    start, end = date.fromisoformat(evidence["from_date"]), date.fromisoformat(evidence["to_date"])
    # Use the same fixed window if the batch crossed midnight ET.
    as_of = datetime.fromisoformat(evidence["as_of"])
    with psycopg.connect(dsn, autocommit=True) as connection:
        repository = PriceRepository(connection)
        before = len(repository.runs())
        pipeline = DailyPricePipeline(None, LocalRawStore(root), repository, clock=lambda: as_of)
        repeated = HistoryBackfill(pipeline, repository, clock=lambda: as_of).run(start, end)
        assert repeated["status"] == "succeeded" and all(row["action"] == "skipped" for row in repeated["symbols"])
        assert len(repository.runs()) == before
        for row in evidence["symbols"]:
            run = repository.get_run(row["run_id"])
            row["raw_sha256"] = run["raw_sha256"]
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api"))
    from test_error_contract import APIErrorContractTests
    APIErrorContractTests.setUpClass()
    case = APIErrorContractTests()
    try:
        case.setUp()
        headers = case.headers()
        case.assertEqual(case.client.get("/api/market-data/AAPL/history").status_code, 403)
        universe = case.client.get("/api/market-data/universe", headers=headers).json()
        case.assertEqual([item["symbol"] for item in universe["symbols"]], list(SYMBOLS))
        histories = {}
        for symbol in SYMBOLS:
            response = case.client.get(f"/api/market-data/{symbol}/history?from_date={start}&to_date={end}", headers=headers)
            case.assertEqual(response.status_code, 200)
            history = response.json()
            case.assertEqual(history["coverage"], "complete")
            case.assertEqual(len(history["days"]), 90)
            case.assertEqual(history["available_count"], history["expected_count"])
            case.assertNotIn("raw_location", response.text)
            histories[symbol] = history
        latest = case.client.get("/api/market-data/AAPL", headers=headers).json()
        (root / "api-history.json").write_text(json.dumps({"universe": universe, "histories": histories, "latest": latest}, indent=2), encoding="utf-8")
        evidence.update(checked_at=datetime.now(timezone.utc).isoformat(),
                        authenticated_history_api="passed for 20 symbols; local JWT test issuer, real API and PostgreSQL",
                        repeated_backfill="all 20 skipped; no new provider requests or run records",
                        subscription_plan="not introspected; no subscription changed")
        (root / "backfill.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print("Live 20-symbol history -> authenticated API and idempotent repeat: passed", flush=True)
        case.tearDown()
    finally:
        case.doCleanups()
        APIErrorContractTests.doClassCleanups()


if __name__ == "__main__":
    main()
