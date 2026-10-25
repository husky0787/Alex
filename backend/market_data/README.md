# Verified daily market data

This package adds a traceable daily-price path alongside Alex's existing account and analysis services. The first screen shows AAPL. It does not treat seeded `instruments.current_price` or the planner's legacy random fallback as a verified quote; replacing portfolio/analysis pricing is task 5.

```text
Massive daily REST bars → raw response → validate → PostgreSQL history + run record
                                                        ↓
                             authenticated API → /market-data page
```

## Provider and price meaning

Use **Stocks Basic ($0)** for personal development. Official access includes daily bars, two years of history and five requests per minute. Account access was exercised with one AAPL request covering 2026-07-28 through 2026-10-23; plan billing itself is not exposed by that API. Confirm Basic in the provider dashboard, and do not select an upgrade.

The existing `POLYGON_API_KEY` name works. `MASSIVE_API_KEY` is also supported and takes precedence if both are set. Requests use `https://api.massive.com` with a bearer header; credentials are never put in request URLs, evidence summaries or source control.

Bars are split-adjusted (`adjusted=true`), denominated in USD, and dated in America/New_York. Volume supports fractional shares: it is stored as PostgreSQL `NUMERIC` and returned as a decimal string, as are prices. Freshness uses the latest XNYS trading date before the current ET date, matching Basic's after-midnight EOD availability. `fresh` means current for this publication schedule, not real-time. `stale` retains the dated verified bar; `unavailable` contains no price.

The 20-symbol v1 universe is recorded in `market_data/universe.py`; task 4 supplies full-universe batch coverage and historical presentation. The current page intentionally displays the first AAPL slice.

## Local configuration

Run commands below from the repository root. Put credentials in the ignored root `.env`:

```dotenv
POLYGON_API_KEY=your_key
MARKET_DATABASE_URL=postgresql://your_user:your_password@127.0.0.1:5432/alex_market
```

Use an isolated local PostgreSQL database. No command below provisions a database server, AWS resource or paid subscription. The API's existing Clerk/Aurora configuration is still required to run the whole Alex application; `MARKET_DATABASE_URL` configures only its new market-data route. Deployed Aurora connectivity and workload identities are part of the later deployment tasks.

```sh
uv sync --project backend --locked --package api
uv run --project backend --locked --package api -m market_data --env-file .env migrate
uv run --project backend --locked --package api -m market_data --env-file .env ingest --symbol AAPL --from 2026-10-23 --to 2026-10-23
uv run --project backend --locked --package api -m market_data --env-file .env latest --symbol AAPL
```

The dated ingestion command is the verification example; choose an already published date for subsequent use. One ingestion accepts at most 90 calendar days. Daily and backfill requests use the same pipeline entry point. The CLI returns nonzero on failed or empty ingestion.

Raw responses default to `.local/market-data/raw/...`, ignored by Git. Every run stores the raw key, SHA-256 digest and location. Observations refer to the run and a normalized-value version. Repeating an unchanged bar preserves its observation identity and still creates a separate run/raw response. Raw writes precede database publication; price inserts and successful completion share one transaction. Invalid responses fail without publishing a partial batch. Quarantine, retries, recovery and concurrent-run control belong to task 3.

For the later AWS environment, `ingest --raw-bucket <private-data-bucket>` uses encrypted S3 writes with overwrite prevention. Provision that private bucket separately from frontend hosting and grant narrowly scoped access. The adapter is tested with AWS stubs; no bucket has been provisioned or live S3 call validated by this task.

## Automated verification

Install PostgreSQL server tools (`initdb`, `pg_ctl`, and `pg_dump`) and set `PG_BIN` to their directory. The runner creates a temporary loopback-only PostgreSQL cluster, runs tests, then stops/removes only that cluster. It never reuses `MARKET_DATABASE_URL` for tests. Windows must run it in the regular user context: PostgreSQL's restricted-token launch cannot run inside the Codex sandbox.

```powershell
# Example for the portable tools used on this workspace:
$env:PG_BIN='D:\learn\production\.tools\postgres17\pgsql\bin'
$env:UV_CACHE_DIR='D:\learn\production\.tools\uv-cache'
uv run --project backend --locked --package api backend/market_data/tests/run_integration.py
```

If uv is not on PATH here, invoke `D:/learn/production/.tools/uv/uv.exe` instead. Other machines can use their installed uv/PostgreSQL.

From `frontend`:

```sh
npm ci --no-audit --no-fund
npm run test:market
npm run build
```

The production build needs the existing Clerk public key. The verification build used the nonfunctional placeholder `pk_test_Y2xlcmsuZXhhbXBsZS50ZXN0JA`; do not deploy that test build. After building, run `node --test tests/static_routes.test.cjs tests/export_routes.test.cjs` from `terraform/7_frontend` to verify the new page's static target as well.

## Real-provider smoke test

This is an explicit network operation and consumes one provider request. Run only after setting a real free-account key:

```sh
uv run --project backend --locked --package api backend/market_data/tests/run_integration.py --live-smoke --env-file .env
```

It migrates a temporary PostgreSQL database, runs the **same** pipeline for AAPL over the recent 90-calendar-day window, requires all expected sessions, and reads the result through the real authenticated API with an offline test issuer. This verifies JWT enforcement and the API/database path, not a live Clerk login.

The ignored `.local/market-data` folder retains raw responses, `smoke.json`, `api-response.json`, and `smoke-database.dump`. The server is stopped afterward. The dump can be restored with PostgreSQL `pg_restore --no-owner` into a separately created local database for inspection. These private artifacts are not intended for public data redistribution.

To exercise the rendered panel with that actual API response, run from `frontend`:

```powershell
$env:MARKET_LIVE_RESPONSE_FILE=(Resolve-Path '../.local/market-data/api-response.json').Path
npm run test:market
```

Normal tests use controlled fixtures and make no provider request. The live smoke, authenticated API check, and rendered panel check together cover source-to-screen behavior without provisioning AWS.

## Failure boundaries

Malformed envelopes/bars, HTTP errors, timeouts and storage failures have explicit run outcomes. The pipeline does not retry automatically yet. If PostgreSQL is completely unreachable after raw storage, the run may remain `running` or lack its raw reference; this is not considered success and requires the recovery work in task 3. The additive migration creates new tables only; no legacy user, account, position or instrument table is altered.

The Lambda packaging helper now copies this module and exports locked external API dependencies. A full Linux Lambda ZIP was not built here because Docker is unavailable; verify its size and runtime in the later deployment stage.

References: [Massive Basic pricing](https://massive.com/pricing), [daily bar API](https://massive.com/docs/rest/stocks/aggregates/custom-bars), [publication timing](https://massive.com/knowledge-base/article/what-time-are-massives-flat-files-ready-each-day), [fractional shares](https://massive.com/changelog), [exchange calendar](https://github.com/gerrymanoim/exchange_calendars).
