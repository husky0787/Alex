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

-- Idempotent task-3 upgrade, including databases created by task 2.
ALTER TABLE market_runs DROP CONSTRAINT IF EXISTS market_runs_status_check;
ALTER TABLE market_runs ADD CONSTRAINT market_runs_status_check
    CHECK (status IN ('running', 'succeeded', 'partial', 'unavailable', 'failed'));
ALTER TABLE market_runs ADD COLUMN IF NOT EXISTS rejected_count INTEGER NOT NULL DEFAULT 0 CHECK (rejected_count >= 0);
ALTER TABLE market_runs ADD COLUMN IF NOT EXISTS missing_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_count >= 0);
ALTER TABLE market_runs ADD COLUMN IF NOT EXISTS completed_through DATE;
ALTER TABLE market_runs ADD COLUMN IF NOT EXISTS sequence BIGSERIAL;
ALTER TABLE market_runs ADD COLUMN IF NOT EXISTS retry_of UUID REFERENCES market_runs(id);

CREATE TABLE IF NOT EXISTS market_quarantine (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES market_runs(id),
    row_index INTEGER,
    reason TEXT NOT NULL,
    raw_key TEXT NOT NULL,
    raw_sha256 TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS market_attempts (
    run_id UUID NOT NULL REFERENCES market_runs(id),
    number INTEGER NOT NULL CHECK (number BETWEEN 1 AND 3),
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    http_status INTEGER,
    error_code TEXT,
    raw_key TEXT,
    raw_sha256 TEXT,
    raw_location TEXT,
    PRIMARY KEY (run_id, number)
);

CREATE TABLE IF NOT EXISTS market_observations (
    run_id UUID NOT NULL REFERENCES market_runs(id),
    price_id UUID NOT NULL REFERENCES daily_prices(id),
    observed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (run_id, price_id)
);
ALTER TABLE market_attempts ADD COLUMN IF NOT EXISTS retry_at TIMESTAMPTZ;
-- Preserve provenance of prices loaded before this migration.
INSERT INTO market_observations (run_id, price_id, observed_at)
    SELECT p.run_id, p.id, p.fetched_at FROM daily_prices p
    JOIN market_runs r ON r.id=p.run_id WHERE r.status IN ('succeeded', 'partial')
    ON CONFLICT DO NOTHING;
