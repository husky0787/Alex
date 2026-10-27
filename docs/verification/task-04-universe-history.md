# Task 4: supported universe, history and resumable backfill

Verified locally on 2026-10-27 on `feat/task-04-universe-history`, based on `7fbe8e69b6f1a762001b31d18e61c21a9ff54953`. Implements GitHub #6; merge and cloud deployment are separate steps.

## Live evidence

The Massive provider supplied all 20 supported symbols for the 90-calendar-day window **2026-07-30 through 2026-10-27**, evaluated at **2026-10-27 12:36 UTC**. Each symbol had **62/62 expected published trading days**, totaling **1,240 daily bars** with no missing expected dates. The current ET trading day was not yet published and was not treated as missing. The CLI spaces request starts by at least 13 seconds within its process.

[Sanitized evidence](task-04-provider-backfill.json) records each symbol's coverage, run ID and raw SHA-256. Source responses, exact prices, database dump and credentials remain private under ignored local paths. The account subscription was not introspected or changed.

Authenticated requests to the real API and isolated PostgreSQL returned complete histories for all 20 symbols; unauthenticated access returned 403. Authentication used a local JWT test issuer, not a live Clerk browser login. Repeating the same backfill skipped all 20 symbols, creating no new provider requests or run records. A frontend test rendered the actual verified universe and AAPL history from these API responses.

## Regression evidence

- 40 isolated PostgreSQL/pipeline/API tests passed: date order, missing earlier dates despite a fresh latest price, weekend/holiday/unpublished distinctions, spring/fall DST, 90-day limits, A→B→A revisions, interrupted multi-symbol recovery, shorter interrupted ranges, partial provider failure and idempotent repetition.
- 11 existing API error/analysis-guard tests passed.
- 9 frontend tests passed, including the optional actual-source response test, symbol switching, stale-response cancellation, explicit gaps, unavailable/error states and signed-out behavior.
- Next.js production build, TypeScript/lint checks and static export passed. 16 edge/export tests passed.

Next.js telemetry was disabled to avoid a Windows cross-drive telemetry-config rename error. The build used a nonfunctional test Clerk public key. No browser screenshot or full browser login was performed.

## Reproduce

Use the environment and PostgreSQL setup in the [module README](../../backend/market_data/README.md). With `PG_BIN` pointing at the installed PostgreSQL binaries:

```text
uv run --project backend --locked --package api backend/market_data/tests/run_integration.py
uv run --project backend --locked --package api -m unittest discover -s backend/api -p test_error_contract.py -q
```

Run `npm run test:market` and `npm run build` from `frontend`. For the optional actual-source rendering test, set `MARKET_LIVE_HISTORY_FILE` to the absolute path of the private `api-history.json` generated below.

```text
uv run --project backend --locked --package api backend/market_data/tests/run_integration.py --live-backfill --env-file .env
```

The live command requests a new rolling window for all 20 symbols; it consumes provider quota. It creates an isolated loopback PostgreSQL cluster, retains private evidence in `.local/market-data/task-04/`, and stops its cluster afterward. Regular regression tests use controlled external HTTP responses, not provider requests.

## Operational boundaries

Coverage is derived from all persisted expected dates, not a maximum-date cursor. Restart first resumes an overlapping interrupted run and then fills remaining gaps after successful recovery. Covered dates are skipped; refreshing provider corrections requires explicit `ingest`. History is the latest verified projection, not a point-in-time report snapshot. See [ADR 0003](../adr/0003-history-coverage-and-backfill.md).

Rate pacing is process-local: concurrent processes sharing one key can still exhaust quota. Existing bounded retries and run evidence remain active. Task 5 must connect immutable price snapshots before enabling analysis; the existing 503/Planner guards remain in place. AWS, live S3/Aurora, Kubernetes scheduling and deployment were not exercised in this task.
