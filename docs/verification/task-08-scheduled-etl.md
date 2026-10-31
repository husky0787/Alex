# Task 8: scheduled ETL verification

Verified on 2026-10-31, after PR #21 merged as
`72a967a9b596264213a5d320bd0face907304190` and issue #9 closed.
All five issue #10 acceptance areas passed in the isolated local Kubernetes lab.
This evidence uses **synthetic quotes**, real PostgreSQL, real Kubernetes Jobs
and the real authenticated API. It does not claim new live-provider or EKS validation.

## Runtime and artifact

- Linux/amd64; k3d 5.9.0; Kubernetes/k3s `v1.35.5+k3s1`; PostgreSQL 17.6.
- Runtime image `alex-api:53b99f9`, built using the committed API Dockerfile and
  locked dependencies. Image reference digest:
  `sha256:caa92247e8f031791da136353c310e89c9ee582de94f120593bdbb6a6742503c`.
- Acceptance harness at `392f384`; it changes only fixture/test execution, not
  the runtime image. It overrides the test container's UID/GID with the host
  signing-key owner's identity; the private key remains mode 0600.
- Dedicated cluster `alex-task07`, namespace `alex-local`, owned by this checkout's
  local runner. The lab's existing name is reused; no unrelated cluster is touched.
- Two API replicas; ETL Jobs have CPU/memory requests/limits, non-root UID 10001,
  read-only root, dropped capabilities, no service-account token, separate Secret,
  and a shared node-local raw PVC. Default installation suspends both CronJobs.

## Results

| Check | Observed result |
| --- | --- |
| Backend integration | 59 tests passed against disposable PostgreSQL, including batch/symbol contention, missing-key recovery, quality rejection, missing-session monitoring and immutable execution snapshots |
| API contracts | 13 tests passed, including authenticated status and safe database-error responses |
| Existing API smoke | Real JWT verification, cross-user authorization, persisted account/snapshot and local queue checks passed after deploying the new image |
| Publication date | At the observed time, 2026-10-31 UTC was still 2026-10-30 Eastern; the latest published trading date was correctly `2026-10-29`, not the trigger's UTC date |
| Initial coverage | 20 symbols, five published sessions each: 100 synthetic price rows |
| Deliberate missed run | Removing AAPL's interior `2026-10-28` session made the monitor Job fail and retained a `missing_session` alert, despite a fresh latest price |
| Manual recovery | The common entry in a manual backfill Job restored the missing session; health returned to true |
| Quality failure | A valid bar plus an invalid bar yielded `partial / quality_rejected`, accepted 1, rejected 1, and a failed Kubernetes Job; complete dates did not turn it into success |
| Actual CronJob controller | Accelerated schedule created `market-daily-29890303`, with a CronJob owner reference; execution `5c753c10-f041-47ad-bb9a-5c6224a0763f` succeeded |
| Concurrent manual Job | While the scheduled provider call was held open, manual execution `6156f305-4f49-4db3-af15-c0d2045b0153` returned `blocked / batch_busy` and failed without fetching |
| Retry idempotency | Retrying after the CronJob completed accepted zero new bars; price and observation counts did not increase |
| Raw persistence | 26 raw files remained on the shared volume after completed ETL Pods were deleted |
| Status API | Anonymous request returned 403; signed request returned 200 with `Cache-Control: no-store`, 20 fresh symbols, 12 executions and 5 historical alert events |
| Fixture/live boundary | Reinstalling this synthetic lab in live mode was rejected before changing deployment configuration |
| Restored schedule | Daily returned to `15 0 * * *`, `America/New_York`; monitor remained `45 * * * *`; both suspended with zero active Jobs |

The accelerated CronJob test exercises the real Kubernetes controller rather
than only creating a Job from a template. The monitor command was executed as
a real Job; its hourly schedule was installed but was not left running for an hour.
The smoke was repeated after a test-container key-permission error; the final
complete run exited 0. Missing-session events deduplicated on repeat while the
monitor continued to exit nonzero for the current gap.

## Review and regression

Standards review: no remaining actionable findings. Spec review found one P2:
resuming a shared run could change the apparent counts of an already finished
batch. Commit `53b99f9` freezes safe run summaries at batch completion. A regression
asserts the original failed execution is identical before and after the later
successful resume; both the 59-test suite and review passed after this fix.

## Evidence, cleanup and limits

Private evidence was retained under the builder checkout's
`.local/kubernetes/task07/`: `task08-evidence.json`, `task08-api.json`,
`task08-kubernetes.json`, per-Job logs, a 50,285-byte synthetic database dump and
a 3,658-byte raw-response archive. Credential-free JSON copies are also in the
Windows checkout's ignored `.local/kubernetes/task08/`. Secrets and signing keys
are not included in the repository or runtime image.

The test cluster is cleaned up after saving evidence; all 11 pre-existing builder
containers are preserved. No AWS resource was created or paid model invoked in
this task. Task 6's actual billing reconciliation remains separate and pending.

Alerts here are durable database events and JSON Job output, inspectable through
the authenticated API. They are not email/Slack delivery or external monitoring
of a completely unavailable cluster. The rolling monitor checks seven calendar
days; the existing history API/backfill supports the full 90-day window. The lab
database and raw volume are not production storage and are removed with the cluster.
Real Massive credentials, S3/Aurora access, workload IAM, EKS ingress, external
alert delivery and cloud costs remain task 9's controlled acceptance work.

Reproduction and operations: [ETL lab README](../../deploy/etl/README.md).
