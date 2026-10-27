"""Single source of truth for the fixed v1 US stock/ETF universe."""
SYMBOLS = (
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    "SPY", "QQQ", "VTI", "VOO", "IWM", "DIA", "VEA", "VWO",
    "BND", "AGG", "TLT", "GLD", "VNQ",
)

NAMES = (
    "Apple", "Microsoft", "Alphabet", "Amazon", "NVIDIA", "Meta Platforms", "Tesla",
    "SPDR S&P 500 ETF", "Invesco QQQ", "Vanguard Total Stock Market ETF",
    "Vanguard S&P 500 ETF", "iShares Russell 2000 ETF", "SPDR Dow Jones Industrial Average ETF",
    "Vanguard FTSE Developed Markets ETF", "Vanguard FTSE Emerging Markets ETF",
    "Vanguard Total Bond Market ETF", "iShares Core US Aggregate Bond ETF",
    "iShares 20+ Year Treasury Bond ETF", "SPDR Gold Shares", "Vanguard Real Estate ETF",
)


def universe_metadata():
    return {"source": "massive", "currency": "USD", "adjusted": True, "frequency": "daily",
            "timezone": "America/New_York", "history_calendar_days": 90,
            "symbols": [{"symbol": symbol, "name": name, "kind": "stock" if index < 7 else "etf"}
                        for index, (symbol, name) in enumerate(zip(SYMBOLS, NAMES, strict=True))]}


def require_symbol(symbol: str) -> str:
    normalized = symbol.upper()
    if normalized not in SYMBOLS:
        raise ValueError("Unsupported symbol")
    return normalized
