# Task 02 verification: first verified daily price

Issue: [#4](https://github.com/husky0787/Alex/issues/4). Date: 2026-10-25 (Asia/Taipei).

## Delivered behavior

One pipeline fetches Massive daily OHLCV, retains the raw response, validates it, and commits versioned PostgreSQL observations with a run record. `GET /api/market-data/AAPL` requires a verified Clerk-style JWT and returns provenance plus `fresh`, `stale` or `unavailable`. The new `/market-data` screen displays the trading date, source and OHLCV with those states. No synthetic price is substituted.

## Real-source evidence

- Verified with the user's locally configured key against `api.massive.com`.
- Requested AAPL from 2026-07-28 through 2026-10-23, within the recent 90-calendar-day window.
- **63 expected trading sessions; 63 accepted bars; run succeeded.** Latest verified trading date: **2026-10-23**.
- The authenticated API returned the same run ID and raw digest; an unauthenticated request returned 403. Authentication used local test signing keys, not a live Clerk browser session.
- The actual API response was rendered by the React panel test, preserving its trading date, source and all fractional-volume digits.
- Sanitized summary: [task-02-provider-smoke.json](task-02-provider-smoke.json). Raw response, API response and PostgreSQL dump remain in ignored `.local/market-data`.
- Provider billing/plan name was not introspected. The API access required for this slice and historical range was demonstrated; the official Stocks Basic plan includes it. No subscription or paid plan was purchased.

The first smoke test correctly failed because the draft spec assumed integer volume. All 63 source bars contained fractional volume. PostgreSQL `NUMERIC`, decimal-string JSON and exact UI formatting now preserve it, with a regression test and a correction in parent spec #2. No rounding workaround was used.

## Local checks

| Check | Result |
| --- | --- |
| PostgreSQL/API/S3 boundary suite | 16 test methods passed, with parameterized cases |
| React panel | 5 fixture tests plus 1 actual live-response test passed |
| Existing API authorization/error suite | 10 test methods passed |
| Frontend production export and static routing | Build/type checks passed; 16 edge/export tests passed |
| Package build | Wheel and source distribution built; wheel contains schema.sql |
| Lambda dependency export | Locked API dependency export succeeded |

Behavioral coverage includes raw provenance, wrong source/envelope, invalid prices/OHLC/volume/date, fractional volume, HTTP 401/403/429/500, timeout, empty results, raw-storage failure, transaction rollback, same-value reruns, bounded input, weekends/holidays/DST, authenticated reads and UI states.

## Limits and next work

All PostgreSQL servers used here were isolated temporary clusters and were stopped. AWS was not deployed or billed by this work; S3 was tested with stubs. The full Lambda Docker package, live Clerk login, cloud networking and final public frontend deployment remain unverified. Existing portfolio/analysis pricing is deliberately separate until task 5. Task 3 covers quarantine/retries/recovery; task 4 covers 20-symbol backfill/history presentation.

Reproduction commands and configuration: [market-data README](../../backend/market_data/README.md).
