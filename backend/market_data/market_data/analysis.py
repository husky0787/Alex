"""Capture owned holdings and verified daily prices before queueing analysis."""
from decimal import Decimal

from src.snapshots import decimal_text, snapshot_digest
from .calendar import latest_published_session
from .universe import SYMBOLS


class PricesUnavailable(ValueError):
    def __init__(self, affected_symbols):
        super().__init__("Required holdings have no supported verified price")
        self.affected_symbols = affected_symbols


def capture_snapshot(db, repository, user, now):
    user_id = user["clerk_user_id"]
    accounts, symbols = [], set()
    for account in db.accounts.find_by_user(user_id):
        if account["clerk_user_id"] != user_id:
            raise ValueError("Account ownership mismatch")
        positions = []
        for position in db.positions.find_by_account(account["id"]):
            if position["account_id"] != account["id"]:
                raise ValueError("Position ownership mismatch")
            quantity = decimal_text(position["quantity"])
            if Decimal(quantity) == 0:
                continue
            symbol = position["symbol"]
            instrument = db.instruments.find_by_symbol(symbol) or {}
            metadata = {key: instrument[key] for key in (
                "name", "instrument_type", "allocation_asset_class", "allocation_regions", "allocation_sectors"
            ) if key in instrument}
            positions.append({"symbol": symbol, "quantity": quantity, "instrument": metadata})
            symbols.add(symbol)
        accounts.append({"id": account["id"], "name": account["account_name"],
                         "type": account.get("account_type", "investment"),
                         "cash_balance": decimal_text(account.get("cash_balance", 0)), "positions": positions})
    prices, affected = [], []
    for symbol in sorted(symbols):
        if symbol not in SYMBOLS:
            affected.append({"symbol": symbol, "reason": "unsupported"})
            continue
        latest = repository.latest(symbol, as_of=now)
        if latest["price"] is None:
            affected.append({"symbol": symbol, "reason": "unavailable"})
            continue
        price = latest["price"]
        prices.append({"symbol": symbol, "status": latest["status"], "close": price["close"],
                       "trade_date": price["trade_date"], "source": price["source"], "currency": "USD",
                       "adjusted": price["adjusted"], "observation_id": price["id"], "version": price["version"],
                       "run_id": price["run_id"], "raw_sha256": price["raw_sha256"], "fetched_at": price["fetched_at"]})
    if affected:
        raise PricesUnavailable(affected)
    snapshot = {"schema_version": 1, "user_id": user_id, "captured_at": now.isoformat(),
                "expected_trade_date": latest_published_session(now).isoformat(),
                "status": "stale" if any(price["status"] == "stale" for price in prices) else "fresh",
                "prices": prices, "accounts": accounts,
                "user_preferences": {"years_until_retirement": int(user["years_until_retirement"] if user.get("years_until_retirement") is not None else 30),
                                     "target_retirement_income": float(user["target_retirement_income"] if user.get("target_retirement_income") is not None else 80000),
                                     "current_age": 40}}
    snapshot["sha256"] = snapshot_digest(snapshot)
    return snapshot
