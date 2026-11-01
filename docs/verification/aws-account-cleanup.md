# AWS account workload cleanup — 2026-11-01

English | [繁體中文](aws-account-cleanup.zh-TW.md)

The user explicitly requested deleting all remaining AWS resources because they
are no longer used. This supersedes the earlier Alex-only scope and includes
devops and turing-eye. No new disk/database snapshots or backups were created.

## Removed in this pass

- Both remaining EC2 instances and their 30 GiB / 100 GiB gp3 volumes.
  The turing-eye stack retained its root volume on instance termination, so that
  volume was explicitly deleted after it became available.
- The turing-eye CloudFormation stack, including its Elastic IP, instance profile,
  role and security group.
- Six Alex Lambda functions, one event-source mapping, one API Gateway API,
  two SQS queues, two ECR repositories and one CloudFront distribution.
- Four remaining Secrets Manager secrets, using irreversible deletion; the
  previous recovery windows no longer apply. Secret values were never read.
- One RDS subnet group and two old Sydney App Runner log groups.
- Nine additional custom IAM roles, two customer policies, the GitHub OIDC
  provider, four EC2 key pairs and three additional custom security groups.
- Two Resource Explorer views and indexes.
- GitHub `cd.yml` and `cd-recovery.yml` were disabled and read back as
  `disabled_manually`. Test-only CI remains enabled.

The original Alex database, database backups and S3 buckets were already removed
in the [earlier cleanup](original-alex-cost-cleanup.md).

## Independent verification

At 2026-11-01 05:22 UTC (13:22 Taipei), a fresh SDK audit completed 657 checks
across all 17 enabled AWS regions and relevant global APIs. It found zero remaining
workload categories and zero query errors. Fourteen service/region combinations
were skipped because SDK endpoint metadata marks App Runner or Lightsail as
unavailable there; these skips are not successful resource checks.

Verified empty categories include nonterminated EC2 instances, EBS volumes and
snapshots, Elastic IPs, network interfaces, NAT gateways, VPC endpoints, custom
VPCs/security groups, EKS/ECS clusters, classic/v2 load balancers, RDS instances,
clusters, snapshots and retained automated backups, Lambda, API Gateway, SQS,
SNS, ECR, log groups, Secrets Manager (including pending deletion), supported
App Runner/Lightsail resources, SageMaker endpoints, S3/S3 Vectors, Route 53
hosted zones, CloudFront, custom IAM roles/policies/instance profiles/OIDC and
Resource Explorer. Earlier supplemental checks found no DynamoDB tables, EFS,
FSx, OpenSearch, Redshift, ElastiCache, SageMaker notebooks/domains, backup vaults,
custom KMS aliases, GuardDuty detectors or CloudTrail/Config recorders.

Private detailed inventories and deletion receipts remain under
`.local/account-cleanup-20261101/`; no credentials or secret values are included
in this public summary. See [summary JSON](aws-account-cleanup.json).

## Retained and cost meaning

Account/root/IAM login identities, billing settings, AWS-managed service-linked
roles and the default VPC networks remain. This was workload deletion, not account
closure. Source repositories, earlier local artifacts and external application
accounts were not deleted.

The inventoried ongoing project infrastructure cost is now approximately US$0/month,
instead of the previous approximately US$14/month for disks and IPv4. Previously
incurred usage and delayed billing entries can still appear; this verification is
not a promise of a zero historical invoice or an audit of every possible AWS
subscription. Local Terraform states and old deployment outputs are historical:
do not blindly apply them to restore deleted infrastructure.

## Rebuilding later

Choose the required environment before creating resources:

- **Offline development/CI:** source and credential-free test workflows remain
  usable with their documented local dependencies. Starting the full UI/API alone
  cannot restore deleted AWS integrations or historical user data.
- **Full application/showcase or Task9 EKS:** rebuild the Aurora cluster, admin
  secret and required network configuration, initialize the application schema,
  then follow the chosen [showcase](../../deploy/showcase/README.md) or
  [EKS](../../deploy/eks/README.md) runbook. Supply fresh outputs in private runtime
  configuration; inspect old ownership ledgers before starting a new acceptance.
- **Manual EKS API delivery:** establish a live GitHub OIDC provider under explicit
  ownership, then rebuild `terraform/12_cd` IAM/ECR. That module consumes a provider
  ARN; it does not create the provider. Refresh GitHub environment outputs, verify
  the required AWS service-linked roles, re-enable recovery before release, and
  establish a new cost/release window. See the [CD runbook](../../deploy/cd/README.md).

Before any rebuild, securely back up existing local Terraform state, reconcile
it with live AWS inventory and review a fresh plan for the selected modules.
Do not erase state as a shortcut or apply historical saved plans. Expired CI image
artifacts require a new successful CI run. This document records prerequisites;
no rebuild or re-enabling was performed during the documentation update.
