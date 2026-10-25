"""Fixed v1 US stock/ETF universe; task 4 adds batch coverage and history UI."""
SYMBOLS = (
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    "SPY", "QQQ", "VTI", "VOO", "IWM", "DIA", "VEA", "VWO",
    "BND", "AGG", "TLT", "GLD", "VNQ",
)


def require_symbol(symbol: str) -> str:
    normalized = symbol.upper()
    if normalized not in SYMBOLS:
        raise ValueError("Unsupported symbol")
    return normalized
