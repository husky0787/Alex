# Task 3: market-data quality and recovery

Verified locally on 2026-10-25 on branch `feat/task-03-quality-recovery`, based on task-2 merge `7691716c7117dcf3489f1df5bce1cc76c994fe9b`. The PR commit records the exact implementation; no AWS deployment or paid model call was performed.

## Evidence

- 30 PostgreSQL/API/storage tests passed against an isolated PostgreSQL 17.11 cluster. The runner stops/removes its own cluster after each test invocation.
- 11 API contract tests passed, including authenticated analysis rejection before job creation/SQS and preservation of existing 403/404 behavior.
- Planner entry-point regression passed for both direct invocation and a pre-existing SQS message. Real planner/database adapters ran with AWS transport stubs; both jobs record failure before Tagger or LLM calls.
- Existing frontend market-panel tests passed. No frontend implementation or dependencies changed.
- No new provider request was needed: task 2 already verified real 63/63 AAPL daily bars. Task-3 fault injection uses controlled HTTP responses, real PostgreSQL transactions and local immutable raw storage. The existing S3 adapter contract test uses AWS stubs, not live S3.

## Behaviors exercised

Mixed valid/invalid responses preserve valid prices, quarantine row reasons and raw digests, expose partial status and stop contiguous completion at gaps. Duplicate trading dates are quarantined; malformed envelopes, missing fields, invalid OHLCV and empty data do not fabricate prices. Fractional volume retains source precision, including revisions beyond Decimal's default 28-digit context.

Transient HTTP/timeout retries retain attempt evidence and stop after three tries; authentication failures stop immediately. Retry-After survives interruption, and a delay above the automatic bound stops rather than retrying early. Two actual PostgreSQL connections verify a competing run cannot fetch/publish while the owner holds the symbol lock; resume also refuses an active owner.

Retained raw replay verifies SHA-256, preserves observation time and is idempotent. Tampered raw fails without publication. A real database constraint failure rolls back prices and completion together; fixing it and explicitly retrying creates a linked new run without changing old failure evidence. A→B→A source revisions preserve both immutable versions and select the latest source sighting.

The upgrade was exercised against the original task-2 SQL schema (`tests/fixtures/task-02-schema.sql`, copied from `7691716`) containing an existing price. Running the migration twice preserved its identity, price and raw provenance. Repeated migration also preserves new run-to-version sightings.

## Reproduce

```powershell
$env:PG_BIN='D:\learn\production\.tools\postgres17\pgsql\bin'
$env:UV_CACHE_DIR='D:\learn\production\.tools\uv-cache'
uv run --project backend --locked --package api backend/market_data/tests/run_integration.py
uv run --project backend --locked --package api -m unittest discover -s backend/api -p test_error_contract.py -q
```

Run `uv run --locked -m unittest test_verified_prices -v` from `backend/planner`, and `npm run test:market` from `frontend`. On this workspace, planner verification explicitly selected the existing cached Python 3.12.14 interpreter to avoid uv's Windows cross-drive managed-interpreter installation issue. Local red/green transcripts live in the untracked `.planning/2026-10-25-alex-task-03-quality-recovery/` directory.

## Limits and rollout

Run the market-data `migrate` command before running task-3 code against a task-2 database. Pipeline session advisory locks require a direct PostgreSQL connection, not transaction pooling. Run completion is per-request contiguous coverage; a global backfill/scheduling watermark is not implemented here. Crashes before a raw pointer commits may leave orphan objects, which are retained and never guessed/reused automatically.

New analysis is intentionally unavailable until task 5 wires verified immutable portfolio snapshots. `/api/analyze` returns safe JSON 503; already queued/direct Planner work fails clearly before models. This prevents legacy seeded prices from masquerading as verified data. Existing historical reports are not rewritten or revalidated.

No cloud deployment, full Linux Lambda package, Kubernetes, live S3/Aurora integration, or new end-to-end browser login was performed. These remain later delivery tasks. This verification consumed no AWS or provider API credits.
