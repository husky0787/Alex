"""Credential-free summary; private raw responses remain in the configured store."""
import exchange_calendars


def smoke_evidence(repository, run, start, end, now):
    expected = exchange_calendars.get_calendar("XNYS").sessions_in_range(start, end)
    latest = repository.latest(run["symbol"], as_of=now)
    complete = (
        run["status"] == "succeeded" and run["accepted_count"] == len(expected)
        and run["from_date"] == start.isoformat() and run["to_date"] == end.isoformat()
        and latest["price"] is not None and latest["price"]["trade_date"] == end.isoformat()
    )
    return {
        "status": "passed" if complete else "failed", "checked_at": now.isoformat(),
        "source": run["source"], "symbol": run["symbol"], "adjustment": "split-adjusted",
        "from_date": start.isoformat(), "to_date": end.isoformat(),
        "expected_session_count": len(expected), "accepted_count": run["accepted_count"],
        "run_id": run["id"], "run_status": run["status"], "error_code": run["error_code"],
        "raw_key": run["raw_key"], "raw_sha256": run["raw_sha256"],
        "latest_verified_trade_date": latest["price"]["trade_date"] if latest["price"] else None,
        "subscription_plan": "not introspected; confirm Stocks Basic in provider dashboard",
    }
