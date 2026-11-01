# Manual EKS CD implementation verification

Date: 2026-10-31. Implementation: PRs #27, #28 and #29. Accepted source under test:
`508920bc9021f58234f05c90cd6b503a8b580c96`.

## Verified locally

- 21 CD boundary tests: exact successful-main provenance, skipped required jobs,
  expired/missing/ambiguous artifacts, foreign ownership, failed deletion, partial
  creation, orphan cluster detection, exact run-attempt recovery after stack
  deletion, current budget window, safe Kubernetes error diagnostics and denied/
  incomplete role-inspection permissions before provisioning.
- 10 existing release/rollback tests remain passing.
- Terraform validate and one mocked apply test with IAM/ECR boundary assertions
  pass. Mocked apply does not create cloud infrastructure.
- actionlint 1.7.12 passes all three workflows; cfn-lint 1.59.0 passes the EKS stack.
- AWS CloudFormation ValidateTemplate and cfn-lint accepted the stack.
- The reviewed bootstrap plan contained 12 creates, zero updates/deletes: four IAM
  roles, two inline policies, four managed-policy attachments, ECR and its lifecycle.
  Shared OIDC is reused. The bootstrap was subsequently applied for the authorized
  cloud window; the role-inspection fixes updated only its two inline policies.
- Existing GitHub immutable OIDC subject and EKS service-linked roles were verified.
  Current billing/credit and EC2 pricing were refreshed into private local evidence;
  account financial values are deliberately not included here.

The first PR CI run passed backend/frontend but rejected the Windows-only provider
package hash on Linux. The lock file now records official HashiCorp-signed hashes
for both `windows_amd64` and `linux_amd64`; readonly lock validation stays enabled.
The final source passed all four main CI jobs: backend, frontend, infrastructure
and image-and-rollout in [run 41211725719](https://github.com/husky0787/Alex/actions/runs/41211725719).

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

## Live provisioning failures and fixes

The first two attempts of [run 41208412088](https://github.com/husky0787/Alex/actions/runs/41208412088)
created the control plane but failed before worker creation. EKS required the
CloudFormation caller to inspect attached policies on both dedicated node and
cluster roles. The initial correction covered only the node role; the second
attempt exposed the remaining cluster-role permission. Both failed environments
were automatically deleted and their cleanup jobs passed.

PRs #28/#29 scoped `iam:ListAttachedRolePolicies` to those two roles. The release
role can simulate only its dedicated CloudFormation role, and creation now rejects
missing/denied GetRole/ListAttachedRolePolicies decisions before creating billable
resources. IAM simulation is an early check, not proof of complete EKS provisioning.

## AWS acceptance

[Run 41212113839](https://github.com/husky0787/Alex/actions/runs/41212113839) used the
corrected main revision and CI run 41211725719's tested archives. Real OIDC and the
IAM role-inspection preflight passed. Worker creation then failed authorization to
launch instances with the launch template. No workers were created. Automatic
cleanup passed at 2026-10-31 15:08:28 UTC, reporting the stack and EKS cluster absent
and release tags removed. This is failure/cleanup evidence, not a successful CD
acceptance. The EC2 authorization failure remains under investigation.

This extension uses real EKS with isolated fixtures. Task 9 Aurora/ETL and Task 11
Clerk/agent integration evidence remain separate; there is no production cutover.
