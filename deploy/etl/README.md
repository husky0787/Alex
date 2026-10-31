# Local Kubernetes scheduled market data

Task 8 runs ETL alongside the task-7 API in the owned `alex-task07` k3d cluster,
namespace `alex-local`. It creates no AWS resources. Kubernetes controls when a
Job starts; `market_data.scheduled` controls dates, database locking and outcomes.
Both CronJob and manual Job call this entry, then the existing `HistoryBackfill`
and `DailyPricePipeline`. The API image includes the same locked market package.

## Dates and concurrency

- `market-daily`: `15 0 * * *`, `America/New_York`. Its date is the most recent
  XNYS session before the current Eastern calendar date, not the trigger date.
  [Massive Stocks Basic REST bars](https://massive.com/knowledge-base/article/on-the-free-basic-plan-when-can-i-pull-the-previous-trading-days-data)
  become available after midnight ET. Weekends, holidays and DST use the existing
  exchange calendar. There is no claim of live prices or flat-file timing.
- `market-monitor`: `45 * * * *`, same time zone. Independently checks every symbol
  for missing published sessions in a rolling seven-calendar-day window, including
  an interior gap with a fresh latest price, and executions running over 45 minutes.
  This gives the daily task 30 minutes after its scheduled start before the first
  check. The complete 90-day history remains available via the history API.
- Both use `Forbid`, 15-minute starting deadline, no automatic Job retries and a
  30-minute execution deadline. Jobs/logs are kept up to 24 hours (history limits
  may remove them sooner); execution/run/alert records persist in PostgreSQL.
- [CronJob concurrency policy](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/#concurrency-policy)
  only covers Jobs from that CronJob. A PostgreSQL advisory lock serializes these
  scheduled/manual batches; a competing Job records `blocked / batch_busy`, exits
  nonzero, and can be retried. The existing symbol lock and unique price-version
  key also protect against legacy CLI ingestion. Other programs using the same
  provider key are not governed by this batch lock and can still cause HTTP 429.
- Each process spaces source requests by 13 seconds. Only missing dates are
  fetched. A retry after coverage is complete skips the source. Quality rejection
  remains `partial` even when all expected dates are present.

## Reproduce the isolated acceptance

Requires Docker, k3d and uv on one host; see [the local API setup](../local/README.md).
Commands below run at the repository root. Use a unique tag for each source build.

```bash
docker build --platform linux/amd64 -f backend/api/Dockerfile -t alex-api:task08 backend
uv run --no-project deploy/local/run.py up --image alex-api:task08
uv run --no-project deploy/etl/run.py install --image alex-api:task08 --fixture
uv run --no-project deploy/etl/smoke.py --image alex-api:task08
uv run --no-project deploy/local/run.py down
```

`--fixture` injects synthetic provider responses from a ConfigMap into the real
entry point; it never sends a source request. The fixture modules and signing key
are excluded from the production image. The smoke script deliberately deletes
only synthetic AAPL observations from this isolated database, then verifies:

1. Initial weekly coverage for all 20 symbols.
2. An interior missing session creates a persisted alert and a failing monitor Job;
   a manual backfill closes the gap.
3. A complete valid response plus a rejected bar makes the Job fail with `partial`.
4. The actual CronJob controller starts an accelerated one-minute schedule. A
   simultaneous manual Job is blocked by PostgreSQL; its later retry skips data
   already published, without increasing prices or observations.
5. Raw files survive completed Pod deletion. Authenticated API status includes
   all 20 prices, execution outcomes and alert history; anonymous requests fail.

The daily schedule is restored and suspended in `finally`. Evidence lives in
`.local/kubernetes/task07/task08-evidence.json`, `task08-api.json` and Job logs.
Do not commit private configuration, signing keys, raw responses or database dumps.
The PostgreSQL fixture uses ephemeral data; deleting its Pod or the cluster loses
test data. The raw PV lasts across Job Pods but is also destroyed with the node.
This is local Kubernetes validation, not an EKS deployment or production backup.

## Use the real source in the local lab

Install the image in the existing local lab first. Supply a private JSON file,
for example `.local/etl-secrets.json`, with `MARKET_DATABASE_URL` pointing to the
same intended database used by the API and `MASSIVE_API_KEY`. Never commit it.
Use a separate clean lab after synthetic testing; do not mix synthetic prices
with real provider records. The installer migrates the chosen market schema.

```bash
uv run --no-project deploy/etl/run.py install --image alex-api:task08 --secret-file .local/etl-secrets.json
uv run --no-project deploy/etl/run.py backfill --from YYYY-MM-DD --to YYYY-MM-DD
uv run --no-project deploy/etl/run.py enable
```

Both dates are required for manual backfill, within the last 90 calendar days;
end at the latest published trading date. Optional `--symbols AAPL MSFT` selects
a subset. Fill the desired initial history before enabling schedules. Installation
leaves both CronJobs suspended until `enable`. `suspend` stops future schedules;
it does not cancel active Jobs. Reinstalling also suspends them.

The local installer provisions a static, node-local raw PV; it is not suitable
for multi-node EKS. A later cloud deployment must supply durable storage (the
entry also supports `--raw-bucket` for an existing private S3 bucket), appropriate
IAM, database connectivity and image distribution. No EKS or IAM changes here.

## Inspect failures and recovery

Use the owned node's kubectl, or an explicitly selected lab kubeconfig:

```bash
docker exec k3d-alex-task07-server-0 kubectl -n alex-local get cronjobs,jobs,pods
docker exec k3d-alex-task07-server-0 kubectl -n alex-local logs job/JOB_NAME
```

`GET /api/market-data/status` requires a valid Clerk JWT and returns `no-store`:
current health and latest dates, 20 recent batch executions with individual run
IDs/counts/timestamps/failure codes, and the last 100 alert events. It does not
return source bodies, raw locations or credentials. The API is read-only; monitoring
is a separate scheduled command. A historical alert is not a claim that its
condition is still active: consult current `health`.

Alerts are durable events in `market_alerts` and structured Job logs, not email or
Slack notifications. Missing-session events deduplicate by symbol/date; execution
failures by execution ID. A monitor Job exits nonzero while gaps remain even if
the event was already recorded. If the entire cluster or database is down, these
in-cluster components cannot provide external outage notification; a database
connection failure emits `etl_process_failed` to Job logs and exits nonzero.

For `batch_busy`, wait for the current Job, then repeat the same manual date range.
For `provider_key_required`, configure the Secret then repeat; the original market
run ID remains available and is resumed. Failed/partial runs retain quarantine
and raw evidence. For a terminated worker, the next batch resumes interrupted
symbol work; while holding the batch lock it marks abandoned batch records older
than 45 minutes as `failed / worker_interrupted`. The independent monitor detects
those overdue records even if the daily ETL never starts. Fix provider/storage
errors before retrying; use the existing `market_data inspect/resume/retry`
commands when a specific original run needs diagnosis.
