# Verified daily market data

This package adds a traceable daily-price path alongside Alex's account services. The market page supports 20 US stocks/ETFs, latest daily prices and a 90-calendar-day history. Seeded `instruments.current_price` is not a verified quote. Task 3 removes the random fallback and temporarily blocks new analysis; task 5 will connect immutable portfolio price snapshots and restore analysis using verified prices.

```text
Massive daily REST bars → raw response → validate → PostgreSQL history + run record
                                                        ↓
                             authenticated API → /market-data page
```

## Provider and price meaning

Use **Stocks Basic ($0)** for personal development. Official access includes daily bars, two years of history and five requests per minute. Account access was exercised with one AAPL request covering 2026-07-28 through 2026-10-23; plan billing itself is not exposed by that API. Confirm Basic in the provider dashboard, and do not select an upgrade.

The existing `POLYGON_API_KEY` name works. `MASSIVE_API_KEY` is also supported and takes precedence if both are set. Requests use `https://api.massive.com` with a bearer header; credentials are never put in request URLs, evidence summaries or source control.

Bars are split-adjusted (`adjusted=true`), denominated in USD, and dated in America/New_York. Volume supports fractional shares: it is stored as PostgreSQL `NUMERIC` and returned as a decimal string, as are prices. Freshness uses the latest XNYS trading date before the current ET date, matching Basic's after-midnight EOD availability. `fresh` means current for this publication schedule, not real-time. `stale` retains the dated verified bar; `unavailable` contains no price.

The fixed v1 universe is AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, SPY, QQQ, VTI, VOO, IWM, DIA, VEA, VWO, BND, AGG, TLT, GLD and VNQ. `market_data/universe.py` is the source of truth; the authenticated `/api/market-data/universe` endpoint supplies the selector. The ETFs are US-listed, including those holding international assets.

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

The dated ingestion command is the verification example; choose an already published date for subsequent use. One ingestion accepts at most 90 calendar days. Daily and backfill requests use the same pipeline entry point. The CLI returns nonzero on failed, partial or empty ingestion.

Raw responses default to `.local/market-data/raw/...`, ignored by Git. Every HTTP attempt stores its raw key, SHA-256 digest and location; the run points to the latest saved response. Quarantine records refer to that immutable object and a zero-based row index (null for an invalid whole response). Quarantine is logical exclusion from published prices, not a copy into a public bucket. Valid rows in a mixed response publish with a `partial` run status; malformed envelopes publish nothing.

Repeating an unchanged bar preserves its version identity while retaining each run's sighting. A correction A→B→A displays the latest sighting of A without duplicating A or losing B. Raw writes precede database publication; price versions, sightings, quarantine and terminal completion commit together. `completed_through` stops at the first missing expected trading date within this run. It is not a global watermark; a fresh visible price does not prove the entire requested history is complete.

For the later AWS environment, `ingest --raw-bucket <private-data-bucket>` uses encrypted S3 writes with overwrite prevention. Provision that private bucket separately from frontend hosting and grant narrowly scoped access. The adapter is tested with AWS stubs; no bucket has been provisioned or live S3 call validated by this task.

## History and resumable backfill

```sh
uv run --project backend --locked --package api -m market_data --env-file .env backfill
uv run --project backend --locked --package api -m market_data --env-file .env history --symbol MSFT
```

Both commands default to today in America/New_York and the preceding 89 calendar dates. `backfill` checks all 20 symbols and uses `DailyPricePipeline` to fetch only the span from the first to last missing published session per symbol. Completed symbols are skipped; interrupted overlapping runs are resumed under the existing symbol lock. If a resumed smaller range succeeds, any remaining dates are fetched. A failed/partial resume remains visible for the next operator pass. No completion cursor jumps over a missing date.

For a specific window/subset, add `--from 2026-08-01 --to 2026-10-26 --symbols AAPL MSFT` (choose dates within the current 90-day window). Repeat the same date arguments after interruption only while they remain within that rolling limit. If the oldest date has aged out, omit dates or select current bounds; the backfill still resumes overlapping interrupted work and fills current gaps. To finish the original run outside the history window, use `resume <run-id>`. Covered bars between gaps may be fetched again but their immutable versions are deduplicated. Backfill skips covered dates; use `ingest` explicitly to refresh covered data for possible source corrections.

The CLI paces requests at least 13 seconds apart across symbols and retries. A first full-universe pull normally needs 20 calls and approximately four minutes, plus response time; external calls using the same key can still trigger 429. A repeated fully covered backfill makes no provider calls and needs no key. `--evidence <path>` optionally saves a credential-free coverage summary; `--raw-dir` and `--raw-bucket` have the same meaning as ingestion. Per-symbol progress goes to stderr, final JSON to stdout, and any remaining expected gap returns a nonzero exit code. On a database outage, rerun after fixing connectivity; persisted symbol results remain available.

`GET /api/market-data/{symbol}/history` requires the same login as the latest-price endpoint and accepts optional `from_date` / `to_date` within the last 90 calendar dates. Results include sorted daily rows, source, currency, adjustment basis, exact decimal OHLCV strings, observation version/run/digest and coverage counts. There are five date states: `available`, `missing`, `weekend`, `holiday` and `not_published`. Non-trading/unpublished dates do not count as expected gaps. No history uses legacy instrument prices or exposes raw storage paths.

The chart connects across weekends and holidays but breaks on missing/unpublished trading days. Empty values stay empty; the table shows exact numeric strings. A latest price can be fresh while historical coverage remains partial. History reflects the latest accepted source sightings, not a historical information-as-of snapshot.

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

For explicit full-universe verification, run `uv run --project backend --locked --package api backend/market_data/tests/run_integration.py --live-backfill --env-file .env`. It uses a new isolated database, runs the paced backfill, checks all 20 histories through real API authentication with a local test issuer, and repeats backfill without a provider to verify that complete coverage is skipped. Private raw data, metadata, API histories and a database dump are retained under `.local/market-data/task-04/`; the test server stops afterward. No subscription or AWS resource is created. Set `MARKET_LIVE_HISTORY_FILE` to that folder's `api-history.json` when running `npm run test:market` to exercise the actual data in the history UI.

## Failure boundaries

Transport failures and HTTP 408/429/500/502/503/504 get at most three attempts, with 1/2 second backoff and a longer valid `Retry-After` respected. A requested delay over 60 seconds stops the run for later operator action. Authentication and schema/quality failures are not retried automatically. Attempt records survive recovery so restarting an interrupted run does not reset its budget or bypass backoff. A new explicit retry has its own bounded budget and points to its original run.

Run `migrate` before using the new commands on a task-2 database. It adds run metadata, quarantine, attempts and sightings, and backfills existing price provenance. It does not alter legacy user/account/position/instrument tables. Use a direct PostgreSQL connection, not a transaction-pooling proxy: ingestion uses session advisory locks. Another run for the same symbol returns `symbol_busy` without fetching or advancing completion; retry it once the owner finishes.

```sh
uv run --project backend --locked --package api -m market_data --env-file .env runs --status running
uv run --project backend --locked --package api -m market_data --env-file .env inspect <run-uuid>
uv run --project backend --locked --package api -m market_data --env-file .env resume <run-uuid>
uv run --project backend --locked --package api -m market_data --env-file .env retry <run-uuid>
```

`inspect` shows private operator evidence: run state, HTTP attempts, quarantine reasons and published observations. `resume` acquires the symbol lock and replays a committed successful raw response after checking its digest; otherwise it consumes the remaining attempt budget. It retains the original observation timestamp so delayed recovery cannot replace a newer source correction. Terminal runs are not changed by resume. `retry` refetches a failed/partial/unavailable range into a new linked run, leaving old evidence intact. Configure the same `--raw-dir` or `--raw-bucket` for recovery. Inspect and saved-response replay need no provider API key; fetching does.

After a database outage or ambiguous commit, reconnect and inspect/resume the original run. A successful committed run is already complete; never assume an error means nothing committed. A crash between object save and pointer commit can leave an orphan object; recovery does not guess its contents and may refetch within its remaining budget. Unrecoverable/mismatched raw evidence fails clearly. Fix the external fault, then explicitly retry. Migration is tested against both the original task-2 schema and repeat invocation.

Until task 5 supplies price snapshots, `/api/analyze` returns an authenticated JSON `503` with code `verified_price_snapshot_required` before creating or queueing a job. Planner also fails existing queued/direct work before Tagger/LLM calls. The `/market-data` page remains usable; this task does not make legacy reports or seed prices verified.

The Lambda packaging helper now copies this module and exports locked external API dependencies. A full Linux Lambda ZIP was not built here because Docker is unavailable; verify its size and runtime in the later deployment stage.

References: [Massive Basic pricing](https://massive.com/pricing), [daily bar API](https://massive.com/docs/rest/stocks/aggregates/custom-bars), [publication timing](https://massive.com/knowledge-base/article/what-time-are-massives-flat-files-ready-each-day), [fractional shares](https://massive.com/changelog), [exchange calendar](https://github.com/gerrymanoim/exchange_calendars).
