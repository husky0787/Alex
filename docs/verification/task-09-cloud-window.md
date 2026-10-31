# Task 9 bounded EKS window

Pre-deployment review, 2026-10-31. This is an estimate and execution boundary, not proof of deployment or actual charges.

## Billing baseline

The user supplied the Billing screenshot and completed temporary AWS CLI browser authentication. Cost Explorer excluding Credit/Refund reports estimated October gross usage **US$5.3664170124**, matching the screenshot's **US$5.37**; Free Tier reports **US$111.67** remaining credit. Previously supplied credit terms expire **2026-11-30** and include EKS, EC2, RDS, S3, Lambda, CloudFront and the other services below. Account status is PAID; the credit is not a spending cap. No extra cash spending is authorized.

The gross baseline includes EC2 Other 3.1925, EC2 Compute 1.2180, VPC 0.4380, Secrets Manager 0.3861, RDS 0.1219 and S3 0.0100 USD. It does not settle Task 6's separate per-window billing reconciliation.

## Eight-hour scenario

Region `us-east-1`; two fixed `t3.medium` workers, Kubernetes 1.35 standard support, one internal ALB, CloudFront VPC origin. No NAT Gateway, new Aurora cluster, paid model inference or SageMaker endpoint. T3 uses standard CPU credits. HPA changes API replicas only, not EC2 count.

| Item | Assumption | USD allowance |
| --- | --- | ---: |
| EKS control plane | 8 h × 0.10 | 0.80 |
| Two EC2 workers | 16 instance-h × 0.0416, verified Pricing API | 0.67 |
| Internal ALB + LCU | 8 h × (0.0225 + 0.008), assuming <=1 LCU | 0.25 |
| Node public IPv4 | Two addresses × 8 h × 0.005 | 0.08 |
| EBS | 40 GB gp3 at 0.08/GB-month, 8/720 month | 0.04 |
| Existing Aurora active time | Conservative 1 ACU × 8 h × 0.16; existing maximum 1 ACU | 1.28 |
| Storage, requests, logs and network | S3/ECR, Secrets Manager, Lambda/SQS/SNS, CloudWatch logs/alarms, CloudFront, cross-AZ transfer and Aurora IO; small test volume allowance, not a unit-price quote | 5.00 |
| Existing October gross usage | Included conservatively even though already consumed credit | 5.37 |
| Existing resources during window | Separate allowance in addition to Aurora above | 2.00 |
| Delay/cleanup contingency | Remaining allocation rounded up | 4.51 |
| **Reviewed scenario total** | Includes existing usage; maximum 8 h runtime | **20.00** |

This fits the approved US$80 project planning allocation with the separate US$20 reserve. Actual use can differ. Check credit/cost and elapsed runtime during acceptance; stop adding work and clean up if the window or allocation is threatened. Billing updates lag, so elapsed resource hours and live inventory are also required. `ExpiresAt` is a cleanup deadline tag, **not automatic shutdown**.

Official sources checked 2026-10-31: [EKS](https://aws.amazon.com/eks/pricing/), [ALB](https://aws.amazon.com/elasticloadbalancing/pricing/), [EBS](https://aws.amazon.com/ebs/pricing/), [public IPv4](https://aws.amazon.com/vpc/pricing/), [Aurora](https://aws.amazon.com/rds/aurora/pricing/). The exact EC2 Pricing API response is kept privately with the plan.

## Ownership and cleanup

Terraform `9_eks` owns only `alex-task09` resources, tagged `Purpose=task-09-acceptance`. It reads existing VPC/subnets/Aurora, checks the existing Aurora TCP5432 VPC rule, and creates one narrowly scoped `eks:DescribeCluster` inline policy for the existing operator. Original CloudFront/API, Aurora cluster, `alex` database, existing VPC routes/security rules and unrelated remote containers are preserved.

The bootstrap job creates **only** database `alex_task09` and roles `alex_task09_api`/`alex_task09_etl`, with ownership comments. Secret values are initialized outside Terraform. Before cleanup, archive acceptance evidence and identify data in the task-owned database, bucket, queues and ECR. Drop only the marked acceptance database/roles, empty only the named task bucket/repository, then destroy this Terraform state. Bucket/repository force deletion is disabled to prevent silent data loss. Secrets have a seven-day recovery window. Verify residual resources and the preservation inventory after destroy.

The temporary endpoint uses a test JWKS signer whose private key stays on the operator computer. This tests JWT validation/authorization through AWS; it is not a real Clerk browser-login acceptance. The SQS worker runs the snapshot-aware Reporter's honest `research unavailable` path; it does not claim a full five-agent research run.
