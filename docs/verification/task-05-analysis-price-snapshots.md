# Task 5: verified prices in analysis reports

Implemented on `feat/task-05-analysis-price-provenance` from task-4 merge `75f301cd94131e920f4debc2b3d9ef0a5d8b3ffe`, locally verified on 2026-10-27. GitHub issue #7 defines acceptance. No deployment or paid model/provider call was performed.

## Behavior and evidence

- Authenticated analysis freezes the owner's holdings, cash, preferences and verified daily prices before creating/queueing a job. Request options cannot supply a different owner or price snapshot. Legacy instrument prices do not enter the snapshot.
- Missing/unsupported required holdings return 422 with affected symbols, without a job or SQS message. Stale prices remain usable with actual dates and the expected published date.
- Source revision from 105 to 108 changes the market projection while the saved job still reads 105 and its original observation ID/digest. Agents read only the persisted job snapshot, not mutable accounts or instrument prices.
- Planner, Reporter, Charter and Retirement all reject absent, null, altered or wrong-owner snapshots before the model boundary. Event-supplied portfolios cannot override saved data. Report and retirement output include deterministic price-basis text and the snapshot digest; the report UI displays dates, exact prices and stale warnings across tabs.
- A known queue send failure marks the inserted job failed and returns 503. Existing owner checks prevent another user from reading snapshot-containing jobs.

Validation: **50 PostgreSQL/pipeline/API integration tests**, **11 API contract tests**, **12 worker contract tests** (3 per agent), the existing direct/queued Planner legacy-guard regression, **2 analysis UI tests** and **8 market UI regressions** passed. Next.js production build, TypeScript/lint and static export passed; the pre-existing unused `Link` warning remains.

## Reproduce

Set `PG_BIN` to local PostgreSQL binaries and install the locked environments. From the repository root:

```text
uv run --project backend --locked --package api backend/market_data/tests/run_integration.py
uv run --project backend --locked --package api -m unittest discover -s backend/api -p test_error_contract.py -q
```

Set `SNAPSHOT_AGENT` to each of `planner`, `reporter`, `charter`, `retirement`, then run:

```text
uv run --project backend/planner --locked backend/tests/test_snapshot_workers.py
```

The shared worker tests use the Planner's installed agent SDK/LiteLLM environment to run each real agent handler, agent construction and database adapter. Only AWS transport and the paid SDK runner boundary are substituted; this proves snapshot routing and persisted output behavior, not real model tool selection or generated narrative quality. Run `uv run --locked -m unittest test_verified_prices -v` from `backend/planner` for old queued/direct work.

From `frontend`, run `npm run test:analysis`, `npm run test:market` and `npm run build`. The local build disabled Next telemetry and used the documented nonfunctional Clerk test public key; do not deploy that test build.

## Limits and rollout

Snapshot values are copied once into the existing job request JSON with immutable price-version references; report updates do not rewrite that input. This is application-level immutability, not a database privilege boundary against operators. The digest detects accidental mutation. Market prices share a repeatable-read transaction, while holdings are copied from the records read through the Data API; there is no cross-database transaction.

PostgreSQL price ingestion/querying is real in tests. RDS Data API job persistence/decoding, SQS, JWKS and paid model calls use external service substitutes. Full browser login, live S3/Aurora, real LLM/research behavior, Lambda packaging and cloud/Kubernetes deployment remain unverified. Existing account/dashboard displays are not converted to verified-price displays by this task. A later release must deploy API and all four updated agent packages together. No schema change or credentials are included.
