# Manual EKS CD implementation verification

Date: 2026-10-31. Branch: `feat/manual-eks-cd`. Baseline: `4fc26b3`.

## Verified locally

- 18 CD boundary tests: exact successful-main provenance, skipped required jobs,
  expired/missing/ambiguous artifacts, foreign ownership, failed deletion, partial
  creation, orphan cluster detection, exact run-attempt recovery after stack
  deletion, current budget window and safe Kubernetes error diagnostics.
- 10 existing release/rollback tests remain passing.
- Terraform validate and one mocked apply test (five IAM/ECR boundary assertions)
  pass. Mocked apply does not create cloud infrastructure.
- actionlint 1.7.12 passes all three workflows; cfn-lint 1.59.0 passes the EKS stack.
- AWS CloudFormation ValidateTemplate and cfn-lint accepted the stack; live
  provisioning is still pending.
- Read-only bootstrap plan contains 12 creates, zero updates/deletes: four IAM
  roles, two inline policies, four managed-policy attachments, ECR and its lifecycle.
  Shared OIDC is reused. No infrastructure was applied during these checks.
- Existing GitHub immutable OIDC subject and EKS service-linked roles were verified.
  Current billing/credit and EC2 pricing were refreshed into private local evidence;
  account financial values are deliberately not included here.

The first PR CI run passed backend/frontend but rejected the Windows-only provider
package hash on Linux. The lock file now records official HashiCorp-signed hashes
for both `windows_amd64` and `linux_amd64`; readonly lock validation stays enabled.
See [PR #27 checks](https://github.com/husky0787/Alex/pull/27/checks) for current results.

## Review fixes

Independent Standards review found lost Kubernetes diagnostics; the helper now
saves private logs and emits sanitized failure evidence, verified by a regression.
Spec review found recovery losing the run identity after stack deletion; completion
events now carry the exact run attempt and can clean corresponding image tags even
when no stack remains. Old attempts cannot delete a newer stack.

The standard node CNI policy has broader ENI permissions than the original proposal
implied. The spec/runbook now disclose that exception. IMDSv2 hop limit 1 and an
application-Pod token-denial probe reduce node-credential exposure. This is not a
claim of VPC-scoped CNI authorization. Unnecessary launch-template instance/volume
tags were removed to avoid expanding the CloudFormation role's RunInstances rights.

## Remaining AWS acceptance

No successful new CD cloud run is claimed. After the reviewed workflow is on main,
complete the one-time bootstrap/environment configuration, open a current reviewed
cost window and manually dispatch `cd.yml`. Record source CI and release run URLs,
EKS release/rollback/authentication evidence, cleanup results and an independent
inventory check before marking cloud acceptance complete.

This extension uses real EKS with isolated fixtures. Task 9 Aurora/ETL and Task 11
Clerk/agent integration evidence remain separate; there is no production cutover.
