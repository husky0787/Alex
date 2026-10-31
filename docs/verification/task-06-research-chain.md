# Task 6: research-chain verification

Status: PR #19 merged on 2026-10-30; local implementation and real-container checks pass. The user explicitly resumed AWS acceptance on 2026-10-31, superseding the earlier deferral. **Both cloud research-to-report and unavailable-research checks passed; actual billing reconciliation remains pending.** See [AWS execution evidence](task-06-aws-acceptance.md). Issue #8 remains open. Container/build follow-up is preserved in [draft PR #20](https://github.com/husky0787/Alex/pull/20).

## Budget evidence, 2026-10-27

- AWS Free Tier API and user console: estimated remaining credit **US$114.63**.
- User console: two credits, issued US$100 and US$20, both expire **2026-11-30**.
- User console: October month-to-date **US$2.41**, forecast **US$2.90**; September total **US$1.75**. Do not subtract October cost again from estimated remaining credit.
- Both user-supplied eligible product lists include SageMaker, Bedrock, S3, Lambda, API Gateway, ECR and CloudWatch. They also list CodeBuild, but service eligibility does not grant IAM permission.
- Extra cash spend remains unauthorized. The 2026-10-30 public regional price lists now support the proposed $2.18 acceptance scenario in task-06-cloud-window.md; refresh account billing and review actual plans before paid execution.

## Read-only resource inventory

Checked `us-east-1` and `us-west-2`: no Alex SageMaker endpoints, no vector buckets and no ECR repositories. The east-region Lambda inventory contains existing API and analysis workers, but no ingestion or Researcher function. Ordinary S3 buckets are distinct from S3 vector buckets. Private account identifiers and full inventory are kept locally, not committed.

At this initial inventory, the IAM identity could not query Cost Explorer or list CodeBuild projects. The Windows workstation had no Docker/Podman/WSL. On 2026-10-29 a user-provided Linux builder became available through Tailscale SSH. No new paid AWS resources or model invocations were created during that initial phase; the subsequent AWS window is recorded separately below.

## Local behavior

- A known research ID survives repeated ingestion and query with its source URLs, UTC capture times and text.
- Researcher cannot report success after skipping ingestion, a rejected write, a malformed receipt or an unvisited source URL.
- Reporter retrieves before model execution, preserves evidence even if the model skips its optional tool, and records unavailable research explicitly. Failed/empty retrieval produces a deterministic holdings summary without model-generated research claims.
- SageMaker flat, single-batch and token-level feature-extraction output shapes use the same adapter for ingestion and query; malformed dimensions and nonnumeric values fail explicitly.

Verified locally: 50 PostgreSQL/pipeline integration tests, 4 ingestion/search tests, 2 Researcher receipt tests (including four failure scenarios), 14 worker tests across Planner/Reporter/Charter/Retirement, and 11 API contract tests passed (81 total). Terraform 3 initialization and validation passed; the Linux ingestion zip built successfully. These local tests substitute external transports and are not cloud end-to-end evidence.

## Remote build verification, 2026-10-29

Linux/amd64 Docker 29.1.3 and Buildx 0.30.1 are available. The isolated checkout contains no copied AWS credentials. Registry proxy configuration and public DNS were needed before downloads could start; the existing seven containers recovered after the authorized Docker restarts.

Commit `33174d1` adds optional Reporter proxy forwarding/host networking, optional Researcher Debian mirror selection, and an offline real Chromium/MCP fixture smoke. Both review axes found zero actionable issues. Packaging CLI help and two Researcher receipt tests passed. The two tests are reruns of the existing 81-test suite, not additional cases.

### Completed container checks, 2026-10-30

- Reporter: 45,849,911-byte ZIP, 120,155,017 bytes uncompressed; SHA256 `e3b8ca61ef41e9a3af5cb7c6e23213141beb0d2071e1e6a659db2aa48542426d`. Importing `lambda_handler`, shared research/database code and native dependencies passed in the AWS Lambda Python 3.12 image with external networking disabled. Five Reporter worker tests were rerun and passed (part of the existing 81, not five additional tests).
- Researcher: Linux/amd64 image manifest `sha256:952204f1aeb0aa9498d403ad0a3e10e5e8355cbf36c22f22869f19bf1e65c632`, media type `application/vnd.docker.distribution.manifest.v2+json`. Builds use `--provenance=false` for Lambda compatibility. Docker reports 608,465,197 bytes for this image; ECR billed storage has not been measured.
- Real browser smoke passed with `--network none --read-only --user 10001:10001` and writable `/tmp`: HTTP app health, Chromium navigation, `browser_snapshot` text, observed source URL and UTC timestamp. Output: `{"health":"passed","chromium_mcp":"passed","source_capture":"passed","aws_calls":0}`.
- A separate container using the image's default Uvicorn command returned HTTP 200 and `status=healthy` at `/health`. It reported `alex_api_configured=false`, as expected without cloud configuration. The temporary container was stopped afterward.
- The initial smoke incorrectly expected page text directly from navigation. Installed MCP 0.0.75 returns a snapshot file link there; explicit `browser_snapshot` returns the text, matching the existing Researcher prompt. The test now exercises both tools; no application-side fallback or output rewriting was added.
- At completion of the offline phase, both artifacts remained on the user's Linux builder without AWS upload. The remote checkout has the committed source changes over its original base; its directory name alone does not identify the built revision.
- Packaging and optional bootstrap-index changes passed Standards and Spec review with zero findings. Follow-up review of the final smoke/deployment-flag changes also found zero Standards and zero Spec findings.

The bounded cloud scenario and acceptance steps are in [task-06-cloud-window.md](task-06-cloud-window.md). These container results do not prove cloud IAM, Bedrock inference, Lambda Web Adapter invocation or the full cloud research-to-report path.

## Cloud acceptance procedure

The following procedure was executed on 2026-10-31 using an isolated Reporter. See the dated [results and remaining billing step](task-06-aws-acceptance.md); this checklist preserves the reproduction procedure, not a claim that every step is still pending.

1. Container builds and offline browser checks are complete. Preserve the recorded artifacts, transfer/push them securely and verify their digests before deployment. The Docker build context is `backend`, not `backend/researcher`.
2. Complete the bounded estimate for SageMaker 3072 MB serverless, one Researcher run, ingestion/search, Reporter model, ECR image storage and logs. Keep the scheduler disabled, provisioned concurrency off and a limited test window. Include existing account spend; a planning allowance is not an AWS hard spend cap.
3. Inspect/import pre-existing IAM/API/S3 resources before applying reviewed Guide 2–4 Terraform plans. Create only missing acceptance resources. Existing private Terraform state is absent from this checkout.
4. Coordinate the task 5 snapshot producer/worker rollout, or use an isolated Reporter acceptance function and dedicated job containing a verified price snapshot. Do not replace the live Reporter while its API still produces legacy jobs.
5. Invoke a known topic through Researcher, retain the receipt, retrieve the same research ID, then run Reporter and read back the saved report. Record job/research IDs, source URLs/times and deployed revision in private evidence; publish a redacted result. Inject a controlled retrieval failure and confirm the saved report is explicit about unavailable research.
6. Record exact resource names, invocation durations and model tokens. Reconcile the test window against Billing after its reporting delay; until then label costs estimates, not actual charges. Clean up only resources explicitly created for this acceptance window.

Sources: [S3 vector limits](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-limitations.html), [Terraform vector index](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3vectors_index), [MiniLM model usage](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2), [SageMaker pricing](https://aws.amazon.com/sagemaker/ai/pricing/), [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/), [Lambda pricing](https://aws.amazon.com/lambda/pricing/), [ECR pricing](https://aws.amazon.com/ecr/pricing/).

## Review

Reviewed commits `55b107c` and `153071a` against merged task 5 baseline `70b3201a7f3135feb277ac6b891787c1dbfc4e76`. Standards found one Docker context allowlist issue; the parent-directory exceptions are now followed by descendant exclusions before exact file exceptions. Follow-up Standards: 0 remaining; Spec: 0 remaining. These reviews did not run Docker or paid cloud tests. Ingestion/search smoke CLI help was checked without network calls; the Researcher live smoke was not run.
