# Manual EKS CD acceptance

Updated: 2026-11-01. Implementation: PRs #27 through #31. Application/workflow source under test:
`508920bc9021f58234f05c90cd6b503a8b580c96`.

**Passed:** [release attempt 3](https://github.com/husky0787/Alex/actions/runs/41212113839/attempts/3)
completed gate, deploy and cleanup successfully. The [durable evidence summary](manual-eks-cd-summary.json)
records release/rollback results and the independent cleanup audit.

## Verified locally

- 23 CD boundary tests: exact successful-main provenance, skipped required jobs,
  expired/missing/ambiguous artifacts, foreign ownership, failed deletion, partial
  creation, orphan cluster detection, exact run-attempt recovery after stack
  deletion, current budget window, safe Kubernetes error diagnostics and denied/
  incomplete role-inspection permissions, including the existing nodegroup
  service-linked role, before provisioning.
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
tags were removed. Live EKS subsequently required scoped RunInstances authorization
even without those instance/volume tags; PR #30 adds the permissions described below.

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
acceptance. The following changes resolved that authorization failure.

STS decoding identified RunInstances on instance/* as the actual denied action.
PR #30 added scoped template/subnet ownership checks, t3.medium On-Demand,
IMDSv2 required/hop1 and regional launch dependencies. The original policy failed
IAM simulation; the corrected policy passed [13 positive/negative cases](manual-eks-cd-policy.json).
This follows [AWS's launch-template authorization examples](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ExamplePolicies_EC2.html#iam-example-runinstances-launch-templates).

Attempt 2 passed launch authorization but failed GetRole on the existing
AWSServiceRoleForAmazonEKSNodegroup. It also automatically cleaned up without
creating workers. PR #31 adds read access to that exact role and an early check;
denied/missing-result tests and live IAM preflight passed.

Attempt 3 passed real EKS release and rollback with the same tested application/
workflow revision and the reviewed IAM fixes from main `9621c25`. The new
service-role preflight was verified locally; the retried workflow ran the earlier
`508920b` helper. Candidate rollout succeeded at 2026-11-01 02:23:10 UTC; the missing
digest fault drill restored the exact candidate at 02:24:20 UTC. Authenticated
smoke passed after baseline, candidate and recovery; the fixture schema remained
unchanged and the application Pod could not obtain a node metadata token.

Automatic cleanup passed at 02:36:30 UTC. Independent AWS checks at 02:39:29 UTC
confirmed stack/cluster absence, both workers terminated, their two EBS volumes
absent, VPC/subnets/ENIs/gateway and launch template absent, and an empty release
ECR repository. The completion recovery workflow also passed in
[run 41265914334](https://github.com/husky0787/Alex/actions/runs/41265914334).

The original six Lambda code hashes, CloudFront configuration and original EC2
states match the earlier inventory. Original Aurora identity is preserved, but
its status changed from available to stopped: CloudTrail records a separate root
console StopDBCluster at 2026-10-31 15:07:02 UTC, before today's acceptance. It was
left stopped; this is explicitly not a claim that every original resource status
was unchanged.

The release window variable was removed. Dedicated IAM bootstrap and an empty ECR
repository remain reusable; recovery stays enabled. The US$2 scenario/US$5 review
threshold are estimates, not settled charges or hard spending limits. Final
billing reconciliation remains separate.

This extension uses real EKS with isolated fixtures. Task 9 Aurora/ETL and Task 11
Clerk/agent integration evidence remain separate; there is no production cutover.
