# Task 6 AWS acceptance, 2026-10-31

The real research-to-report path and the controlled unavailable-research path both passed in `us-east-1`. The user explicitly resumed AWS work on this date, superseding the earlier deferral. Issue #8 remains open for actual billing reconciliation; runtime measurements and price estimates are not an AWS invoice.

## Executed checks

| Check | Result |
| --- | --- |
| SageMaker serverless embedding | 384 finite dimensions; 12.656 seconds for the initial probe |
| Reporter Linux dependencies | AWS Python 3.12 imported the rebuilt ZIP; empty event returned the expected `400 / job_id is required` |
| Researcher browser and Bedrock | One Apple Newsroom request succeeded; real Chromium navigation and snapshot preceded ingestion |
| Ingestion and retrieval | One receipt; querying `market analysis AAPL` returned the same research ID and identical source URL/UTC capture time |
| Normal Reporter | AWS returned success; Aurora read-back matched returned content, research ID, source URL/time and price snapshot SHA-256 |
| Retrieval failure | Only the isolated Reporter's endpoint setting was changed to an inaccessible test endpoint; AWS returned a saved holdings summary with `research.status=unavailable`, `reason=retrieval_failed` |
| Failure recovery | Restored the healthy endpoint configuration before the successful normal report |

The observed source was `https://www.apple.com/newsroom/`, captured at `2026-10-31T02:32:42.717478+00:00`. This validates provenance and transport, not independent factual verification of every model claim. Private receipts, returned vectors, reports and CloudWatch events are retained in `.local/research/task-06/`; full account and job identifiers are excluded from Git.

The dedicated Aurora fixture contained one AAPL share and $1,000 cash. Its price snapshot used the previously verified Massive bar for 2026-10-23, close `347.725`, with the raw response SHA-256 checked before fixture creation. It was correctly marked **stale** on the acceptance date. This was a direct isolated Reporter test; it does not establish deployment of the task 5 API/snapshot producer or the complete live Planner workflow.

The first unavailable-report invocation encountered `DatabaseResumingException` before retrieval or model execution because the existing Aurora instance had auto-paused. One retry after resume passed. The native import probe and both report paths were validated using application status and database read-back, not only Lambda's transport HTTP 200.

## Deployed artifacts and isolation

- Researcher ECR manifest: `sha256:952204f1aeb0aa9498d403ad0a3e10e5e8355cbf36c22f22869f19bf1e65c632`, matching the offline-tested Linux/amd64 Docker v2 manifest. ECR reported 608,462,127 bytes. The deployed reference used the digest. Public Function URL and scheduler were disabled.
- Reporter cloud ZIP: SHA-256 `277c02fd119381a2c6a2c3b305815563fa7d546494daf0c1ed522499c5067d3d`, 46,371,608 compressed bytes and 121,136,576 uncompressed bytes. This is a distinct locally assembled artifact, using locked, hash-checked Python 3.12 Linux binary wheels and the shared source packages. Its actual AWS import and executions passed. The earlier remote ZIP hash is not evidence for this ZIP.
- Live API and analysis-worker deployments were not changed. The new `alex-reporter-acceptance` had its own role and log group, scoped dependency permissions, no URL, and no event source.
- AWS reported account concurrency 10. The default reserved concurrency of 1 was unsuitable for this account's minimum unreserved pool, so acceptance explicitly used `reserved_concurrency=-1` with manual serial invocations. This is a shared pool, not an enforced one-invocation limit.
- Terraform private Researcher configuration passed two mocked tests; isolated Reporter configuration passed five. Follow-up Standards review found no remaining findings after the scheduler/URL conflict was rejected explicitly.

## Usage and cost boundary

| Invocation | Client elapsed | Lambda duration | Billed duration |
| --- | ---: | ---: | ---: |
| Researcher | 75.087 s | 64.038 s | 64.038 s |
| Reporter, available | 17.930 s | 9.421 s | 16.434 s |
| Reporter, unavailable after DB resume | 1.73 s | 0.984 s | 0.984 s |

The Researcher log also records an initial 10-second initialization timeout followed by successful initialization and processing. The table does not claim to include every bootstrap/probe invocation or all billable initialization time.

CloudWatch `AWS/Bedrock`, model dimension `us.amazon.nova-pro-v1:0`, reported **46,698 input tokens, 1,237 output tokens and 7 invocations**, with no client/server errors, for the queried 02:00–02:34 UTC account/region/model window. These are account-level model metrics, not request-isolated billing. At the previously recorded public rates, the token component estimates to **$0.0413**; this excludes SageMaker, Lambda, Aurora, storage, requests, logs and transfer. Actual total charges are **not yet reconciled**.

The pre-execution Free Tier API reported remaining credit **$111.81**, superseding the older $114.63 snapshot. The authorized planning scenario remains $2.18 with a $5 review threshold, not an AWS-enforced cap. Cost Explorer access was unavailable to the working IAM identity. After AWS posts the usage, reconcile the test window against Billing before marking issue #8 complete.

## Resource ownership and cleanup

Reviewed plans created 6 Terraform resources for SageMaker, 20 for ingestion, 6 for Researcher including its ECR/IAM bootstrap, and 4 for the isolated Reporter. These counts include IAM, API configuration and a Terraform wait resource; they are not counts of running servers.

Final AWS inventory confirmed all 36 Terraform-managed acceptance resources were removed and the four local Terraform states contain zero managed resources. The two auto-created Researcher/SageMaker log groups were exported and deleted after their exact creation timestamps were checked. The temporary object bucket had no objects, versions or outstanding multipart uploads before deletion. Remote ECR credentials were logged out after the completed push.

Dedicated fixture evidence was saved before removing only its test user, two jobs, one account and one position. The existing AAPL instrument was verified preserved. The six existing application Lambdas and Aurora were confirmed present after cleanup. Existing secrets and unrelated remote containers were outside the cleanup scope and were not modified. The research services are therefore **not left running**; reproduction requires deployment from the saved code/artifacts.
