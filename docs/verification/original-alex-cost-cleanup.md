# Original Alex AWS cost cleanup — 2026-11-01

English | [繁體中文](original-alex-cost-cleanup.zh-TW.md)

Historical first cleanup pass. Later on 2026-11-01 the user expanded authorization
to every AWS project. The retained resources described below were subsequently
removed; see [account-wide cleanup](aws-account-cleanup.md) for current status.

The user explicitly authorized stopping the original Alex website/API/analysis
and deleting its original database without retaining a final snapshot or database
backups. Scope was Alex only; devops and turing-eye were excluded.

## Removed

- Original Aurora instance and cluster. AWS required starting the stopped cluster
  before deleting the instance. Deletion skipped the final snapshot and requested
  automated-backup deletion. The seven automated snapshot entries briefly remained
  visible after cluster removal, then disappeared; no retained automated backup or
  manual/final snapshot remains for the original cluster.
- Two original Alex S3 buckets: frontend static assets and Lambda deployment ZIPs.
  All 48 object versions were archived locally, checked for size and SHA-256, and
  checked against source ETags where applicable before deletion.
- Six original Alex Lambda log groups, after archiving their events locally.
- Two Alex CloudWatch dashboards, after saving their definitions locally.

The original database credential secret is scheduled for deletion with a seven-day
recovery window. It is no longer an active secret. This recovery window does not
preserve the deleted database or its backups.

## Disabled and retained

- CloudFront is disabled and the configuration has finished deploying.
- The API Gateway execute-api endpoint is disabled; its stage uses auto-deploy.
- All six original Lambda functions have reserved concurrency zero. The Planner
  SQS event-source mapping is disabled.
- Reusable IAM, empty CI/CD ECR repositories, and inactive application configuration
  remain. There is no running Alex EKS, SageMaker endpoint, App Runner service,
  NAT gateway, load balancer or VPC Interface Endpoint from the inspected deployment.

Other projects' two stopped EC2 instances, their 30/100 GiB disks and turing-eye's
fixed IP are outside the cleanup scope and remain. Those projects can continue to
incur their own storage/address charges. Historical usage can appear in later bills;
this record is a resource-state check, not a claim that the entire AWS bill is zero.

## Evidence and reproduction

The [independent audit](original-alex-cost-cleanup.json) passed at
2026-11-01 03:18:04 UTC (11:18:04 Asia/Taipei), including checks of the excluded
projects' instances, disks and fixed IP.

Private configuration, deployment-file and log archives are under
`.local/cost-cleanup-20261101/` on the operator's computer, excluded from Git.
The cleanup creates no new database backup. Earlier acceptance records remain
historical evidence; their statements about preserving the original database
describe the state before this separately authorized cleanup.

The original website is no longer runnable against its former database/buckets.
Reprovision original application dependencies, restore deployment configuration and
initialize new data before using it again. Review existing Terraform state and the
proposed changes first: the original module 5/6/7/8 state was not in this checkout,
so no blanket Terraform destroy was used. The separate manual EKS CD uses isolated
fixtures and retains its own reusable bootstrap; its billing window remains closed.
