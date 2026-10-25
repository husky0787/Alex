CREATE TABLE IF NOT EXISTS market_runs (
    id UUID PRIMARY KEY,
    source TEXT NOT NULL,
    symbol TEXT NOT NULL,
    from_date DATE NOT NULL,
    to_date DATE NOT NULL CHECK (to_date >= from_date),
    adjusted BOOLEAN NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'unavailable', 'failed')),
    accepted_count INTEGER NOT NULL DEFAULT 0 CHECK (accepted_count >= 0),
    raw_key TEXT,
    raw_sha256 TEXT,
    raw_location TEXT,
    error_code TEXT
);

CREATE TABLE IF NOT EXISTS daily_prices (
    id UUID PRIMARY KEY,
    source TEXT NOT NULL,
    symbol TEXT NOT NULL,
    trade_date DATE NOT NULL,
    adjusted BOOLEAN NOT NULL,
    open NUMERIC NOT NULL CHECK (open > 0 AND open < 'Infinity'::numeric),
    high NUMERIC NOT NULL CHECK (high > 0 AND high < 'Infinity'::numeric),
    low NUMERIC NOT NULL CHECK (low > 0 AND low < 'Infinity'::numeric),
    close NUMERIC NOT NULL CHECK (close > 0 AND close < 'Infinity'::numeric),
    volume NUMERIC NOT NULL CHECK (volume >= 0 AND volume < 'Infinity'::numeric),
    fetched_at TIMESTAMPTZ NOT NULL,
    version TEXT NOT NULL,
    run_id UUID NOT NULL REFERENCES market_runs(id),
    CHECK (low <= open AND low <= close AND high >= open AND high >= close AND low <= high),
    UNIQUE (source, symbol, trade_date, adjusted, version)
);
CREATE INDEX IF NOT EXISTS daily_prices_latest
    ON daily_prices (symbol, source, adjusted, trade_date DESC, fetched_at DESC);
