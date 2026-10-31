# Task 11 showcase acceptance window

Prepared and executed 2026-10-31. Status: **real authenticated analysis passed; cleanup independently verified at12:49:32 UTC**. See the [acceptance record](task-11-showcase.md). Final billing reconciliation is tracked independently in issue #8 and no longer blocks issue #13, as confirmed by the user.

## Boundary

Use local Next.js, the real FastAPI application, real Clerk login, and a dedicated loopback PostgreSQL market database. Use a separate `alex_task11` application database on the existing Aurora cluster with a dedicated database login and secret. Create only `alex-task11-*` workers, queues, roles and logs for the live SQS -> Planner -> Reporter/Charter/Retirement path. Tagger classification is a separate explicit preflight: the current Planner does not automatically call it.

Restore the previously cleaned SageMaker/ingestion resources from guides 2–3 after verifying their absence and reviewing creation-only plans. Re-ingest the genuinely captured, attributed Task6 research document without changing its original source or capture timestamp. Verify its research ID through live vector retrieval and the new report. This does not claim a second Researcher browser run; the original live browser-to-ingestion evidence remains in the Task6 record.

Do not replace the original six Lambda functions, modify existing user portfolios, change CloudFront/DNS or provision another EKS cluster. Task9's EKS acceptance and Task10's CI release remain separate evidence. Current API/worker source overlays use the hash-verified Linux Reporter dependency runtime; all worker imports must be tested on AWS before model calls.

## Spending and lifetime

Use the existing authorized credit-only budget. Read current billing/credit privately before apply. Plan for one successful two-position analysis and at most two diagnosed retries, plus one Tagger preflight and one unavailable-research case if needed. Keep schedulers disabled; the acceptance queue has a one-receive dead-letter policy to avoid unbounded model retries.

The incremental planning allowance is **US$5**, using the documented Task6 regional rates as a dated estimate: US$1.60 for up to one million Nova Pro input / 250,000 output tokens, US$0.32 for up to two Aurora ACU-hours at the higher recorded rate, US$0.25 combined serverless embedding/Lambda, and US$2.83 reserve for probes, storage, logs, requests and shared-service uncertainty. This is a planning allowance, not an AWS-enforced cap or an actual bill. Inspect observed invocation/token usage after each complete attempt; stop paid retries if usage exceeds the scenario or the original overall budget. Do not assume that remaining credit differences measure this task's cost.

Target a four-hour active window, with operator-owned cleanup in the same session. Preserve private raw data, build hashes, application results and CloudWatch logs before deletion. Destroy only the new Terraform states' resources; delete the dedicated database/login only after checking the ownership marker and confirming the original database still exists. Schedule recovery deletion for the new database secret. Stop only the task-owned local database/processes. Retain no public always-on showcase environment.

## Evidence required before declaring success

- Real Clerk-authenticated API requests from the normal browser, and unauthorized requests rejected.
- User-visible holdings, dated latest prices/history and one saved analysis using the identical frozen price basis.
- Persisted report, charts and retirement output, with attributed research ID, original URL and capture time in the report.
- A short, privacy-reviewed demonstration. Native Brave capture was unavailable; the delivered video explicitly presents checked results and does not claim to be a browser recording. Actual UI visibility was confirmed by the user and matching API requests.
- Explicit source/data/storage/runtime inventory, cleanup verification and limitations. Earlier synthetic or isolated tests must remain labelled as such.
