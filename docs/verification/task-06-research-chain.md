# Task 6: research-chain verification

Status: local implementation ready for review; **cloud acceptance is not complete**. On 2026-10-27 the user explicitly chose to retain local work and defer cloud acceptance. Issue #8 must remain open.

## Budget evidence, 2026-10-27

- AWS Free Tier API and user console: estimated remaining credit **US$114.63**.
- User console: two credits, issued US$100 and US$20, both expire **2026-11-30**.
- User console: October month-to-date **US$2.41**, forecast **US$2.90**; September total **US$1.75**. Do not subtract October cost again from estimated remaining credit.
- Both user-supplied eligible product lists include SageMaker, Bedrock, S3, Lambda, API Gateway, ECR and CloudWatch. They also list CodeBuild, but service eligibility does not grant IAM permission.
- Extra cash spend remains unauthorized. A complete region/model-specific restoration estimate is still required before paid deployment; current pricing pages did not expose all region-specific rates in their static tables.

## Read-only resource inventory

Checked `us-east-1` and `us-west-2`: no Alex SageMaker endpoints, no vector buckets and no ECR repositories. The east-region Lambda inventory contains existing API and analysis workers, but no ingestion or Researcher function. Ordinary S3 buckets are distinct from S3 vector buckets. Private account identifiers and full inventory are kept locally, not committed.

The current IAM identity cannot query Cost Explorer or list CodeBuild projects. Docker/Podman are absent and WSL is not installed, so the Researcher image cannot currently be built here. No new paid AWS resources or model invocations were created during this work.

## Local behavior

- A known research ID survives repeated ingestion and query with its source URLs, UTC capture times and text.
- Researcher cannot report success after skipping ingestion, a rejected write, a malformed receipt or an unvisited source URL.
- Reporter retrieves before model execution, preserves evidence even if the model skips its optional tool, and records unavailable research explicitly. Failed/empty retrieval produces a deterministic holdings summary without model-generated research claims.
- SageMaker flat, single-batch and token-level feature-extraction output shapes use the same adapter for ingestion and query; malformed dimensions and nonnumeric values fail explicitly.

Verified locally: 50 PostgreSQL/pipeline integration tests, 4 ingestion/search tests, 2 Researcher receipt tests (including four failure scenarios), and 14 worker tests across Planner/Reporter/Charter/Retirement passed. Terraform 3 initialization and validation passed; the Linux ingestion zip built successfully. The Researcher image and Reporter Docker package are not built because Docker is unavailable. These local tests substitute external transports and are not cloud end-to-end evidence.

## Cloud acceptance still required

1. Provide a working Linux container builder (Docker Desktop/Linux Docker), build the Researcher image and Reporter package, and verify the image's browser/MCP behavior. The Docker build context is `backend`, not `backend/researcher`.
2. Complete the bounded estimate for SageMaker 3072 MB serverless, one Researcher run, ingestion/search, Reporter model, ECR image storage and logs. Keep the scheduler disabled, provisioned concurrency off and a limited test window. Include existing account spend; a planning allowance is not an AWS hard spend cap.
3. Inspect/import pre-existing IAM/API/S3 resources before applying reviewed Guide 2–4 Terraform plans. Create only missing acceptance resources. Existing private Terraform state is absent from this checkout.
4. Coordinate the task 5 snapshot producer/worker rollout, or use an isolated Reporter acceptance function and dedicated job containing a verified price snapshot. Do not replace the live Reporter while its API still produces legacy jobs.
5. Invoke a known topic through Researcher, retain the receipt, retrieve the same research ID, then run Reporter and read back the saved report. Record job/research IDs, source URLs/times and deployed revision in private evidence; publish a redacted result. Inject a controlled retrieval failure and confirm the saved report is explicit about unavailable research.
6. Record exact resource names, invocation durations and model tokens. Reconcile the test window against Billing after its reporting delay; until then label costs estimates, not actual charges. Clean up only resources explicitly created for this acceptance window.

Sources: [S3 vector limits](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-limitations.html), [Terraform vector index](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3vectors_index), [MiniLM model usage](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2), [SageMaker pricing](https://aws.amazon.com/sagemaker/ai/pricing/), [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/), [Lambda pricing](https://aws.amazon.com/lambda/pricing/), [ECR pricing](https://aws.amazon.com/ecr/pricing/).

