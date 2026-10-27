"""Read the write-once analysis input stored with a job, without live prices."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json


class SnapshotUnavailable(ValueError):
    pass


def decimal_text(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0:
            raise ValueError
        return str(result)
    except (InvalidOperation, ValueError):
        raise SnapshotUnavailable("Invalid portfolio amount") from None


def snapshot_digest(snapshot):
    body = {key: value for key, value in snapshot.items() if key != "sha256"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def read_snapshot(job):
    """Legacy jobs and wrong-owner/changed snapshots fail before any agent runs."""
    payload = (job or {}).get("request_payload") or {}
    snapshot = payload.get("price_snapshot")
    if not isinstance(snapshot, dict) or snapshot.get("schema_version") != 1:
        raise SnapshotUnavailable("verified_price_snapshot_required: This job has no verified price snapshot.")
    if snapshot.get("user_id") != job.get("clerk_user_id") or snapshot.get("sha256") != snapshot_digest(snapshot):
        raise SnapshotUnavailable("verified_price_snapshot_invalid: Snapshot ownership or content changed.")
    prices = {price["symbol"]: price for price in snapshot["prices"]}
    if len(prices) != len(snapshot["prices"]):
        raise SnapshotUnavailable("Duplicate snapshot prices")
    for account in snapshot["accounts"]:
        decimal_text(account["cash_balance"])
        for position in account["positions"]:
            decimal_text(position["quantity"])
            price = prices.get(position["symbol"])
            if not price or Decimal(decimal_text(price["close"])) <= 0:
                raise SnapshotUnavailable("verified_price_snapshot_invalid: A holding has no verified price.")
    return deepcopy(snapshot)


def load_snapshot(db, job_id):
    return read_snapshot(db.jobs.find_by_id(job_id))


def portfolio_from_snapshot(snapshot):
    accounts = deepcopy(snapshot["accounts"])
    prices = {price["symbol"]: price for price in snapshot["prices"]}
    for account in accounts:
        for position in account["positions"]:
            position["instrument"]["current_price"] = prices[position["symbol"]]["close"]
    return {"user_id": snapshot["user_id"], "accounts": accounts,
            "price_snapshot": deepcopy(snapshot), "user_preferences": deepcopy(snapshot["user_preferences"])}


def pricing_markdown(snapshot):
    lines = ["## Price basis", "",
             f"Captured: {snapshot['captured_at']}. Expected published trading date: {snapshot['expected_trade_date']}.",
             "Prices are USD, split-adjusted daily closes; this is not a live valuation."]
    if snapshot["status"] == "stale":
        lines.append("WARNING: STALE prices were used. Actual trading dates are shown below.")
    lines.extend(["", "| Symbol | Close (USD) | Trading date | Status | Source |",
                  "| --- | --- | --- | --- | --- |"])
    for price in snapshot["prices"]:
        lines.append(f"| {price['symbol']} | {price['close']} | {price['trade_date']} | {price['status']} | {price['source']} |")
    if not snapshot["prices"]:
        lines.append("\nCash-only portfolio; no market prices required.")
    return "\n".join(lines)
