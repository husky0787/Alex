# Task11: real authenticated showcase

Executed2026-10-31. Billing reconciliation is independently tracked in issue#8 and does not block this task by user decision. This record distinguishes backend read-back, user-confirmed UI, offline regression tests and older cloud drills.

## Real application result

| Check | Observed result |
| --- | --- |
| Login | Ordinary Brave using real Clerk; `/api/user`, accounts, jobs and market endpoints returned200. No copied token or test signer was used. |
| Portfolio | Clearly labelled fictional account:1 AAPL,2 MSFT,USD1,000 cash in a dedicated database. The original account/holdings were not modified. |
| Real market backfill |20 symbols ×64 expected sessions =1,280 verified bars. Window2026-08-03 through2026-10-30; no invented weekend bar. |
| User-visible prices/history | User pasted the Market Data result: Massive AAPL close344.63, date2026-10-30, Fresh,64/64 history. User confirmed report, charts and retirement output were visible. |
| Classification | One explicit live Tagger preflight persisted asset-class, sector and region allocations. This was not an automatic Planner step. |
| Analysis | User clicked Start New Analysis once. Job created12:13:33.364689 UTC and completed12:14:10.560097 UTC: **37.195 seconds**, one observation rather than a latency benchmark. |
| Price consistency | Reporter/Retirement payload hashes match the stored snapshot. Charter has no top-level digest field; its actual stored holding values matched1×344.63 and2×521.91 exactly. |
| Research | Live ingestion → SageMaker embedding → S3 Vectors retrieval → Reporter preserved the genuine Task6 research ID, source URL and original capture time2026-10-31T02:32:42.717478+00:00. Task11 did not rerun Researcher's browser. |
| Artifacts | All five deployed ZIP hashes matched the built manifests, and native imports/empty-event probes passed on actual Lambda before paid agent calls. |

The browser was authenticated by the user. Native Brave capture returned black; the fallback refused capture while another application held focus. No screenshot/video is presented as proof of independently captured UI. The [short video](../showcase/walkthrough.mp4) is an explicit evidence walkthrough; browser visibility is the user's confirmation plus the pasted Market Data content and matching authenticated API results.

## Transient Dashboard403

At12:10:02 UTC the local API recorded two `/api/user`403 responses; later analysis and market requests succeeded. The user reported that the Dashboard message had disappeared. The retained request ledger intentionally omits tokens; it cannot establish whether the rejected credential was expired, malformed or from an authentication transition. Missing/invalid/expired credentials map to403 in the installed Clerk guard.

Three deterministic tests against the actual Dashboard component reproduced early synchronization before Clerk was ready, a403 message surviving a successful new session, and an obsolete request's late403 overwriting a successful session. Before the fix all three failed. The page now gates synchronization on loaded/signed-in status, clears previous errors when a new sync starts, and cancels/ignores the old request chain when the session changes or page unmounts. All three pass; genuine rejection remains an error. This fixes verified lifecycle defects without claiming the historical403's exact token cause.

At12:31:12–12:31:15 UTC real Dashboard profile, accounts, positions and job requests returned200. These successful requests are a limited real read-through, not proof of deliberately reproduced Clerk expiry. Frontend lint/type checks passed with one pre-existing unused-import warning in ErrorBoundary.

## Reproduction and evidence collection

Use the [showcase runbook](../../deploy/showcase/README.md). Final local checks passed: **12 showcase helper tests, 3 standalone Terraform mock tests, 14 API contract tests and 13 frontend tests**, plus lint/type checks. Helper tests cover runtime hash/source integrity, required persisted outputs, failure-reason preservation, malformed work IDs and cleanup ownership/resumption. Terraform tests use committed empty ZIP fixtures and fake inputs, without private variables or AWS resources.

The two-axis review found one Standards issue (overwriting original failure reasons) and two Spec issues (dotenv isolation and nonportable Terraform tests). All were fixed and independently re-reviewed with zero remaining findings. API/database loaders now explicitly honor the no-dotenv flag, the launcher checks all effective isolation settings, and a fresh-process import test verifies the behavior. These final safety refinements passed offline regressions after the live analysis; they are not claimed as another cloud/model run.

Private storage retains original market responses, a market database dump, application table exports, deployment hashes, API route/status timestamps and seven named CloudWatch log groups (**1,592 events**, archived through12:33:27 UTC). Model usage is recorded as account/model-window observations; it may include concurrent work and is not a task invoice. The first archive attempt failed with AWS CLI exit255; rerunning with explicit UTF-8 succeeded. No destructive cleanup ran before a matching archive receipt existed.

For quarantine, missing-day backfill, repeat safety, notifications and rollback, see the [evidence map](../showcase/README.md). Those results retain their original Task3/4/8/9/10 scope, including injected inputs and independent environments. They were not all rerun within this one37-second analysis.

## Cleanup, cost and retention

Reviewed destroy plans matched the original creation addresses and current state identities: **23 worker +20 ingestion +6 embedding resources**, all removed. The independent audit at **12:49:32 UTC /20:49:32 Asia/Taipei** verified all three Terraform states empty, no task workers/queues/vector bucket/embedding endpoint, and no owned worker/SageMaker log groups. The automatically created SageMaker log group was deleted only after its exact name, creation timestamp and private archive were checked.

The dedicated `alex_task11` database/login were removed after archiving; the original `alex` database remains. All six original Lambda code hashes and modification timestamps match the baseline. The dedicated secret is scheduled for deletion with a **seven-day recovery window**, not forcibly purged. The owned local PostgreSQL, API and Next.js processes have been stopped; the user's normal Brave session was left alone. The demo URLs are no longer serving this acceptance environment. See [machine-readable cleanup summary](task-11-cleanup-summary.json).

The approved incremental planning allowance wasUS$5 with a four-hour window, not a service-enforced cap or a measured charge. Final billing remains unreconciled; account-level totals and credit balances are intentionally not reproduced here. Shared-service attribution and reporting lag limit exact task costing.

Public source, summaries and the evidence walkthrough are retained in Git. Private raw data, dumps and detailed logs remain in ignored local storage and need secure handoff if moving computers. The showcase is intentionally not an always-on public endpoint. The original application and separately retained Task10 delivery configuration are outside this cleanup scope.
