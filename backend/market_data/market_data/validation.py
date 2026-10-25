"""Validate the provider envelope and every bar before any history is published."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json

from .calendar import EASTERN, is_session, latest_published_session


class InvalidMarketData(ValueError):
    pass


def normalize_bars(body, symbol, start, end, now):
    try:
        payload = json.loads(body, parse_float=Decimal)
    except (ValueError, UnicodeError):
        raise InvalidMarketData("invalid_json") from None
    if not isinstance(payload, dict) or payload.get("ticker") != symbol or payload.get("adjusted") is not True:
        raise InvalidMarketData("unexpected_source_contract")
    if payload.get("status") not in ("OK", "DELAYED") or payload.get("next_url"):
        raise InvalidMarketData("incomplete_source_response")
    rows = payload.get("results", [])
    if not isinstance(rows, list) or payload.get("resultsCount") != len(rows):
        raise InvalidMarketData("invalid_result_count")
    bars = []
    dates = set()
    expected = latest_published_session(now)
    for row in rows:
        if not isinstance(row, dict) or not all(key in row for key in ("o", "h", "l", "c", "v", "t")):
            raise InvalidMarketData("missing_bar_fields")
        if any(type(row[key]) not in (int, Decimal) for key in ("o", "h", "l", "c", "v", "t")):
            raise InvalidMarketData("invalid_numeric_type")
        values = {name: Decimal(row[field]) for name, field in
                  [("open", "o"), ("high", "h"), ("low", "l"), ("close", "c")]}
        if any(not value.is_finite() or value <= 0 for value in values.values()):
            raise InvalidMarketData("invalid_price")
        if not (values["low"] <= min(values["open"], values["close"]) <=
                max(values["open"], values["close"]) <= values["high"]):
            raise InvalidMarketData("invalid_ohlc")
        volume = Decimal(row["v"])
        if not volume.is_finite() or volume < 0:
            raise InvalidMarketData("invalid_volume")
        timestamp = Decimal(row["t"])
        if not timestamp.is_finite() or timestamp != timestamp.to_integral_value():
            raise InvalidMarketData("invalid_timestamp")
        try:
            trade_date = datetime.fromtimestamp(int(timestamp) / 1000, timezone.utc).astimezone(EASTERN).date()
        except (ValueError, OverflowError, OSError):
            raise InvalidMarketData("invalid_timestamp") from None
        if not start <= trade_date <= min(end, expected) or not is_session(trade_date) or trade_date in dates:
            raise InvalidMarketData("invalid_trade_date")
        dates.add(trade_date)
        canonical = {key: str(value.normalize()) for key, value in values.items()}
        canonical.update(symbol=symbol, trade_date=trade_date.isoformat(), volume=str(volume.normalize()), adjusted=True)
        version = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
        bars.append({**values, "symbol": symbol, "trade_date": trade_date, "volume": volume,
                     "version": version, "fetched_at": now})
    return bars
