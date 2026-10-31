# Task 6 cloud acceptance window

Prepared 2026-10-30. **Plan only: no resources restored and no paid inference executed.** The earlier user decision deferred cloud acceptance. PR #19 merged the local implementation; issue #8 remains open until the cloud evidence and billing reconciliation exist.

## Scope and acceptance

Use `us-east-1` and explicitly configure both agents for the standard on-demand `us.amazon.nova-pro-v1:0` inference profile (Researcher prefixes it with `bedrock/`). Do not use the repository's different default models for this estimate. The Bedrock read-only API reports `amazon.nova-pro-v1:0` as ACTIVE and supporting inference profiles; account/profile access must still be checked before inference.

1. Inspect existing names and local state before planning Guide 2–4 Terraform. Import matching resources rather than creating duplicates. Review plans for replacement/deletion and record exactly which resources this window owns.
2. Restore the 3072 MB SageMaker serverless embedding endpoint without provisioned concurrency; create the ingestion function/API, vector bucket/index, ECR image and Researcher Lambda. Keep the scheduler disabled. Use the built image digest, not a mutable tag, for the deployed revision record.
3. Deploy a separate Reporter acceptance function. Keep the live API and analysis workers unchanged: the current API may still create legacy jobs without task 5 snapshots. Use a dedicated job with a real verified price snapshot and record its provenance.
4. Submit one known topic to Researcher, save its receipt, retrieve the same research ID, then invoke the isolated Reporter. Read the saved report back from Aurora and verify the source URL, UTC capture time and research ID survived. A local mock result cannot satisfy this step.
5. Inject an unavailable retrieval configuration only into the acceptance function and verify the saved report explicitly records unavailable research. Restore its configuration and record both outcomes. Bound retries to three complete attempts; inspect the failure and usage before another attempt.
6. Record names, image digest, ZIP hash, invocation durations, model input/output tokens and the time window privately. Publish redacted results. Clean up only resources created for this window; preserve pre-existing IAM/API/database resources and data.
7. Reconcile charges after Billing has reported the window. Estimates and remaining credits are not actual test charges. Keep issue #8 open until this evidence is recorded.

## Cost estimate

All USD; conservative gross usage estimate before credits/free-tier benefits. This is a planning scenario, **not an enforced AWS spending cap**. Re-estimate if the actual model, region, volume or retention changes. Provisioned throughput, provisioned concurrency, scheduled runs, EKS and new databases are excluded from this window.

| Component | Planned usage / allowance | Estimated cost |
| --- | --- | --- |
| Nova Pro, both agents combined across attempts | 500,000 input tokens at $0.0008/1K; 50,000 output at $0.0032/1K | $0.56 |
| SageMaker serverless, 3 GB | 1,200 billable seconds at $0.00006/s | $0.072 |
| Lambda, x86 | 3,900 GB-seconds at $0.0000166667/GB-s | $0.065 |
| Existing Aurora wake-up | At most 1 ACU for 2 hours, using higher IO-Optimized $0.16/ACU-hour as allowance | $0.32 |
| ECR | Up to 2 GB for 1 day at $0.10/GB-month, using 30 days | $0.0067 |
| CloudWatch log ingestion | 0.1 GB at $0.50/GB | $0.05 |
| REST API Gateway | 1,000 requests at $3.50/million | $0.0035 |
| Small vector/object storage, query/PUT requests, data transfer, Lambda requests, log retention and database I/O/API calls | Combined planning reserve; confirm actual volumes before deployment | $1.00 |
| **Scenario total** | Rounded up | **$2.18** |

Use **$5 as the proposed review threshold** for this window, leaving margin above the scenario. Check token usage and resource duration after each attempt; do not interpret the threshold as a billing alarm or automatic shutdown. Existing account costs continue separately. The last user-provided billing snapshot was October month-to-date $2.41, forecast $2.90 and estimated credit $114.63, with expiry 2026-11-30; refresh that snapshot before paid execution rather than treating it as current.

The read-only 2026-10-30 inventory confirms `alex-aurora-cluster` is available, has Data API enabled, scales from 0 to 1 ACU and auto-pauses after 300 seconds. This does not establish its actual billable duration or other account costs.

## Price evidence

Official public regional price lists queried on 2026-10-30 (the authenticated Pricing API was denied; the public lists require no account permission):

- [SageMaker, us-east-1](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonSageMaker/current/us-east-1/index.json): `USE1-ServerlessInf:Mem-3GB`, SKU `PUE6HBQ8KFHBUN5T`.
- [Bedrock, us-east-1](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonBedrock/current/us-east-1/index.json): `USE1-NovaPro-input-tokens` and `USE1-NovaPro-output-tokens`; exclude custom, latency-optimized and provisioned products.
- [Lambda, us-east-1](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AWSLambda/current/us-east-1/index.json): first-tier `Lambda-GB-Second`.
- [RDS, us-east-1](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonRDS/current/us-east-1/index.json): Aurora PostgreSQL Serverless v2 is $0.12/ACU-hour standard or $0.16 IO-Optimized.
- [ECR, us-east-1](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonECR/current/us-east-1/index.json): `TimedStorage-ByteHrs`.
- [CloudWatch, us-east-1](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonCloudWatch/current/us-east-1/index.json): `DataProcessing-Bytes`.
- [API Gateway, us-east-1](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonApiGateway/current/us-east-1/index.json): first-tier `USE1-ApiGatewayRequest`.
- [S3 pricing](https://aws.amazon.com/s3/pricing/): the N. Virginia vector example lists $0.06/GB-month storage, $0.20/GB PUT and $2.50/million query requests, plus query processing. The small acceptance dataset is covered by the reserve above; it is not assumed free.

## Deployment preflight, 2026-10-30

Private saved Terraform plans were generated without applying them:

| Directory | Creates | Updates | Deletes | Scope |
| --- | ---: | ---: | ---: | --- |
| `terraform/2_sagemaker` | 6 | 0 | 0 | Role/attachment, model, endpoint configuration, propagation wait and endpoint |
| `terraform/3_ingestion` | 20 | 0 | 0 | Ordinary/vector storage, index, ingestion Lambda/IAM, logs and REST API/key/usage plan |
| `terraform/4_researcher` | 5 | 0 | 0 | ECR/repository policy and Researcher role/policies only |

Live read-only checks found no SageMaker endpoint, S3 vector bucket, REST API or matching research IAM roles in the selected account/region. The ordinary bucket targeted by Guide 3 returned 404. Plan files are private under `.local/`; do not publish them or Terraform state.

The Researcher bootstrap plan intentionally leaves image URI/API endpoint/API key empty, so no Researcher function or scheduler is created at this stage. After ingestion and ECR exist, generate and review a second plan with their real outputs and the tested image digest. The isolated Reporter acceptance function is not part of these three saved plans. Its separate configuration is now prepared in `terraform/6_research_acceptance`, with a dedicated role, exact resource permissions and four passing mocked Terraform tests. A real plan still requires the verified ZIP and actual dependency ARNs. These plans are preparation, not evidence of a deployed or fully accepted system.
