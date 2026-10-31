# Task 9 EKS acceptance

Executed on 2026-10-31 in `us-east-1`, using an isolated `alex-task09` environment. The original API and `alex` database were not switched or migrated. Reproduction: [EKS runbook](../../deploy/eks/README.md); preflight and complete allocation: [cloud window](task-09-cloud-window.md).

## Observed results

| Check | Actual result |
| --- | --- |
| Infrastructure | Reviewed plan and apply: 67 new Terraform resources, zero changes to existing resources; EKS 1.35 control plane and two 1.35.9 managed nodes |
| Workload identity | Real API and ETL Pods assumed separate roles; each could read its own secret and was denied the other workload's secret and the Aurora admin secret |
| Storage authorization | API S3 writes denied; ETL writes outside raw/quarantine prefixes denied; all 22 archived S3 objects used AES256 encryption |
| Real market backfill | 20 symbols × 64 trading dates = **1,280 verified prices**, 2026-08-03–2026-10-30; zero missing/rejected bars; execution 09:18:08–09:22:16 UTC |
| Daily/manual scheduling | Both a manual daily Job and an actual controller-created CronJob succeeded; current prices and immutable observations remained **1,280 / 1,280**, proving repeat idempotency |
| Quarantine | A separate labelled malformed response produced one quarantine manifest and zero accepted bars; verified-price count remained unchanged |
| HTTPS and ownership | Health/readiness succeeded; malformed, expired and forged JWTs returned JSON 403; unknown API route returned JSON 404; another user's account and job access was denied |
| SQS report | API created the price snapshot and enqueued its job; isolated Lambda Reporter stored a report with the same snapshot SHA256 and explicit research-unavailable status; two test reports completed including one manual retry |
| HPA | Real metrics were available; a bounded CPU load scaled API replicas **2 → 3** during 09:19:30–09:21:03 UTC |
| Pod recovery | Deleted API Pod was replaced and ready during 09:26:00–09:26:17 UTC |
| Rollback | Invalid image produced `ErrImagePull`; rollout undo restored the original digest and readiness during 09:26:19–09:26:32 UTC |
| ETL alert | Real secret-access denial caused a failed Job; SNS delivered its safe error event to SQS at 09:28:17 UTC |
| ALB alert | Actual zero-healthy-target metrics at 09:30/09:31 triggered ALARM at 09:34:38 UTC; notification arrived in the task SQS receiver. Recovery observation is recorded separately below. |

The source data was fetched using the user's configured Massive key. Daily repeats reused the already verified latest date; they did not invent another trading day or force duplicate source records. The deliberately invalid quarantine probe is labelled and is not evidence of a provider quality incident.

## Failures found and fixed

- Initial Aurora connection establishment timed out before SQL writes. A same-network read-only probe then passed TCP in 0.006 seconds and verified-TLS `SELECT 1` in 0.059 seconds. Auto-resume is plausible but not established by the empty RDS event response. Bootstrap now retries only connection establishment, never database/role creation, and preserves AWS error codes, SQLSTATE and stage. Invalid-password errors are not retried. The subsequent actual bootstrap succeeded and removed its temporary admin ServiceAccount/Job/ConfigMap.
- The new SQS adapter initially expected JSON while `/api/analyze` sends a plain UUID. A regression test first failed on the real wire format, then passed after the adapter was corrected. A reviewed update changed only the task-owned Lambda. The original failed test job was explicitly requeued; a fresh HTTPS → SQS → Reporter test also passed. This is not evidence of automatic redrive after the queue's 30-minute visibility timeout.
- The first ALB observation timed out after 240 seconds and restored the API automatically. CloudWatch later evaluated the real zero-host datapoints and delivered the alarm; two configured 60-second periods did not imply a two-minute delivery guarantee. The runbook now allows a bounded 600-second observation window without weakening the alarm threshold. [AWS alarm evaluation guidance](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/alarm-evaluation.html).

## Artifact and verification boundaries

API ECR manifest digest: `sha256:a83a82196f8d61f9552c9bf1ee79671ee5311868f9e5a34a55a0576aad8ae023`; ECR size 100,287,866 bytes. The deployed manifest references that digest. Offline runtime imports passed with explicit fake credentials and networking disabled; no real AWS credentials entered the image or remote build context. The remote ECR session was logged out after push.

Final Reporter ZIP SHA256: `dc7664437bb56f1d9c32a7723dd3ca7562c90f1baceb37d3ffff91e4213a5448`, assembled from the verified Task 6 Linux ZIP plus the corrected SQS adapter. This worker validates the honest unavailable-research holdings path. It does **not** establish a complete five-agent Planner orchestration or another paid research/model execution.

Authentication uses a local acceptance signer whose private key never enters the cluster; only public JWKS is deployed. This validates JWT/ownership behavior through the AWS HTTPS entry, not a real Clerk browser login. CloudFront viewer traffic is HTTPS, the internal ALB hop is private HTTP, and PostgreSQL uses verified TLS. No claim is made that every hop uses TLS.

Final local checks passed: **62 PostgreSQL integration tests, 13 API contracts, 11 cloud-helper tests and 3 Terraform boundary tests**. These supplement the live tests above. Private raw responses, complete job payloads, Kubernetes snapshots and service logs remain in ignored `.local/eks/task09/`.

## Recovery, cleanup and cost

Final alarm recovery and cleanup are still being observed; do not interpret this draft section as completion. Cleanup is limited to the separately marked acceptance database/roles and the 67-resource task state after evidence is archived. The preflight credit was US$111.67 and the conservative complete scenario allocation was US$20. Actual AWS billing has not yet been reconciled; the US$20 estimate is not the measured charge or a hard spending cap.
